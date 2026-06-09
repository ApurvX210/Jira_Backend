"""
WebSocket connection manager with presence tracking and event replay.

• Pools connections per project_id.
• Tracks active user_ids per project and broadcasts presence_updated on join/leave.
• Persists every broadcast to the event_log table with a monotonic sequence_id.
• Replays missed events to reconnecting clients.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from fastapi import WebSocket

from app.models.event_log import EventLog

log = logging.getLogger(__name__)

# ── Types ────────────────────────────────────────────────────────────────────

_Conn = tuple[str, WebSocket]  # (user_id, websocket)


class ConnectionManager:
    def __init__(self) -> None:
        self._pools: dict[str, list[_Conn]] = defaultdict(list)

    # ── connect / disconnect ─────────────────────────────────────────────

    async def connect(self, project_id: str, user_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._pools[project_id].append((user_id, ws))
        log.info("WS connect: project=%s user=%s pool=%d", project_id, user_id, len(self._pools[project_id]))
        await self._broadcast_presence(project_id)

    async def disconnect(self, project_id: str, user_id: str, ws: WebSocket) -> None:
        pool = self._pools.get(project_id)
        if pool:
            try:
                pool.remove((user_id, ws))
            except ValueError:
                pass
        log.info("WS disconnect: project=%s user=%s pool=%d", project_id, user_id, len(self._pools.get(project_id, [])))
        await self._broadcast_presence(project_id)

    # ── presence ─────────────────────────────────────────────────────────

    def get_active_users(self, project_id: str) -> list[str]:
        return list({uid for uid, _ in self._pools.get(project_id, [])})

    async def _broadcast_presence(self, project_id: str) -> None:
        payload = {
            "event": "presence_updated",
            "data": {"active_users": self.get_active_users(project_id)},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self._send_to_pool(project_id, payload)

    # ── broadcast ────────────────────────────────────────────────────────

    async def broadcast(self, project_id: str, payload: dict[str, Any]) -> None:
        await self._send_to_pool(project_id, payload)

    async def _send_to_pool(self, project_id: str, payload: dict[str, Any]) -> None:
        pool = self._pools.get(project_id, [])
        stale: list[_Conn] = []
        for conn in pool:
            try:
                await conn[1].send_json(payload)
            except Exception:
                stale.append(conn)
        for conn in stale:
            try:
                pool.remove(conn)
            except ValueError:
                pass

    # ── replay ───────────────────────────────────────────────────────────

    async def replay(self, ws: WebSocket, project_id: str, after_seq: int) -> None:
        """Stream missed events from the event_log table."""
        from app.db.session import async_session_factory

        try:
            async with async_session_factory() as session:
                rows = (
                    await session.execute(
                        sa.select(EventLog)
                        .where(
                            EventLog.project_id == uuid.UUID(project_id),
                            EventLog.id > after_seq,
                        )
                        .order_by(EventLog.id.asc())
                    )
                ).scalars().all()
                for ev in rows:
                    enriched = {**ev.payload, "sequence_id": ev.id}
                    await ws.send_json(enriched)
        except Exception:
            log.exception("event replay failed for project=%s after_seq=%s", project_id, after_seq)


manager = ConnectionManager()


# ── Public helper ────────────────────────────────────────────────────────────

async def broadcast_project_event(
    project_id: str | Any,
    event: str,
    data: dict[str, Any],
) -> None:
    """
    Persist the event to event_log (for replay), enrich with sequence_id,
    then broadcast to all connected clients. Never raises.
    """
    pid = str(project_id)
    payload: dict[str, Any] = {
        "event": event,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Persist to DB
    from app.db.session import async_session_factory

    try:
        async with async_session_factory() as session:
            entry = EventLog(
                project_id=uuid.UUID(pid),
                event_type=event,
                payload=payload,
            )
            session.add(entry)
            await session.commit()
            await session.refresh(entry)
            payload["sequence_id"] = entry.id
    except Exception:
        log.exception("Failed to persist event to event_log")

    # Broadcast to WebSocket pool
    try:
        await manager.broadcast(pid, payload)
    except Exception:
        log.exception("broadcast_project_event failed for project=%s", pid)
