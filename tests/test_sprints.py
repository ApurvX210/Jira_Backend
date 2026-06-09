"""
Tests for the Sprint lifecycle:
  • starting a sprint
  • preventing two concurrent active sprints
  • atomic sprint completion with velocity calculation
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import (
    PROJECT_ID,
    SPRINT_BACKLOG_ID,
    SPRINT_ID,
    STORY_ID,
    USER_ID,
)

pytestmark = pytest.mark.asyncio

HEADERS = {"X-User-Id": str(USER_ID)}


class TestStartSprint:
    async def test_start_backlog_sprint(self, client: AsyncClient) -> None:
        """A backlog sprint can be started when no other sprint is active."""
        # Complete the currently active sprint first
        await client.post(
            f"/api/sprints/{SPRINT_ID}/complete",
            json={"carry_over_issue_ids": []},
        )
        resp = await client.post(f"/api/sprints/{SPRINT_BACKLOG_ID}/start")
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    async def test_cannot_start_while_another_active(
        self, client: AsyncClient
    ) -> None:
        """Only one active sprint per project at a time."""
        resp = await client.post(f"/api/sprints/{SPRINT_BACKLOG_ID}/start")
        assert resp.status_code == 422
        assert "already active" in resp.json()["detail"].lower()


class TestCompleteSprint:
    async def test_complete_calculates_velocity(self, client: AsyncClient) -> None:
        """Velocity = sum of story_points for 'done' issues."""
        # Mark the story as done first
        await client.post(
            f"/api/issues/{STORY_ID}/transitions",
            headers=HEADERS,
            json={"new_status": "in_progress"},
        )
        await client.post(
            f"/api/issues/{STORY_ID}/transitions",
            headers=HEADERS,
            json={"new_status": "in_review"},
        )
        await client.post(
            f"/api/issues/{STORY_ID}/transitions",
            headers=HEADERS,
            json={"new_status": "done"},
        )

        # Now complete the sprint
        resp = await client.post(
            f"/api/sprints/{SPRINT_ID}/complete",
            json={"carry_over_issue_ids": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["velocity"] == 5  # the story had story_points=5
        assert data["sprint"]["status"] == "completed"

    async def test_carry_over_moves_issues(self, client: AsyncClient) -> None:
        """Incomplete issues listed in carry_over_issue_ids move to target sprint."""
        # Create a new issue that stays to_do (incomplete)
        create_resp = await client.post(
            f"/api/projects/{PROJECT_ID}/issues",
            headers=HEADERS,
            json={
                "type": "task",
                "title": "Leftover task",
                "sprint_id": str(SPRINT_ID),
                "story_points": 3,
            },
        )
        assert create_resp.status_code == 201
        leftover_id = create_resp.json()["id"]

        resp = await client.post(
            f"/api/sprints/{SPRINT_ID}/complete",
            json={
                "carry_over_issue_ids": [leftover_id],
                "target_sprint_id": str(SPRINT_BACKLOG_ID),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["carried_over"] >= 1

    async def test_cannot_complete_non_active_sprint(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post(
            f"/api/sprints/{SPRINT_BACKLOG_ID}/complete",
            json={"carry_over_issue_ids": []},
        )
        assert resp.status_code == 422
        assert "expected 'active'" in resp.json()["detail"].lower()
