from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from src.domain.types import NodeId, RouteId, StationId, TrackId, TrainId
from src.domain.station.types import SwitchPosition


class TimeWindow(BaseModel):
    start: datetime
    end: datetime

    def overlaps(self, other: "TimeWindow") -> bool:
        """Return True if this time window overlaps with another."""
        return self.start < other.end and self.end > other.start

    def duration_minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60


class RouteStatus(str, Enum):
    PLANNED = "Planned"
    ACTIVE = "Active"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"


class PathElement(BaseModel):
    element_id: TrackId
    sequence: int
    enter_time: datetime
    exit_time: datetime


class TrainPathPlan(BaseModel):
    train_id: TrainId
    path_elements: list[PathElement] = []
    created_at: datetime


class Route(BaseModel):
    id: RouteId
    train_id: TrainId
    path: list[TrackId] = []
    switch_positions: dict[NodeId, SwitchPosition] = {}
    reserved_elements: set[TrackId] = set()
    time_window: TimeWindow
    status: RouteStatus = RouteStatus.PLANNED

    model_config = {"arbitrary_types_allowed": True}


class CandidateRoute(BaseModel):
    route: Route
    receiving_track_id: TrackId
    time_window: TimeWindow
    potential_conflicts: list[dict] = []  # list[Conflict] — avoid circular
    projected_consequences: list[str] = []
    feasibility_score: float = 1.0
