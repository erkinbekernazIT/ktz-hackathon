from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.domain.planning.models import TimeWindow
from src.domain.planning.state import AlternativePlan, GlobalPlan, PlanChange, PlanElement
from src.domain.types import CrewId, RouteId, TrackId, TrainId
from src.planning.coordinators.conflict_resolution import AffectedObject
from src.services.conflict.models import Conflict, ConflictType


def analyze_impact(conflicts: list[Conflict]) -> list[AffectedObject]:
    """Determine all objects affected by the given conflicts."""
    affected: list[AffectedObject] = []
    seen: set[tuple[str, str]] = set()

    def _add(object_type: str, object_id: str) -> None:
        key = (object_type, object_id)
        if key not in seen:
            seen.add(key)
            affected.append(
                AffectedObject(object_type=object_type, object_id=object_id)
            )

    for conflict in conflicts:
        for train_id in conflict.affected_trains:
            _add("Train", str(train_id))
        for route_id in conflict.affected_routes:
            _add("Route", str(route_id))
        for resource_id in conflict.affected_resources:
            _add("Crew", str(resource_id))
        for infra_id in conflict.affected_infrastructure:
            _add("Track", str(infra_id))
        for window in conflict.affected_time_intervals:
            _add(
                "TimeWindow",
                f"{window.start.isoformat()}..{window.end.isoformat()}",
            )

    return affected


def request_alternatives(
    affected: list[AffectedObject],
    plan_element: PlanElement,
    global_plan: GlobalPlan,
    conflicts: list[Conflict],
    max_shift_minutes: int = 30,
    shift_step_minutes: int = 5,
) -> list[AlternativePlan]:
    """Request alternative plan variants for affected objects.

    Deterministic strategies (no LLM):
    1. Time-shift the conflicting path / window by step increments
    2. Drop overlapping track segments where possible (metadata flag)
    """
    alternatives: list[AlternativePlan] = []
    now = datetime.now(timezone.utc)

    # Strategy 1: progressive time shifts
    for minutes in range(shift_step_minutes, max_shift_minutes + 1, shift_step_minutes):
        shift = timedelta(minutes=minutes)
        changes: list[PlanChange] = []

        if plan_element.time_window is not None:
            new_tw = TimeWindow(
                start=plan_element.time_window.start + shift,
                end=plan_element.time_window.end + shift,
            )
            changes.append(
                PlanChange(
                    element_id=plan_element.element_id,
                    element_type=plan_element.element_type,
                    old_value={
                        "start": plan_element.time_window.start.isoformat(),
                        "end": plan_element.time_window.end.isoformat(),
                    },
                    new_value={
                        "time_window": {
                            "start": new_tw.start,
                            "end": new_tw.end,
                        },
                        "path_plan": {"shift_minutes": minutes},
                    },
                    changed_at=now,
                    reason=f"Shift by {minutes} minutes to avoid conflict",
                )
            )

        if plan_element.path_plan is not None and not changes:
            changes.append(
                PlanChange(
                    element_id=plan_element.element_id,
                    element_type=plan_element.element_type,
                    old_value=None,
                    new_value={"path_plan": {"shift_minutes": minutes}},
                    changed_at=now,
                    reason=f"Shift path plan by {minutes} minutes",
                )
            )

        if changes:
            score = 1.0 - (minutes / max(max_shift_minutes, 1)) * 0.5
            # Penalise if many track-overlap conflicts remain conceptually
            track_conflicts = sum(
                1 for c in conflicts if c.conflict_type == ConflictType.TRACK_OVERLAP
            )
            score -= track_conflicts * 0.05

            alternatives.append(
                AlternativePlan(
                    plan_id=str(uuid4()),
                    affected_element=plan_element,
                    proposed_changes=changes,
                    feasibility_score=max(0.0, score),
                    description=f"Time-shift alternative (+{minutes} min)",
                )
            )

    # Strategy 2: for each affected train, propose shifting *their* path in global plan
    # (recorded as alternatives that the coordinator can try on the incoming element)
    for obj in affected:
        if obj.object_type != "Train":
            continue
        if plan_element.train_id and str(plan_element.train_id) == obj.object_id:
            continue  # already covered
        # Suggest delaying the incoming element further as courtesy to the other train
        if plan_element.time_window is not None:
            minutes = shift_step_minutes * 2
            shift = timedelta(minutes=minutes)
            new_tw = TimeWindow(
                start=plan_element.time_window.start + shift,
                end=plan_element.time_window.end + shift,
            )
            alternatives.append(
                AlternativePlan(
                    plan_id=str(uuid4()),
                    affected_element=plan_element,
                    proposed_changes=[
                        PlanChange(
                            element_id=plan_element.element_id,
                            element_type=plan_element.element_type,
                            old_value=None,
                            new_value={
                                "time_window": {
                                    "start": new_tw.start,
                                    "end": new_tw.end,
                                },
                                "path_plan": {"shift_minutes": minutes},
                            },
                            changed_at=now,
                            reason=(
                                f"Yield to train {obj.object_id} "
                                f"by shifting +{minutes} min"
                            ),
                        )
                    ],
                    feasibility_score=0.6,
                    description=f"Yield to conflicting train {obj.object_id}",
                )
            )

    # Sort best-first
    alternatives.sort(key=lambda a: a.feasibility_score, reverse=True)
    return alternatives
