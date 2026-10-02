from __future__ import annotations

from enum import Enum


class CrewCapability(str, Enum):
    BRAKE_INSPECTION = "BrakeInspection"
    REFUELLING = "Refuelling"
    CLEANING = "Cleaning"
    CREW_CHANGE = "CrewChange"
    LOADING = "Loading"
    UNLOADING = "Unloading"
    TECHNICAL_INSPECTION = "TechnicalInspection"
    MAINTENANCE = "Maintenance"
    SAFETY_CHECK = "SafetyCheck"
    DRIVING = "Driving"


class EquipmentType(str, Enum):
    REFUELLING_UNIT = "RefuellingUnit"
    CLEANING_EQUIPMENT = "CleaningEquipment"
    INSPECTION_KIT = "InspectionKit"
    LOADING_CRANE = "LoadingCrane"
    MAINTENANCE_TOOLS = "MaintenanceTools"
    SAFETY_EQUIPMENT = "SafetyEquipment"


class CrewStatus(str, Enum):
    AVAILABLE = "Available"
    BUSY = "Busy"
    ON_REST = "OnRest"
    OFF_DUTY = "OffDuty"


class EquipmentStatus(str, Enum):
    AVAILABLE = "Available"
    IN_USE = "InUse"
    MAINTENANCE = "Maintenance"
    OUT_OF_SERVICE = "OutOfService"
