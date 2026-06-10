# Jira Backend — Async Project Management Platform

A production-grade, high-throughput project management API built with **async FastAPI**, **Supabase PostgreSQL**, and **native WebSockets**. Designed from the ground up for real-time collaborative engineering workflows at scale.

---

## Table of Contents

- [Executive Overview \& System Architecture](#executive-overview--system-architecture)
- [Tech Stack](#tech-stack)
- [Advanced Relational Database Schema (ERD)](#advanced-relational-database-schema-erd)
- [API Reference](#api-reference)
- [Core Scenario Implementations](#core-scenario-implementations)
  - [Scenario 1: Concurrent Issue Updates (Optimistic Concurrency Control)](#scenario-1-concurrent-issue-updates-optimistic-concurrency-control)
  - [Scenario 2: Sprint Completion Lifecycle](#scenario-2-sprint-completion-lifecycle)
  - [Scenario 3: Workflow State Guardrails](#scenario-3-workflow-state-guardrails)
- [High-Throughput Trade-Offs \& Optimizations](#high-throughput-trade-offs--optimizations)
  - [Custom Fields: JSONB vs EAV](#custom-fields-jsonb-vs-eav)
  - [Search: Native Full-Text Indexing vs Elasticsearch](#search-native-full-text-indexing-vs-elasticsearch)
  - [Pagination: Cursor-Based vs Offset](#pagination-cursor-based-vs-offset)
- [Real-Time Collaboration Infrastructure](#real-time-collaboration-infrastructure)
- [Production Scale Blueprint](#production-scale-blueprint)
- [Getting Started](#getting-started)
- [Deployment (Render)](#deployment-render)

---

## Executive Overview & System Architecture

This system implements a fully asynchronous request lifecycle engineered for high concurrency. The architecture follows a layered separation of concerns:

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Client Layer                                │
│          (Browser / Mobile / API Consumer / WebSocket)               │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                       HTTP / WebSocket
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                     ASGI Server (Uvicorn)                            │
│            Single-process event loop, zero thread-blocking          │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                      FastAPI Application                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────────┐   │
│  │ Routers  │→ │ Services │→ │  Models  │→ │  SQLAlchemy Async │   │
│  │ (HTTP)   │  │ (Logic)  │  │ (SQLModel)│  │  Engine + Pool    │   │
│  └──────────┘  └──────────┘  └──────────┘  └─────────┬─────────┘   │
│  ┌──────────────────────────────────────────┐         │             │
│  │ WebSocket Manager (Presence + Broadcast) │         │             │
│  └──────────────────────────────────────────┘         │             │
└───────────────────────────────────────────────────────┼─────────────┘
                                                        │
                                               asyncpg + SSL
                                                        │
┌───────────────────────────────────────────────────────▼─────────────┐
│                    Supabase PostgreSQL 17                            │
│      (Connection Pooler — Supavisor, Transaction Mode)              │
└─────────────────────────────────────────────────────────────────────┘
```

**Data lifecycle for a mutation:**

1. Client sends an HTTP request (e.g., `PATCH /api/issues/{id}`)
2. FastAPI router validates the payload via Pydantic schemas
3. Service layer executes business logic (optimistic lock check, workflow validation, hierarchy enforcement)
4. SQLAlchemy async engine commits the transaction atomically to PostgreSQL
5. An audit trail entry is written to `activity_logs`
6. The event is persisted to `event_log` with a monotonic `sequence_id`
7. The enriched event is broadcast to all WebSocket clients connected to that project's channel
8. Affected users receive in-app notifications (assignee changes, @mentions, status transitions)

Every database call is fully non-blocking via `asyncpg`, and the entire request pipeline runs inside a single Python event loop — no threads, no blocking I/O.

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Framework** | FastAPI 0.115+ | Async ASGI web framework with automatic OpenAPI docs |
| **Server** | Uvicorn | High-performance ASGI server with `uvloop` on Linux |
| **ORM** | SQLModel + SQLAlchemy 2.0 | Type-safe models with full async session support |
| **DB Driver** | asyncpg | Zero-copy PostgreSQL wire protocol, fully async |
| **Database** | Supabase PostgreSQL 17 | Managed Postgres with connection pooling (Supavisor) |
| **Migrations** | Alembic | Async-aware schema migrations |
| **Validation** | Pydantic v2 | Request/response serialization with `ConfigDict(from_attributes=True)` |
| **Real-time** | Native WebSockets | Per-project connection pools with presence tracking |
| **Settings** | pydantic-settings | Typed `.env` configuration with environment variable overlay |

---

## Advanced Relational Database Schema (ERD)

```mermaid
erDiagram
    USERS {
        uuid id PK
        varchar email UK
        varchar display_name
        timestamp created_at
    }

    PROJECTS {
        uuid id PK
        varchar name
        varchar key UK
        text description
        jsonb workflow_config
        int issue_counter
        timestamp created_at
    }

    SPRINTS {
        uuid id PK
        uuid project_id FK
        varchar name
        date start_date
        date end_date
        enum status
        int velocity
        timestamp created_at
    }

    ISSUES {
        uuid id PK
        varchar key UK
        uuid project_id FK
        uuid sprint_id FK
        enum type
        uuid parent_id FK
        varchar title
        text description
        enum status
        enum priority
        int story_points
        int version
        uuid assignee_id FK
        uuid reporter_id FK
        jsonb custom_fields
        timestamp created_at
        timestamp updated_at
    }

    COMMENTS {
        uuid id PK
        uuid issue_id FK
        uuid user_id FK
        text body
        uuid parent_id FK
        timestamp created_at
    }

    ACTIVITY_LOGS {
        uuid id PK
        uuid issue_id FK
        uuid user_id FK
        varchar action_type
        jsonb old_values
        jsonb new_values
        timestamp created_at
    }

    WATCHERS {
        uuid user_id PK_FK
        uuid issue_id PK_FK
        timestamp created_at
    }

    NOTIFICATIONS {
        uuid id PK
        uuid user_id FK
        text message
        bool is_read
        uuid triggered_by_issue_id FK
        timestamp created_at
    }

    EVENT_LOG {
        bigint id PK
        uuid project_id FK
        varchar event_type
        jsonb payload
        timestamp created_at
    }

    PROJECTS ||--o{ SPRINTS : "has"
    PROJECTS ||--o{ ISSUES : "contains"
    PROJECTS ||--o{ EVENT_LOG : "emits"
    SPRINTS ||--o{ ISSUES : "scopes"
    USERS ||--o{ ISSUES : "reports"
    USERS ||--o{ ISSUES : "is assigned"
    USERS ||--o{ COMMENTS : "authors"
    USERS ||--o{ ACTIVITY_LOGS : "triggers"
    USERS ||--o{ NOTIFICATIONS : "receives"
    USERS ||--o{ WATCHERS : "watches"
    ISSUES ||--o{ ISSUES : "parent → child (Epic → Story → Sub-task)"
    ISSUES ||--o{ COMMENTS : "has"
    ISSUES ||--o{ ACTIVITY_LOGS : "tracked by"
    ISSUES ||--o{ WATCHERS : "watched by"
    ISSUES ||--o{ NOTIFICATIONS : "triggers"
    COMMENTS ||--o{ COMMENTS : "threaded replies"
```

**Recursive Hierarchy Constraint:**
The `Issues` table has a self-referential `parent_id` foreign key. The service layer enforces a strict three-level hierarchy:

- **Epic** can only parent **Story** issues
- **Story** can only parent **Sub-task** issues
- **Sub-task**, **Task**, and **Bug** types cannot have children

This is enforced at the application layer (not via DB constraints) to provide rich, actionable error messages describing exactly which child types are permitted.

---

## API Reference

### Users
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/users` | List all provisioned users |
| `POST` | `/api/users` | Create a new user |

### Projects
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/projects` | List all projects |
| `GET` | `/api/projects/{id}` | Get project details (404 if not found) |
| `POST` | `/api/projects` | Create project with optional workflow config |

### Issues
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/projects/{project_id}/issues` | Search + cursor-paginated listing |
| `POST` | `/api/projects/{project_id}/issues` | Create issue (hierarchy validated) |
| `PATCH` | `/api/issues/{issue_id}` | Partial update (optimistic lock) |
| `POST` | `/api/issues/{issue_id}/transitions` | Workflow state transition |

### Sprints
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/projects/{project_id}/sprints` | Create sprint (status: future) |
| `POST` | `/api/sprints/{sprint_id}/start` | Activate sprint (one active per project) |
| `POST` | `/api/sprints/{sprint_id}/complete` | Atomic close + velocity calculation |

### Comments
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/issues/{issue_id}/comments` | List comments (chronological) |
| `POST` | `/api/issues/{issue_id}/comments` | Create comment (threaded, @mention aware) |

### Watchers & Notifications
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/issues/{issue_id}/watchers` | Subscribe to issue updates |
| `DELETE` | `/api/issues/{issue_id}/watchers/{user_id}` | Unsubscribe |
| `GET` | `/api/users/{user_id}/notifications` | Get user notifications |
| `PATCH` | `/api/notifications/{id}/read` | Mark notification as read |

### Board & WebSocket
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/projects/{project_id}/board` | Kanban board view (issues grouped by status) |
| `WS` | `/ws/projects/{project_id}?user_id=...` | Real-time events + presence |

### Health
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service health check |

---

## Core Scenario Implementations

### Scenario 1: Concurrent Issue Updates (Optimistic Concurrency Control)

When multiple users simultaneously edit the same issue, data corruption is prevented through **Optimistic Concurrency Control (OCC)** using a `version` integer column on the `issues` table.

**How it works:**

1. Every issue has a `version` field (default: `1`)
2. When a client fetches an issue, it receives the current `version`
3. To update, the client must send back the `version` it read:

```json
PATCH /api/issues/{id}
{
  "title": "Updated title",
  "version": 3
}
```

4. The service layer executes an **atomic conditional update**:

```sql
UPDATE issues
SET title = :title, version = version + 1, updated_at = :now
WHERE id = :id AND version = :provided_version
```

5. If `rowcount == 0`, another request modified the issue first. The server:
   - Fetches the current version from the database
   - Returns **HTTP 409 Conflict** with the body:

```json
{
  "detail": "Issue has been modified by another request. Current version is 4, you provided 3.",
  "current_version": 4,
  "provided_version": 3
}
```

6. The client must re-fetch, merge changes, and retry with the updated version

**Why OCC over pessimistic locking:** Row-level locks (`SELECT ... FOR UPDATE`) block concurrent readers and create contention under high load. OCC is lock-free during reads, only checking at write time — ideal for web applications where reads vastly outnumber writes and conflicts are rare.

---

### Scenario 2: Sprint Completion Lifecycle

Sprint completion is an **atomic multi-table transaction** that calculates velocity, redistributes incomplete work, and finalizes the sprint record — all within a single database commit boundary.

**Transaction flow:**

```
POST /api/sprints/{sprint_id}/complete
{
  "carry_over_issue_ids": ["uuid-1", "uuid-2"],
  "target_sprint_id": "uuid-future-sprint"
}
```

**Step 1 — Velocity Calculation:**
```sql
SELECT COALESCE(SUM(story_points), 0)
FROM issues
WHERE sprint_id = :sprint_id AND status = 'done'
```

**Step 2 — Identify Incomplete Issues:**
All issues in the sprint where `status != 'done'` are collected.

**Step 3a — Carry Over:**
Issues explicitly listed in `carry_over_issue_ids` are moved to `target_sprint_id`:
```sql
UPDATE issues SET sprint_id = :target_sprint_id WHERE id IN (:carry_ids)
```

**Step 3b — Backlog Cleanup:**
Remaining incomplete issues (not carried over) have their `sprint_id` set to `NULL`, returning them to the backlog:
```sql
UPDATE issues SET sprint_id = NULL WHERE id IN (:backlog_ids)
```

**Step 4 — Finalize Sprint:**
The sprint status is set to `completed` and the calculated velocity is persisted.

**All four steps execute within a single `await session.commit()`** — if any step fails, the entire transaction rolls back, leaving the sprint and all issues in their original state.

**Response:**
```json
{
  "sprint": { "id": "...", "status": "completed", "velocity": 34 },
  "velocity": 34,
  "carried_over": 2,
  "moved_to_backlog": 1
}
```

---

### Scenario 3: Workflow State Guardrails

Each project stores a configurable JSON-driven state machine in the `workflow_config` JSONB column. Every status transition request is validated against this configuration before execution.

**Default workflow configuration:**

```json
{
  "to_do": ["in_progress"],
  "in_progress": ["in_review"],
  "in_review": ["to_do", "done"],
  "done": ["in_progress"]
}
```

**Extended configuration with hooks:**

```json
{
  "to_do": ["in_progress"],
  "in_progress": ["in_review", "to_do"],
  "in_review": ["done", "in_progress"],
  "done": [],
  "on_enter": {
    "in_review": { "clear_fields": ["assignee_id"] }
  },
  "required_fields": {
    "in_review": ["story_points"],
    "done": ["story_points"]
  },
  "auto_actions": {
    "in_review": { "assignee_id": "<manager-uuid>" }
  }
}
```

**Validation pipeline (executed in order):**

1. **Transition Permission Gate** — The current status must list the target status as a permitted transition. If not, an HTTP 422 is returned:

```json
{
  "detail": "Transition from 'to_do' to 'done' is not permitted by the project workflow.",
  "current_status": "to_do",
  "requested_status": "done",
  "allowed_transitions": ["in_progress"]
}
```

2. **Required Fields Check** — If the target status has `required_fields` entries, each field is checked for non-null values. Missing fields trigger HTTP 422:

```json
{
  "detail": "Cannot transition to 'in_review': required fields are missing: ['story_points']",
  "missing_fields": ["story_points"],
  "target_status": "in_review"
}
```

3. **on_enter Side-Effects** — After validation passes, automatic mutations are applied:
   - `clear_fields`: Sets specified fields to `NULL` (e.g., unassign on review)
   - `set_fields`: Sets fields to explicit values

4. **auto_actions** — Automatic field assignments (e.g., auto-reassign to a reviewer)

5. **Audit + Notification** — A diff of old vs new values is persisted to `activity_logs`, and affected users receive notifications.

---

## High-Throughput Trade-Offs & Optimizations

### Custom Fields: JSONB vs EAV

**Decision:** Native PostgreSQL `JSONB` column on the `issues` table.

**Alternative considered:** Entity-Attribute-Value (EAV) pattern — a separate `custom_field_values` table with `(issue_id, field_name, field_value)` rows.

| Factor | JSONB | EAV |
|---|---|---|
| **Read performance** | Single-table scan, no JOINs | N JOINs per custom field, or pivot queries |
| **Write performance** | Atomic JSON merge | Multiple row inserts/updates |
| **Indexing** | GIN index on entire JSONB column | Composite index per field name |
| **Schema flexibility** | Arbitrary keys, no migrations | Arbitrary keys, no migrations |
| **Type enforcement** | Application-level only | Can enforce per-row types |
| **Query complexity** | `WHERE custom_fields->>'priority_flag' = 'true'` | `WHERE field_name = 'priority_flag' AND field_value = 'true'` with JOIN |
| **Client serialization** | Direct JSON — zero transformation | Requires pivot/reshape logic |

**Trade-off accepted:** We sacrifice strict relational type enforcement per custom field in exchange for massive reduction in JOIN complexity, faster single-table scans, and direct JSON serialization to API clients. At our scale (hundreds of custom fields per issue), EAV would require expensive pivot queries that degrade linearly with field count.

The `issues` table includes a **GIN index** on the `custom_fields` column:
```sql
CREATE INDEX ix_issues_custom_fields ON issues USING gin (custom_fields);
```

---

### Search: Native Full-Text Indexing vs Elasticsearch

**Decision:** PostgreSQL native `to_tsvector` / `websearch_to_tsquery` across issue titles, descriptions, and comment bodies.

**Alternative considered:** External Elasticsearch cluster with change-data-capture sync.

| Factor | PostgreSQL FTS | Elasticsearch |
|---|---|---|
| **Operational overhead** | Zero — same database | Separate cluster, monitoring, scaling |
| **Sync latency** | Zero — queries live data | CDC lag (seconds to minutes) |
| **Query capability** | English stemming, phrase search, ranking | Advanced analyzers, fuzzy matching, aggregations |
| **Infrastructure cost** | Included in existing DB | Additional compute + storage |
| **Consistency** | Strongly consistent | Eventually consistent |

**Implementation:**

Issue search combines two GIN-indexed text search vectors:

```sql
-- Issue title + description vector (GIN indexed)
to_tsvector('english', title || ' ' || COALESCE(description, ''))

-- Comment body vector (GIN indexed, correlated subquery)
EXISTS (
  SELECT 1 FROM comments
  WHERE issue_id = issues.id
  AND to_tsvector('english', body) @@ websearch_to_tsquery('english', :query)
)
```

**Trade-off accepted:** We forego Elasticsearch's advanced features (fuzzy matching, sophisticated relevance scoring, faceted aggregations) in favor of zero operational overhead, zero sync latency, and strong consistency. For a project management tool where users search by known terms, PostgreSQL FTS provides more than adequate quality.

---

### Pagination: Cursor-Based vs Offset

**Decision:** Base64-encoded cursor tokens anchored on `(created_at, id)` composite keys.

**Alternative considered:** Traditional `LIMIT/OFFSET` pagination.

| Factor | Cursor-Based | Offset |
|---|---|---|
| **Deep page performance** | O(1) — always seeks to exact row | O(n) — database skips `offset` rows |
| **Consistency** | Stable under concurrent inserts/deletes | Rows shift — duplicates or gaps possible |
| **Client complexity** | Must track opaque cursor token | Simple page number arithmetic |
| **Random access** | Not possible (sequential only) | Jump to any page |

**How it works:**

1. Results are ordered by `(created_at DESC, id DESC)`
2. After fetching `limit + 1` rows, if an extra row exists, the last row's `(created_at, id)` is encoded into a Base64 cursor token
3. The next request passes this cursor, and the query adds a keyset predicate:

```sql
WHERE (created_at < :cursor_ts)
   OR (created_at = :cursor_ts AND id < :cursor_id)
ORDER BY created_at DESC, id DESC
LIMIT :limit + 1
```

4. A composite index `ix_issues_project_created_id` on `(project_id, created_at, id)` ensures this query is an index-only scan regardless of how deep the pagination goes.

**Trade-off accepted:** We sacrifice random page access (jumping to page 50) in favor of consistent O(1) performance at any depth. For a project management API where users scroll through chronological feeds, sequential cursor pagination is the natural interaction model.

---

## Real-Time Collaboration Infrastructure

### WebSocket Architecture

Each project has a dedicated WebSocket channel at `/ws/projects/{project_id}?user_id={user_id}`.

**Connection lifecycle:**

1. **Connect** — Client opens WebSocket, server accepts and adds to the project's in-memory connection pool
2. **Presence Broadcast** — All connected clients immediately receive a `presence_updated` event with the current active user list
3. **Event Streaming** — Every mutation (issue created, updated, transitioned, comment added) is:
   - Persisted to `event_log` with an auto-incrementing `sequence_id`
   - Broadcast to all WebSocket connections in the project pool
4. **Reconnection Replay** — If a client reconnects with `?last_seq=N`, the server replays all events from `event_log` where `id > N`
5. **Disconnect** — Connection is removed from the pool, `presence_updated` is broadcast to remaining clients

**Event payload structure:**

```json
{
  "event": "issue.updated",
  "data": { "id": "...", "title": "...", "version": 4, ... },
  "timestamp": "2026-06-10T12:00:00Z",
  "sequence_id": 42
}
```

---

## Production Scale Blueprint

### WebSocket Scaling: Redis Pub/Sub

The current in-memory `ConnectionManager` works for a single server process. Under horizontal scaling (multiple server pods behind a load balancer), WebSocket connections are distributed across pods and an in-memory pool can't reach clients on other nodes.

**Solution:** Replace the in-memory dictionary with a **Redis Pub/Sub** backbone:

```
Pod A ──publish──▶ Redis Channel: project:{id} ◀──subscribe── Pod B
  │                                                              │
  ▼                                                              ▼
Local WS Pool A                                        Local WS Pool B
```

Each pod subscribes to Redis channels for its connected projects. When a mutation occurs on Pod A, the event is published to Redis, which fans it out to all subscribing pods. Each pod then broadcasts locally to its WebSocket connections.

### Database Scaling: Connection Pooling

The Supabase Supavisor connection pooler already provides transparent connection multiplexing in transaction mode. For extreme traffic spikes:

1. **Application-level pooling** — SQLAlchemy's `pool_size=20, max_overflow=10` creates a local pool of 30 connections, reusing them across thousands of concurrent requests
2. **Supavisor (server-side)** — Multiplexes hundreds of application connections onto a smaller set of PostgreSQL backend connections
3. **Read replicas** — Route read-heavy queries (search, board views, notification listings) to read replicas while writes target the primary

### Horizontal Pod Scaling

```
                    Load Balancer (sticky sessions for WS)
                   ╱           │           ╲
               Pod A        Pod B        Pod C
                 │            │            │
                 └────────────┼────────────┘
                              │
                         Redis Pub/Sub
                              │
                     Supabase PostgreSQL
                    (Primary + Read Replicas)
```

---

## Getting Started

### Prerequisites

- Python 3.12+
- A Supabase project (or local PostgreSQL instance)

### Installation

```bash
git clone https://github.com/ApurvX210/Jira_Backend.git
cd Jira_Backend
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root:

```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
POSTGRES_DB=postgres
POSTGRES_HOST=db.your-project.supabase.co
POSTGRES_PORT=5432
DATABASE_URL=postgresql+asyncpg://postgres:your_password@your-pooler-host:6543/postgres
ENVIRONMENT=development
```

### Database Setup

```bash
python -m alembic upgrade head
```

### Run the Server

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level info
```

### Seed Data (Optional)

```bash
python seed.py
```

### Run Tests

```bash
# In-process integration tests (no server needed)
python test_suite.py

# Live server tests (start server first)
python test_live.py
```

---

## Deployment (Render)

### Environment Variables

Set these on the Render dashboard:

| Key | Value |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://...@...pooler.supabase.com:6543/postgres` |
| `POSTGRES_HOST` | `aws-0-region.pooler.supabase.com` |
| `ENVIRONMENT` | `production` |

### Build & Start Commands

```yaml
buildCommand: pip install -r requirements.txt && alembic upgrade head
startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### Important Notes

- Use the Supabase **connection pooler** URL (port 6543), not the direct connection (port 5432), to avoid IPv6 compatibility issues
- Do **not** append `?sslmode=require` to the `DATABASE_URL` — SSL is handled programmatically via `connect_args`
- `statement_cache_size` is set to `0` for compatibility with Supavisor's transaction-mode pooling

---

## Project Structure

```
Jira_Backend/
├── alembic/                  # Database migration scripts
│   ├── env.py                # Async migration runner with SSL support
│   └── versions/             # Migration files
├── app/
│   ├── core/
│   │   ├── config.py         # Typed settings via pydantic-settings
│   │   ├── exceptions.py     # Structured error hierarchy (AppError subclasses)
│   │   └── websocket.py      # Connection pool, presence tracking, event replay
│   ├── db/
│   │   └── session.py        # Async engine factory with SSL + pooler support
│   ├── models/               # SQLModel table definitions
│   │   ├── user.py           # Users
│   │   ├── project.py        # Projects (workflow_config JSONB)
│   │   ├── sprint.py         # Sprints (lifecycle status machine)
│   │   ├── issue.py          # Issues (hierarchy, version, custom_fields JSONB)
│   │   ├── comment.py        # Comments (threaded, FTS indexed)
│   │   ├── activity_log.py   # Audit trail (old/new value diffs)
│   │   ├── event_log.py      # WebSocket replay log (sequence_id)
│   │   ├── notification.py   # In-app notifications
│   │   └── watcher.py        # Issue subscription junction table
│   ├── routers/              # FastAPI route handlers
│   ├── schemas/              # Pydantic request/response models
│   └── services/             # Business logic layer
│       ├── issue_service.py  # Create, update (OCC), transition
│       ├── sprint_service.py # Start, complete (velocity + carry-over)
│       ├── search_service.py # FTS + cursor pagination
│       ├── workflow_service.py # State machine validation engine
│       ├── comment_service.py  # Threaded comments + @mention parsing
│       ├── audit_service.py    # Field-level diff tracking
│       └── notification_service.py # Notification dispatch
├── seed.py                   # Production-grade data seeding script
├── test_suite.py             # In-process integration tests (ASGI transport)
├── test_live.py              # Live server integration + concurrency tests
├── requirements.txt          # Pinned dependencies
├── Procfile                  # PaaS start command
├── render.yaml               # Render infrastructure-as-code blueprint
└── alembic.ini               # Alembic configuration
```

---

## License

MIT
