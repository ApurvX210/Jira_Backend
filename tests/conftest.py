"""
Shared pytest fixtures for the Jira backend test suite.

The test database is the same Postgres instance from .env / docker-compose.
Each test runs inside a rolled-back transaction so the DB is never mutated.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    AsyncTransaction,
    create_async_engine,
)
from sqlmodel import SQLModel

from app.core.config import settings
from app.db.session import get_session
from app.main import app
from app.models import (  # noqa: F401  — register metadata
    Issue,
    IssuePriority,
    IssueStatus,
    IssueType,
    Project,
    Sprint,
    SprintStatus,
    User,
)

TEST_ENGINE = create_async_engine(settings.async_database_url, echo=False)

# Deterministic IDs
USER_ID = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
PROJECT_ID = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
SPRINT_ID = uuid.UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
SPRINT_BACKLOG_ID = uuid.UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccd")
EPIC_ID = uuid.UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
STORY_ID = uuid.UUID("dddddddd-dddd-4ddd-8ddd-ddddddddddde")


@pytest.fixture(scope="session", autouse=True)
async def _create_tables() -> AsyncGenerator[None, None]:
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await TEST_ENGINE.dispose()


@pytest.fixture()
async def connection() -> AsyncGenerator[AsyncConnection, None]:
    async with TEST_ENGINE.connect() as conn:
        yield conn


@pytest.fixture()
async def transaction(
    connection: AsyncConnection,
) -> AsyncGenerator[AsyncTransaction, None]:
    txn = await connection.begin()
    yield txn
    await txn.rollback()


@pytest.fixture()
async def session(
    connection: AsyncConnection,
    transaction: AsyncTransaction,
) -> AsyncGenerator[AsyncSession, None]:
    sess = AsyncSession(bind=connection, join_transaction_block=True)
    yield sess
    await sess.close()


@pytest.fixture()
async def seed(session: AsyncSession) -> None:
    """Insert minimal seed data for tests."""
    now = datetime.now(timezone.utc)

    session.add(User(id=USER_ID, email="test@example.com", display_name="Tester"))
    session.add(
        Project(
            id=PROJECT_ID,
            name="Test Project",
            key="TEST",
            workflow_config={
                "to_do": ["in_progress"],
                "in_progress": ["in_review", "to_do"],
                "in_review": ["done", "in_progress"],
                "done": [],
                "on_enter": {
                    "in_review": {"clear_fields": ["assignee_id"]},
                },
            },
            issue_counter=2,
        )
    )
    session.add(
        Sprint(
            id=SPRINT_ID,
            project_id=PROJECT_ID,
            name="Sprint 1",
            start_date=date(2026, 6, 9),
            end_date=date(2026, 6, 23),
            status=SprintStatus.active,
        )
    )
    session.add(
        Sprint(
            id=SPRINT_BACKLOG_ID,
            project_id=PROJECT_ID,
            name="Sprint 2",
            status=SprintStatus.backlog,
        )
    )
    session.add(
        Issue(
            id=EPIC_ID,
            key="TEST-1",
            project_id=PROJECT_ID,
            type=IssueType.epic,
            title="Test Epic",
            status=IssueStatus.to_do,
            priority=IssuePriority.high,
            reporter_id=USER_ID,
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        Issue(
            id=STORY_ID,
            key="TEST-2",
            project_id=PROJECT_ID,
            sprint_id=SPRINT_ID,
            type=IssueType.story,
            parent_id=EPIC_ID,
            title="Test Story",
            status=IssueStatus.to_do,
            priority=IssuePriority.medium,
            story_points=5,
            assignee_id=USER_ID,
            reporter_id=USER_ID,
            created_at=now,
            updated_at=now,
        )
    )
    await session.flush()


@pytest.fixture()
async def client(
    session: AsyncSession,
    seed: None,
) -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient wired to use the test session (auto-rolled-back)."""

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
