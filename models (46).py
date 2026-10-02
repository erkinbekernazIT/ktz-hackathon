from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from src.domain.types import CrewId, EquipmentId, NodeId, OperationId
from src.domain.resources.types import (
    CrewCapability,
    CrewStatus,
    EquipmentStatus,
    EquipmentType,
)
from src.domain.planning.models import TimeWindow
from src.domain.operations.types import ProcedureType


class CrewAvailability(BaseModel):
    available_from: datetime
    available_until: datetime
    rest_periods: list[TimeWindow] = []


class Crew(BaseModel):
    id: CrewId
    crew_type: str
    members: list[str] = []  # list[CrewMemberId]
    qualifications: list[CrewCapability] = []
    capabilities: set[ProcedureType] = set()
    current_location: NodeId | None = None
    availability: CrewAvailability
    status: CrewStatus = CrewStatus.AVAILABLE
    assigned_operation_id: OperationId | None = None

    model_config = {"arbitrary_types_allowed": True}


class Equipment(BaseModel):
    id: EquipmentId
    equipment_type: EquipmentType
    location: NodeId | None = None
    status: EquipmentStatus = EquipmentStatus.AVAILABLE
    assigned_operation_id: OperationId | None = None


class CrewScheduleEntry(BaseModel):
    operation_id: OperationId
    start_time: datetime
    end_time: datetime
    entry_type: Literal["Operation", "Rest"] = "Operation"
    assigned_at: datetime


class CrewSchedule(BaseModel):
    crew_id: CrewId
    entries: list[CrewScheduleEntry] = []  # ordered by time
