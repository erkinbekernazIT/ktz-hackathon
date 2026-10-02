from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.agents.service_planning.context import ServicePlanningContext
from src.domain.operations.models import Procedure
from src.domain.planning.models import TimeWindow, TrainPathPlan
from src.domain.planning.schedule import ScheduleEntry
from src.domain.train.models import Train, TrainComposition, TrainState, TrainStatus
from src.domain.train.views import TechnicalTrainView
from src.domain.types import StationId, TrackId, TrainId
from src.services.occupancy.service import OccupancyService
from src.services.resources.service import ResourceService
from src.services.schedule.service import ScheduleService
from src.services.station_state.service import StationStateService


class ServicePlanningContextBuilder:
    """Assembles ServicePlanningContext for ServicePlanningAgent."""

    def __init__(
        self,
        station_state_service: StationStateService,
        occupancy_service: OccupancyService,
        schedule_service: ScheduleService,
        resource_service: ResourceService,
    ) -> None:
        self._station_state = station_state_service
        self._occupancy = occupancy_service
        self._schedule = schedule_service
        self._resources = resource_service
        self._trains: dict[TrainId, Train] = {}
        self._compositions: dict[TrainId, TrainComposition] = {}
        self._train_states: dict[TrainId, TrainState] = {}
        self._path_plans: dict[TrainId, TrainPathPlan] = {}
        self._procedures: dict[TrainId, list[Procedure]] = {}
        self._recommended: dict[TrainId, list[Procedure]] = {}

    def register_train(
        self,
        train: Train,
        composition: TrainComposition,
        state: TrainState | None = None,
        path_plan: TrainPathPlan | None = None,
    ) -> None:
        self._trains[train.id] = train
        self._compositions[train.id] = composition
        self._train_states[train.id] = state or TrainState(
            train_id=train.id,
            status=TrainStatus.AT_STATION,
            last_updated=datetime.now(timezone.utc),
        )
        if path_plan is not None:
            self._path_plans[train.id] = path_plan

    def set_procedures(
        self,
        train_id: TrainId,
        required: list[Procedure],
        recommended: list[Procedure] | None = None,
    ) -> None:
        self._procedures[train_id] = required
        self._recommended[train_id] = recommended or []

    def set_path_plan(self, path_plan: TrainPathPlan) -> None:
        self._path_plans[path_plan.train_id] = path_plan

    def build(self, train_id: TrainId, station_id: StationId) -> ServicePlanningContext:
        train = self._trains.get(train_id)
        if train is None:
            raise KeyError(f"Train {train_id!r} is not registered in context builder")

        composition = self._compositions.get(train_id)
        if composition is None:
            raise KeyError(f"Composition for train {train_id!r} is not registered")

        train_state = self._train_states[train_id]
        now = datetime.now(timezone.utc)

        current_track_id = train.current_track_id
        if current_track_id is None:
            # Fall back to first occupied track by this train, else first free track
            occupied = self._occupancy.get_all_occupied_tracks(station_id)
            for occ in occupied:
                if occ.occupying_train_id == train_id:
                    current_track_id = occ.track_id
                    break
            if current_track_id is None:
                free = self._station_state.get_free_tracks(station_id)
                if not free:
                    raise ValueError(
                        f"Cannot determine current track for train {train_id!r}"
                    )
                current_track_id = free[0]

        try:
            train_schedule = self._schedule.get_train_schedule(train_id)
            schedule_entry = next(
                (e for e in train_schedule.entries if e.station_id == station_id),
                ScheduleEntry(station_id=station_id, last_updated=now),
            )
        except KeyError:
            schedule_entry = ScheduleEntry(station_id=station_id, last_updated=now)

        path_plan = self._path_plans.get(
            train_id,
            TrainPathPlan(train_id=train_id, path_elements=[], created_at=now),
        )

        # Collect crews + schedules
        available_crews = self._resources.list_crews()
        crew_schedules = {}
        for crew in available_crews:
            try:
                crew_schedules[crew.id] = self._resources.get_crew_schedule(crew.id)
            except KeyError:
                from src.domain.resources.models import CrewSchedule

                crew_schedules[crew.id] = CrewSchedule(crew_id=crew.id)

        available_equipment = self._resources.list_equipment()

        # Occupancy forecast for relevant tracks
        forecast_horizon = TimeWindow(start=now, end=now + timedelta(hours=4))
        track_ids = {current_track_id}
        for element in path_plan.path_elements:
            track_ids.add(element.element_id)

        track_occupancy_forecast: dict[TrackId, list] = {}
        for tid in track_ids:
            intervals = self._occupancy.get_occupancy_forecast(tid, forecast_horizon)
            track_occupancy_forecast[tid] = [iv.time_window for iv in intervals]

        state = self._station_state.get_current_state(station_id)
        infrastructure_constraints = [
            f"blocked:{e}" for e in state.blocked_elements
        ]

        technical_view = TechnicalTrainView(
            train_id=train.id,
            train_type=train.train_type,
            composition=composition,
            active_operations=list(train_state.active_operations),
            maintenance_history=[],
        )

        return ServicePlanningContext(
            train=technical_view,
            train_state=train_state,
            current_track_id=current_track_id,
            required_procedures=self._procedures.get(train_id, []),
            recommended_procedures=self._recommended.get(train_id, []),
            available_crews=available_crews,
            crew_schedules=crew_schedules,
            available_equipment=available_equipment,
            current_path_plan=path_plan,
            schedule_entry=schedule_entry,
            infrastructure_constraints=infrastructure_constraints,
            track_occupancy_forecast=track_occupancy_forecast,
        )
