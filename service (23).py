from __future__ import annotations

from datetime import datetime, timezone

from src.domain.types import CrewId, NodeId, OperationId, TrackId, TrainId
from src.domain.operations.models import Operation
from src.domain.resources.models import CrewSchedule
from src.domain.planning.models import TrainPathPlan


class PredictionService:
    """Predicts future availability of infrastructure and resources."""

    def __init__(self) -> None:
        self._operations: dict[OperationId, Operation] = {}
        self._crew_schedules: dict[CrewId, CrewSchedule] = {}
        self._path_plans: dict[TrainId, TrainPathPlan] = {}

    def register_operation(self, operation: Operation) -> None:
        self._operations[operation.id] = operation

    def register_crew_schedule(self, schedule: CrewSchedule) -> None:
        self._crew_schedules[schedule.crew_id] = schedule

    def register_path_plan(self, plan: TrainPathPlan) -> None:
        self._path_plans[plan.train_id] = plan

    def predict_track_free_time(self, track_id: TrackId) -> datetime | None:
        """Predict when a track will next be free based on path plans."""
        latest_exit: datetime | None = None
        for plan in self._path_plans.values():
            for element in plan.path_elements:
                if element.element_id == track_id:
                    if latest_exit is None or element.exit_time > latest_exit:
                        latest_exit = element.exit_time
        return latest_exit

    def predict_operation_completion(self, operation_id: OperationId) -> datetime:
        """Return the scheduled end time of an operation."""
        op = self._operations.get(operation_id)
        if op is None:
            raise KeyError(f"Operation {operation_id!r} not found")
        if op.actual_end is not None:
            return op.actual_end
        return op.scheduled_end

    def predict_crew_availability(self, crew_id: CrewId) -> datetime:
        """Return the earliest datetime when the crew will be free."""
        schedule = self._crew_schedules.get(crew_id)
        if schedule is None or not schedule.entries:
            return datetime.now(timezone.utc)
        latest_end = max(e.end_time for e in schedule.entries)
        return latest_end

    def estimate_arrival_delay(
        self,
        train_id: TrainId,  # noqa: ARG002
        current_position: NodeId,  # noqa: ARG002
    ) -> int:
        """Estimate arrival delay in minutes (stub — returns 0)."""
        # Real implementation would compute based on path plan progress
        return 0
