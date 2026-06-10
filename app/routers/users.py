"""
User routes.

GET   /api/users  — list all provisioned users
POST  /api/users  — provision/sync a team member
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
async def list_users(
    session: AsyncSession = Depends(get_session),
) -> list[UserResponse]:
    result = await session.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return [UserResponse.model_validate(u) for u in users]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    user = User(email=payload.email, display_name=payload.display_name)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return UserResponse.model_validate(user)
