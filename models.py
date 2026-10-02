"""
Smart Station — Pydantic data models
All core entities: trains, tracks, conflicts, AI plans, events, station state.
"""
from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import time


# ─────────────────────────────────────────
#  ENUMERATIONS
# ─────────────────────────────────────────

class TrainStatus(str, Enum):
    MOVING      = "В движении"
    ARRIVING    = "Прибытие"
    DEPARTING   = "Отправление"
    WAITING     = "Ожидание"
    STOPPED     = "Остановлен"
    DELAYED     = "Задержан"
    CONFLICT    = "Конфликт"

class TrackStatus(str, Enum):
    FREE        = "Свободен"
    OCCUPIED    = "Занят"
    CLOSED      = "Закрыт"
    CONFLICT    = "Конфликт"
    MAINTENANCE = "Техобслуживание"

class TrainType(str, Enum):
    PASSENGER   = "Пассажирский"
    FREIGHT     = "Грузовой"
    EXPRESS     = "Скоростной"
    LOCAL       = "Пригородный"
    TECHNICAL   = "Технический"

class ConflictType(str, Enum):
    TRACK_CLOSED     = "Путь закрыт"
    ROUTE_CONFLICT   = "Конфликт маршрутов"
    RESOURCE_LACK    = "Нехватка ресурса"
    EQUIPMENT_FAIL   = "Отказ оборудования"
    SCHEDULE_OVERLAP = "Пересечение расписания"
    DELAY_CASCADE    = "Каскадная задержка"

class EventType(str, Enum):
    INFO      = "info"
    WARNING   = "warning"
    CONFLICT  = "conflict"
    AI        = "ai"
    DISPATCH  = "dispatch"
    SYSTEM    = "system"

class Direction(str, Enum):
    ARRIVAL   = "Прибытие"
    DEPARTURE = "Отправление"
    TRANSIT   = "Транзит"


# ─────────────────────────────────────────
#  TRAIN
# ─────────────────────────────────────────

class Train(BaseModel):
    id:          str
    number:      str                    # "101А"
    type:        TrainType
    route:       str                    # "Алматы–Астана"
    direction:   Direction
    track_id:    Optional[int] = None   # current track 1-6, None = approaching
    next_stop:   str
    planned_arrival:  Optional[str] = None   # "14:30"
    expected_arrival: Optional[str] = None
    planned_departure: Optional[str] = None
    expected_departure: Optional[str] = None
    delay_min:   int   = 0              # minutes of delay
    speed_kmh:   float = 0.0
    status:      TrainStatus = TrainStatus.MOVING
    operation:   str   = ""             # current operation description
    # canvas position (0.0–1.0 relative to track lane)
    position_x:  float = 0.0
    passengers:  int   = 0
    platform:    Optional[int] = None

    class Config:
        use_enum_values = True


# ─────────────────────────────────────────
#  TRACK
# ─────────────────────────────────────────

class Track(BaseModel):
    id:          int                    # 1-6
    name:        str                    # "Путь №1"
    status:      TrackStatus = TrackStatus.FREE
    occupied_by: Optional[str] = None  # train id
    platform:    bool = False
    length_m:    int  = 800
    direction:   str  = "both"          # "in", "out", "both"

    class Config:
        use_enum_values = True


# ─────────────────────────────────────────
#  CONFLICT
# ─────────────────────────────────────────

class Conflict(BaseModel):
    id:            str
    type:          ConflictType
    severity:      str  = "high"        # "high", "medium", "low"
    track_id:      Optional[int] = None
    train_id:      Optional[str] = None
    description:   str
    detected_at:   float = Field(default_factory=time.time)
    resolved:      bool  = False
    resolved_at:   Optional[float] = None
    resolution:    Optional[str]   = None

    class Config:
        use_enum_values = True


# ─────────────────────────────────────────
#  AI PLAN OPTION
# ─────────────────────────────────────────

class PlanOption(BaseModel):
    index:           int
    title:           str
    description:     str
    target_train_id: Optional[str] = None
    target_track_id: Optional[int] = None
    action:          str           # "reroute" | "wait" | "reorder" | "delay"
    extra_delay_min: int   = 0
    efficiency_pct:  float = 90.0
    risk_level:      str   = "low"  # "low", "medium", "high"


class AIResponse(BaseModel):
    conflict_id:  str
    summary:      str
    options:      list[PlanOption]
    generated_at: float = Field(default_factory=time.time)
    model_used:   str   = "llama-3.3-70b-versatile"


# ─────────────────────────────────────────
#  EVENT LOG ENTRY
# ─────────────────────────────────────────

class EventEntry(BaseModel):
    id:        str
    ts:        float = Field(default_factory=time.time)
    type:      EventType
    message:   str
    detail:    Optional[str] = None
    train_id:  Optional[str] = None
    track_id:  Optional[int] = None

    class Config:
        use_enum_values = True


# ─────────────────────────────────────────
#  STATION SNAPSHOT  (full state at a moment)
# ─────────────────────────────────────────

class StationSnapshot(BaseModel):
    ts:              float
    trains:          list[Train]
    tracks:          list[Track]
    conflicts:       list[Conflict]
    events:          list[EventEntry]
    efficiency_pct:  float
    total_trains:    int
    occupied_tracks: int
    delayed_trains:  int
    active_conflicts: int


# ─────────────────────────────────────────
#  WEBSOCKET MESSAGES
# ─────────────────────────────────────────

class WSMessage(BaseModel):
    type:    str        # "state" | "conflict" | "ai_response" | "plan_applied" | "event"
    payload: dict


# ─────────────────────────────────────────
#  REST: apply plan request
# ─────────────────────────────────────────

class ApplyPlanRequest(BaseModel):
    conflict_id:  str
    option_index: int


# ─────────────────────────────────────────
#  REST: trigger event request
# ─────────────────────────────────────────

class TriggerEventRequest(BaseModel):
    event_type: str   # "close_track" | "delay_train" | "equip_fail" | "route_conflict" | "resource_lack"
    target_id:  Optional[str] = None   # train id or track id
