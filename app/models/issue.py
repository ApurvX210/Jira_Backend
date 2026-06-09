import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Field, SQLModel


class IssueType(str, Enum):
    epic = "epic"
    story = "story"
    task = "task"
    bug = "bug"
    sub_task = "sub_task"


class IssuePriority(str, Enum):
    highest = "highest"
    high = "high"
    medium = "medium"
    low = "low"
    lowest = "lowest"


class IssueStatus(str, Enum):
    to_do = "to_do"
    in_progress = "in_progress"
    in_review = "in_review"
    done = "done"


class Issue(SQLModel, table=True):
    __tablename__ = "issues"
    __table_args__ = (
        sa.Index("ix_issues_project_created_id", "project_id", "created_at", "id"),
        sa.Index(
            "ix_issues_fts",
            sa.text("to_tsvector('english', title || ' ' || COALESCE(description, ''))"),
            postgresql_using="gin",
        ),
        sa.Index("ix_issues_custom_fields", "custom_fields", postgresql_using="gin"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    key: str = Field(
        max_length=20,
        sa_column_kwargs={"unique": True, "index": True},
        description="Human-readable identifier, e.g. PROJ-123",
    )

    project_id: uuid.UUID = Field(foreign_key="projects.id", index=True)
    sprint_id: uuid.UUID | None = Field(default=None, foreign_key="sprints.id", index=True)
    type: IssueType
    parent_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="issues.id",
        index=True,
        description="Self-referential FK supporting Epic->Story->Sub-task hierarchy",
    )

    title: str = Field(max_length=500)
    description: str | None = Field(default=None, sa_column=sa.Column(sa.Text, nullable=True))
    status: IssueStatus = Field(default=IssueStatus.to_do, sa_column_kwargs={"index": True})
    priority: IssuePriority = Field(default=IssuePriority.medium, sa_column_kwargs={"index": True})
    story_points: int | None = Field(default=None)

    version: int = Field(
        default=1,
        description="Optimistic locking counter — reject updates when stale",
    )

    assignee_id: uuid.UUID | None = Field(default=None, foreign_key="users.id", index=True)
    reporter_id: uuid.UUID = Field(foreign_key="users.id", index=True)

    custom_fields: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"nullable": False},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={
            "nullable": False,
            "onupdate": lambda: datetime.now(timezone.utc),
        },
    )
