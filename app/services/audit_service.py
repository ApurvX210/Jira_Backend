"""
Reusable audit-logging utility.

Every successful issue mutation (create, update, transition) passes through
`log_change` which writes a JSON-diff entry to the activity_logs table.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog


def _serialisable(value: Any) -> Any:
    """Convert non-JSON-native types so JSONB accepts them."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def compute_diff(
    old: dict[str, Any],
    new: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (old_values, new_values) containing only the keys that changed."""
    old_vals: dict[str, Any] = {}
    new_vals: dict[str, Any] = {}
    all_keys = set(old) | set(new)
    for k in all_keys:
        ov = _serialisable(old.get(k))
        nv = _serialisable(new.get(k))
        if ov != nv:
            old_vals[k] = ov
            new_vals[k] = nv
    return old_vals, new_vals


async def log_change(
    session: AsyncSession,
    *,
    issue_id: uuid.UUID,
    user_id: uuid.UUID,
    action_type: str,
    old_values: dict[str, Any] | None = None,
    new_values: dict[str, Any] | None = None,
) -> ActivityLog:
    entry = ActivityLog(
        issue_id=issue_id,
        user_id=user_id,
        action_type=action_type,
        old_values=old_values,
        new_values=new_values,
    )
    session.add(entry)
    return entry


def snapshot_fields(obj: Any, fields: list[str]) -> dict[str, Any]:
    """Capture a subset of an ORM object's attributes as a plain dict."""
    return {f: getattr(obj, f) for f in fields if hasattr(obj, f)}
