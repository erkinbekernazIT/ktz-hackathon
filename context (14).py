from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from src.domain.types import NodeId, StationId, TrackId, TrainId
from src.domain.train.views import AcceptanceTrainView
from src.domain.train.models import TrainState
from src.domain.station.types import TrackOccupancy
from src.domain.planning.models import CandidateRoute, Route, TimeWindow
from src.domain.planning.schedule import ScheduleEntry, StationArrivalDepartureSchedule
from src.domain.resources.models import Crew
from src.domain.station.types import MaintenanceZone
from src.services.conflict.models import Conflict


class AcceptanceDecisionContext(BaseModel):
    """Specialised context for AcceptanceAgent — contains only what is needed."""

    # Train
    train: AcceptanceTrainView
    train_state: TrainState
    eta: datetime

    # Schedule & priorities
    schedule_entry: ScheduleEntry
    station_schedule: StationArrivalDepartureSchedule
    nearby_arrivals: list[ScheduleEntry] = []
    nearby_departures: list[ScheduleEntry] = []

    # Station state
    free_tracks: list[TrackId] = []
    occupied_tracks: list[TrackOccupancy] = []
    blocked_elements: list[str] = []  # TrackId | NodeId
    active_routes: list[Route] = []
    maintenance_zones: list[MaintenanceZone] = []

    # Resources
    available_crews: list[Crew] = []

    # Pre-calculated candidate routes from RoutingService
    candidate_routes: list[CandidateRoute] = []

    model_config = {"arbitrary_types_allowed": True}
