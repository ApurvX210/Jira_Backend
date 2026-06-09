"""
Issue routes.

GET    /api/projects/{project_id}/issues   — search + cursor pagination
POST   /api/projects/{project_id}/issues   — create (with hierarchy validation)
PATCH  /api/issues/{issue_id}               — partial update (optimistic lock)
POST   /api/issues/{issue_id}/transitions   — workflow state-machine transition
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.websocket import broadcast_project_event
from app.db.session import get_session
from app.dependencies import get_current_user_id
from app.models.issue import IssuePriority, IssueStatus
from app.schemas.issue import (
    IssueCreate,
    IssueResponse,
    IssueUpdate,
    PaginatedIssuesResponse,
    TransitionRequest,
    TransitionResponse,
)
from app.services import issue_service, search_service

router = APIRouter(prefix="/api", tags=["issues"])


# ── List / Search ────────────────────────────────────────────────────────────

@router.get(
    "/projects/{project_id}/issues",
    response_model=PaginatedIssuesResponse,
)
async def list_issues(
    project_id: uuid.UUID,
    status: IssueStatus | None = Query(default=None),
    assignee_id: uuid.UUID | None = Query(default=None),
    sprint_id: uuid.UUID | None = Query(default=None),
    priority: IssuePriority | None = Query(default=None),
    q: str | None = Query(default=None, description="Full-text search query"),
    cursor: str | None = Query(default=None, description="Base64 pagination cursor"),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> PaginatedIssuesResponse:
    issues, next_cursor = await search_service.list_issues(
        session,
        project_id,
        status=status,
        assignee_id=assignee_id,
        sprint_id=sprint_id,
        priority=priority,
        q=q,
        cursor=cursor,
        limit=limit,
    )
    return PaginatedIssuesResponse(
        items=[IssueResponse.model_validate(i) for i in issues],
        next_cursor=next_cursor,
    )


# ── Create ───────────────────────────────────────────────────────────────────

@router.post(
    "/projects/{project_id}/issues",
    response_model=IssueResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_issue(
    project_id: uuid.UUID,
    payload: IssueCreate,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> IssueResponse:
    issue = await issue_service.create_issue(session, project_id, payload, user_id)
    resp = IssueResponse.model_validate(issue)

    await broadcast_project_event(
        project_id, "issue.created", resp.model_dump(mode="json")
    )
    return resp


# ── Update (optimistic lock) ─────────────────────────────────────────────────

@router.patch(
    "/issues/{issue_id}",
    response_model=IssueResponse,
)
async def update_issue(
    issue_id: uuid.UUID,
    payload: IssueUpdate,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> IssueResponse:
    issue = await issue_service.update_issue(session, issue_id, payload, user_id)
    resp = IssueResponse.model_validate(issue)

    await broadcast_project_event(
        issue.project_id, "issue.updated", resp.model_dump(mode="json")
    )
    return resp


# ── Transition (workflow state machine) ──────────────────────────────────────

@router.post(
    "/issues/{issue_id}/transitions",
    response_model=TransitionResponse,
)
async def transition_issue(
    issue_id: uuid.UUID,
    payload: TransitionRequest,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> TransitionResponse:
    issue, applied = await issue_service.transition_issue(
        session, issue_id, payload, user_id
    )
    resp = TransitionResponse(
        issue=IssueResponse.model_validate(issue),
        applied_actions=applied,
    )

    await broadcast_project_event(
        issue.project_id,
        "issue.transitioned",
        resp.model_dump(mode="json"),
    )
    return resp
