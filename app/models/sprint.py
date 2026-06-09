import uuid
from datetime import date, datetime, timezone
from enum import Enum

from sqlmodel import Field, SQLModel


class SprintStatus(str, Enum):
    backlog = "backlog"
    active = "active"
    completed = "completed"


class Sprint(SQLModel, table=True):
    __tablename__ = "sprints"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    project_id: uuid.UUID = Field(foreign_key="projects.id", index=True)
    name: str = Field(max_length=255)
    start_date: date | None = Field(default=None)
    end_date: date | None = Field(default=None)
    status: SprintStatus = Field(default=SprintStatus.backlog)
    velocity: int | None = Field(
        default=None,
        description="Total story points completed; calculated when sprint is closed",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"nullable": False},
    )
