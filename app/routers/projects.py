"""
Project routes.

POST  /api/projects  — create a project with optional workflow_config
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.project import Project
from app.schemas.project import DEFAULT_WORKFLOW, ProjectCreate, ProjectResponse

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    session: AsyncSession = Depends(get_session),
) -> ProjectResponse:
    project = Project(
        name=payload.name,
        key=payload.key.upper(),
        description=payload.description,
        workflow_config=payload.workflow_config or DEFAULT_WORKFLOW,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return ProjectResponse.model_validate(project)
