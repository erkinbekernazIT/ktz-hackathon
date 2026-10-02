from __future__ import annotations

from datetime import datetime, timezone

from src.domain.types import CrewId, EquipmentId, NodeId, OperationId
from src.domain.resources.types import CrewCapability, EquipmentType
from src.domain.resources.models import Crew, CrewSchedule, CrewScheduleEntry, Equipment
from src.domain.planning.models import TimeWindow
from src.domain.errors import DomainError


class ResourceService:
    """Manages crew and equipment resources."""

    def __init__(self) -> None:
        self._crews: dict[CrewId, Crew] = {}
        self._crew_schedules: dict[CrewId, CrewSchedule] = {}
        self._equipment: dict[EquipmentId, Equipment] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_crew(self, crew: Crew) -> None:
        self._crews[crew.id] = crew
        if crew.id not in self._crew_schedules:
            self._crew_schedules[crew.id] = CrewSchedule(crew_id=crew.id)

    def register_equipment(self, equipment: Equipment) -> None:
        self._equipment[equipment.id] = equipment

    # ------------------------------------------------------------------
    # Crew queries
    # ------------------------------------------------------------------

    def find_available_crews(
        self,
        required_capability: CrewCapability,
        time_window: TimeWindow,
        location: NodeId | None = None,
    ) -> list[Crew]:
        result = []
        for crew in self._crews.values():
            if required_capability not in crew.qualifications:
                continue
            if not self.check_crew_availability(crew.id, time_window):
                continue
            if location is not None and crew.current_location is not None:
                if crew.current_location != location:
                    continue  # location filter (non-strict for now)
            result.append(crew)
        return result

    def get_crew_schedule(self, crew_id: CrewId) -> CrewSchedule:
        if crew_id not in self._crew_schedules:
            raise KeyError(f"No schedule for crew {crew_id!r}")
        return self._crew_schedules[crew_id]

    def assign_crew_to_operation(
        self,
        crew_id: CrewId,
        operation_id: OperationId,
        time_window: TimeWindow,
    ) -> CrewSchedule:
        """Assign crew to an operation. Raises DomainError on overlap."""
        if not self.check_crew_availability(crew_id, time_window):
            raise DomainError(
                error_code="CREW_SCHEDULE_OVERLAP",
                entity_type="Crew",
                entity_id=crew_id,
                description=(
                    f"Crew {crew_id!r} is not available during "
                    f"{time_window.start} – {time_window.end}"
                ),
            )
        schedule = self._crew_schedules[crew_id]
        schedule.entries.append(
            CrewScheduleEntry(
                operation_id=operation_id,
                start_time=time_window.start,
                end_time=time_window.end,
                entry_type="Operation",
                assigned_at=datetime.now(timezone.utc),
            )
        )
        # Sort by start time
        schedule.entries.sort(key=lambda e: e.start_time)
        # Update crew status
        crew = self._crews.get(crew_id)
        if crew:
            from src.domain.resources.types import CrewStatus
            crew.status = CrewStatus.BUSY
            crew.assigned_operation_id = operation_id
        return schedule

    def release_crew(self, crew_id: CrewId, operation_id: OperationId) -> None:
        schedule = self._crew_schedules.get(crew_id)
        if schedule:
            schedule.entries = [
                e for e in schedule.entries if e.operation_id != operation_id
            ]
        crew = self._crews.get(crew_id)
        if crew and crew.assigned_operation_id == operation_id:
            from src.domain.resources.types import CrewStatus
            crew.status = CrewStatus.AVAILABLE
            crew.assigned_operation_id = None

    def check_crew_availability(
        self, crew_id: CrewId, time_window: TimeWindow
    ) -> bool:
        if crew_id not in self._crew_schedules:
            return True
        schedule = self._crew_schedules[crew_id]
        for entry in schedule.entries:
            entry_window = TimeWindow(start=entry.start_time, end=entry.end_time)
            if time_window.overlaps(entry_window):
                return False
        return True

    # ------------------------------------------------------------------
    # Equipment queries
    # ------------------------------------------------------------------

    def find_available_equipment(
        self, equipment_type: EquipmentType, time_window: TimeWindow  # noqa: ARG002
    ) -> list[Equipment]:
        from src.domain.resources.types import EquipmentStatus
        return [
            eq
            for eq in self._equipment.values()
            if eq.equipment_type == equipment_type
            and eq.status == EquipmentStatus.AVAILABLE
        ]

    def list_crews(self) -> list[Crew]:
        return list(self._crews.values())

    def list_equipment(self) -> list[Equipment]:
        return list(self._equipment.values())
