"""
Sprint routes.

POST  /api/projects/{project_id}/sprints   — create a sprint (status=future)
POST  /api/sprints/{sprint_id}/start       — activate a sprint
POST  /api/sprints/{sprint_id}/complete     — atomic close + velocity calc
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.session import get_session
from app.models.project import Project
from app.models.sprint import Sprint, SprintStatus
from app.schemas.sprint import (
    SprintCompleteRequest,
    SprintCompleteResponse,
    SprintCreate,
    SprintResponse,
)
from app.services import sprint_service

router = APIRouter(prefix="/api", tags=["sprints"])


@router.post(
    "/projects/{project_id}/sprints",
    response_model=SprintResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_sprint(
    project_id: uuid.UUID,
    payload: SprintCreate,
    session: AsyncSession = Depends(get_session),
) -> SprintResponse:
    project = await session.get(Project, project_id)
    if project is None:
        raise NotFoundError("Project", project_id)

    sprint = Sprint(
        project_id=project_id,
        name=payload.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status=SprintStatus.future,
    )
    session.add(sprint)
    await session.commit()
    await session.refresh(sprint)
    return SprintResponse.model_validate(sprint)


@router.post("/sprints/{sprint_id}/start", response_model=SprintResponse)
async def start_sprint(
    sprint_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> SprintResponse:
    sprint = await sprint_service.start_sprint(session, sprint_id)
    return SprintResponse.model_validate(sprint)


@router.post("/sprints/{sprint_id}/complete", response_model=SprintCompleteResponse)
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
