"""
Decoupled notification worker.

Called from service-layer mutation points (status change, assignee change,
@mention) to write Notification records for relevant users.

Recipients = {assignee, reporter, watchers} − {actor}.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.issue import Issue
from app.models.notification import Notification
from app.models.watcher import Watcher


async def _gather_recipients(
    session: AsyncSession,
    issue: Issue,
    actor_id: uuid.UUID,
    extra: set[uuid.UUID] | None = None,
) -> set[uuid.UUID]:
    recipients: set[uuid.UUID] = set()

    if issue.assignee_id:
        recipients.add(issue.assignee_id)
    if issue.reporter_id:
        recipients.add(issue.reporter_id)

    watcher_rows = (
        await session.execute(
            sa.select(Watcher.user_id).where(Watcher.issue_id == issue.id)
        )
    ).scalars().all()
    recipients.update(watcher_rows)

    if extra:
        recipients.update(extra)

    recipients.discard(actor_id)
    return recipients


async def notify_status_change(
    session: AsyncSession,
    issue: Issue,
    actor_id: uuid.UUID,
    old_status: str,
    new_status: str,
) -> None:
    recipients = await _gather_recipients(session, issue, actor_id)
    msg = f"{issue.key} transitioned from '{old_status}' to '{new_status}'"
    for uid in recipients:
        session.add(Notification(user_id=uid, message=msg, triggered_by_issue_id=issue.id))


async def notify_assignee_change(
    session: AsyncSession,
    issue: Issue,
    actor_id: uuid.UUID,
    old_assignee_id: uuid.UUID | None,
    new_assignee_id: uuid.UUID | None,
) -> None:
    extra: set[uuid.UUID] = set()
    if old_assignee_id:
        extra.add(old_assignee_id)
    if new_assignee_id:
        extra.add(new_assignee_id)
    recipients = await _gather_recipients(session, issue, actor_id, extra)
    msg = f"{issue.key} was reassigned"
    for uid in recipients:
        session.add(Notification(user_id=uid, message=msg, triggered_by_issue_id=issue.id))


async def notify_mention(
    session: AsyncSession,
    issue: Issue,
    actor_id: uuid.UUID,
    mentioned_user_ids: list[uuid.UUID],
) -> None:
    for uid in mentioned_user_ids:
        if uid == actor_id:
            continue
        session.add(
            Notification(
                user_id=uid,
                message=f"You were mentioned in a comment on {issue.key}",
                triggered_by_issue_id=issue.id,
            )
        )
