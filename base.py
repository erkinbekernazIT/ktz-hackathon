from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ConstraintViolation(BaseModel):
    rule: str
    affected_entity: str
    description: str
    severity: Literal["Error", "Warning"] = "Error"


class ValidationResult(BaseModel):
    is_valid: bool
    violations: list[ConstraintViolation] = []
