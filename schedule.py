from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from src.domain.types import StationId, TimeSlotId, TrackId, TrainId


class ScheduleEntry(BaseModel):
    station_id: StationId
    planned_arrival: datetime | None = None
    planned_departure: datetime | None = None
    expected_arrival: datetime | None = None
    expected_departure: datetime | None = None
    last_updated: datetime


class ScheduleUpdate(BaseModel):
    field: str
    old_value: datetime | None = None
    new_value: datetime | None = None
    updated_at: datetime


class TrainSchedule(BaseModel):
    train_id: TrainId
    entries: list[ScheduleEntry] = []
    update_history: list[ScheduleUpdate] = []


class StationScheduleEntry(BaseModel):
    train_index: str
    train_id: TrainId
    planned_arrival: datetime | None = None
    planned_departure: datetime | None = None
    expected_arrival: datetime | None = None
    expected_departure: datetime | None = None


class StationArrivalDepartureSchedule(BaseModel):
    station_id: StationId
    entries: list[StationScheduleEntry] = []
    generated_at: datetime


class TimeSlot(BaseModel):
    id: TimeSlotId
    start: datetime
    end: datetime


class TimeTableCell(BaseModel):
    track_id: TrackId
    time_slot_id: TimeSlotId
    train_index: str | None = None  # None = free
    is_conflicted: bool = False
    conflicting_trains: list[str] = []


class TrackTimeTable(BaseModel):
    station_id: StationId
    time_slots: list[TimeSlot] = []
    cells: dict[tuple[TrackId, TimeSlotId], TimeTableCell] = {}

    model_config = {"arbitrary_types_allowed": True}
