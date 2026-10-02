from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from src.domain.types import OperationId, StationId, TrainId
from src.domain.train.models import TrainComposition, TrainType
from src.domain.train.restrictions import TrainRestriction


class AcceptanceTrainView(BaseModel):
    """For AcceptanceAgent: train characteristics for acceptance evaluation."""
    train_id: TrainId
    train_type: TrainType
    length_m: float
    weight_t: float
    priority: int
    restrictions: list[TrainRestriction] = []
    eta: datetime
    origin_station_id: StationId


class RoutingTrainView(BaseModel):
    """For RoutingService: physical parameters for path finding."""
    train_id: TrainId
    length_m: float
    weight_t: float
    train_type: TrainType
    restrictions: list[TrainRestriction] = []


class TechnicalTrainView(BaseModel):
    """For ServicePlanningAgent: technical state for maintenance planning."""
    train_id: TrainId
    train_type: TrainType
    composition: TrainComposition
    active_operations: list[OperationId] = []
    maintenance_history: list[OperationId] = []
