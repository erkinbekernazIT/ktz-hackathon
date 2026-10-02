from __future__ import annotations
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from src.agents.acceptance.decision import AcceptanceDecision
    from src.agents.service_planning.plan import MaintenancePlan


class DomainError(BaseModel):
    error_code: str
    entity_type: str
    entity_id: str | None = None
    description: str
    affected_fields: list[str] = []


class ValidationError(BaseModel):
    violations: list[dict]  # list[ConstraintViolation] — avoid circular import
    rejected_decision: dict | None = None  # AcceptanceDecision | MaintenancePlan
