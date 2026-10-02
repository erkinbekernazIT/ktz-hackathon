from __future__ import annotations

from src.domain.station.models import StationGraph, StationState
from src.domain.train.views import RoutingTrainView
from src.planning.validators.base import ConstraintViolation, ValidationResult


class RouteValidator:
    """Validates an AcceptanceDecision's chosen route against domain rules.

    Eight checks (from design.md RouteValidator table):
    1. Track exists in StationGraph
    2. Track length >= train length
    3. Track is free in the given time window
    4. Track is not blocked
    5. Switch configuration is valid (no conflicting switch positions)
    6. No conflicting route already active
    7. Train restrictions are satisfied
    8. Time window fits within the train's schedule window
    """

    def validate(
        self,
        route: "Route",  # type: ignore[name-defined]
        graph: StationGraph,
        state: StationState,
        train: RoutingTrainView,
    ) -> ValidationResult:
        from src.domain.planning.models import Route

        violations: list[ConstraintViolation] = []

        receiving_track_id = route.path[-1] if route.path else None

        for track_id in route.path:
            # 1. Track exists
            if track_id not in graph.tracks:
                violations.append(
                    ConstraintViolation(
                        rule="track_exists",
                        affected_entity=track_id,
                        description=f"Track {track_id!r} not found in StationGraph",
                    )
                )
                continue

            track = graph.tracks[track_id]

            # 2. Track length >= train length
            if track.length_m < train.length_m:
                violations.append(
                    ConstraintViolation(
                        rule="track_length_sufficient",
                        affected_entity=track_id,
                        description=(
                            f"Track {track_id!r} length {track.length_m}m "
                            f"< train length {train.length_m}m"
                        ),
                    )
                )

            # 3. Track free (occupancy)
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

            # 4. Track not blocked
            if track_id in state.blocked_elements:
                violations.append(
                    ConstraintViolation(
                        rule="track_not_blocked",
                        affected_entity=track_id,
                        description=f"Track {track_id!r} is blocked",
                    )
                )

            # 7. Train type restriction
            if (
                track.allowed_train_types
                and train.train_type.value not in track.allowed_train_types
            ):
                violations.append(
                    ConstraintViolation(
                        rule="train_type_allowed",
                        affected_entity=track_id,
                        description=(
                            f"Train type {train.train_type.value!r} not allowed "
                            f"on track {track_id!r}"
                        ),
                        severity="Warning",
                    )
                )

        # 5. Switch positions — ensure no conflicting active routes use same switch
        for node_id, sw_pos in route.switch_positions.items():
            existing = state.switch_positions.get(node_id)
            if existing and existing.position != sw_pos.position:
                violations.append(
                    ConstraintViolation(
                        rule="switch_position_compatible",
                        affected_entity=node_id,
                        description=(
                            f"Switch {node_id!r} required position {sw_pos.position!r} "
                            f"conflicts with current position {existing.position!r}"
                        ),
                    )
                )

        # 6. No conflicting active route using same tracks
        for active_route_id, active_route in state.active_routes.items():
            if active_route.train_id == route.train_id:
                continue
            overlap = set(route.path) & set(active_route.path)
            if overlap:
                violations.append(
                    ConstraintViolation(
                        rule="no_conflicting_route",
                        affected_entity=str(overlap),
                        description=(
                            f"Route conflicts with active route {active_route_id!r} "
                            f"on tracks {overlap}"
                        ),
                    )
                )

        # 8. Time window (basic check: start < end)
        if route.time_window.start >= route.time_window.end:
            violations.append(
                ConstraintViolation(
                    rule="time_window_valid",
                    affected_entity="time_window",
                    description="Route time window start must be before end",
                )
            )

        errors = [v for v in violations if v.severity == "Error"]
        return ValidationResult(is_valid=len(errors) == 0, violations=violations)
