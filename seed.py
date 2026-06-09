"""
Seed script — populate the database with realistic dummy data.

Usage:
    python seed.py            # uses DATABASE_URL from .env
    python seed.py --drop     # drops and re-creates all tables first

Expand the `_seed` function with additional records as the schema evolves.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from app.core.config import settings
from app.db.session import async_session_factory, engine
from app.models import (  # noqa: F401  — registers metadata
    ActivityLog,
    Comment,
    Issue,
    IssuePriority,
    IssueStatus,
    IssueType,
    Project,
    Sprint,
    SprintStatus,
    User,
    Watcher,
)

# ---------------------------------------------------------------------------
# Deterministic UUIDs so re-runs are idempotent
# ---------------------------------------------------------------------------
USER_IDS = [uuid.UUID(f"00000000-0000-4000-8000-00000000000{i}") for i in range(1, 4)]
PROJECT_ID = uuid.UUID("10000000-0000-4000-8000-000000000001")
SPRINT_ID = uuid.UUID("20000000-0000-4000-8000-000000000001")
EPIC_ID = uuid.UUID("30000000-0000-4000-8000-000000000001")
STORY_ID = uuid.UUID("30000000-0000-4000-8000-000000000002")
TASK_ID = uuid.UUID("30000000-0000-4000-8000-000000000003")


async def _seed(session: AsyncSession) -> None:
    # --- Users ---------------------------------------------------------------
    users = [
        User(id=USER_IDS[0], email="alice@example.com", display_name="Alice"),
        User(id=USER_IDS[1], email="bob@example.com", display_name="Bob"),
        User(id=USER_IDS[2], email="carol@example.com", display_name="Carol"),
    ]
    session.add_all(users)

    # --- Project -------------------------------------------------------------
    project = Project(
        id=PROJECT_ID,
        name="Platform Alpha",
        key="ALPHA",
        description="The flagship product backlog.",
        workflow_config={
            "to_do": ["in_progress"],
            "in_progress": ["in_review", "to_do"],
            "in_review": ["done", "in_progress"],
            "done": [],
        },
        issue_counter=3,
    )
    session.add(project)

    # --- Sprint --------------------------------------------------------------
    sprint = Sprint(
        id=SPRINT_ID,
        project_id=PROJECT_ID,
        name="Sprint 1",
        start_date=date(2026, 6, 9),
        end_date=date(2026, 6, 23),
        status=SprintStatus.active,
    )
    session.add(sprint)

    # --- Issues (Epic -> Story -> Task) --------------------------------------
    epic = Issue(
        id=EPIC_ID,
        key="ALPHA-1",
        project_id=PROJECT_ID,
        type=IssueType.epic,
        title="User Authentication Epic",
        description="All auth-related work lives under this epic.",
        status=IssueStatus.in_progress,
        priority=IssuePriority.high,
        reporter_id=USER_IDS[0],
    )
    story = Issue(
        id=STORY_ID,
        key="ALPHA-2",
        project_id=PROJECT_ID,
        sprint_id=SPRINT_ID,
        type=IssueType.story,
        parent_id=EPIC_ID,
        title="Implement login flow",
        description="OAuth2 + JWT based login.",
        status=IssueStatus.to_do,
        priority=IssuePriority.high,
        story_points=5,
        reporter_id=USER_IDS[0],
        assignee_id=USER_IDS[1],
        custom_fields={"team": "backend", "estimation_method": "t-shirt"},
    )
    task = Issue(
        id=TASK_ID,
        key="ALPHA-3",
        project_id=PROJECT_ID,
        sprint_id=SPRINT_ID,
        type=IssueType.task,
        parent_id=STORY_ID,
        title="Set up JWT token generation",
        status=IssueStatus.to_do,
        priority=IssuePriority.medium,
        story_points=2,
        reporter_id=USER_IDS[1],
        assignee_id=USER_IDS[2],
    )
    session.add_all([epic, story, task])

    # --- Comment (threaded) --------------------------------------------------
    comment_root_id = uuid.UUID("40000000-0000-4000-8000-000000000001")
    comment_reply_id = uuid.UUID("40000000-0000-4000-8000-000000000002")
    session.add_all(
        [
            Comment(
                id=comment_root_id,
                issue_id=STORY_ID,
                user_id=USER_IDS[1],
                body="Should we use RS256 or HS256 for the JWT?",
            ),
            Comment(
                id=comment_reply_id,
                issue_id=STORY_ID,
                user_id=USER_IDS[0],
                body="RS256 — we'll need asymmetric keys for the gateway.",
                parent_id=comment_root_id,
            ),
        ]
    )

    # --- Activity Log --------------------------------------------------------
    session.add(
        ActivityLog(
            issue_id=STORY_ID,
            user_id=USER_IDS[0],
            action_type="status_change",
            old_values={"status": "to_do"},
            new_values={"status": "in_progress"},
        )
    )

    # --- Watcher -------------------------------------------------------------
    session.add(Watcher(user_id=USER_IDS[2], issue_id=STORY_ID))

    await session.commit()
    print("Seed data committed successfully.")


async def main(drop: bool = False) -> None:
    if drop:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
            await conn.run_sync(SQLModel.metadata.create_all)
            print("Tables dropped and re-created.")

    async with async_session_factory() as session:
        await _seed(session)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the Jira database")
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop and re-create all tables before seeding",
    )
    args = parser.parse_args()
    asyncio.run(main(drop=args.drop))
