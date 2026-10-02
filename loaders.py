from __future__ import annotations

import json
from pathlib import Path

import yaml

from src.domain.station.models import Node, Position, StationGraph, Track
from src.domain.station.types import NodeType
from src.domain.types import NodeId, TrackId
from src.infrastructure.database.models import StationTopologyConfig


class TopologyLoader:
    """Loads StationGraph from JSON or YAML configuration files."""

    @staticmethod
    def load_from_file(path: str | Path) -> StationGraph:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Topology config not found: {path}")

        raw = path.read_text(encoding="utf-8")
        suffix = path.suffix.lower()

        if suffix in {".yaml", ".yml"}:
            data = yaml.safe_load(raw)
        elif suffix == ".json":
            data = json.loads(raw)
        else:
            # Try JSON first, then YAML
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = yaml.safe_load(raw)

        config = StationTopologyConfig.model_validate(data)
        return TopologyLoader._to_station_graph(config)

    @staticmethod
    def load_from_dict(data: dict) -> StationGraph:
        config = StationTopologyConfig.model_validate(data)
        return TopologyLoader._to_station_graph(config)

    @staticmethod
    def _to_station_graph(config: StationTopologyConfig) -> StationGraph:
        nodes: dict[NodeId, Node] = {}
        for nc in config.nodes:
            node_id = NodeId(nc.id)
            position = None
            if nc.position is not None:
                position = Position(x=nc.position.x, y=nc.position.y)
            nodes[node_id] = Node(
                id=node_id,
                node_type=nc.node_type
                if isinstance(nc.node_type, NodeType)
                else NodeType(nc.node_type),
                name=nc.name,
                position=position,
            )

        tracks: dict[TrackId, Track] = {}
        for tc in config.tracks:
            track_id = TrackId(tc.id)
            tracks[track_id] = Track(
                id=track_id,
                source_node_id=NodeId(tc.source_node_id),
                target_node_id=NodeId(tc.target_node_id),
                length_m=tc.length_m,
                max_weight_t=tc.max_weight_t,
                allowed_train_types=list(tc.allowed_train_types),
                is_bidirectional=tc.is_bidirectional,
            )

        return StationGraph(nodes=nodes, tracks=tracks)
