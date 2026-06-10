import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class Notification(SQLModel, table=True):
    __tablename__ = "notifications"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    message: str = Field(sa_column=sa.Column(sa.Text, nullable=False))
    is_read: bool = Field(default=False, sa_column_kwargs={"index": True})
    triggered_by_issue_id: uuid.UUID = Field(foreign_key="issues.id", index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column_kwargs={"nullable": False},
    )
