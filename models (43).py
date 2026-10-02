from __future__ import annotations

from datetime import datetime
from typing import Union

from pydantic import BaseModel

from src.domain.types import (
    CrewId,
    EquipmentId,
    NodeId,
    OperationId,
    ProcedureId,
    TrackId,
    TrainId,
)
from src.domain.operations.types import OperationStatus, ProcedureType


class Procedure(BaseModel):
    id: ProcedureId
    procedure_type: ProcedureType
    duration_minutes: int
    required_capabilities: list[str] = []  # list[CrewCapability] — avoid circular
    required_equipment: list[str] = []  # list[EquipmentType] — avoid circular
    required_location: str | None = None  # NodeType — avoid circular
    prerequisites: list[ProcedureId] = []
    crew_size: int = 1


class Operation(BaseModel):
    id: OperationId
    train_id: TrainId
    procedure_id: ProcedureId
    crew_id: CrewId
    equipment_id: EquipmentId | None = None
    location: Union[TrackId, NodeId]
    scheduled_start: datetime
    scheduled_end: datetime
    actual_start: datetime | None = None
    actual_end: datetime | None = None
    status: OperationStatus = OperationStatus.PLANNED
