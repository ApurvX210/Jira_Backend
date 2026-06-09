"""
Board state aggregator.

Returns every issue for a project grouped by status column,
plus the active sprint metadata — all in a single efficient query.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.issue import Issue
from app.models.project import Project
from app.models.sprint import Sprint, SprintStatus


async def get_board(
    session: AsyncSession,
    project_id: uuid.UUID,
) -> dict[str, Any]:
    project = await session.get(Project, project_id)
    if project is None:
        raise NotFoundError("Project", project_id)

    # All issues for the project, ordered for deterministic output
    rows = (
        await session.execute(
            sa.select(Issue)
            .where(Issue.project_id == project_id)
            .order_by(Issue.priority.desc(), Issue.created_at.desc())
        )
    ).scalars().all()

    columns: dict[str, list[Issue]] = defaultdict(list)
    for issue in rows:
        status_key = issue.status.value if hasattr(issue.status, "value") else issue.status
        columns[status_key].append(issue)

    # Active sprint (if any)
    active_sprint = (
        await session.execute(
            sa.select(Sprint).where(
                Sprint.project_id == project_id,
                Sprint.status == SprintStatus.active,
            )
        )
    ).scalars().first()

    return {
        "columns": dict(columns),
        "active_sprint": active_sprint,
    }
