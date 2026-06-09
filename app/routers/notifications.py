"""
Notification routes.

GET    /api/notifications              — unread notifications for the caller
PATCH  /api/notifications/{id}/read    — mark a notification as read
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

import sqlalchemy as sa
from app.core.exceptions import NotFoundError
from app.db.session import get_session
from app.dependencies import get_current_user_id
from app.models.notification import Notification
from app.schemas.notification import NotificationResponse

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> list[NotificationResponse]:
    rows = (
        await session.execute(
            sa.select(Notification)
            .where(Notification.user_id == user_id, Notification.is_read == False)  # noqa: E712
            .order_by(Notification.created_at.desc())
        )
    ).scalars().all()
    return [NotificationResponse.model_validate(r) for r in rows]


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_read(
    notification_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> NotificationResponse:
    notif = await session.get(Notification, notification_id)
    if notif is None or notif.user_id != user_id:
        raise NotFoundError("Notification", notification_id)

    notif.is_read = True
    session.add(notif)
    await session.commit()
    await session.refresh(notif)
    return NotificationResponse.model_validate(notif)
