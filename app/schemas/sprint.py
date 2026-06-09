from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.sprint import SprintStatus


# ── Requests ─────────────────────────────────────────────────────────────────

class SprintCompleteRequest(BaseModel):
    carry_over_issue_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Incomplete issues to move to target_sprint_id (rest go to backlog)",
    )
    target_sprint_id: uuid.UUID | None = Field(
        default=None,
        description="Sprint to receive carried-over issues. null → backlog.",
    )


# ── Responses ────────────────────────────────────────────────────────────────

class SprintResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    start_date: date | None
    end_date: date | None
    status: SprintStatus
    velocity: int | None
    created_at: datetime


class SprintCompleteResponse(BaseModel):
    sprint: SprintResponse
    velocity: int
    carried_over: int
    moved_to_backlog: int
