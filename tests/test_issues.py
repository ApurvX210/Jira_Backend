"""
Tests for the Issue engine:
  • hierarchy validation
  • workflow transitions (valid + invalid → 422)
  • optimistic locking (stale version → 409)
  • on_enter automatic actions
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import EPIC_ID, PROJECT_ID, STORY_ID, USER_ID

pytestmark = pytest.mark.asyncio

HEADERS = {"X-User-Id": str(USER_ID)}


# ── Issue Creation ───────────────────────────────────────────────────────────

class TestCreateIssue:
    async def test_create_story_under_epic(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"/api/projects/{PROJECT_ID}/issues",
            headers=HEADERS,
            json={
                "type": "story",
                "title": "New Story",
                "parent_id": str(EPIC_ID),
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["key"].startswith("TEST-")
        assert data["parent_id"] == str(EPIC_ID)
        assert data["type"] == "story"

    async def test_create_sub_task_under_story(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"/api/projects/{PROJECT_ID}/issues",
            headers=HEADERS,
            json={
                "type": "sub_task",
                "title": "Sub-task",
                "parent_id": str(STORY_ID),
            },
        )
        assert resp.status_code == 201

    async def test_reject_sub_task_under_epic(self, client: AsyncClient) -> None:
        """Epic cannot directly parent a sub_task (must go through Story)."""
        resp = await client.post(
            f"/api/projects/{PROJECT_ID}/issues",
            headers=HEADERS,
            json={
                "type": "sub_task",
                "title": "Bad child",
                "parent_id": str(EPIC_ID),
            },
        )
        assert resp.status_code == 422

    async def test_reject_child_of_sub_task(self, client: AsyncClient) -> None:
        """Sub-tasks cannot be parents."""
        # First create a valid sub-task
        r1 = await client.post(
            f"/api/projects/{PROJECT_ID}/issues",
            headers=HEADERS,
            json={
                "type": "sub_task",
                "title": "Valid sub-task",
                "parent_id": str(STORY_ID),
            },
        )
        assert r1.status_code == 201
        sub_id = r1.json()["id"]

        # Try to create a child under the sub-task
        r2 = await client.post(
            f"/api/projects/{PROJECT_ID}/issues",
            headers=HEADERS,
            json={
                "type": "task",
                "title": "Should fail",
                "parent_id": sub_id,
            },
        )
        assert r2.status_code == 422


# ── Workflow Transitions ─────────────────────────────────────────────────────

class TestWorkflowTransitions:
    async def test_valid_transition(self, client: AsyncClient) -> None:
        """to_do → in_progress is allowed."""
        resp = await client.post(
            f"/api/issues/{STORY_ID}/transitions",
            headers=HEADERS,
            json={"new_status": "in_progress"},
        )
        assert resp.status_code == 200
        assert resp.json()["issue"]["status"] == "in_progress"

    async def test_invalid_transition_returns_422(self, client: AsyncClient) -> None:
        """to_do → done is forbidden; response must list allowed targets."""
        resp = await client.post(
            f"/api/issues/{STORY_ID}/transitions",
            headers=HEADERS,
            json={"new_status": "done"},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "allowed_transitions" in body
        assert body["current_status"] == "to_do"
        assert body["requested_status"] == "done"
        assert "in_progress" in body["allowed_transitions"]

    async def test_on_enter_clears_assignee(self, client: AsyncClient) -> None:
        """Transitioning to in_review should auto-clear assignee_id."""
        # Move to_do → in_progress first
        r1 = await client.post(
            f"/api/issues/{STORY_ID}/transitions",
            headers=HEADERS,
            json={"new_status": "in_progress"},
        )
        assert r1.status_code == 200

        # Now in_progress → in_review (on_enter clears assignee_id)
        r2 = await client.post(
            f"/api/issues/{STORY_ID}/transitions",
            headers=HEADERS,
            json={"new_status": "in_review"},
        )
        assert r2.status_code == 200
        data = r2.json()
        assert data["issue"]["assignee_id"] is None
        assert "cleared" in data["applied_actions"]


# ── Optimistic Locking ───────────────────────────────────────────────────────

class TestOptimisticLocking:
    async def test_successful_update_increments_version(
        self, client: AsyncClient
    ) -> None:
        resp = await client.patch(
            f"/api/issues/{STORY_ID}",
            headers=HEADERS,
            json={"priority": "highest", "version": 1},
        )
        assert resp.status_code == 200
        assert resp.json()["version"] == 2
        assert resp.json()["priority"] == "highest"

    async def test_stale_version_returns_409(self, client: AsyncClient) -> None:
        """Two writers with the same version — second one must lose."""
        # First update succeeds (version 1 → 2)
        r1 = await client.patch(
            f"/api/issues/{STORY_ID}",
            headers=HEADERS,
            json={"priority": "high", "version": 1},
        )
        assert r1.status_code == 200
        assert r1.json()["version"] == 2

        # Second update uses stale version 1 → 409 Conflict
        r2 = await client.patch(
            f"/api/issues/{STORY_ID}",
            headers=HEADERS,
            json={"priority": "low", "version": 1},
        )
        assert r2.status_code == 409
        body = r2.json()
        assert "current_version" in body
        assert body["provided_version"] == 1
