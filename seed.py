"""
Seed script — clear transient data and populate the Supabase database
with realistic, deeply relational engineering data.

Usage:
    python seed.py            # uses DATABASE_URL from .env
    python seed.py --drop     # drops and re-creates all tables first

Scenario:
    - 3 users (Alice Smith, Jane Smith, Bob Chen)
    - 1 project "Platform Core" (key PROJ) with full workflow config
    - 3 sprints (Sprint 9 completed, Sprint 10 active, Sprint 11 future)
    - Hierarchical issues: Epic → Story → Sub-task in Sprint 10
    - 3 extra incomplete stories (8 story points total) for carry-over testing
    - Threaded comments, watchers, activity logs, event logs, notifications
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from app.core.config import settings
from app.db.session import async_session_factory, engine
from app.models import (  # noqa: F401  — registers metadata
    ActivityLog,
    Comment,
    EventLog,
    Issue,
    IssuePriority,
    IssueStatus,
    IssueType,
    Notification,
    Project,
    Sprint,
    SprintStatus,
    User,
    Watcher,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Deterministic UUIDs — re-runs are idempotent after truncation
# ---------------------------------------------------------------------------
ALICE_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
JANE_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")
BOB_ID = uuid.UUID("00000000-0000-4000-8000-000000000003")

PROJECT_ID = uuid.UUID("10000000-0000-4000-8000-000000000001")

SPRINT_9_ID = uuid.UUID("20000000-0000-4000-8000-000000000001")
SPRINT_10_ID = uuid.UUID("20000000-0000-4000-8000-000000000002")
SPRINT_11_ID = uuid.UUID("20000000-0000-4000-8000-000000000003")

EPIC_ID = uuid.UUID("30000000-0000-4000-8000-000000000001")
STORY_ID = uuid.UUID("30000000-0000-4000-8000-000000000002")
SUBTASK_ID = uuid.UUID("30000000-0000-4000-8000-000000000003")
EXTRA_STORY_1_ID = uuid.UUID("30000000-0000-4000-8000-000000000004")
EXTRA_STORY_2_ID = uuid.UUID("30000000-0000-4000-8000-000000000005")
EXTRA_STORY_3_ID = uuid.UUID("30000000-0000-4000-8000-000000000006")

COMMENT_ROOT_ID = uuid.UUID("40000000-0000-4000-8000-000000000001")
COMMENT_REPLY_ID = uuid.UUID("40000000-0000-4000-8000-000000000002")

NOTIFICATION_1_ID = uuid.UUID("50000000-0000-4000-8000-000000000001")
NOTIFICATION_2_ID = uuid.UUID("50000000-0000-4000-8000-000000000002")


async def _clear_tables(session: AsyncSession) -> None:
    """Truncate all tables in FK-safe order using CASCADE."""
    await session.execute(
        text(
            "TRUNCATE TABLE event_log, notifications, watchers, activity_logs, "
            "comments, issues, sprints, projects, users CASCADE"
        )
    )
    await session.commit()
    log.info("All existing data cleared (TRUNCATE CASCADE).")


async def _seed(session: AsyncSession) -> None:
    now = datetime.now(timezone.utc)

    # ── 1. Users ──────────────────────────────────────────────────────────────
    alice = User(
        id=ALICE_ID,
        email="alice.smith@example.com",
        display_name="Alice Smith",
    )
    jane = User(
        id=JANE_ID,
        email="jane.smith@example.com",
        display_name="Jane Smith",
    )
    bob = User(
        id=BOB_ID,
        email="bob.chen@example.com",
        display_name="Bob Chen",
    )
    session.add_all([alice, jane, bob])
    await session.flush()
    log.info("Inserted 3 users: Alice Smith (Team Lead), Jane Smith (SDE-1), Bob Chen (PM).")

    # ── 2. Project ────────────────────────────────────────────────────────────
    project = Project(
        id=PROJECT_ID,
        name="Platform Core",
        key="PROJ",
        description="Core platform services and authentication infrastructure.",
        workflow_config={
            "to_do": ["in_progress"],
            "in_progress": ["in_review", "to_do"],
            "in_review": ["done", "in_progress"],
            "done": [],
        },
        issue_counter=6,
    )
    session.add(project)
    await session.flush()
    log.info("Inserted project 'Platform Core' (PROJ) with workflow state machine.")

    # ── 3. Sprints ────────────────────────────────────────────────────────────
    sprint_9 = Sprint(
        id=SPRINT_9_ID,
        project_id=PROJECT_ID,
        name="Sprint 9",
        start_date=date(2026, 5, 26),
        end_date=date(2026, 6, 8),
        status=SprintStatus.completed,
        velocity=12,
    )
    sprint_10 = Sprint(
        id=SPRINT_10_ID,
        project_id=PROJECT_ID,
        name="Sprint 10",
        start_date=date(2026, 6, 9),
        end_date=date(2026, 6, 22),
        status=SprintStatus.active,
    )
    sprint_11 = Sprint(
        id=SPRINT_11_ID,
        project_id=PROJECT_ID,
        name="Sprint 11",
        start_date=date(2026, 6, 23),
        end_date=date(2026, 7, 6),
        status=SprintStatus.future,
    )
    session.add_all([sprint_9, sprint_10, sprint_11])
    await session.flush()
    log.info("Inserted 3 sprints: Sprint 9 (completed, v=12), Sprint 10 (active), Sprint 11 (future).")

    # ── 4. Hierarchical Issues (Epic → Story → Sub-task) ──────────────────────
    epic = Issue(
        id=EPIC_ID,
        key="PROJ-1",
        project_id=PROJECT_ID,
        sprint_id=SPRINT_10_ID,
        type=IssueType.epic,
        title="OAuth 2.0 Integration",
        description="End-to-end OAuth 2.0 implementation for platform authentication.",
        status=IssueStatus.in_progress,
        priority=IssuePriority.high,
        reporter_id=ALICE_ID,
        assignee_id=ALICE_ID,
    )
    session.add(epic)
    await session.flush()
    log.info("Inserted Epic PROJ-1: 'OAuth 2.0 Integration' (high priority).")

    story = Issue(
        id=STORY_ID,
        key="PROJ-2",
        project_id=PROJECT_ID,
        sprint_id=SPRINT_10_ID,
        type=IssueType.story,
        parent_id=EPIC_ID,
        title="Add user authentication via OAuth",
        description="Implement OAuth 2.0 authorization code flow with PKCE for user login.",
        status=IssueStatus.in_progress,
        priority=IssuePriority.high,
        story_points=5,
        reporter_id=ALICE_ID,
        assignee_id=JANE_ID,
        custom_fields={"qa_signoff_required": True},
    )
    session.add(story)
    await session.flush()
    log.info("Inserted Story PROJ-2: 'Add user authentication via OAuth' (5 SP, parent=PROJ-1).")

    subtask = Issue(
        id=SUBTASK_ID,
        key="PROJ-3",
        project_id=PROJECT_ID,
        sprint_id=SPRINT_10_ID,
        type=IssueType.sub_task,
        parent_id=STORY_ID,
        title="Database Schema Setup for Tokens",
        description="Design and migrate token storage tables (refresh tokens, access tokens, scopes).",
        status=IssueStatus.to_do,
        priority=IssuePriority.medium,
        story_points=2,
        reporter_id=JANE_ID,
        assignee_id=JANE_ID,
    )
    session.add(subtask)
    await session.flush()
    log.info("Inserted Sub-task PROJ-3: 'Database Schema Setup for Tokens' (parent=PROJ-2).")

    # ── 5. Scenario 2 Readiness: 3 incomplete stories totaling 8 SP ───────────
    extra_story_1 = Issue(
        id=EXTRA_STORY_1_ID,
        key="PROJ-4",
        project_id=PROJECT_ID,
        sprint_id=SPRINT_10_ID,
        type=IssueType.story,
        title="Implement token refresh endpoint",
        description="Build the /auth/refresh endpoint to issue new access tokens.",
        status=IssueStatus.to_do,
        priority=IssuePriority.medium,
        story_points=3,
        reporter_id=BOB_ID,
        assignee_id=JANE_ID,
    )
    extra_story_2 = Issue(
        id=EXTRA_STORY_2_ID,
        key="PROJ-5",
        project_id=PROJECT_ID,
        sprint_id=SPRINT_10_ID,
        type=IssueType.story,
        title="Add OAuth scope validation middleware",
        description="Create FastAPI middleware to validate OAuth scopes per endpoint.",
        status=IssueStatus.to_do,
        priority=IssuePriority.high,
        story_points=3,
        reporter_id=ALICE_ID,
        assignee_id=JANE_ID,
    )
    extra_story_3 = Issue(
        id=EXTRA_STORY_3_ID,
        key="PROJ-6",
        project_id=PROJECT_ID,
        sprint_id=SPRINT_10_ID,
        type=IssueType.story,
        title="Write OAuth integration tests",
        description="End-to-end test suite for the OAuth login and token refresh flows.",
        status=IssueStatus.in_progress,
        priority=IssuePriority.medium,
        story_points=2,
        reporter_id=BOB_ID,
        assignee_id=JANE_ID,
    )
    session.add_all([extra_story_1, extra_story_2, extra_story_3])
    await session.flush()
    log.info("Inserted 3 extra incomplete stories (PROJ-4/5/6) totaling 8 SP for carry-over testing.")

    # ── 6. Threaded Comments on OAuth Story ───────────────────────────────────
    root_comment = Comment(
        id=COMMENT_ROOT_ID,
        issue_id=STORY_ID,
        user_id=BOB_ID,
        body="Please review the compliance docs @Alice",
    )
    session.add(root_comment)
    await session.flush()

    reply_comment = Comment(
        id=COMMENT_REPLY_ID,
        issue_id=STORY_ID,
        user_id=ALICE_ID,
        body="Reviewed — GDPR section 4.2 covers our token storage requirements. We're compliant.",
        parent_id=COMMENT_ROOT_ID,
    )
    session.add(reply_comment)
    await session.flush()
    log.info("Inserted 2 threaded comments on PROJ-2 (Bob root → Alice reply).")

    # ── 7. Watchers (Bob + Alice on OAuth Story) ──────────────────────────────
    session.add_all([
        Watcher(user_id=BOB_ID, issue_id=STORY_ID),
        Watcher(user_id=ALICE_ID, issue_id=STORY_ID),
    ])
    await session.flush()
    log.info("Registered Bob Chen and Alice Smith as watchers on PROJ-2.")

    # ── 8. Activity Logs ──────────────────────────────────────────────────────
    session.add_all([
        ActivityLog(
            issue_id=STORY_ID,
            user_id=JANE_ID,
            action_type="transition",
            old_values={"status": "to_do"},
            new_values={"status": "in_progress"},
        ),
        ActivityLog(
            issue_id=STORY_ID,
            user_id=BOB_ID,
            action_type="mentioned",
            old_values=None,
            new_values={"comment_id": str(COMMENT_ROOT_ID), "mentioned_user": "Alice Smith"},
        ),
    ])
    await session.flush()
    log.info("Inserted 2 activity logs (transition + mention) on PROJ-2.")

    # ── 9. Event Log (WebSocket replay entries) ───────────────────────────────
    session.add_all([
        EventLog(
            project_id=PROJECT_ID,
            event_type="issue.created",
            payload={
                "event": "issue.created",
                "data": {"issue_key": "PROJ-1", "title": "OAuth 2.0 Integration"},
                "timestamp": now.isoformat(),
            },
        ),
        EventLog(
            project_id=PROJECT_ID,
            event_type="issue.transitioned",
            payload={
                "event": "issue.transitioned",
                "data": {
                    "issue_key": "PROJ-2",
                    "old_status": "to_do",
                    "new_status": "in_progress",
                },
                "timestamp": now.isoformat(),
            },
        ),
        EventLog(
            project_id=PROJECT_ID,
            event_type="comment.created",
            payload={
                "event": "comment.created",
                "data": {
                    "issue_key": "PROJ-2",
                    "comment_id": str(COMMENT_ROOT_ID),
                    "author": "Bob Chen",
                },
                "timestamp": now.isoformat(),
            },
        ),
    ])
    await session.flush()
    log.info("Inserted 3 event log entries for WebSocket replay.")

    # ── 10. Notifications ─────────────────────────────────────────────────────
    session.add_all([
        Notification(
            id=NOTIFICATION_1_ID,
            user_id=ALICE_ID,
            message="Bob Chen mentioned you in a comment on PROJ-2: 'Please review the compliance docs @Alice'",
            is_read=False,
            triggered_by_issue_id=STORY_ID,
        ),
        Notification(
            id=NOTIFICATION_2_ID,
            user_id=ALICE_ID,
            message="PROJ-2 'Add user authentication via OAuth' transitioned from to_do → in_progress",
            is_read=True,
            triggered_by_issue_id=STORY_ID,
        ),
    ])
    await session.flush()
    log.info("Inserted 2 notifications for Alice Smith.")

    await session.commit()
    log.info("All seed data committed successfully.")


async def main(drop: bool = False) -> None:
    if drop:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
            await conn.run_sync(SQLModel.metadata.create_all)
            log.info("Tables dropped and re-created via --drop flag.")

    async with async_session_factory() as session:
        await _clear_tables(session)

    async with async_session_factory() as session:
        await _seed(session)

    log.info("Database seeding complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the Jira database")
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop and re-create all tables before seeding",
    )
    args = parser.parse_args()
    asyncio.run(main(drop=args.drop))
