from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from src.domain.types import CrewId, OperationId, ProcedureId, StationId, TrainId
from src.domain.operations.models import Operation, Procedure
from src.domain.operations.types import OperationStatus, ProcedureType
from src.domain.resources.models import Crew
from src.domain.planning.models import TimeWindow
from src.domain.errors import DomainError
from src.services.routing.service import ConstraintViolation


class OperationService:
    """Creates and manages operations (concrete procedure executions)."""

    def __init__(self) -> None:
        self._operations: dict[OperationId, Operation] = {}
        self._procedures: dict[ProcedureId, Procedure] = {}
        self._crews: dict[CrewId, Crew] = {}
        self._trains: dict[TrainId, bool] = {}  # registered train ids

    def register_procedure(self, procedure: Procedure) -> None:
        self._procedures[procedure.id] = procedure

    def register_crew(self, crew: Crew) -> None:
        self._crews[crew.id] = crew

    def register_train_id(self, train_id: TrainId) -> None:
        self._trains[train_id] = True

    def create_operation(
        self,
        train_id: TrainId,
        procedure_id: ProcedureId,
        crew_id: CrewId,
        time_window: TimeWindow,
        location: str | None = None,
    ) -> Operation:
        # Validate train registered
        if train_id not in self._trains:
            raise DomainError(
                error_code="TRAIN_NOT_REGISTERED",
                entity_type="Train",
                entity_id=train_id,
                description=f"Train {train_id!r} is not registered",
            )
        # Validate crew registered
        if crew_id not in self._crews:
            raise DomainError(
                error_code="CREW_NOT_REGISTERED",
                entity_type="Crew",
                entity_id=crew_id,
                description=f"Crew {crew_id!r} is not registered",
            )
        # Validate crew qualification
        procedure = self._procedures.get(procedure_id)
        if procedure:
            crew = self._crews[crew_id]
            required_caps = set(procedure.required_capabilities)
            crew_caps = {cap.value for cap in crew.qualifications}
            missing = required_caps - crew_caps
            if missing:
                raise DomainError(
                    error_code="CREW_UNQUALIFIED",
                    entity_type="Crew",
                    entity_id=crew_id,
                    description=(
                        f"Crew {crew_id!r} lacks required capabilities: {missing}"
                    ),
                )

        op = Operation(
            id=OperationId(str(uuid4())),
            train_id=train_id,
            procedure_id=procedure_id,
            crew_id=crew_id,
            location=location or "unknown",
            scheduled_start=time_window.start,
            scheduled_end=time_window.end,
            status=OperationStatus.PLANNED,
        )
        self._operations[op.id] = op
        return op

    def start_operation(self, operation_id: OperationId) -> Operation:
        op = self._get_or_raise(operation_id)
        op.status = OperationStatus.IN_PROGRESS
        op.actual_start = datetime.now(timezone.utc)
        return op

    def complete_operation(self, operation_id: OperationId) -> Operation:
        op = self._get_or_raise(operation_id)
        op.status = OperationStatus.COMPLETED
        op.actual_end = datetime.now(timezone.utc)
        return op

    def get_active_operations(self, station_id: StationId) -> list[Operation]:  # noqa: ARG002
        return [
            op for op in self._operations.values()
            if op.status == OperationStatus.IN_PROGRESS
        ]

    def validate_operation(self, operation: Operation) -> list[ConstraintViolation]:
        violations: list[ConstraintViolation] = []
        if operation.train_id not in self._trains:
            violations.append(
                ConstraintViolation(
                    rule="train_registered",
                    affected_entity=operation.train_id,
                    description=f"Train {operation.train_id!r} not registered",
                )
            )
        if operation.crew_id not in self._crews:
            violations.append(
                ConstraintViolation(
                    rule="crew_registered",
                    affected_entity=operation.crew_id,
                    description=f"Crew {operation.crew_id!r} not registered",
                )
            )
        return violations

    def _get_or_raise(self, operation_id: OperationId) -> Operation:
        op = self._operations.get(operation_id)
        if op is None:
            raise KeyError(f"Operation {operation_id!r} not found")
        return op
