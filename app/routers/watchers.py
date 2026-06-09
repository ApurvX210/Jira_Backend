"""
Watcher routes.

POST    /api/issues/{issue_id}/watch  — subscribe to issue notifications
DELETE  /api/issues/{issue_id}/watch  — unsubscribe
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.session import get_session
from app.dependencies import get_current_user_id
from app.models.issue import Issue
from app.models.watcher import Watcher

router = APIRouter(prefix="/api/issues", tags=["watchers"])


@router.post("/{issue_id}/watch", status_code=status.HTTP_201_CREATED)
async def watch_issue(
    issue_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> dict[str, str]:
    issue = await session.get(Issue, issue_id)
    if issue is None:
        raise NotFoundError("Issue", issue_id)

    existing = await session.get(Watcher, (user_id, issue_id))
    if existing is None:
        session.add(Watcher(user_id=user_id, issue_id=issue_id))
        await session.commit()

    return {"status": "watching"}


@router.delete("/{issue_id}/watch", status_code=status.HTTP_200_OK)
async def unwatch_issue(
    issue_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> dict[str, str]:
    existing = await session.get(Watcher, (user_id, issue_id))
    if existing is not None:
        await session.delete(existing)
        await session.commit()

    return {"status": "unwatched"}
