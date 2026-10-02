from __future__ import annotations

from src.domain.types import TrainId
from src.domain.planning.models import TimeWindow, TrainPathPlan
from src.domain.planning.state import GlobalPlan, PlanElement
from src.domain.planning.schedule import StationArrivalDepartureSchedule
from src.domain.resources.models import CrewSchedule, CrewScheduleEntry
from src.services.conflict.models import (
    Conflict,
    ConflictSeverity,
    ConflictType,
    CrewConflict,
    ScheduleConflict,
    TrackConflict,
)


class ConflictService:
    """Detects conflicts between plan elements."""

    def detect_all_conflicts(
        self,
        plan_element: PlanElement,
        global_plan: GlobalPlan,
    ) -> list[Conflict]:
        """Detect all conflict types for a new plan element."""
        conflicts: list[Conflict] = []

        # Track conflicts from path plan
        if plan_element.path_plan is not None:
            existing = list(global_plan.train_path_plans.values())
            existing_without_this = [
                p for p in existing
                if p.train_id != plan_element.path_plan.train_id
            ]
            track_conflicts = self.detect_track_conflicts(
                plan_element.path_plan, existing_without_this
            )
            conflicts.extend(track_conflicts)

        return conflicts

    def detect_track_conflicts(
        self,
        new_path: TrainPathPlan,
        existing_paths: list[TrainPathPlan],
    ) -> list[TrackConflict]:
        """Detect overlapping track usage between new path and existing paths."""
        conflicts: list[TrackConflict] = []

        for existing in existing_paths:
            for new_elem in new_path.path_elements:
                for ex_elem in existing.path_elements:
                    if new_elem.element_id != ex_elem.element_id:
                        continue
                    new_window = TimeWindow(
                        start=new_elem.enter_time, end=new_elem.exit_time
                    )
                    ex_window = TimeWindow(
                        start=ex_elem.enter_time, end=ex_elem.exit_time
                    )
                    if new_window.overlaps(ex_window):
                        conflicts.append(
                            TrackConflict(
                                track_id=new_elem.element_id,
                                time_slot=new_window,
                                affected_trains=[
                                    new_path.train_id,
                                    existing.train_id,
                                ],
                                affected_infrastructure=[new_elem.element_id],
                                affected_time_intervals=[new_window],
                                violated_constraints=[
                                    f"Track {new_elem.element_id!r} double-booked"
                                ],
                                severity=ConflictSeverity.CRITICAL,
                                description=(
                                    f"Track {new_elem.element_id!r} used by "
                                    f"{new_path.train_id!r} and "
                                    f"{existing.train_id!r} in overlapping windows"
                                ),
                            )
                        )
        return conflicts

    def detect_crew_conflicts(
        self,
        new_assignment: CrewScheduleEntry,
        existing_schedule: CrewSchedule,
    ) -> list[CrewConflict]:
        """Detect overlapping crew schedule entries."""
        conflicts: list[CrewConflict] = []
        new_window = TimeWindow(
            start=new_assignment.start_time, end=new_assignment.end_time
        )
        for entry in existing_schedule.entries:
            if entry.operation_id == new_assignment.operation_id:
                continue
            entry_window = TimeWindow(start=entry.start_time, end=entry.end_time)
            if new_window.overlaps(entry_window):
                conflicts.append(
                    CrewConflict(
                        crew_id=existing_schedule.crew_id,
                        overlapping_window=new_window,
                        affected_resources=[existing_schedule.crew_id],
                        affected_time_intervals=[new_window],
                        violated_constraints=[
                            f"Crew {existing_schedule.crew_id!r} has schedule overlap"
                        ],
                        severity=ConflictSeverity.HIGH,
                        description=(
                            f"Crew {existing_schedule.crew_id!r} already has "
                            f"operation {entry.operation_id!r} overlapping with "
                            f"new operation {new_assignment.operation_id!r}"
                        ),
                    )
                )
        return conflicts

    def detect_schedule_conflicts(
        self,
        new_element: PlanElement,
        station_schedule: StationArrivalDepartureSchedule,
    ) -> list[ScheduleConflict]:
        """Detect schedule violations caused by a new plan element."""
        conflicts: list[ScheduleConflict] = []

        if new_element.time_window is None or new_element.train_id is None:
            return conflicts

        # Check if any train in station schedule has planned departure that
        # overlaps with the new element's time window
        for entry in station_schedule.entries:
            if entry.train_id == new_element.train_id:
                continue
            if entry.planned_departure and new_element.time_window:
                # Simple check: if the entry departure falls within the window
                if (
                    new_element.time_window.start
                    <= entry.planned_departure
                    <= new_element.time_window.end
                ):
                    conflicts.append(
                        ScheduleConflict(
                            train_id=new_element.train_id,
                            violation_description=(
                                f"New plan for train {new_element.train_id!r} conflicts "
                                f"with departure of train {entry.train_id!r}"
                            ),
                            affected_trains=[new_element.train_id, entry.train_id],
                            severity=ConflictSeverity.MEDIUM,
                            violated_constraints=["schedule_window_conflict"],
                        )
                    )

        return conflicts
