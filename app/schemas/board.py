from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.schemas.issue import IssueResponse
from app.schemas.sprint import SprintResponse


class BoardResponse(BaseModel):
    columns: dict[str, list[IssueResponse]]
    active_sprint: SprintResponse | None = None
