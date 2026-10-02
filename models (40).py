from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

from src.domain.types import (
    CarId,
    LocomotiveId,
    NodeId,
    OperationId,
    RouteId,
    StationId,
    TrackId,
    TrainId,
)
from src.domain.train.restrictions import TrainRestriction


class TrainType(str, Enum):
    PASSENGER = "Passenger"
    FREIGHT = "Freight"
    SERVICE = "Service"
    HIGH_SPEED = "HighSpeed"


class TrainStatus(str, Enum):
    APPROACHING = "Approaching"
    AT_STATION = "AtStation"
    IN_SERVICE = "InService"
    DEPARTING = "Departing"
    DEPARTED = "Departed"


class Locomotive(BaseModel):
    id: LocomotiveId
    series: str
    max_pull_weight_t: float


class Car(BaseModel):
    id: CarId
    name: str
    car_type: str
    length_m: float
    weight_t: float


class TrainComposition(BaseModel):
    train_id: TrainId
    locomotive: Locomotive
    cars: list[Car] = []

    @model_validator(mode="after")
    def car_ids_must_be_unique(self) -> "TrainComposition":
        car_ids = [car.id for car in self.cars]
        if len(car_ids) != len(set(car_ids)):
            seen = set()
            duplicates = []
            for cid in car_ids:
                if cid in seen:
                    duplicates.append(cid)
                seen.add(cid)
            raise ValueError(
                f"Duplicate Car IDs found in TrainComposition: {duplicates}"
            )
        return self


class Train(BaseModel):
    id: TrainId
    number: str
    train_index: str
    train_type: TrainType
    origin_station_id: StationId
    destination_station_id: StationId
    current_station_id: StationId | None = None
    current_track_id: TrackId | None = None
    next_station_id: StationId | None = None
    length_m: float
    weight_t: float
    car_count: int
    priority: int = 5  # 1 = highest
    restrictions: list[TrainRestriction] = []
    operating_day: date

    @field_validator("length_m")
    @classmethod
    def length_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Train length_m must be greater than 0")
        return v

    @field_validator("weight_t")
    @classmethod
    def weight_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Train weight_t must be greater than 0")
        return v

    @field_validator("car_count")
    @classmethod
    def car_count_must_be_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Train car_count must be >= 0")
        return v


class TrainState(BaseModel):
    train_id: TrainId
    status: TrainStatus
    current_location: TrackId | NodeId | None = None
    is_delayed: bool = False
    delay_minutes: int = 0
    active_operations: list[OperationId] = []
    last_updated: datetime


class MovementStep(BaseModel):
    sequence: int
    element_id: TrackId | NodeId
    element_type: Literal["Track", "Node"]
    enter_time: datetime
    exit_time: datetime


class TrainMovementPlan(BaseModel):
    train_id: TrainId
    steps: list[MovementStep] = []
    created_at: datetime
    valid_until: datetime
