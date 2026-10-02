from __future__ import annotations

from datetime import datetime, timezone
from typing import Union

from pydantic import BaseModel

from src.domain.types import StationId, TimeSlotId, TrackId, TrainId
from src.domain.station.models import StationGraph
from src.domain.station.types import TrackOccupancy
from src.domain.planning.models import TimeWindow
from src.domain.planning.schedule import TimeSlot, TimeTableCell, TrackTimeTable
from src.domain.errors import DomainError


class OccupancyInterval(BaseModel):
    track_id: TrackId
    time_window: TimeWindow
    occupying_train_id: TrainId | None = None


class OccupancyService:
    """Manages track occupancy state and forecasts."""

    def __init__(self) -> None:
        # track_id -> TrackOccupancy
        self._occupancy: dict[TrackId, TrackOccupancy] = {}
        # track_id -> list of planned intervals (from TrainPathPlan entries)
        self._forecast: dict[TrackId, list[OccupancyInterval]] = {}
        self._station_graph: StationGraph | None = None

    def set_station_graph(self, graph: StationGraph) -> None:
        self._station_graph = graph
        # Initialise all tracks as free
        for tid in graph.tracks:
            if tid not in self._occupancy:
                self._occupancy[tid] = TrackOccupancy(
                    track_id=tid, is_occupied=False
                )

    def get_track_occupancy(self, track_id: TrackId) -> TrackOccupancy:
        return self._occupancy.get(
            track_id,
            TrackOccupancy(track_id=track_id, is_occupied=False),
        )

    def get_all_occupied_tracks(self, station_id: StationId) -> list[TrackOccupancy]:  # noqa: ARG002
        return [occ for occ in self._occupancy.values() if occ.is_occupied]

    def assign_train_to_track(self, train_id: TrainId, track_id: TrackId) -> None:
        """Assign a train to a track. Raises DomainError if already occupied."""
        current = self.get_track_occupancy(track_id)
        if current.is_occupied and current.occupying_train_id != train_id:
            raise DomainError(
                error_code="TRACK_ALREADY_OCCUPIED",
                entity_type="Track",
                entity_id=track_id,
                description=(
                    f"Track {track_id!r} is already occupied by "
                    f"train {current.occupying_train_id!r}"
                ),
            )
        self._occupancy[track_id] = TrackOccupancy(
            track_id=track_id,
            is_occupied=True,
            occupying_train_id=train_id,
            occupied_since=datetime.now(timezone.utc),
        )

    def vacate_track(self, track_id: TrackId) -> None:
        self._occupancy[track_id] = TrackOccupancy(
            track_id=track_id, is_occupied=False
        )

    def add_forecast_interval(self, interval: OccupancyInterval) -> None:
        """Register a planned occupancy interval (from TrainPathPlan)."""
        self._forecast.setdefault(interval.track_id, []).append(interval)

    def get_occupancy_forecast(
        self, track_id: TrackId, time_window: TimeWindow
    ) -> list[OccupancyInterval]:
        intervals = self._forecast.get(track_id, [])
        return [
            iv
            for iv in intervals
            if iv.time_window.overlaps(time_window)
        ]

    def get_track_time_table(self, station_id: StationId) -> TrackTimeTable:  # noqa: ARG002
        """Build a TrackTimeTable from current forecast intervals."""
        # Collect all unique time slots from forecast
        all_intervals: list[OccupancyInterval] = []
        for ivs in self._forecast.values():
            all_intervals.extend(ivs)

        # Build time slots (one per unique interval)
        time_slots: list[TimeSlot] = []
        seen_slots: set[tuple] = set()
        for iv in all_intervals:
            key = (iv.time_window.start, iv.time_window.end)
            if key not in seen_slots:
                seen_slots.add(key)
                time_slots.append(
                    TimeSlot(
                        id=TimeSlotId(f"{iv.time_window.start.isoformat()}_{iv.time_window.end.isoformat()}"),
                        start=iv.time_window.start,
                        end=iv.time_window.end,
                    )
                )

        cells: dict[tuple[TrackId, TimeSlotId], TimeTableCell] = {}
        for slot in time_slots:
            for track_id, ivs in self._forecast.items():
                matching = [
                    iv for iv in ivs
                    if iv.time_window.start == slot.start and iv.time_window.end == slot.end
                ]
                if matching:
                    train_indices = [
                        str(iv.occupying_train_id) for iv in matching if iv.occupying_train_id
                    ]
                    is_conflicted = len(train_indices) > 1
                    cells[(track_id, slot.id)] = TimeTableCell(
                        track_id=track_id,
                        time_slot_id=slot.id,
                        train_index=train_indices[0] if train_indices else None,
                        is_conflicted=is_conflicted,
                        conflicting_trains=train_indices if is_conflicted else [],
                    )

        return TrackTimeTable(
            station_id=station_id,
            time_slots=time_slots,
            cells=cells,
        )
