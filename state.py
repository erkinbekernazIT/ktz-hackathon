from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel

from src.domain.types import (
    CrewId,
    NodeId,
    RouteId,
    StationId,
    TrackId,
    TrainId,
)
from src.domain.planning.models import TimeWindow, TrainPathPlan


class DeviationType(str, Enum):
    DELAYED_ARRIVAL = "DelayedArrival"
    EARLY_ARRIVAL = "EarlyArrival"
    WRONG_TRACK = "WrongTrack"
    ROUTE_DEVIATION = "RouteDeviation"
    MISSED_DEPARTURE = "MissedDeparture"


class Deviation(BaseModel):
    train_id: TrainId
    deviation_type: DeviationType
    planned_value: str
    actual_value: str
    delta_minutes: int | None = None
    detected_at: datetime


class PlanElement(BaseModel):
    element_id: str
    element_type: Literal["Train", "Route", "Track", "Procedure", "Crew", "TimeWindow"]
    train_id: TrainId | None = None
    route_id: RouteId | None = None
    crew_id: CrewId | None = None
    time_window: TimeWindow | None = None
    path_plan: TrainPathPlan | None = None
    metadata: dict = {}


class PlanChange(BaseModel):
    element_id: str
    element_type: str
    old_value: dict | None = None
    new_value: dict | None = None
    changed_at: datetime
    reason: str = ""


class AlternativePlan(BaseModel):
    plan_id: str
    affected_element: PlanElement
    proposed_changes: list[PlanChange] = []
    feasibility_score: float = 1.0
    description: str = ""


class GlobalPlan(BaseModel):
    station_id: StationId
    plan_elements: list[PlanElement] = []
    train_path_plans: dict[TrainId, TrainPathPlan] = {}
    created_at: datetime
    last_updated: datetime
