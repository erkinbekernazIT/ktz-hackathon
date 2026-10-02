from __future__ import annotations

from datetime import datetime, timezone
from typing import Union

from src.domain.types import NodeId, RouteId, StationId, TrackId
from src.domain.station.models import Station, StationGraph, StationState
from src.domain.station.types import SwitchPosition, TrackOccupancy
from src.domain.planning.models import Route


class StationStateService:
    """Manages the dynamic state of a railway station."""

    def __init__(self) -> None:
        self._stations: dict[StationId, Station] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_station(self, station: Station) -> None:
        """Register a station in the service."""
        self._stations[station.id] = station

    def get_station(self, station_id: StationId) -> Station | None:
        return self._stations.get(station_id)

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    def get_current_state(self, station_id: StationId) -> StationState:
        station = self._stations.get(station_id)
        if station is None:
            raise KeyError(f"Station {station_id!r} not registered")
        return station.state

    def get_free_tracks(self, station_id: StationId) -> list[TrackId]:
        state = self.get_current_state(station_id)
        station = self._stations[station_id]
        all_track_ids = list(station.graph.tracks.keys())
        free = []
        for tid in all_track_ids:
            occupancy = state.track_occupancy.get(tid)
            if occupancy is None or not occupancy.is_occupied:
                if tid not in state.blocked_elements:
                    free.append(tid)
        return free

    def get_blocked_elements(
        self, station_id: StationId
    ) -> list[Union[TrackId, NodeId]]:
        state = self.get_current_state(station_id)
        return list(state.blocked_elements)

    # ------------------------------------------------------------------
    # Route reservation
    # ------------------------------------------------------------------

    def apply_route_reservation(self, route: Route) -> StationState:
        """Reserve all tracks in a route for the given train."""
        state = self._get_state_for_route(route)
        now = datetime.now(timezone.utc)
        for track_id in route.path:
            state.track_occupancy[track_id] = TrackOccupancy(
                track_id=track_id,
                is_occupied=True,
                occupying_train_id=route.train_id,
                occupied_since=now,
            )
        state.active_routes[route.id] = route
        state.timestamp = now
        # Update reserved_elements on the route object
        route.reserved_elements = set(route.path)
        return state

    def release_route_reservation(self, route_id: RouteId) -> StationState:
        """Release all track reservations held by a route."""
        now = datetime.now(timezone.utc)
        for station in self._stations.values():
            state = station.state
            if route_id in state.active_routes:
                route = state.active_routes.pop(route_id)
                for track_id in route.reserved_elements:
                    if track_id in state.track_occupancy:
                        state.track_occupancy[track_id] = TrackOccupancy(
                            track_id=track_id,
                            is_occupied=False,
                        )
                state.timestamp = now
                return state
        raise KeyError(f"Route {route_id!r} not found in any active routes")

    # ------------------------------------------------------------------
    # Switch management
    # ------------------------------------------------------------------

    def update_switch_position(
        self, node_id: NodeId, position: SwitchPosition
    ) -> None:
        for station in self._stations.values():
            if node_id in station.graph.nodes:
                station.state.switch_positions[node_id] = position
                station.state.timestamp = datetime.now(timezone.utc)
                return
        raise KeyError(f"Node {node_id!r} not found in any station graph")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_state_for_route(self, route: Route) -> StationState:
        """Find the station state that owns the route's tracks."""
        for station in self._stations.values():
            if any(tid in station.graph.tracks for tid in route.path):
                return station.state
        # Fallback: return first station state
        if self._stations:
            return next(iter(self._stations.values())).state
        raise RuntimeError("No stations registered in StationStateService")
