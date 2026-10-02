from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from src.domain.planning.models import TimeWindow
from src.domain.types import CrewId, ProcedureId, TrackId, TrainId
from src.services.conflict.models import Conflict


class ProcedureAssignmentStatus(str, Enum):
    PLANNED = "Planned"
    DEFERRED = "Deferred"
    UNASSIGNABLE = "Unassignable"
    IN_PROGRESS = "InProgress"
    COMPLETED = "Completed"


class ProcedureAssignment(BaseModel):
    procedure_id: ProcedureId
    assigned_crew_id: CrewId | None = None
    time_window: TimeWindow | None = None
    required_track_id: TrackId | None = None
    expected_completion: datetime | None = None
    status: ProcedureAssignmentStatus
    reason: str | None = None


class MaintenancePlan(BaseModel):
    train_id: TrainId
    procedure_assignments: list[ProcedureAssignment] = []
    expected_completion: datetime
    identified_conflicts: list[Conflict] = []
    alternatives: list[ProcedureAssignment] = []
    created_at: datetime

    model_config = {"arbitrary_types_allowed": True}
