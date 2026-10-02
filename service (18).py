from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel

from src.domain.types import NodeId, RouteId, StationId, TrackId, TrainId
from src.domain.station.models import StationGraph, StationState
from src.domain.station.types import NodeType
from src.domain.train.views import RoutingTrainView
from src.domain.train.restrictions import RestrictionType
from src.domain.planning.models import (
    CandidateRoute,
    Route,
    RouteStatus,
    TimeWindow,
)
from src.infrastructure.graph.engine import GraphEngine


class ConstraintViolation(BaseModel):
    rule: str
    affected_entity: str
    description: str
    severity: Literal["Error", "Warning"] = "Error"


class RouteValidationResult(BaseModel):
    is_valid: bool
    violations: list[ConstraintViolation] = []


class RoutingService:
    """Finds and validates train routes through station topology."""

    def __init__(self) -> None:
        self._engine = GraphEngine()

    def find_candidate_routes(
        self,
        graph: StationGraph,
        state: StationState,
        train: RoutingTrainView,
        from_node: NodeId,
        to_node: NodeId,
        time_window: TimeWindow,
    ) -> list[CandidateRoute]:
        """Compute candidate routes from from_node to to_node for this train."""
        nx_graph = self._engine.build_from_station_graph(graph)

        # Collect occupied tracks to exclude
        occupied_tracks: set[TrackId] = {
            tid
            for tid, occ in state.track_occupancy.items()
            if occ.is_occupied
        }
        blocked: set[TrackId] = {
            e for e in state.blocked_elements if e in graph.tracks
        }
        exclude = occupied_tracks | blocked

        raw_paths = self._engine.find_paths(nx_graph, from_node, to_node, exclude)

        candidates: list[CandidateRoute] = []
        for path in raw_paths:
            violations = self._check_path_constraints(path, graph, train)
            if any(v.severity == "Error" for v in violations):
                continue  # skip infeasible paths

            receiving_track_id = path[-1] if path else TrackId("")
            route = Route(
                id=RouteId(str(uuid4())),
                train_id=train.train_id,
                path=path,
                reserved_elements=set(path),
                time_window=time_window,
                status=RouteStatus.PLANNED,
            )
            candidates.append(
                CandidateRoute(
                    route=route,
                    receiving_track_id=receiving_track_id,
                    time_window=time_window,
                    projected_consequences=[],
                    feasibility_score=1.0 - len(violations) * 0.1,
                )
            )

        return candidates

    def validate_route(
        self,
        route: Route,
        graph: StationGraph,
        state: StationState,
        train: RoutingTrainView,
    ) -> RouteValidationResult:
        """Full validation of a proposed route."""
        violations: list[ConstraintViolation] = []

        for track_id in route.path:
            # Track exists
            if track_id not in graph.tracks:
                violations.append(
                    ConstraintViolation(
                        rule="track_exists",
                        affected_entity=track_id,
                        description=f"Track {track_id!r} does not exist in StationGraph",
                    )
                )
                continue

            track = graph.tracks[track_id]
            # Physical constraints
            violations.extend(self.check_physical_constraints(track, train))

            # Track free
            occ = state.track_occupancy.get(track_id)
            if occ and occ.is_occupied and occ.occupying_train_id != route.train_id:
                violations.append(
                    ConstraintViolation(
                        rule="track_free",
                        affected_entity=track_id,
                        description=(
                            f"Track {track_id!r} is occupied by "
                            f"train {occ.occupying_train_id!r}"
                        ),
                    )
                )

            # Track not blocked
            if track_id in state.blocked_elements:
                violations.append(
                    ConstraintViolation(
                        rule="track_not_blocked",
                        affected_entity=track_id,
                        description=f"Track {track_id!r} is blocked",
                    )
                )

        return RouteValidationResult(
            is_valid=not any(v.severity == "Error" for v in violations),
            violations=violations,
        )

    def check_physical_constraints(
        self,
        track: "Track",  # type: ignore[name-defined]
        train: RoutingTrainView,
    ) -> list[ConstraintViolation]:
        """Check physical compatibility between a track and a train."""
        from src.domain.station.models import Track

        violations: list[ConstraintViolation] = []

        # Length check
        if track.length_m < train.length_m:
            violations.append(
                ConstraintViolation(
                    rule="track_length",
                    affected_entity=str(track.id),
                    description=(
                        f"Track length {track.length_m}m < train length {train.length_m}m"
                    ),
                )
            )

        # Weight check
        if track.max_weight_t < train.weight_t:
            violations.append(
                ConstraintViolation(
                    rule="track_weight",
                    affected_entity=str(track.id),
                    description=(
                        f"Track max weight {track.max_weight_t}t < train weight {train.weight_t}t"
                    ),
                )
            )

        # Train type allowed
        if track.allowed_train_types and train.train_type.value not in track.allowed_train_types:
            violations.append(
                ConstraintViolation(
                    rule="train_type_allowed",
                    affected_entity=str(track.id),
                    description=(
                        f"Train type {train.train_type.value!r} not in "
                        f"allowed types {track.allowed_train_types}"
                    ),
                    severity="Warning",
                )
            )

        return violations

    def _check_path_constraints(
        self,
        path: list[TrackId],
        graph: StationGraph,
        train: RoutingTrainView,
    ) -> list[ConstraintViolation]:
        violations: list[ConstraintViolation] = []
        for track_id in path:
            if track_id in graph.tracks:
                violations.extend(
                    self.check_physical_constraints(graph.tracks[track_id], train)
                )
        return violations
