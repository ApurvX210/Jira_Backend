"""
Workflow validation state machine.

Reads a project's `workflow_config` JSONB and decides whether a given
status transition is legal.  Optionally returns `on_enter` side-effects
(e.g. clearing a field when an issue enters a particular status).

Expected workflow_config shapes
────────────────────────────────
Minimal (just allowed transitions):
    {
        "to_do": ["in_progress"],
        "in_progress": ["in_review", "to_do"],
        "in_review": ["done", "in_progress"],
        "done": []
    }

With automatic on_enter actions:
    {
        "to_do": ["in_progress"],
        ...
        "on_enter": {
            "in_review": {"clear_fields": ["assignee_id"]},
            "done":      {"set_fields":   {"resolution": "completed"}}
        }
    }
"""

from __future__ import annotations

from typing import Any

from app.core.exceptions import WorkflowError


def validate_transition(
    workflow_config: dict[str, Any],
    current_status: str,
    new_status: str,
) -> None:
    """Raise WorkflowError if the transition is forbidden."""
    allowed = workflow_config.get(current_status)
    if allowed is None:
        raise WorkflowError(
            current_status=current_status,
            requested_status=new_status,
            allowed_transitions=[],
        )
    if new_status not in allowed:
        raise WorkflowError(
            current_status=current_status,
            requested_status=new_status,
            allowed_transitions=list(allowed),
        )


def get_on_enter_actions(
    workflow_config: dict[str, Any],
    target_status: str,
) -> dict[str, Any]:
    """Return the side-effect dict for entering *target_status*, or {}."""
    on_enter: dict[str, Any] = workflow_config.get("on_enter", {})
    return dict(on_enter.get(target_status, {}))


def apply_on_enter(
    issue_updates: dict[str, Any],
    actions: dict[str, Any],
) -> dict[str, Any]:
    """
    Mutate *issue_updates* according to the on_enter rule actions.

    Supported action keys
    ─────────────────────
    clear_fields : list[str]   — set each named field to None
    set_fields   : dict[str,v] — set each named field to v

    Returns a summary of what was applied (for the API response).
    """
    applied: dict[str, Any] = {}

    for field in actions.get("clear_fields", []):
        issue_updates[field] = None
        applied.setdefault("cleared", []).append(field)

    for field, value in actions.get("set_fields", {}).items():
        issue_updates[field] = value
        applied.setdefault("set", {})[field] = value

    return applied
