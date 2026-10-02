from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.agents.acceptance.context import AcceptanceDecisionContext
from src.domain.planning.models import TimeWindow
from src.domain.planning.schedule import ScheduleEntry
from src.domain.station.types import NodeType
from src.domain.train.models import Train, TrainState, TrainStatus
from src.domain.train.views import AcceptanceTrainView, RoutingTrainView
from src.domain.types import NodeId, StationId, TrainId
from src.services.occupancy.service import OccupancyService
from src.services.prediction.service import PredictionService
from src.services.resources.service import ResourceService
from src.services.routing.service import RoutingService
from src.services.schedule.service import ScheduleService
from src.services.station_state.service import StationStateService


class AcceptanceContextBuilder:
    """Assembles AcceptanceDecisionContext from global state via domain services.

    Does NOT call the agent — only gathers and pre-computes candidate routes.
    """

    def __init__(
        self,
        station_state_service: StationStateService,
        routing_service: RoutingService,
        occupancy_service: OccupancyService,
        schedule_service: ScheduleService,
        resource_service: ResourceService,
        prediction_service: PredictionService | None = None,
    ) -> None:
        self._station_state = station_state_service
        self._routing = routing_service
        self._occupancy = occupancy_service
        self._schedule = schedule_service
        self._resources = resource_service
        self._prediction = prediction_service or PredictionService()
        self._trains: dict[TrainId, Train] = {}
        self._train_states: dict[TrainId, TrainState] = {}

    def register_train(self, train: Train, state: TrainState | None = None) -> None:
        self._trains[train.id] = train
        if state is not None:
            self._train_states[train.id] = state
        elif train.id not in self._train_states:
            self._train_states[train.id] = TrainState(
                train_id=train.id,
                status=TrainStatus.APPROACHING,
                last_updated=datetime.now(timezone.utc),
            )

    def build(
        self,
        train_id: TrainId,
        station_id: StationId,
        from_node: NodeId | None = None,
        to_node: NodeId | None = None,
        time_window: TimeWindow | None = None,
    ) -> AcceptanceDecisionContext:
        train = self._trains.get(train_id)
        if train is None:
            raise KeyError(f"Train {train_id!r} is not registered in context builder")

        station = self._station_state.get_station(station_id)
        if station is None:
            raise KeyError(f"Station {station_id!r} is not registered")

        state = self._station_state.get_current_state(station_id)
        train_state = self._train_states.get(
            train_id,
            TrainState(
                train_id=train_id,
                status=TrainStatus.APPROACHING,
                last_updated=datetime.now(timezone.utc),
            ),
        )

        now = datetime.now(timezone.utc)
        try:
            train_schedule = self._schedule.get_train_schedule(train_id)
            schedule_entry = next(
                (e for e in train_schedule.entries if e.station_id == station_id),
                ScheduleEntry(station_id=station_id, last_updated=now),
            )
        except KeyError:
            schedule_entry = ScheduleEntry(station_id=station_id, last_updated=now)

        eta = (
            schedule_entry.expected_arrival
            or schedule_entry.planned_arrival
            or now + timedelta(minutes=15)
        )

        try:
            station_schedule = self._schedule.get_station_schedule(station_id)
        except KeyError:
            from src.domain.planning.schedule import StationArrivalDepartureSchedule

            station_schedule = StationArrivalDepartureSchedule(
                station_id=station_id,
                entries=[],
                generated_at=now,
            )

        nearby_arrivals, nearby_departures = self._nearby_schedule_entries(
            station_schedule, eta
        )

        free_tracks = self._station_state.get_free_tracks(station_id)
        occupied_tracks = self._occupancy.get_all_occupied_tracks(station_id)
        blocked = [str(e) for e in self._station_state.get_blocked_elements(station_id)]
        active_routes = list(state.active_routes.values())

        # Available crews in a default window around ETA
        default_window = time_window or TimeWindow(
            start=eta,
            end=eta + timedelta(hours=2),
        )
        available_crews = [
            crew
            for crew in self._resources.list_crews()
            if self._resources.check_crew_availability(crew.id, default_window)
        ]

        entry_node = from_node or self._pick_node(station.graph, NodeType.ENTRY)
        platform_node = to_node or self._pick_node(station.graph, NodeType.PLATFORM)

        routing_view = RoutingTrainView(
            train_id=train.id,
            length_m=train.length_m,
            weight_t=train.weight_t,
            train_type=train.train_type,
            restrictions=train.restrictions,
        )

        candidate_routes = []
        if entry_node is not None and platform_node is not None:
            candidate_routes = self._routing.find_candidate_routes(
                graph=station.graph,
                state=state,
                train=routing_view,
                from_node=entry_node,
                to_node=platform_node,
                time_window=default_window,
            )

        acceptance_view = AcceptanceTrainView(
            train_id=train.id,
            train_type=train.train_type,
            length_m=train.length_m,
            weight_t=train.weight_t,
            priority=train.priority,
            restrictions=train.restrictions,
            eta=eta,
            origin_station_id=train.origin_station_id,
        )

        return AcceptanceDecisionContext(
            train=acceptance_view,
            train_state=train_state,
            eta=eta,
            schedule_entry=schedule_entry,
            station_schedule=station_schedule,
            nearby_arrivals=nearby_arrivals,
            nearby_departures=nearby_departures,
            free_tracks=free_tracks,
            occupied_tracks=occupied_tracks,
            blocked_elements=blocked,
            active_routes=active_routes,
            maintenance_zones=list(state.maintenance_zones),
            available_crews=available_crews,
            candidate_routes=candidate_routes,
        )

    @staticmethod
    def _pick_node(graph, node_type: NodeType) -> NodeId | None:
        for node_id, node in graph.nodes.items():
            if node.node_type == node_type:
                return node_id
        return None

    @staticmethod
    def _nearby_schedule_entries(station_schedule, reference: datetime, window_minutes: int = 60):
        from src.domain.planning.schedule import ScheduleEntry as SE

        horizon = timedelta(minutes=window_minutes)
        arrivals: list[SE] = []
        departures: list[SE] = []
        for entry in station_schedule.entries:
            arr = entry.expected_arrival or entry.planned_arrival
            dep = entry.expected_departure or entry.planned_departure
            if arr is not None and abs(arr - reference) <= horizon:
                arrivals.append(
                    SE(
                        station_id=station_schedule.station_id,
                        planned_arrival=entry.planned_arrival,
                        expected_arrival=entry.expected_arrival,
                        planned_departure=entry.planned_departure,
                        expected_departure=entry.expected_departure,
                        last_updated=reference,
                    )
                )
            if dep is not None and abs(dep - reference) <= horizon:
                departures.append(
                    SE(
                        station_id=station_schedule.station_id,
                        planned_arrival=entry.planned_arrival,
                        expected_arrival=entry.expected_arrival,
                        planned_departure=entry.planned_departure,
                        expected_departure=entry.expected_departure,
                        last_updated=reference,
                    )
                )
        return arrivals, departures
