from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_WORKFLOW: dict[str, list[str]] = {
    "to_do": ["in_progress"],
    "in_progress": ["in_review"],
    "in_review": ["to_do", "done"],
    "done": ["in_progress"],
}


class ProjectCreate(BaseModel):
    name: str = Field(max_length=255)
    key: str = Field(max_length=10, description="Short uppercase key, e.g. JIRA")
    description: str | None = None
    workflow_config: dict[str, Any] | None = Field(
        default=None,
        description="Custom state-machine. null → default workflow is applied.",
    )


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    key: str
    description: str | None
    workflow_config: dict[str, Any]
    issue_counter: int
    created_at: datetime
