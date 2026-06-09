"""
Board route.

GET  /api/projects/{project_id}/board  — issues grouped by status
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.board import BoardResponse
from app.schemas.issue import IssueResponse
from app.schemas.sprint import SprintResponse
from app.services import board_service

router = APIRouter(prefix="/api/projects", tags=["board"])


@router.get("/{project_id}/board", response_model=BoardResponse)
async def get_board(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> BoardResponse:
    result = await board_service.get_board(session, project_id)

    columns: dict[str, list[IssueResponse]] = {}
    for status_key, issues in result["columns"].items():
        columns[status_key] = [IssueResponse.model_validate(i) for i in issues]

    active_sprint = None
    if result["active_sprint"] is not None:
        active_sprint = SprintResponse.model_validate(result["active_sprint"])

    return BoardResponse(columns=columns, active_sprint=active_sprint)
