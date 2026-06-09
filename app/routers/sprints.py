"""
Sprint routes.

POST  /api/sprints/{sprint_id}/start     — activate a sprint
POST  /api/sprints/{sprint_id}/complete   — atomic close + velocity calc
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.sprint import (
    SprintCompleteRequest,
    SprintCompleteResponse,
    SprintResponse,
)
from app.services import sprint_service

router = APIRouter(prefix="/api/sprints", tags=["sprints"])


@router.post("/{sprint_id}/start", response_model=SprintResponse)
async def start_sprint(
    sprint_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> SprintResponse:
    sprint = await sprint_service.start_sprint(session, sprint_id)
    return SprintResponse.model_validate(sprint)


@router.post("/{sprint_id}/complete", response_model=SprintCompleteResponse)
async def complete_sprint(
    sprint_id: uuid.UUID,
    payload: SprintCompleteRequest,
    session: AsyncSession = Depends(get_session),
) -> SprintCompleteResponse:
    sprint, velocity, carried, backlogged = await sprint_service.complete_sprint(
        session, sprint_id, payload
    )
    return SprintCompleteResponse(
        sprint=SprintResponse.model_validate(sprint),
        velocity=velocity,
        carried_over=carried,
        moved_to_backlog=backlogged,
    )
