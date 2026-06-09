import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class Comment(SQLModel, table=True):
    __tablename__ = "comments"
    __table_args__ = (
        sa.Index(
            "ix_comments_fts",
            sa.text("to_tsvector('english', body)"),
            postgresql_using="gin",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    issue_id: uuid.UUID = Field(foreign_key="issues.id", index=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    body: str = Field(sa_column=sa.Column(sa.Text, nullable=False))
    parent_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="comments.id",
        description="Nullable self-ref FK for threaded replies",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"nullable": False},
    )
