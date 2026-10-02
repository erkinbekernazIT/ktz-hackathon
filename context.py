from __future__ import annotations

from pydantic import BaseModel

from src.domain.operations.models import Procedure
from src.domain.planning.models import TimeWindow, TrainPathPlan
from src.domain.planning.schedule import ScheduleEntry
from src.domain.resources.models import Crew, CrewSchedule, Equipment
from src.domain.train.models import TrainState
from src.domain.train.views import TechnicalTrainView
from src.domain.types import CrewId, TrackId


class ServicePlanningContext(BaseModel):
    """Specialised context for ServicePlanningAgent."""

    train: TechnicalTrainView
    train_state: TrainState
    current_track_id: TrackId

    required_procedures: list[Procedure] = []
    recommended_procedures: list[Procedure] = []

    available_crews: list[Crew] = []
    crew_schedules: dict[CrewId, CrewSchedule] = {}
    available_equipment: list[Equipment] = []

    current_path_plan: TrainPathPlan
    schedule_entry: ScheduleEntry
    infrastructure_constraints: list[str] = []
    track_occupancy_forecast: dict[TrackId, list[TimeWindow]] = {}

    model_config = {"arbitrary_types_allowed": True}
