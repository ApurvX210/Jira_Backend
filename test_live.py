"""
test_live.py — Live-server integration test suite with heavy concurrency focus.

Unlike test_suite.py (which uses in-process ASGI transport), this script
hits a REAL running server over the network. It validates all routes and
puts special emphasis on concurrent race conditions.

Usage:
    # Start the server first:
    uvicorn app.main:app --host 127.0.0.1 --port 8000

    # Then in another terminal:
    python test_live.py                                   # defaults to localhost:8000
    python test_live.py --base-url http://localhost:8000   # explicit
    python test_live.py --base-url https://my-app.onrender.com  # deployed
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import uuid
from typing import Any

import httpx
import websockets

RUN = uuid.uuid4().hex[:8]


# ═══════════════════════════════════════════════════════════════════════════
# State
# ═══════════════════════════════════════════════════════════════════════════

class S:
    base_url: str = ""
    ws_url: str = ""
    pm_id: str = ""
    dev_id: str = ""
    reviewer_id: str = ""
    project_id: str = ""
    project_key: str = ""
    epic_id: str = ""
    story_id: str = ""
    story_key: str = ""
    subtask_id: str = ""
    sprint_1_id: str = ""
    sprint_2_id: str = ""
    bug_1_id: str = ""
    bug_2_id: str = ""
    story_version: int = 1
    user_ids: list[str] = []
    issue_ids: list[str] = []
    sprint_ids: list[str] = []


# ═══════════════════════════════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════════════════════════════

def banner(emoji: str, title: str) -> None:
    print(f"\n{'=' * 72}")
    print(f"  {emoji}  {title}")
    print(f"{'=' * 72}")

def ok(msg: str) -> None:
    print(f"  [PASS]  {msg}")

def fail(msg: str) -> None:
    print(f"  [FAIL]  {msg}")

def info(msg: str) -> None:
    print(f"  [INFO]  {msg}")

def step(msg: str) -> None:
    print(f"  [STEP]  {msg}")

def check(resp: httpx.Response, code: int, label: str) -> dict[str, Any]:
    if resp.status_code == code:
        ok(f"{label} -> HTTP {code}")
    else:
        fail(f"{label}: expected HTTP {code}, got {resp.status_code}")
        info(f"Body: {resp.text[:500]}")
        raise AssertionError(f"{label}: {resp.status_code} != {code}")
    return resp.json()


# ═══════════════════════════════════════════════════════════════════════════
# BLOCK 1 — Fixtures
# ═══════════════════════════════════════════════════════════════════════════

async def block_1(c: httpx.AsyncClient) -> None:
    banner("SETUP", "BLOCK 1 -- Fixtures, Setup & Global Provisioning")

    for role, prefix, display in [
        ("PM", "pm", "ProjectManager"),
        ("Dev", "dev", "Developer"),
        ("Reviewer", "reviewer", "Reviewer"),
    ]:
        body = check(
            await c.post("/api/users", json={
                "email": f"{prefix}_{RUN}@test.com",
                "display_name": display,
            }),
            201, f"Create user {role} ({display})",
        )
        uid = body["id"]
        S.user_ids.append(uid)
        if role == "PM":
            S.pm_id = uid
        elif role == "Dev":
            S.dev_id = uid
        else:
            S.reviewer_id = uid

    step(f"PM={S.pm_id[:8]}...  Dev={S.dev_id[:8]}...  Reviewer={S.reviewer_id[:8]}...")

    S.project_key = f"T{RUN[:4].upper()}"
    body = check(
        await c.post("/api/projects", json={
            "name": f"Test Project {RUN}",
            "key": S.project_key,
            "description": "Live integration test project",
            "workflow_config": {
                "to_do": ["in_progress"],
                "in_progress": ["in_review"],
                "in_review": ["to_do", "done"],
                "done": ["in_progress"],
            },
        }),
        201, "Create project with workflow config",
    )
    S.project_id = body["id"]
    ok("Block 1 complete -- 3 users + 1 project provisioned.\n")


# ═══════════════════════════════════════════════════════════════════════════
# BLOCK 2 — Hierarchy & CRUD
# ═══════════════════════════════════════════════════════════════════════════

async def block_2(c: httpx.AsyncClient) -> None:
    banner("HIERARCHY", "BLOCK 2 -- Structural Hierarchy & CRUD")
    h = {"X-User-Id": S.pm_id}

    body = check(
        await c.post(f"/api/projects/{S.project_id}/issues", headers=h, json={
            "type": "epic", "title": "OAuth 2.0 Integration Epic",
            "description": "Umbrella epic.", "priority": "high",
        }),
        201, "Create Epic",
    )
    S.epic_id = body["id"]
    S.issue_ids.append(S.epic_id)

    body = check(
        await c.post(f"/api/projects/{S.project_id}/issues", headers=h, json={
            "type": "story", "title": "Add user authentication via OAuth",
            "description": "OAuth 2.0 flow with PKCE.", "parent_id": S.epic_id,
            "priority": "high", "story_points": 3,
        }),
        201, "Create Story (parent=Epic)",
    )
    S.story_id = body["id"]
    S.story_key = body["key"]
    S.story_version = body["version"]
    S.issue_ids.append(S.story_id)
    assert body["parent_id"] == S.epic_id
    ok("Story.parent_id correctly linked to Epic")

    body = check(
        await c.post(f"/api/projects/{S.project_id}/issues", headers=h, json={
            "type": "sub_task", "title": "DB Schema Setup for Tokens",
            "parent_id": S.story_id, "priority": "medium",
        }),
        201, "Create Sub-task (parent=Story)",
    )
    S.subtask_id = body["id"]
    S.issue_ids.append(S.subtask_id)
    assert body["parent_id"] == S.story_id
    ok("Sub-task.parent_id correctly linked to Story")

    # Constraint violations
    check(
        await c.post(f"/api/projects/{S.project_id}/issues", headers=h, json={
            "type": "sub_task", "title": "Invalid", "parent_id": S.epic_id,
        }),
        422, "Sub-task under Epic -> BLOCKED",
    )
    check(
        await c.post(f"/api/projects/{S.project_id}/issues", headers=h, json={
            "type": "story", "title": "Invalid", "parent_id": S.story_id,
        }),
        422, "Story under Story -> BLOCKED",
    )
    ok("Block 2 complete -- hierarchy validated.\n")


# ═══════════════════════════════════════════════════════════════════════════
# BLOCK 3 — Workflow Guardrails
# ═══════════════════════════════════════════════════════════════════════════

async def block_3(c: httpx.AsyncClient) -> None:
    banner("WORKFLOW", "BLOCK 3 -- Workflow Engine Guardrails")
    h = {"X-User-Id": S.pm_id}

    # Illegal: to_do -> done
    body = check(
        await c.post(f"/api/issues/{S.story_id}/transitions", headers=h, json={
            "new_status": "done",
        }),
        422, "Illegal transition to_do -> done",
    )
    assert "in_progress" in body.get("allowed_transitions", [])
    ok(f"allowed_transitions={body['allowed_transitions']}")

    # Legitimate path
    for target in ["in_progress", "in_review"]:
        body = check(
            await c.post(f"/api/issues/{S.story_id}/transitions", headers=h, json={
                "new_status": target,
            }),
            200, f"Transition -> {target}",
        )
        S.story_version = body["issue"]["version"]
    ok(f"Story now 'in_review' (v={S.story_version})")
    ok("Block 3 complete -- workflow guardrails validated.\n")


# ═══════════════════════════════════════════════════════════════════════════
# BLOCK 4 — HEAVY Concurrent Updates & Race Conditions
# ═══════════════════════════════════════════════════════════════════════════

async def block_4(c: httpx.AsyncClient) -> None:
    banner("CONCURRENCY", "BLOCK 4 -- Heavy Concurrent Updates & Race Conditions")
    h = {"X-User-Id": S.pm_id}

    # ── Test 4a: Classic 2-way race (baseline) ────────────────────────────
    step("Test 4a: Two concurrent PATCHes with same version...")
    resp = await c.get(f"/api/projects/{S.project_id}/issues")
    story = next(i for i in resp.json()["items"] if i["id"] == S.story_id)
    version = story["version"]
    info(f"Story version before race = {version}")

    resp_a, resp_b = await asyncio.gather(
        c.patch(f"/api/issues/{S.story_id}", headers=h, json={
            "assignee_id": S.dev_id, "version": version,
        }),
        c.patch(f"/api/issues/{S.story_id}", headers=h, json={
            "priority": "highest", "version": version,
        }),
    )
    codes = sorted([resp_a.status_code, resp_b.status_code])
    assert codes == [200, 409], f"Expected [200, 409], got {codes}"
    ok(f"2-way race: codes={codes} -- exactly one winner, one 409 conflict")

    winner = resp_a if resp_a.status_code == 200 else resp_b
    S.story_version = winner.json()["version"]

    # ── Test 4b: N-way stampede (10 concurrent writes) ────────────────────
    N = 10
    step(f"Test 4b: {N}-way concurrent stampede with same version...")
    resp = await c.get(f"/api/projects/{S.project_id}/issues")
    story = next(i for i in resp.json()["items"] if i["id"] == S.story_id)
    version = story["version"]
    info(f"Story version before stampede = {version}")

    priorities = ["highest", "high", "medium", "low", "lowest",
                  "highest", "high", "medium", "low", "lowest"]
    tasks = [
        c.patch(f"/api/issues/{S.story_id}", headers=h, json={
            "priority": priorities[i], "version": version,
        })
        for i in range(N)
    ]
    results = await asyncio.gather(*tasks)
    result_codes = [r.status_code for r in results]
    winners_count = result_codes.count(200)
    conflicts_count = result_codes.count(409)

    info(f"Result codes: {result_codes}")
    assert winners_count == 1, f"Expected exactly 1 winner, got {winners_count}"
    assert conflicts_count == N - 1, f"Expected {N-1} conflicts, got {conflicts_count}"
    ok(f"{N}-way stampede: 1 winner + {N-1} conflicts -- zero data loss")

    winning_resp = next(r for r in results if r.status_code == 200)
    S.story_version = winning_resp.json()["version"]
    ok(f"Story version after stampede = {S.story_version}")

    # ── Test 4c: Verify data integrity after stampede ─────────────────────
    step("Test 4c: Verifying data integrity post-stampede...")
    resp = await c.get(f"/api/projects/{S.project_id}/issues")
    story = next(i for i in resp.json()["items"] if i["id"] == S.story_id)
    winning_priority = winning_resp.json()["priority"]
    assert story["priority"] == winning_priority, \
        f"DB has priority={story['priority']}, winner wrote {winning_priority}"
    assert story["version"] == S.story_version
    ok(f"Data integrity confirmed: priority='{winning_priority}', version={S.story_version}")

    # ── Test 4d: Concurrent issue creation (no conflicts expected) ────────
    N_CREATE = 10
    step(f"Test 4d: {N_CREATE} concurrent issue creations...")
    create_tasks = [
        c.post(f"/api/projects/{S.project_id}/issues", headers=h, json={
            "type": "task",
            "title": f"Concurrent task #{i} ({RUN})",
            "priority": "low",
        })
        for i in range(N_CREATE)
    ]
    create_results = await asyncio.gather(*create_tasks)
    create_codes = [r.status_code for r in create_results]
    assert all(code == 201 for code in create_codes), \
        f"Some creations failed: {create_codes}"
    ok(f"All {N_CREATE} concurrent creations succeeded (201)")

    created_keys = sorted([r.json()["key"] for r in create_results])
    unique_keys = set(created_keys)
    assert len(unique_keys) == N_CREATE, f"Duplicate keys detected: {created_keys}"
    ok(f"All {N_CREATE} issue keys are unique: {created_keys}")

    for r in create_results:
        S.issue_ids.append(r.json()["id"])

    # ── Test 4e: Concurrent transitions on separate issues ────────────────
    step("Test 4e: Concurrent transitions on multiple issues...")
    concurrent_issue_ids = [r.json()["id"] for r in create_results[:5]]
    transition_tasks = [
        c.post(f"/api/issues/{iid}/transitions", headers=h, json={
            "new_status": "in_progress",
        })
        for iid in concurrent_issue_ids
    ]
    transition_results = await asyncio.gather(*transition_tasks)
    transition_codes = [r.status_code for r in transition_results]
    assert all(code == 200 for code in transition_codes), \
        f"Some transitions failed: {transition_codes}"
    ok(f"All 5 concurrent transitions succeeded (no cross-issue interference)")

    # ── Test 4f: Read-write mix under load ────────────────────────────────
    step("Test 4f: Mixed read/write load (5 reads + 5 writes concurrently)...")
    resp = await c.get(f"/api/projects/{S.project_id}/issues")
    story = next(i for i in resp.json()["items"] if i["id"] == S.story_id)
    current_v = story["version"]

    mixed_tasks = []
    for i in range(5):
        mixed_tasks.append(c.get(f"/api/projects/{S.project_id}/issues"))
    mixed_tasks.append(
        c.patch(f"/api/issues/{S.story_id}", headers=h, json={
            "description": f"Updated under load ({RUN})",
            "version": current_v,
        })
    )
    for iid in concurrent_issue_ids[:4]:
        mixed_tasks.append(
            c.post(f"/api/issues/{iid}/transitions", headers=h, json={
                "new_status": "in_review",
            })
        )

    mixed_results = await asyncio.gather(*mixed_tasks)
    read_results = mixed_results[:5]
    write_results = mixed_results[5:]

    assert all(r.status_code == 200 for r in read_results), "Some reads failed under load"
    ok(f"5 concurrent reads all returned 200 under write pressure")

    write_codes = [r.status_code for r in write_results]
    write_successes = sum(1 for c_ in write_codes if c_ == 200)
    info(f"Write results under load: {write_codes}")
    ok(f"{write_successes}/{len(write_codes)} writes succeeded under mixed load")

    if write_results[0].status_code == 200:
        S.story_version = write_results[0].json()["version"]

    ok("Block 4 complete -- all concurrency tests passed.\n")


# ═══════════════════════════════════════════════════════════════════════════
# BLOCK 5 — Sprint Completion
# ═══════════════════════════════════════════════════════════════════════════

async def block_5(c: httpx.AsyncClient) -> None:
    banner("SPRINT", "BLOCK 5 -- Sprint Completion, Carry-Over & Velocity")
    h = {"X-User-Id": S.pm_id}

    for name, attr in [("Sprint 1", "sprint_1_id"), ("Sprint 2", "sprint_2_id")]:
        body = check(
            await c.post(f"/api/projects/{S.project_id}/sprints", json={
                "name": f"{name} ({RUN})",
            }),
            201, f"Create {name}",
        )
        setattr(S, attr, body["id"])
        S.sprint_ids.append(body["id"])

    # Move Story to Sprint 1
    resp = await c.get(f"/api/projects/{S.project_id}/issues")
    story = next(i for i in resp.json()["items"] if i["id"] == S.story_id)
    S.story_version = story["version"]

    check(
        await c.patch(f"/api/issues/{S.story_id}", headers=h, json={
            "sprint_id": S.sprint_1_id, "version": S.story_version,
        }),
        200, "Move Story to Sprint 1",
    )

    # Create Bug 1 (3 SP) and Bug 2 (2 SP)
    body = check(
        await c.post(f"/api/projects/{S.project_id}/issues", headers=h, json={
            "type": "bug", "title": "Token expiration bug",
            "priority": "high", "story_points": 3, "sprint_id": S.sprint_1_id,
        }),
        201, "Create Bug 1 (3 SP)",
    )
    S.bug_1_id = body["id"]
    S.issue_ids.append(S.bug_1_id)

    body = check(
        await c.post(f"/api/projects/{S.project_id}/issues", headers=h, json={
            "type": "bug", "title": "Refresh token race condition",
            "priority": "medium", "story_points": 2, "sprint_id": S.sprint_1_id,
        }),
        201, "Create Bug 2 (2 SP)",
    )
    S.bug_2_id = body["id"]
    S.issue_ids.append(S.bug_2_id)
    info("Sprint 1: Story(3) + Bug1(3) + Bug2(2) = 8 SP total")

    # Start Sprint 1
    check(await c.post(f"/api/sprints/{S.sprint_1_id}/start"), 200, "Start Sprint 1")

    # Transition Bug 1 to done
    for target in ["in_progress", "in_review", "done"]:
        check(
            await c.post(f"/api/issues/{S.bug_1_id}/transitions", headers=h, json={
                "new_status": target,
            }),
            200, f"Bug 1 -> {target}",
        )

    # Complete Sprint 1
    body = check(
        await c.post(f"/api/sprints/{S.sprint_1_id}/complete", json={
            "carry_over_issue_ids": [S.bug_2_id],
            "target_sprint_id": S.sprint_2_id,
        }),
        200, "Complete Sprint 1",
    )

    assert body["sprint"]["status"] == "completed"
    ok("Sprint 1 status = 'completed'")
    assert body["velocity"] == 3
    ok(f"Velocity = {body['velocity']}")
    assert body["carried_over"] == 1
    ok(f"carried_over = {body['carried_over']}")
    assert body["moved_to_backlog"] == 1
    ok(f"moved_to_backlog = {body['moved_to_backlog']}")

    # Verify carry-over
    resp = await c.get(f"/api/projects/{S.project_id}/issues",
                       params={"sprint_id": S.sprint_2_id})
    assert S.bug_2_id in [i["id"] for i in resp.json()["items"]]
    ok("Bug 2 carried over to Sprint 2")

    resp = await c.get(f"/api/projects/{S.project_id}/issues")
    story = next(i for i in resp.json()["items"] if i["id"] == S.story_id)
    assert story["sprint_id"] is None
    ok("Story moved to backlog (sprint_id=null)")
    ok("Block 5 complete -- sprint lifecycle validated.\n")


# ═══════════════════════════════════════════════════════════════════════════
# BLOCK 6 — Search & Pagination
# ═══════════════════════════════════════════════════════════════════════════

async def block_6(c: httpx.AsyncClient) -> None:
    banner("SEARCH", "BLOCK 6 -- Full-Text Search & Cursor Pagination")
    h = {"X-User-Id": S.pm_id}
    search_ids: list[str] = []

    titles = [
        ("Supabase Connection Pooling", "Configure pooling."),
        ("Supabase Auth Integration", "Integrate auth."),
        ("Storage Configuration", "Set up Supabase storage."),
        ("Supabase Realtime Setup", "Enable realtime."),
    ]
    for title, desc in titles:
        body = check(
            await c.post(f"/api/projects/{S.project_id}/issues", headers=h, json={
                "type": "task", "title": title, "description": desc,
            }),
            201, f"Create: '{title[:35]}...'",
        )
        search_ids.append(body["id"])
        S.issue_ids.append(body["id"])

    body = check(
        await c.post(f"/api/projects/{S.project_id}/issues", headers=h, json={
            "type": "task", "title": "Database Migration Scripts",
            "description": "Prepare migration scripts.",
        }),
        201, "Create issue (FTS match via comment)",
    )
    comment_issue_id = body["id"]
    search_ids.append(comment_issue_id)
    S.issue_ids.append(comment_issue_id)

    check(
        await c.post(f"/api/issues/{comment_issue_id}/comments", json={
            "body": "Validate against our Supabase staging environment.",
            "user_id": S.dev_id,
        }),
        201, "Add comment with 'Supabase'",
    )

    # Paginated search
    all_found: list[str] = []
    cursor: str | None = None
    page = 0
    while True:
        page += 1
        params: dict[str, Any] = {"q": "Supabase", "limit": 2}
        if cursor:
            params["cursor"] = cursor
        resp = await c.get(f"/api/projects/{S.project_id}/issues", params=params)
        assert resp.status_code == 200
        data = resp.json()
        all_found.extend(i["id"] for i in data["items"])
        cursor = data.get("next_cursor")
        ok(f"Page {page}: {len(data['items'])} items" +
           (", has next_cursor" if cursor else ", final page"))
        if cursor:
            raw = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
            assert "c" in raw and "i" in raw
        if not cursor:
            break

    for sid in search_ids:
        assert sid in all_found, f"Issue {sid[:8]}... missing from search"
    ok(f"All {len(search_ids)} issues found across {page} pages")
    ok("Block 6 complete -- search & pagination validated.\n")


# ═══════════════════════════════════════════════════════════════════════════
# BLOCK 7 — WebSocket & Notifications (real network)
# ═══════════════════════════════════════════════════════════════════════════

async def block_7(c: httpx.AsyncClient) -> None:
    banner("WEBSOCKET", "BLOCK 7 -- Real-Time WebSocket & Notifications")

    # Parent comment
    parent = check(
        await c.post(f"/api/issues/{S.epic_id}/comments", json={
            "body": "Architecture review notes.", "user_id": S.pm_id,
        }),
        201, "Create parent comment",
    )
    parent_id = parent["id"]

    # Connect real WebSocket
    ws_uri = f"{S.ws_url}/ws/projects/{S.project_id}?user_id={S.dev_id}"
    step(f"Connecting WebSocket to {ws_uri[:60]}...")

    async with websockets.connect(ws_uri) as ws:
        # Read presence
        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        presence = json.loads(raw)
        assert presence["event"] == "presence_updated"
        assert S.dev_id in presence["data"]["active_users"]
        ok("WebSocket connected -- received presence_updated")

        # Post threaded reply with @mention while WS listens
        step("Posting threaded comment with @Reviewer while WS listens...")
        reply = check(
            await c.post(f"/api/issues/{S.epic_id}/comments", json={
                "body": "Looking into this @Reviewer",
                "user_id": S.dev_id,
                "parent_id": parent_id,
            }),
            201, "Create threaded reply with @mention",
        )
        reply_id = reply["id"]
        assert reply["parent_id"] == parent_id
        ok("Reply.parent_id correctly set")

        # Read broadcast
        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        event = json.loads(raw)
        assert event["event"] == "comment.created"
        assert event["data"]["id"] == reply_id
        ok(f"WebSocket received 'comment.created' for {reply_id[:8]}...")
        if "sequence_id" in event:
            ok(f"Broadcast has sequence_id={event['sequence_id']}")

    ok("WebSocket disconnected cleanly")

    # Verify comment hierarchy
    resp = await c.get(f"/api/issues/{S.epic_id}/comments")
    assert resp.status_code == 200
    reply_obj = next((cm for cm in resp.json() if cm["id"] == reply_id), None)
    assert reply_obj is not None and reply_obj["parent_id"] == parent_id
    ok("Comment hierarchy verified via REST")

    # Check notification for Reviewer
    resp = await c.get("/api/notifications", headers={"X-User-Id": S.reviewer_id})
    assert resp.status_code == 200
    mention = next(
        (n for n in resp.json()
         if "mentioned" in n["message"].lower()
         and n["triggered_by_issue_id"] == S.epic_id),
        None,
    )
    assert mention is not None, f"No mention notification found. Got: {resp.json()}"
    assert mention["is_read"] is False
    ok(f"Reviewer has unread notification: '{mention['message']}'")
    ok("Block 7 complete -- WebSocket, threading & mentions validated.\n")


# ═══════════════════════════════════════════════════════════════════════════
# Cleanup
# ═══════════════════════════════════════════════════════════════════════════

async def cleanup(c: httpx.AsyncClient) -> None:
    banner("CLEANUP", "Removing test data via API-compatible cleanup")
    try:
        from app.db.session import async_session_factory
        from sqlalchemy import text as sql_text

        async with async_session_factory() as session:
            pid = S.project_id
            uids = S.user_ids
            if not pid:
                info("No project_id -- skipping")
                return

            rows = (await session.execute(
                sql_text("SELECT id FROM issues WHERE project_id = :pid"), {"pid": pid},
            )).fetchall()
            all_iids = [str(r[0]) for r in rows]

            if all_iids:
                ph = ",".join(f"'{i}'" for i in all_iids)
                await session.execute(sql_text(
                    f"DELETE FROM notifications WHERE triggered_by_issue_id IN ({ph})"
                ))
                for tbl in ["watchers", "activity_logs", "comments"]:
                    await session.execute(sql_text(
                        f"DELETE FROM {tbl} WHERE issue_id IN ({ph})"
                    ))

            await session.execute(sql_text(
                "DELETE FROM event_log WHERE project_id = :pid"), {"pid": pid})

            if all_iids:
                await session.execute(sql_text(
                    "UPDATE issues SET parent_id = NULL WHERE project_id = :pid"), {"pid": pid})
                await session.execute(sql_text(
                    "DELETE FROM issues WHERE project_id = :pid"), {"pid": pid})

            await session.execute(sql_text(
                "DELETE FROM sprints WHERE project_id = :pid"), {"pid": pid})
            await session.execute(sql_text(
                "DELETE FROM projects WHERE id = :pid"), {"pid": pid})

            if uids:
                uph = ",".join(f"'{u}'" for u in uids)
                await session.execute(sql_text(
                    f"DELETE FROM notifications WHERE user_id IN ({uph})"))
                await session.execute(sql_text(
                    f"DELETE FROM activity_logs WHERE user_id IN ({uph})"))
                await session.execute(sql_text(
                    f"DELETE FROM users WHERE id IN ({uph})"))

            await session.commit()
            ok("All test data removed.")
    except Exception as exc:
        fail(f"Cleanup error (non-fatal): {exc}")


# ═══════════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════════

async def run_all(base_url: str) -> None:
    S.base_url = base_url.rstrip("/")
    S.ws_url = S.base_url.replace("http://", "ws://").replace("https://", "wss://")

    banner("LAUNCH", f"LIVE SERVER TEST SUITE -- Run ID: {RUN}")
    info(f"Target: {S.base_url}")
    info(f"WebSocket: {S.ws_url}")

    # Health check
    async with httpx.AsyncClient(base_url=S.base_url, timeout=10) as probe:
        try:
            resp = await probe.get("/health")
            assert resp.status_code == 200 and resp.json().get("status") == "ok"
            ok("Server health check passed")
        except Exception as exc:
            fail(f"Server not reachable at {S.base_url}: {exc}")
            info("Start the server first: uvicorn app.main:app --host 127.0.0.1 --port 8000")
            raise SystemExit(1)

    async with httpx.AsyncClient(base_url=S.base_url, timeout=30) as c:
        blocks = [
            (block_1, "Fixtures & Setup"),
            (block_2, "Hierarchy & CRUD"),
            (block_3, "Workflow Guardrails"),
            (block_4, "Heavy Concurrency"),
            (block_5, "Sprint Completion"),
            (block_6, "Search & Pagination"),
            (block_7, "WebSocket & Notifications"),
        ]
        passed = 0
        try:
            for fn, name in blocks:
                await fn(c)
                passed += 1
        except Exception as exc:
            banner("FAILURE", f"Block {passed + 1} ({blocks[passed][1]})")
            fail(str(exc))
            import traceback
            traceback.print_exc()
        finally:
            await cleanup(c)

        if passed == len(blocks):
            banner("SUCCESS", f"ALL {passed}/{len(blocks)} BLOCKS PASSED")
        else:
            banner("PARTIAL", f"{passed}/{len(blocks)} blocks passed")
            raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live-server integration tests")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL of the running server (default: http://127.0.0.1:8000)",
    )
    args = parser.parse_args()
    asyncio.run(run_all(args.base_url))
