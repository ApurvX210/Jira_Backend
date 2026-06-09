"""
Reusable FastAPI dependencies.

get_current_user_id: reads the caller identity from the X-User-Id header.
Replace this with a proper auth dependency (JWT / Supabase auth) later.
"""

from __future__ import annotations

import uuid

from fastapi import Header


async def get_current_user_id(
    x_user_id: uuid.UUID = Header(..., description="Caller's user UUID"),
) -> uuid.UUID:
    return x_user_id
