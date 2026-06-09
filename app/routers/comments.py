"""
Comment routes.

POST  /api/issues/{issue_id}/comments  — create (threaded, @mention aware)
GET   /api/issues/{issue_id}/comments  — chronological flat list
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.websocket import broadcast_project_event
from app.db.session import get_session
from app.schemas.comment import CommentCreate, CommentResponse
from app.services import comment_service

router = APIRouter(prefix="/api/issues", tags=["comments"])


@router.post(
    "/{issue_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_comment(
    issue_id: uuid.UUID,
    payload: CommentCreate,
    session: AsyncSession = Depends(get_session),
) -> CommentResponse:
    comment, project_id = await comment_service.create_comment(session, issue_id, payload)
    resp = CommentResponse.model_validate(comment)

    await broadcast_project_event(
        project_id=project_id,
        event="comment.created",
        data=resp.model_dump(mode="json"),
    )
    return resp


@router.get(
    "/{issue_id}/comments",
    response_model=list[CommentResponse],
)
async def list_comments(
    issue_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[CommentResponse]:
    comments = await comment_service.list_comments(session, issue_id)
    return [CommentResponse.model_validate(c) for c in comments]
