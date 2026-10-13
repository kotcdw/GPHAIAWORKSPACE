"""Field-level validation errors raised by business rules (cross-field checks).

Rendered exactly like request-schema errors: HTTP 422 with
``{"detail": "...", "errors": [{"field": ..., "message": ...}]}``.
"""

from __future__ import annotations


class FieldValidationError(Exception):
    def __init__(self, errors: list[dict[str, str]]):
        super().__init__("; ".join(f"{e['field']}: {e['message']}" for e in errors))
        self.errors = errors


def field_error(field: str, message: str) -> FieldValidationError:
    return FieldValidationError([{"field": field, "message": message}])
