"""
High-throughput issue listing with cursor-based pagination and
PostgreSQL full-text search across issue titles, descriptions, and comments.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comment import Comment
from app.models.issue import Issue, IssuePriority, IssueStatus

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


# ── Cursor helpers ───────────────────────────────────────────────────────────

def encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    payload = {"c": created_at.isoformat(), "i": str(row_id)}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    raw = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    return datetime.fromisoformat(raw["c"]), uuid.UUID(raw["i"])


# ── Query builder ────────────────────────────────────────────────────────────

async def list_issues(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    status: IssueStatus | None = None,
    assignee_id: uuid.UUID | None = None,
    sprint_id: uuid.UUID | None = None,
    priority: IssuePriority | None = None,
    q: str | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> tuple[list[Issue], str | None]:
    limit = min(limit, MAX_PAGE_SIZE)

    stmt = sa.select(Issue).where(Issue.project_id == project_id)

    # ── Filters ──────────────────────────────────────────────────────────
    if status is not None:
        stmt = stmt.where(Issue.status == status)
    if assignee_id is not None:
        stmt = stmt.where(Issue.assignee_id == assignee_id)
    if sprint_id is not None:
        stmt = stmt.where(Issue.sprint_id == sprint_id)
    if priority is not None:
        stmt = stmt.where(Issue.priority == priority)

    # ── Full-text search (title + description + comment bodies) ──────────
    if q:
        ts_query = sa.func.websearch_to_tsquery("english", q)

        issue_vector = sa.func.to_tsvector(
            "english",
            sa.func.concat(Issue.title, " ", sa.func.coalesce(Issue.description, "")),
        )

        comment_hit = (
            sa.select(sa.literal(1))
            .where(
                Comment.issue_id == Issue.id,
                sa.func.to_tsvector("english", Comment.body).bool_op("@@")(ts_query),
            )
            .correlate(Issue)
            .exists()
        )

        stmt = stmt.where(sa.or_(issue_vector.bool_op("@@")(ts_query), comment_hit))

    # ── Cursor keyset pagination (descending by created_at, id) ──────────
    if cursor:
        cur_ts, cur_id = decode_cursor(cursor)
        stmt = stmt.where(
            sa.or_(
                Issue.created_at < cur_ts,
                sa.and_(Issue.created_at == cur_ts, Issue.id < cur_id),
            )
        )

    stmt = stmt.order_by(Issue.created_at.desc(), Issue.id.desc())
    stmt = stmt.limit(limit + 1)

    rows = list((await session.execute(stmt)).scalars().all())

    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return rows, next_cursor
