"""
Structured application exceptions.

Each exception carries enough context for the exception handlers in main.py
to build a rich JSON error body without leaking internals.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code: int = 400

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        super().__init__(message)

    def body(self) -> dict[str, Any]:
        return {"detail": self.message}


class NotFoundError(AppError):
    status_code = 404

    def __init__(self, entity: str, entity_id: Any) -> None:
        self.entity = entity
        self.entity_id = str(entity_id)
        super().__init__(f"{entity} '{self.entity_id}' not found")


class ConflictError(AppError):
    """Raised when optimistic locking detects a stale write."""

    status_code = 409

    def __init__(
        self,
        *,
        issue_id: Any,
        current_version: int,
        provided_version: int,
    ) -> None:
        self.current_version = current_version
        self.provided_version = provided_version
        super().__init__(
            f"Issue '{issue_id}' has been modified by another request. "
            f"Current version is {current_version}, you provided {provided_version}."
        )

    def body(self) -> dict[str, Any]:
        return {
            "detail": self.message,
            "current_version": self.current_version,
            "provided_version": self.provided_version,
        }


class WorkflowError(AppError):
    """Raised when a status transition violates the project workflow config."""

    status_code = 422

    def __init__(
        self,
        *,
        current_status: str,
        requested_status: str,
        allowed_transitions: list[str],
    ) -> None:
        self.current_status = current_status
        self.requested_status = requested_status
        self.allowed_transitions = allowed_transitions
        super().__init__(
            f"Transition from '{current_status}' to '{requested_status}' "
            f"is not permitted by the project workflow."
        )

    def body(self) -> dict[str, Any]:
        return {
            "detail": self.message,
            "current_status": self.current_status,
            "requested_status": self.requested_status,
            "allowed_transitions": self.allowed_transitions,
        }


class HierarchyError(AppError):
    """Raised when parent-child issue type constraints are violated."""

    status_code = 422

    def __init__(self, message: str) -> None:
        super().__init__(message)


class SprintError(AppError):
    """Raised for sprint lifecycle constraint violations."""

    status_code = 422

    def __init__(self, message: str) -> None:
        super().__init__(message)


class TransitionValidationError(AppError):
    """Raised when required fields are missing for the target status."""

    status_code = 422

    def __init__(self, *, missing_fields: list[str], target_status: str) -> None:
        self.missing_fields = missing_fields
        self.target_status = target_status
        super().__init__(
            f"Cannot transition to '{target_status}': "
            f"required fields are missing: {missing_fields}"
        )

    def body(self) -> dict[str, Any]:
        return {
            "detail": self.message,
            "missing_fields": self.missing_fields,
            "target_status": self.target_status,
        }
