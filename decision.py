from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from src.domain.types import DispatcherId, TrackId, TrainId
from src.domain.planning.models import CandidateRoute, Route, TimeWindow
from src.services.conflict.models import Conflict


class AcceptanceAction(str, Enum):
    ACCEPT = "Accept"
    ACCEPT_WITH_CONDITIONS = "AcceptWithConditions"
    DELAY = "Delay"
    REJECT = "Reject"
    NO_FEASIBLE_ROUTE = "NoFeasibleRoute"
    NEED_MORE_INFORMATION = "NeedMoreInformation"


class TrainImpact(BaseModel):
    train_id: TrainId
    impact_description: str
    delay_minutes: int = 0


class RequiredAction(BaseModel):
    action_type: str
    description: str
    target_entity: str = ""
    priority: int = 5


class AcceptanceDecision(BaseModel):
    """Structured result produced by AcceptanceAgent."""

    train_id: TrainId
    dispatcher_id: DispatcherId = DispatcherId("system")
    timestamp: datetime
    recommended_action: AcceptanceAction
    selected_route: Route | None = None
    receiving_track_id: TrackId | None = None
    time_window: TimeWindow | None = None
    reasoning: str
    identified_conflicts: list[Conflict] = []
    expected_impact: list[TrainImpact] = []
    alternatives: list[CandidateRoute] = []
    required_actions: list[RequiredAction] = []

    model_config = {"arbitrary_types_allowed": True}
