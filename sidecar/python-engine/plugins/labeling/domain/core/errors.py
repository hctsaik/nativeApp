from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AnnotationError(Exception):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
                "retryable": self.retryable,
            },
        }


class NotFoundError(AnnotationError):
    def __init__(self, resource: str, resource_id: str) -> None:
        super().__init__(
            code="NOT_FOUND",
            message=f"{resource} not found.",
            details={"resource": resource, "id": resource_id},
        )


class ConflictError(AnnotationError):
    def __init__(self, message: str, details: dict[str, Any]) -> None:
        super().__init__(code="CONFLICT", message=message, details=details)


class ValidationFailedError(AnnotationError):
    def __init__(self, issues: list[dict[str, Any]]) -> None:
        super().__init__(
            code="VALIDATION_ERROR",
            message="Validation failed.",
            details={"issues": issues},
        )
