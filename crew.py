from __future__ import annotations

from src.domain.resources.models import Crew
from src.domain.planning.models import TimeWindow
from src.domain.operations.models import Procedure
from src.planning.validators.base import ConstraintViolation, ValidationResult
from src.services.resources.service import ResourceService


class CrewValidator:
    """Validates crew assignments against domain rules.

    Five checks (from design.md CrewValidator table):
    1. Crew is registered in the system
    2. Crew has the required qualification
    3. Crew is available during the requested time window
    4. No overlap in Crew_Schedule
    5. Location is compatible (non-strict)
    """

    def __init__(self, resource_service: ResourceService) -> None:
        self._resource_service = resource_service

    def validate(
        self,
        crew: Crew,
        procedure: Procedure,
        time_window: TimeWindow,
    ) -> ValidationResult:
        violations: list[ConstraintViolation] = []

        # 1. Crew registered
        try:
            self._resource_service.get_crew_schedule(crew.id)
        except KeyError:
            violations.append(
                ConstraintViolation(
                    rule="crew_registered",
                    affected_entity=crew.id,
                    description=f"Crew {crew.id!r} is not registered",
                )
            )
            return ValidationResult(is_valid=False, violations=violations)

        # 2. Crew qualification
        required_caps = set(procedure.required_capabilities)
        crew_caps = {cap.value for cap in crew.qualifications}
        missing = required_caps - crew_caps
        if missing:
            violations.append(
                ConstraintViolation(
                    rule="crew_qualification",
                    affected_entity=crew.id,
                    description=(
                        f"Crew {crew.id!r} lacks required capabilities: {missing}"
                    ),
                )
            )

        # 3 & 4. Crew availability (checks schedule overlap)
        is_available = self._resource_service.check_crew_availability(
            crew.id, time_window
        )
        if not is_available:
            violations.append(
                ConstraintViolation(
                    rule="crew_available",
                    affected_entity=crew.id,
                    description=(
                        f"Crew {crew.id!r} is not available during "
                        f"{time_window.start} – {time_window.end}"
                    ),
                )
            )

        # 5. Location compatible (warning only — no strict location enforcement)
        if crew.current_location is not None:
            # Non-strict: just a warning if location is unusual
            pass  # Location compatibility check would go here

        errors = [v for v in violations if v.severity == "Error"]
        return ValidationResult(is_valid=len(errors) == 0, violations=violations)
