"""
Sprint lifecycle service.

  • start  — activate a sprint (one active per project)
  • complete — atomic close: velocity calc, carry-over, backlog cleanup
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, SprintError
from app.models.issue import Issue, IssueStatus
from app.models.sprint import Sprint, SprintStatus
from app.schemas.sprint import SprintCompleteRequest


async def _get_sprint_or_404(session: AsyncSession, sprint_id: uuid.UUID) -> Sprint:
    sprint = await session.get(Sprint, sprint_id)
    if sprint is None:
        raise NotFoundError("Sprint", sprint_id)
    return sprint


async def start_sprint(
    session: AsyncSession,
    sprint_id: uuid.UUID,
) -> Sprint:
    sprint = await _get_sprint_or_404(session, sprint_id)

    startable = {SprintStatus.backlog, SprintStatus.future}
    if sprint.status not in startable:
        raise SprintError(
            f"Sprint '{sprint.name}' cannot be started — "
            f"current status is '{sprint.status.value}', expected 'backlog' or 'future'."
        )

    # Ensure no other sprint in this project is already active
    conflict = (
        await session.execute(
            sa.select(Sprint.id).where(
                Sprint.project_id == sprint.project_id,
                Sprint.status == SprintStatus.active,
                Sprint.id != sprint_id,
            )
        )
    ).first()
    if conflict is not None:
        raise SprintError(
            "Another sprint is already active in this project. "
            "Complete it before starting a new one."
        )

    sprint.status = SprintStatus.active
    session.add(sprint)
    await session.commit()
    await session.refresh(sprint)
    return sprint


async def complete_sprint(
    session: AsyncSession,
    sprint_id: uuid.UUID,
    payload: SprintCompleteRequest,
) -> tuple[Sprint, int, int, int]:
    """
    Atomic sprint completion.

    Returns (sprint, velocity, carried_over_count, moved_to_backlog_count).
    """
    sprint = await _get_sprint_or_404(session, sprint_id)

    if sprint.status != SprintStatus.active:
        raise SprintError(
            f"Sprint '{sprint.name}' cannot be completed — "
            f"current status is '{sprint.status.value}', expected 'active'."
        )

    # ── 1. Velocity: sum story_points of done issues ─────────────────────
    velocity_row = await session.execute(
        sa.select(sa.func.coalesce(sa.func.sum(Issue.story_points), 0)).where(
            Issue.sprint_id == sprint_id,
            Issue.status == IssueStatus.done,
        )
    )
    velocity: int = velocity_row.scalar_one()

    # ── 2. Identify incomplete issues ────────────────────────────────────
    incomplete_rows = (
        await session.execute(
            sa.select(Issue.id).where(
                Issue.sprint_id == sprint_id,
                Issue.status != IssueStatus.done,
            )
        )
    ).scalars().all()
    incomplete_ids = set(incomplete_rows)

    carry_set = set(payload.carry_over_issue_ids) & incomplete_ids

    # ── 3a. Carry over selected issues ───────────────────────────────────
    carried = 0
    if carry_set:
        target = payload.target_sprint_id  # may be None → backlog
        res = await session.execute(
            sa.update(Issue)
            .where(Issue.id.in_(carry_set))
            .values(sprint_id=target)
        )
        carried = res.rowcount  # type: ignore[assignment]

    # ── 3b. Remaining incomplete → backlog (nullify sprint_id) ───────────
    backlog_ids = incomplete_ids - carry_set
    moved_to_backlog = 0
    if backlog_ids:
        res = await session.execute(
            sa.update(Issue)
            .where(Issue.id.in_(backlog_ids))
            .values(sprint_id=None)
        )
        moved_to_backlog = res.rowcount  # type: ignore[assignment]

    # ── 4. Finalise sprint record ────────────────────────────────────────
    sprint.status = SprintStatus.completed
    sprint.velocity = velocity
    session.add(sprint)

    await session.commit()
    await session.refresh(sprint)
    return sprint, velocity, carried, moved_to_backlog
