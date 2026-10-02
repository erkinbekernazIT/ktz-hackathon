from __future__ import annotations

from pydantic import BaseModel, Field

from src.domain.station.types import NodeType
from src.domain.types import NodeId, StationId, TrackId


class PositionConfig(BaseModel):
    x: float
    y: float


class NodeConfig(BaseModel):
    id: str
    node_type: NodeType
    name: str
    position: PositionConfig | None = None


class TrackConfig(BaseModel):
    id: str
    source_node_id: str
    target_node_id: str
    length_m: float
    max_weight_t: float
    allowed_train_types: list[str] = Field(default_factory=list)
    is_bidirectional: bool = False


class StationTopologyConfig(BaseModel):
    """Pydantic schema for station topology configuration files."""

    station_id: str
    station_name: str
    nodes: list[NodeConfig]
    tracks: list[TrackConfig]
