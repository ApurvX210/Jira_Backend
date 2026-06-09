"""
Sequential event log for WebSocket replay.

Uses an auto-incrementing BIGINT primary key as the global sequence_id so
reconnecting clients can request all events after their last-seen id.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Field, SQLModel


class EventLog(SQLModel, table=True):
    __tablename__ = "event_log"
    __table_args__ = (
        sa.Index("ix_event_log_project_seq", "project_id", "id"),
    )

    id: int | None = Field(
        default=None,
        sa_column=sa.Column(sa.BigInteger, primary_key=True, autoincrement=True),
    )
    project_id: uuid.UUID = Field(foreign_key="projects.id", index=True)
    event_type: str = Field(max_length=50)
    payload: dict[str, Any] = Field(
        sa_column=Column(JSONB, nullable=False),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"nullable": False},
    )
