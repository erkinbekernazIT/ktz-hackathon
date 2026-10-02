from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from src.domain.station.models import Station, StationState
from src.domain.station.types import NodeType
from src.domain.types import StationId
from src.infrastructure.database.loaders import TopologyLoader
from src.infrastructure.database.models import StationTopologyConfig
from src.infrastructure.graph.engine import GraphEngine
from src.infrastructure.llm import LLMClient, create_llm_client
from src.services.conflict.service import ConflictService
from src.services.occupancy.service import OccupancyService
from src.services.operations.service import OperationService
from src.services.prediction.service import PredictionService
from src.services.resources.service import ResourceService
from src.services.routing.service import RoutingService
from src.services.schedule.service import ScheduleService
from src.services.station_state.service import StationStateService

logger = logging.getLogger(__name__)


class StartupSequence:
    """Bootstraps the railway station manager from a topology config file.

    Steps:
    1. Load topology (JSON/YAML)
    2. Validate Entry → Platform connectivity via GraphEngine
    3. If disconnected entries found → log and abort (return False)
    4. Otherwise initialise all domain services and return True
    """

    def __init__(self, *, llm_client: LLMClient | None = None) -> None:
        self.station_state_service = StationStateService()
        self.routing_service = RoutingService()
        self.occupancy_service = OccupancyService()
        self.schedule_service = ScheduleService()
        self.resource_service = ResourceService()
        self.operation_service = OperationService()
        self.prediction_service = PredictionService()
        self.conflict_service = ConflictService()
        self.graph_engine = GraphEngine()
        self.llm_client = llm_client if llm_client is not None else create_llm_client()

        self.station: Station | None = None
        self.station_id: StationId | None = None
        self.disconnected_nodes: list[str] = []
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def run(self, config_path: str) -> bool:
        """Load topology, validate connectivity, initialise services.

        Returns True on success, False if connectivity check fails.
        """
        path = Path(config_path)
        logger.info("Loading station topology from %s", path)

        # Load raw config for station metadata
        import json

        import yaml

        raw_text = path.read_text(encoding="utf-8")
        suffix = path.suffix.lower()
        if suffix in {".yaml", ".yml"}:
            raw_data = yaml.safe_load(raw_text)
        else:
            try:
                raw_data = json.loads(raw_text)
            except json.JSONDecodeError:
                raw_data = yaml.safe_load(raw_text)

        topo_config = StationTopologyConfig.model_validate(raw_data)
        graph = TopologyLoader.load_from_file(path)

        # Connectivity check
        nx_graph = self.graph_engine.build_from_station_graph(graph)
        entry_nodes = [
            nid
            for nid, node in graph.nodes.items()
            if node.node_type == NodeType.ENTRY
        ]
        platform_nodes = [
            nid
            for nid, node in graph.nodes.items()
            if node.node_type == NodeType.PLATFORM
        ]

        disconnected = self.graph_engine.check_connectivity(
            nx_graph, entry_nodes, platform_nodes
        )
        self.disconnected_nodes = [str(n) for n in disconnected]

        if disconnected:
            logger.error(
                "Startup aborted: Entry nodes without path to any Platform: %s",
                self.disconnected_nodes,
            )
            self._initialized = False
            return False

        # Build station aggregate
        station_id = StationId(topo_config.station_id)
        now = datetime.now(timezone.utc)
        station_state = StationState(
            station_id=station_id,
            track_occupancy={},
            switch_positions={},
            blocked_elements=set(),
            active_routes={},
            maintenance_zones=[],
            timestamp=now,
        )
        station = Station(
            id=station_id,
            name=topo_config.station_name,
            graph=graph,
            state=station_state,
        )

        # Initialise services
        self.station_state_service.register_station(station)
        self.occupancy_service.set_station_graph(graph)

        self.station = station
        self.station_id = station_id
        self._initialized = True

        logger.info(
            "Startup successful: station %r (%s) with %d nodes, %d tracks",
            station.name,
            station_id,
            len(graph.nodes),
            len(graph.tracks),
        )
        return True
