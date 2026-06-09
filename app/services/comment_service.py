"""
Comment service — threaded comments + @mention detection + notifications.

Mentions matching `@DisplayName` are resolved against the users table,
logged in the activity history, and trigger in-app notifications.
"""

from __future__ import annotations

import re
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import HierarchyError, NotFoundError
from app.models.activity_log import ActivityLog
from app.models.comment import Comment
from app.models.issue import Issue
from app.models.user import User
from app.schemas.comment import CommentCreate
from app.services import notification_service

MENTION_RE = re.compile(r"@(\w+)", re.UNICODE)


async def _get_issue_or_404(session: AsyncSession, issue_id: uuid.UUID) -> Issue:
    issue = await session.get(Issue, issue_id)
    if issue is None:
        raise NotFoundError("Issue", issue_id)
    return issue


async def create_comment(
    session: AsyncSession,
    issue_id: uuid.UUID,
    payload: CommentCreate,
) -> tuple[Comment, uuid.UUID]:
    issue = await _get_issue_or_404(session, issue_id)

    if payload.parent_id is not None:
        parent = await session.get(Comment, payload.parent_id)
        if parent is None:
            raise NotFoundError("Comment", payload.parent_id)
        if parent.issue_id != issue_id:
            raise HierarchyError("Parent comment does not belong to the same issue.")

    comment = Comment(
        issue_id=issue_id,
        user_id=payload.user_id,
        body=payload.body,
        parent_id=payload.parent_id,
    )
    session.add(comment)
    await session.flush()

    # @mention detection + notifications
    await _process_mentions(session, comment, issue)

    await session.commit()
    await session.refresh(comment)
    return comment, issue.project_id


async def _process_mentions(
    session: AsyncSession,
    comment: Comment,
    issue: Issue,
) -> None:
    raw_names = MENTION_RE.findall(comment.body)
    if not raw_names:
        return

    rows = (
        await session.execute(
            sa.select(User.id, User.display_name).where(
                sa.func.lower(User.display_name).in_([n.lower() for n in raw_names])
            )
        )
    ).all()

    mentioned_ids: list[uuid.UUID] = []
    for user_id, display_name in rows:
        mentioned_ids.append(user_id)
        session.add(
            ActivityLog(
                issue_id=issue.id,
                user_id=comment.user_id,
                action_type="mentioned",
                new_values={
                    "mentioned_user_id": str(user_id),
                    "mentioned_name": display_name,
                    "comment_id": str(comment.id),
                },
            )
        )

    if mentioned_ids:
        await notification_service.notify_mention(
            session, issue, comment.user_id, mentioned_ids
        )


async def list_comments(
    session: AsyncSession,
    issue_id: uuid.UUID,
) -> list[Comment]:
    await _get_issue_or_404(session, issue_id)
    result = await session.execute(
        sa.select(Comment)
        .where(Comment.issue_id == issue_id)
        .order_by(Comment.created_at.asc())
    )
    return list(result.scalars().all())
