"""
Issue routes.

POST   /api/projects/{project_id}/issues   — create (with hierarchy validation)
PATCH  /api/issues/{issue_id}               — partial update (optimistic lock)
POST   /api/issues/{issue_id}/transitions   — workflow state-machine transition
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.dependencies import get_current_user_id
from app.schemas.issue import (
    IssueCreate,
    IssueResponse,
    IssueUpdate,
    TransitionRequest,
    TransitionResponse,
)
from app.services import issue_service

router = APIRouter(prefix="/api", tags=["issues"])


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
    return IssueResponse.model_validate(issue)


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
    return IssueResponse.model_validate(issue)


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
    return TransitionResponse(
        issue=IssueResponse.model_validate(issue),
        applied_actions=applied,
    )
