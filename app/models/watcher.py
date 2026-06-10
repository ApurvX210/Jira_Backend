import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class Watcher(SQLModel, table=True):
    """Junction table: many-to-many between User and Issue."""

    __tablename__ = "watchers"

    user_id: uuid.UUID = Field(foreign_key="users.id", primary_key=True)
    issue_id: uuid.UUID = Field(foreign_key="issues.id", primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column_kwargs={"nullable": False},
    )
