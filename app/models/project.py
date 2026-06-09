import uuid
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Field, SQLModel


class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255)
    key: str = Field(
        max_length=10,
        sa_column_kwargs={"unique": True, "index": True},
        description="Short uppercase key used in issue identifiers, e.g. PROJ",
    )
    description: str | None = Field(default=None, sa_column=sa.Column(sa.Text, nullable=True))

    workflow_config: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )

    issue_counter: int = Field(
        default=0,
        description="Monotonic counter for generating sequential issue keys",
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"nullable": False},
    )
