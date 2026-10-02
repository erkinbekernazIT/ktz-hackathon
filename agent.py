from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from src.agents.base import BaseAgent
from src.agents.service_planning.context import ServicePlanningContext
from src.agents.service_planning.plan import (
    MaintenancePlan,
    ProcedureAssignment,
    ProcedureAssignmentStatus,
)
from src.domain.planning.models import TimeWindow
from src.domain.types import CrewId, ProcedureId, TrackId
from src.infrastructure.llm.client import LLMClient, LLMError, create_llm_client

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a railway station maintenance planner (ServicePlanningAgent).
Assign required procedures to available crews using only the provided data.
Do NOT invent crew or procedure IDs.

Respond with a single JSON object only (no markdown), schema:
{
  "assignments": [
    {
      "procedure_id": "<id from required_procedures>",
      "assigned_crew_id": "<id or null>",
      "status": "Planned" | "Deferred" | "Unassignable",
      "start": "<ISO-8601 datetime or null>",
      "end": "<ISO-8601 datetime or null>",
      "reason": "<string or null>"
    }
  ],
  "notes": "<optional string>"
}

Rules:
- Planned: crew free now for the procedure duration
- Deferred: qualified crew exists but only free later — use their next free time as start
- Unassignable: no qualified crew at all — explain in reason
"""


class ServicePlanningAgent(BaseAgent):
    """Maintenance Planning Agent backed by Groq LLM (with deterministic fallback)."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        *,
        use_llm: bool = True,
    ) -> None:
        if llm_client is not None:
            self._llm = llm_client
        elif use_llm:
            self._llm = create_llm_client()
        else:
            self._llm = create_llm_client(use_stub=True)

    def evaluate(self, context: ServicePlanningContext) -> MaintenancePlan:  # type: ignore[override]
        return self.plan(context)

    def plan(self, context: ServicePlanningContext) -> MaintenancePlan:
        from src.infrastructure.llm.client import LLMClientStub

        if isinstance(self._llm, LLMClientStub):
            return self._stub_plan(context)

        try:
            return self._llm_plan(context)
        except (LLMError, ValueError, KeyError, json.JSONDecodeError) as exc:
            logger.error("ServicePlanningAgent LLM planning failed: %s — falling back to stub", exc)
            return self._stub_plan(context)

    def _llm_plan(self, context: ServicePlanningContext) -> MaintenancePlan:
        now = datetime.now(timezone.utc)
        prompt = self._build_prompt(context, now)
        raw = self._llm.complete(
            prompt,
            system=_SYSTEM_PROMPT,
            response_json=True,
            temperature=0.1,
        )
        data = json.loads(raw)
        return self._parse_plan(data, context, now)

    def _build_prompt(self, context: ServicePlanningContext, now: datetime) -> str:
        procedures = [
            {
                "procedure_id": str(p.id),
                "procedure_type": p.procedure_type.value,
                "duration_minutes": p.duration_minutes,
                "required_capabilities": list(p.required_capabilities),
            }
            for p in context.required_procedures
        ]
        crews = []
        for crew in context.available_crews:
            schedule = context.crew_schedules.get(crew.id)
            entries = []
            if schedule:
                for e in schedule.entries:
                    entries.append(
                        {
                            "start": e.start_time.isoformat(),
                            "end": e.end_time.isoformat(),
                            "entry_type": e.entry_type,
                        }
                    )
            crews.append(
                {
                    "crew_id": str(crew.id),
                    "qualifications": [q.value for q in crew.qualifications],
                    "capabilities": [c.value for c in crew.capabilities]
                    if crew.capabilities
                    else [],
                    "status": crew.status.value,
                    "schedule_entries": entries,
                }
            )

        payload = {
            "now": now.isoformat(),
            "train_id": str(context.train.train_id),
            "current_track_id": str(context.current_track_id),
            "required_procedures": procedures,
            "available_crews": crews,
            "infrastructure_constraints": context.infrastructure_constraints,
        }
        return (
            "Build a maintenance plan and return JSON per the schema.\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

    def _parse_plan(
        self, data: dict, context: ServicePlanningContext, now: datetime
    ) -> MaintenancePlan:
        known_procedures = {str(p.id): p for p in context.required_procedures}
        known_crews = {str(c.id) for c in context.available_crews}
        assignments: list[ProcedureAssignment] = []
        latest = now

        for item in data.get("assignments") or []:
            proc_id = str(item.get("procedure_id", ""))
            if proc_id not in known_procedures:
                continue

            status_raw = item.get("status", "Unassignable")
            try:
                status = ProcedureAssignmentStatus(status_raw)
            except ValueError:
                status = ProcedureAssignmentStatus.UNASSIGNABLE

            crew_id_raw = item.get("assigned_crew_id")
            crew_id = None
            if crew_id_raw and str(crew_id_raw) in known_crews:
                crew_id = CrewId(str(crew_id_raw))

            tw = None
            expected = None
            start_s, end_s = item.get("start"), item.get("end")
            if start_s and end_s:
                start = datetime.fromisoformat(str(start_s).replace("Z", "+00:00"))
                end = datetime.fromisoformat(str(end_s).replace("Z", "+00:00"))
                tw = TimeWindow(start=start, end=end)
                expected = end
                if end > latest:
                    latest = end

            assignments.append(
                ProcedureAssignment(
                    procedure_id=ProcedureId(proc_id),
                    assigned_crew_id=crew_id,
                    time_window=tw,
                    required_track_id=context.current_track_id,
                    expected_completion=expected,
                    status=status,
                    reason=item.get("reason"),
                )
            )

        # Ensure every required procedure has an assignment
        covered = {str(a.procedure_id) for a in assignments}
        for proc in context.required_procedures:
            if str(proc.id) not in covered:
                assignments.append(
                    ProcedureAssignment(
                        procedure_id=proc.id,
                        status=ProcedureAssignmentStatus.UNASSIGNABLE,
                        reason="Missing from LLM response",
                        required_track_id=context.current_track_id,
                    )
                )

        return MaintenancePlan(
            train_id=context.train.train_id,
            procedure_assignments=assignments,
            expected_completion=latest,
            identified_conflicts=[],
            alternatives=[],
            created_at=now,
        )

    # ------------------------------------------------------------------
    # Deterministic stub (tests / offline / LLM failure fallback)
    # ------------------------------------------------------------------

    def _stub_plan(self, context: ServicePlanningContext) -> MaintenancePlan:
        now = datetime.now(timezone.utc)
        assignments: list[ProcedureAssignment] = []
        latest_completion = now

        for procedure in context.required_procedures:
            assignment = self._assign_procedure(procedure, context, now)
            assignments.append(assignment)
            if (
                assignment.expected_completion is not None
                and assignment.expected_completion > latest_completion
            ):
                latest_completion = assignment.expected_completion

        return MaintenancePlan(
            train_id=context.train.train_id,
            procedure_assignments=assignments,
            expected_completion=latest_completion,
            identified_conflicts=[],
            alternatives=[],
            created_at=now,
        )

    def _assign_procedure(
        self,
        procedure,
        context: ServicePlanningContext,
        now: datetime,
    ) -> ProcedureAssignment:
        duration = timedelta(minutes=procedure.duration_minutes)
        matching = [c for c in context.available_crews if self._crew_matches(c, procedure)]

        if not matching:
            return ProcedureAssignment(
                procedure_id=procedure.id,
                status=ProcedureAssignmentStatus.UNASSIGNABLE,
                reason=(
                    f"No crew with qualification for "
                    f"{procedure.procedure_type.value} [STUB]"
                ),
                required_track_id=context.current_track_id,
            )

        immediate = TimeWindow(start=now, end=now + duration)
        for crew in matching:
            schedule = context.crew_schedules.get(crew.id)
            if schedule is None or self._is_free(schedule, immediate):
                return ProcedureAssignment(
                    procedure_id=procedure.id,
                    assigned_crew_id=crew.id,
                    time_window=immediate,
                    required_track_id=context.current_track_id,
                    expected_completion=immediate.end,
                    status=ProcedureAssignmentStatus.PLANNED,
                    reason="Assigned by stub agent",
                )

        earliest_start: datetime | None = None
        deferred_crew_id = None
        for crew in matching:
            schedule = context.crew_schedules.get(crew.id)
            if schedule is None or not schedule.entries:
                earliest_start = now
                deferred_crew_id = crew.id
                break
            free_at = max(e.end_time for e in schedule.entries)
            if earliest_start is None or free_at < earliest_start:
                earliest_start = free_at
                deferred_crew_id = crew.id

        if earliest_start is not None and deferred_crew_id is not None:
            deferred = TimeWindow(start=earliest_start, end=earliest_start + duration)
            return ProcedureAssignment(
                procedure_id=procedure.id,
                assigned_crew_id=deferred_crew_id,
                time_window=deferred,
                required_track_id=context.current_track_id,
                expected_completion=deferred.end,
                status=ProcedureAssignmentStatus.DEFERRED,
                reason="Crew busy now; deferred to future availability [STUB]",
            )

        return ProcedureAssignment(
            procedure_id=procedure.id,
            status=ProcedureAssignmentStatus.UNASSIGNABLE,
            reason=(
                f"No crew with qualification for "
                f"{procedure.procedure_type.value} [STUB]"
            ),
            required_track_id=context.current_track_id,
        )

    @staticmethod
    def _crew_matches(crew, procedure) -> bool:
        needed: set[str] = set(procedure.required_capabilities or [])
        needed.add(procedure.procedure_type.value)
        crew_caps = {c.value for c in crew.qualifications}
        if crew.capabilities:
            crew_caps |= {c.value for c in crew.capabilities}
        return bool(needed & crew_caps)

    @staticmethod
    def _is_free(schedule, window: TimeWindow) -> bool:
        for entry in schedule.entries:
            entry_window = TimeWindow(start=entry.start_time, end=entry.end_time)
            if window.overlaps(entry_window):
                return False
        return True
