from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from pydantic import BaseModel

from src.domain.planning.models import PathElement, TimeWindow, TrainPathPlan
from src.domain.planning.state import (
    AlternativePlan,
    GlobalPlan,
    PlanChange,
    PlanElement,
)
from src.domain.types import CrewId, RouteId, TrackId, TrainId
from src.services.conflict.models import Conflict
from src.services.conflict.service import ConflictService


class AffectedObject(BaseModel):
    object_type: str  # Train | Route | Track | Procedure | Crew | TimeWindow
    object_id: str
    old_value: dict | None = None
    new_value: dict | None = None


class ConflictResolutionResult(BaseModel):
    success: bool
    reconciled_changes: list[PlanChange] | None = None
    affected_objects: list[AffectedObject] | None = None
    unresolvable_conflicts: list[Conflict] | None = None
    iterations_used: int = 0
    timestamp: datetime

    model_config = {"arbitrary_types_allowed": True}


class ReplanningCoordinator:
    """Iteratively resolves conflicts in the global station plan.

    Loop: detect conflicts → analyse impact → request alternatives → re-check.
    Persists each invocation in an in-memory history repository.
    """

    def __init__(
        self,
        conflict_service: ConflictService | None = None,
        max_shift_minutes: int = 30,
        shift_step_minutes: int = 5,
    ) -> None:
        self._conflict_service = conflict_service or ConflictService()
        self._max_shift_minutes = max_shift_minutes
        self._shift_step_minutes = shift_step_minutes
        self._history: list[ConflictResolutionResult] = []

    def resolve(
        self,
        plan_element: PlanElement,
        global_plan: GlobalPlan,
        max_iterations: int = 10,
    ) -> ConflictResolutionResult:
        from src.planning.planners.replanning import (
            analyze_impact,
            request_alternatives,
        )

        now = datetime.now(timezone.utc)
        current_element = plan_element
        working_plan = global_plan.model_copy(deep=True)
        all_affected: list[AffectedObject] = []
        last_conflicts: list[Conflict] = []

        for iteration in range(1, max_iterations + 1):
            conflicts = self._conflict_service.detect_all_conflicts(
                current_element, working_plan
            )
            last_conflicts = conflicts

            if not conflicts:
                # Apply element to plan and succeed
                self._apply_element(working_plan, current_element)
                result = ConflictResolutionResult(
                    success=True,
                    reconciled_changes=[
                        PlanChange(
                            element_id=current_element.element_id,
                            element_type=current_element.element_type,
                            old_value=None,
                            new_value={"applied": True},
                            changed_at=now,
                            reason="Conflict-free after replanning",
                        )
                    ],
                    affected_objects=all_affected or None,
                    unresolvable_conflicts=None,
                    iterations_used=iteration,
                    timestamp=now,
                )
                # Sync caller's plan
                global_plan.plan_elements = working_plan.plan_elements
                global_plan.train_path_plans = working_plan.train_path_plans
                global_plan.last_updated = now
                self._history.append(result)
                return result

            affected = analyze_impact(conflicts)
            all_affected.extend(affected)

            alternatives = request_alternatives(
                affected=affected,
                plan_element=current_element,
                global_plan=working_plan,
                conflicts=conflicts,
                max_shift_minutes=self._max_shift_minutes,
                shift_step_minutes=self._shift_step_minutes,
            )

            resolved = False
            for alt in alternatives:
                candidate = self._apply_alternative(current_element, alt)
                trial_conflicts = self._conflict_service.detect_all_conflicts(
                    candidate, working_plan
                )
                if not trial_conflicts:
                    current_element = candidate
                    resolved = True
                    break

            if not resolved:
                # Try shifting the element's own time window as last resort
                shifted = self._shift_element(current_element, iteration)
                if shifted is None:
                    result = ConflictResolutionResult(
                        success=False,
                        reconciled_changes=None,
                        affected_objects=all_affected or None,
                        unresolvable_conflicts=last_conflicts,
                        iterations_used=iteration,
                        timestamp=now,
                    )
                    self._history.append(result)
                    return result
                current_element = shifted

        result = ConflictResolutionResult(
            success=False,
            reconciled_changes=None,
            affected_objects=all_affected or None,
            unresolvable_conflicts=last_conflicts,
            iterations_used=max_iterations,
            timestamp=now,
        )
        self._history.append(result)
        return result

    def get_history(self) -> list[ConflictResolutionResult]:
        """Return resolution history newest-first."""
        return sorted(self._history, key=lambda r: r.timestamp, reverse=True)

    @staticmethod
    def _apply_element(plan: GlobalPlan, element: PlanElement) -> None:
        # Replace existing element with same id if present
        plan.plan_elements = [
            e for e in plan.plan_elements if e.element_id != element.element_id
        ]
        plan.plan_elements.append(element)
        if element.path_plan is not None and element.train_id is not None:
            plan.train_path_plans[element.train_id] = element.path_plan
        plan.last_updated = datetime.now(timezone.utc)

    @staticmethod
    def _apply_alternative(
        element: PlanElement, alternative: AlternativePlan
    ) -> PlanElement:
        """Produce a new PlanElement reflecting the alternative's proposed changes."""
        updated = element.model_copy(deep=True)
        for change in alternative.proposed_changes:
            if change.new_value is None:
                continue
            if "time_window" in change.new_value and updated.time_window is not None:
                tw = change.new_value["time_window"]
                updated.time_window = TimeWindow(
                    start=datetime.fromisoformat(tw["start"])
                    if isinstance(tw["start"], str)
                    else tw["start"],
                    end=datetime.fromisoformat(tw["end"])
                    if isinstance(tw["end"], str)
                    else tw["end"],
                )
            if "path_plan" in change.new_value and updated.path_plan is not None:
                shift_minutes = change.new_value["path_plan"].get("shift_minutes", 0)
                updated.path_plan = _shift_path_plan(
                    updated.path_plan, timedelta(minutes=shift_minutes)
                )
                updated.time_window = (
                    TimeWindow(
                        start=updated.path_plan.path_elements[0].enter_time,
                        end=updated.path_plan.path_elements[-1].exit_time,
                    )
                    if updated.path_plan.path_elements
                    else updated.time_window
                )
        return updated

    def _shift_element(
        self, element: PlanElement, iteration: int
    ) -> PlanElement | None:
        shift = timedelta(minutes=self._shift_step_minutes * iteration)
        if shift.total_seconds() / 60 > self._max_shift_minutes:
            return None
        updated = element.model_copy(deep=True)
        if updated.time_window is not None:
            updated.time_window = TimeWindow(
                start=updated.time_window.start + shift,
                end=updated.time_window.end + shift,
            )
        if updated.path_plan is not None:
            updated.path_plan = _shift_path_plan(updated.path_plan, shift)
        return updated


def _shift_path_plan(plan: TrainPathPlan, shift: timedelta) -> TrainPathPlan:
    new_elements = [
        PathElement(
            element_id=e.element_id,
            sequence=e.sequence,
            enter_time=e.enter_time + shift,
            exit_time=e.exit_time + shift,
        )
        for e in plan.path_elements
    ]
    return TrainPathPlan(
        train_id=plan.train_id,
        path_elements=new_elements,
        created_at=plan.created_at,
    )
