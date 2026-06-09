from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.issue import IssuePriority, IssueStatus, IssueType


# ── Requests ─────────────────────────────────────────────────────────────────

class IssueCreate(BaseModel):
    type: IssueType
    title: str = Field(max_length=500)
    description: str | None = None
    parent_id: uuid.UUID | None = None
    priority: IssuePriority = IssuePriority.medium
    story_points: int | None = None
    assignee_id: uuid.UUID | None = None
    sprint_id: uuid.UUID | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class IssueUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: IssuePriority | None = None
    assignee_id: uuid.UUID | None = None
    story_points: int | None = None
    sprint_id: uuid.UUID | None = None
    custom_fields: dict[str, Any] | None = None
    version: int = Field(
        ..., description="Client's known version — required for optimistic locking"
    )


class TransitionRequest(BaseModel):
    new_status: IssueStatus


# ── Responses ────────────────────────────────────────────────────────────────

class IssueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    project_id: uuid.UUID
    sprint_id: uuid.UUID | None
    type: IssueType
    parent_id: uuid.UUID | None
    title: str
    description: str | None
    status: IssueStatus
    priority: IssuePriority
    story_points: int | None
    version: int
    assignee_id: uuid.UUID | None
    reporter_id: uuid.UUID
    custom_fields: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class TransitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    issue: IssueResponse
    applied_actions: dict[str, Any] = Field(
        default_factory=dict,
        description="Side-effects applied by on_enter rules, if any",
    )
