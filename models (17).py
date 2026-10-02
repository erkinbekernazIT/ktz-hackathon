from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from src.domain.types import CrewId, EquipmentId, NodeId, RouteId, TrackId, TrainId
from src.domain.planning.models import TimeWindow


class ConflictType(str, Enum):
    TRACK_OVERLAP = "TrackOverlap"
    CREW_OVERLAP = "CrewOverlap"
    RESOURCE_CONTENTION = "ResourceContention"
    SCHEDULE_VIOLATION = "ScheduleViolation"


class ConflictSeverity(str, Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class Conflict(BaseModel):
    conflict_type: ConflictType
    affected_trains: list[TrainId] = []
    affected_routes: list[RouteId] = []
    affected_resources: list[str] = []  # CrewId | EquipmentId
    affected_infrastructure: list[str] = []  # TrackId | NodeId
    affected_time_intervals: list[TimeWindow] = []
    violated_constraints: list[str] = []
    severity: ConflictSeverity = ConflictSeverity.HIGH
    description: str = ""


class TrackConflict(Conflict):
    conflict_type: ConflictType = ConflictType.TRACK_OVERLAP
    track_id: TrackId
    time_slot: TimeWindow


class CrewConflict(Conflict):
    conflict_type: ConflictType = ConflictType.CREW_OVERLAP
    crew_id: CrewId
    overlapping_window: TimeWindow


class ScheduleConflict(Conflict):
    conflict_type: ConflictType = ConflictType.SCHEDULE_VIOLATION
    train_id: TrainId
    violation_description: str = ""
