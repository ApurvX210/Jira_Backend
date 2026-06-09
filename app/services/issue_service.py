"""
Issue business-logic layer.

Covers:
  • create  — hierarchy validation + atomic key generation
  • update  — optimistic-locking PATCH
  • transition — workflow state-machine enforcement
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, HierarchyError, NotFoundError
from app.models.issue import Issue, IssueType
from app.models.project import Project
from app.schemas.issue import IssueCreate, IssueUpdate, TransitionRequest
from app.services import audit_service
from app.services.audit_service import compute_diff, snapshot_fields
from app.services.workflow_service import (
    apply_on_enter,
    get_on_enter_actions,
    validate_transition,
)

# ── Hierarchy rules ──────────────────────────────────────────────────────────

ALLOWED_CHILDREN: dict[IssueType, set[IssueType]] = {
    IssueType.epic: {IssueType.story},
    IssueType.story: {IssueType.sub_task},
}

_AUDITABLE_FIELDS = [
    "title",
    "description",
    "status",
    "priority",
    "story_points",
    "assignee_id",
    "reporter_id",
    "sprint_id",
    "custom_fields",
]


async def _get_issue_or_404(session: AsyncSession, issue_id: uuid.UUID) -> Issue:
    issue = await session.get(Issue, issue_id)
    if issue is None:
        raise NotFoundError("Issue", issue_id)
    return issue


async def _get_project_or_404(session: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise NotFoundError("Project", project_id)
    return project


def _validate_hierarchy(parent: Issue, child_type: IssueType) -> None:
    """Raise HierarchyError if parent→child_type is invalid."""
    allowed = ALLOWED_CHILDREN.get(parent.type)
    if allowed is None:
        raise HierarchyError(
            f"Issues of type '{parent.type.value}' cannot have children."
        )
    if child_type not in allowed:
        raise HierarchyError(
            f"A '{parent.type.value}' can only parent "
            f"{sorted(t.value for t in allowed)}, not '{child_type.value}'."
        )


# ── Public API ───────────────────────────────────────────────────────────────

async def create_issue(
    session: AsyncSession,
    project_id: uuid.UUID,
    payload: IssueCreate,
    reporter_id: uuid.UUID,
) -> Issue:
    project = await _get_project_or_404(session, project_id)

    # Hierarchy validation
    if payload.parent_id is not None:
        parent = await _get_issue_or_404(session, payload.parent_id)
        if parent.project_id != project_id:
            raise HierarchyError(
                "Parent issue does not belong to the same project."
            )
        _validate_hierarchy(parent, payload.type)

    # Atomic counter increment → issue key
    result = await session.execute(
        sa.update(Project)
        .where(Project.id == project_id)
        .values(issue_counter=Project.issue_counter + 1)
        .returning(Project.issue_counter)
    )
    new_number = result.scalar_one()
    issue_key = f"{project.key}-{new_number}"

    now = datetime.now(timezone.utc)
    issue = Issue(
        key=issue_key,
        project_id=project_id,
        sprint_id=payload.sprint_id,
        type=payload.type,
        parent_id=payload.parent_id,
        title=payload.title,
        description=payload.description,
        status=payload.type == IssueType.epic
        and "to_do"  # epics start to_do by default
        or "to_do",
        priority=payload.priority,
        story_points=payload.story_points,
        assignee_id=payload.assignee_id,
        reporter_id=reporter_id,
        custom_fields=payload.custom_fields,
        created_at=now,
        updated_at=now,
    )
    session.add(issue)
    await session.flush()

    # Audit
    new_snapshot = snapshot_fields(issue, _AUDITABLE_FIELDS)
    await audit_service.log_change(
        session,
        issue_id=issue.id,
        user_id=reporter_id,
        action_type="created",
        new_values={k: audit_service._serialisable(v) for k, v in new_snapshot.items()},
    )

    await session.commit()
    await session.refresh(issue)
    return issue


async def update_issue(
    session: AsyncSession,
    issue_id: uuid.UUID,
    payload: IssueUpdate,
    user_id: uuid.UUID,
) -> Issue:
    issue = await _get_issue_or_404(session, issue_id)

    # Build the dict of explicitly-provided fields (minus version)
    changes = payload.model_dump(exclude_unset=True, exclude={"version"})
    if not changes:
        return issue  # nothing to update

    # Merge custom_fields (shallow) when provided
    if "custom_fields" in changes and changes["custom_fields"] is not None:
        merged = {**(issue.custom_fields or {}), **changes["custom_fields"]}
        changes["custom_fields"] = merged

    # Snapshot BEFORE for audit diff
    old_snap = snapshot_fields(issue, list(changes.keys()))

    now = datetime.now(timezone.utc)
    changes["updated_at"] = now

    # Optimistic-locking UPDATE
    stmt = (
        sa.update(Issue)
        .where(Issue.id == issue_id, Issue.version == payload.version)
        .values(**changes, version=Issue.version + 1)
    )
    result = await session.execute(stmt)

    if result.rowcount == 0:
        # Re-read to distinguish "not found" from "version mismatch"
        fresh = await session.get(Issue, issue_id)
        if fresh is None:
            raise NotFoundError("Issue", issue_id)
        raise ConflictError(
            issue_id=issue_id,
            current_version=fresh.version,
            provided_version=payload.version,
        )

    # Refresh the ORM object so caller sees updated values
    await session.refresh(issue)

    # Audit diff
    new_snap = snapshot_fields(issue, list(changes.keys()))
    old_vals, new_vals = compute_diff(old_snap, new_snap)
    if old_vals or new_vals:
        await audit_service.log_change(
            session,
            issue_id=issue.id,
            user_id=user_id,
            action_type="updated",
            old_values=old_vals,
            new_values=new_vals,
        )

    await session.commit()
    await session.refresh(issue)
    return issue


async def transition_issue(
    session: AsyncSession,
    issue_id: uuid.UUID,
    payload: TransitionRequest,
    user_id: uuid.UUID,
) -> tuple[Issue, dict[str, Any]]:
    """
    Returns (updated_issue, applied_actions).
    Raises WorkflowError (422) on illegal transitions.
    """
    issue = await _get_issue_or_404(session, issue_id)
    project = await _get_project_or_404(session, issue.project_id)

    current = issue.status.value if hasattr(issue.status, "value") else issue.status
    target = payload.new_status.value if hasattr(payload.new_status, "value") else payload.new_status

    # ── Workflow gate ────────────────────────────────────────────────────
    validate_transition(project.workflow_config, current, target)

    # ── Build mutation dict ──────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    updates: dict[str, Any] = {"status": target, "updated_at": now}

    # on_enter side-effects
    actions = get_on_enter_actions(project.workflow_config, target)
    applied = apply_on_enter(updates, actions) if actions else {}

    # Snapshot before
    old_snap = snapshot_fields(issue, list(updates.keys()))

    # Apply (uses version bump to keep optimistic-lock counter accurate)
    stmt = (
        sa.update(Issue)
        .where(Issue.id == issue_id)
        .values(**updates, version=Issue.version + 1)
    )
    await session.execute(stmt)
    await session.refresh(issue)

    # Audit
    new_snap = snapshot_fields(issue, list(updates.keys()))
    old_vals, new_vals = compute_diff(old_snap, new_snap)
    if old_vals or new_vals:
        await audit_service.log_change(
            session,
            issue_id=issue.id,
            user_id=user_id,
            action_type="transition",
            old_values=old_vals,
            new_values=new_vals,
        )

    await session.commit()
    await session.refresh(issue)
    return issue, applied
