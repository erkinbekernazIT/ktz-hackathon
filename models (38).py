from __future__ import annotations

from datetime import datetime
from typing import Union

from pydantic import BaseModel, field_validator

from src.domain.types import (
    CrewId,
    EquipmentId,
    NodeId,
    RouteId,
    StationId,
    TrackId,
)
from src.domain.station.types import (
    MaintenanceZone,
    NodeType,
    SwitchPosition,
    TrackOccupancy,
)

# Import TrainType lazily to avoid circular — define it here temporarily
# Actually TrainType is in domain/train/models — use a forward-compatible approach
from enum import Enum


class _TrainTypePlaceholder(str, Enum):
    PASSENGER = "Passenger"
    FREIGHT = "Freight"
    SERVICE = "Service"
    HIGH_SPEED = "HighSpeed"


class Position(BaseModel):
    x: float
    y: float


class Node(BaseModel):
    id: NodeId
    node_type: NodeType
    name: str
    position: Position | None = None


class Track(BaseModel):
    id: TrackId
    source_node_id: NodeId
    target_node_id: NodeId
    length_m: float
    max_weight_t: float
    allowed_train_types: list[str]  # Using str to avoid circular import with TrainType
    is_bidirectional: bool = False

    @field_validator("length_m")
    @classmethod
    def length_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Track length_m must be greater than 0")
        return v

    @field_validator("max_weight_t")
    @classmethod
    def weight_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Track max_weight_t must be greater than 0")
        return v


class StationGraph(BaseModel):
    nodes: dict[NodeId, Node] = {}
    tracks: dict[TrackId, Track] = {}

    @field_validator("tracks")
    @classmethod
    def tracks_reference_existing_nodes(
        cls, tracks: dict[TrackId, Track], info
    ) -> dict[TrackId, Track]:
        # Get nodes from the data dict if available
        nodes = {}
        if hasattr(info, "data") and info.data and "nodes" in info.data:
            nodes = info.data["nodes"]
        for track_id, track in tracks.items():
            if nodes and track.source_node_id not in nodes:
                raise ValueError(
                    f"Track {track_id} references non-existent source node {track.source_node_id}"
                )
            if nodes and track.target_node_id not in nodes:
                raise ValueError(
                    f"Track {track_id} references non-existent target node {track.target_node_id}"
                )
        return tracks


class StationState(BaseModel):
    station_id: StationId
    track_occupancy: dict[TrackId, TrackOccupancy] = {}
    switch_positions: dict[NodeId, SwitchPosition] = {}
    blocked_elements: set[Union[TrackId, NodeId]] = set()
    active_routes: dict[RouteId, "Route"] = {}  # type: ignore[name-defined]
    maintenance_zones: list[MaintenanceZone] = []
    timestamp: datetime

    model_config = {"arbitrary_types_allowed": True}


class Station(BaseModel):
    id: StationId
    name: str
    graph: StationGraph
    state: StationState
    crews: list[CrewId] = []
    equipment: list[EquipmentId] = []


# Avoid circular import — Route is defined in planning.models
# We use a forward reference string in StationState; resolve at runtime if needed
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.planning.models import Route

# Resolve forward refs for Pydantic
def _rebuild_station_models() -> None:
    from src.domain.planning.models import Route  # noqa: F401

    StationState.model_rebuild()
    Station.model_rebuild()


_rebuild_station_models()
