"""
Workflow validation state machine.

Reads a project's `workflow_config` JSONB and decides whether a given
status transition is legal.  Supports:

  • allowed transition lists
  • on_enter side-effects (clear_fields, set_fields)
  • required_fields — abort with 422 if any are null for the target status
  • auto_actions — automatic field mutations (e.g. reassign on review)

Expected workflow_config shape
──────────────────────────────
{
    "to_do": ["in_progress"],
    "in_progress": ["in_review", "to_do"],
    "in_review": ["done", "in_progress"],
    "done": [],
    "on_enter": {
        "in_review": {"clear_fields": ["assignee_id"]}
    },
    "required_fields": {
        "in_review": ["story_points"],
        "done": ["story_points"]
    },
    "auto_actions": {
        "in_review": {"assignee_id": "<manager-uuid>"}
    }
}
"""

from __future__ import annotations

from typing import Any

from app.core.exceptions import TransitionValidationError, WorkflowError


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


# ── Validation hooks ────────────────────────────────────────────────────────

def validate_required_fields(
    workflow_config: dict[str, Any],
    target_status: str,
    issue_snapshot: dict[str, Any],
) -> None:
    """
    Raise TransitionValidationError if any required fields for *target_status*
    are null / empty on the issue.
    """
    required: list[str] = workflow_config.get("required_fields", {}).get(target_status, [])
    if not required:
        return

    missing: list[str] = []
    for field in required:
        val = issue_snapshot.get(field)
        if val is None:
            missing.append(field)
        elif field == "custom_fields" and not val:
            missing.append(field)

    if missing:
        raise TransitionValidationError(missing_fields=missing, target_status=target_status)


# ── on_enter side-effects ───────────────────────────────────────────────────

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


# ── auto_actions ─────────────────────────────────────────────────────────────

def get_auto_actions(
    workflow_config: dict[str, Any],
    target_status: str,
) -> dict[str, Any]:
    """Return the auto-assignment dict for *target_status*, or {}."""
    return dict(workflow_config.get("auto_actions", {}).get(target_status, {}))


def apply_auto_actions(
    issue_updates: dict[str, Any],
    auto: dict[str, Any],
) -> dict[str, Any]:
    """
    Apply automatic field mutations (e.g. reassign to a manager).
    Returns a summary for the API response.
    """
    applied: dict[str, Any] = {}
    for field, value in auto.items():
        issue_updates[field] = value
        applied.setdefault("auto_set", {})[field] = value
    return applied
