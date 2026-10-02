from __future__ import annotations

from enum import Enum


class ProcedureType(str, Enum):
    BRAKE_INSPECTION = "BrakeInspection"
    REFUELLING = "Refuelling"
    CLEANING = "Cleaning"
    CREW_CHANGE = "CrewChange"
    LOADING = "Loading"
    UNLOADING = "Unloading"
    TECHNICAL_INSPECTION = "TechnicalInspection"
    MAINTENANCE = "Maintenance"
    SAFETY_CHECK = "SafetyCheck"


class OperationStatus(str, Enum):
    PLANNED = "Planned"
    IN_PROGRESS = "InProgress"
    COMPLETED = "Completed"
    FAILED = "Failed"
