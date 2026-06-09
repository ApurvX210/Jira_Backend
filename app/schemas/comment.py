from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CommentCreate(BaseModel):
    body: str = Field(min_length=1)
    user_id: uuid.UUID
    parent_id: uuid.UUID | None = Field(
        default=None,
        description="Reply to an existing comment (must belong to the same issue).",
    )


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    issue_id: uuid.UUID
    user_id: uuid.UUID
    body: str
    parent_id: uuid.UUID | None
    created_at: datetime
