from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class RestrictionType(str, Enum):
    MAX_SPEED = "MaxSpeed"
    HAZMAT = "Hazmat"
    SPECIAL_HANDLING = "SpecialHandling"
    PLATFORM_REQUIRED = "PlatformRequired"
    NO_ELECTRIFIED_TRACK = "NoElectrifiedTrack"


class TrainRestriction(BaseModel):
    restriction_type: RestrictionType
    value: str | float | None = None
    description: str = ""
