from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel

from src.domain.types import NodeId, TrackId, TrainId


class NodeType(str, Enum):
    SWITCH = "Switch"
    PLATFORM = "Platform"
    ENTRY = "Entry"
    EXIT = "Exit"
    JUNCTION = "Junction"


class TrackOccupancy(BaseModel):
    track_id: TrackId
    is_occupied: bool
    occupying_train_id: TrainId | None = None
    occupied_since: datetime | None = None


class SwitchPosition(BaseModel):
    node_id: NodeId
    position: Literal["normal", "reversed"]


class MaintenanceZone(BaseModel):
    zone_id: str
    name: str
    blocked_tracks: list[TrackId] = []
    blocked_nodes: list[NodeId] = []
    active_from: datetime | None = None
    active_until: datetime | None = None
    description: str = ""
