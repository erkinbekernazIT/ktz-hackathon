from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel

from src.domain.types import StationId, TrackId, TrainId
from src.domain.planning.models import TimeWindow
from src.domain.planning.schedule import (
    ScheduleEntry,
    ScheduleUpdate,
    StationArrivalDepartureSchedule,
    StationScheduleEntry,
    TrainSchedule,
)
from src.domain.train.models import Train


class DelayInfo(BaseModel):
    train_id: TrainId
    station_id: StationId
    delay_minutes: int
    planned_arrival: datetime
    expected_arrival: datetime


class ScheduleDiscrepancy(BaseModel):
    train_id: TrainId
    field: str
    train_schedule_value: datetime | None
    station_schedule_value: datetime | None
    difference_minutes: float


class ScheduleService:
    """Manages train schedules and station-level arrival/departure schedule."""

    def __init__(self) -> None:
        self._schedules: dict[TrainId, TrainSchedule] = {}
        self._station_schedules: dict[StationId, StationArrivalDepartureSchedule] = {}
        self._trains: dict[TrainId, Train] = {}
        # track_id -> list of occupied time windows
        self._track_windows: dict[TrackId, list[tuple[TimeWindow, TrainId]]] = {}

    def register_train(self, train: Train, schedule: TrainSchedule) -> None:
        self._trains[train.id] = train
        self._schedules[train.id] = schedule

    def get_train_schedule(self, train_id: TrainId) -> TrainSchedule:
        if train_id not in self._schedules:
            raise KeyError(f"No schedule for train {train_id!r}")
        return self._schedules[train_id]

    def update_expected_arrival(
        self,
        train_id: TrainId,
        station_id: StationId,
        expected_arrival: datetime,
    ) -> TrainSchedule:
        schedule = self.get_train_schedule(train_id)
        now = datetime.now(timezone.utc)

        for entry in schedule.entries:
            if entry.station_id == station_id:
                old_value = entry.expected_arrival
                entry.expected_arrival = expected_arrival
                entry.last_updated = now
                schedule.update_history.append(
                    ScheduleUpdate(
                        field="expected_arrival",
                        old_value=old_value,
                        new_value=expected_arrival,
                        updated_at=now,
                    )
                )
                # Atomically sync to station schedule
                self._sync_to_station_schedule(train_id, station_id)
                return schedule

        # Entry not found — create one
        entry = ScheduleEntry(
            station_id=station_id,
            expected_arrival=expected_arrival,
            last_updated=now,
        )
        schedule.entries.append(entry)
        schedule.update_history.append(
            ScheduleUpdate(
                field="expected_arrival",
                old_value=None,
                new_value=expected_arrival,
                updated_at=now,
            )
        )
        self._sync_to_station_schedule(train_id, station_id)
        return schedule

    def detect_delay(
        self,
        schedule_entry: ScheduleEntry,
        threshold_minutes: int = 5,
    ) -> DelayInfo | None:
        if (
            schedule_entry.planned_arrival is None
            or schedule_entry.expected_arrival is None
        ):
            return None
        diff = schedule_entry.expected_arrival - schedule_entry.planned_arrival
        delay_minutes = int(diff.total_seconds() / 60)
        if delay_minutes > threshold_minutes:
            return DelayInfo(
                train_id=TrainId("unknown"),
                station_id=schedule_entry.station_id,
                delay_minutes=delay_minutes,
                planned_arrival=schedule_entry.planned_arrival,
                expected_arrival=schedule_entry.expected_arrival,
            )
        return None

    def get_station_schedule(
        self, station_id: StationId
    ) -> StationArrivalDepartureSchedule:
        if station_id not in self._station_schedules:
            self._station_schedules[station_id] = StationArrivalDepartureSchedule(
                station_id=station_id,
                entries=[],
                generated_at=datetime.now(timezone.utc),
            )
        return self._station_schedules[station_id]

    def compare_schedules(self, train_id: TrainId) -> list[ScheduleDiscrepancy]:
        schedule = self.get_train_schedule(train_id)
        discrepancies: list[ScheduleDiscrepancy] = []

        for entry in schedule.entries:
            station_sched = self._station_schedules.get(entry.station_id)
            if station_sched is None:
                continue
            station_entry = next(
                (e for e in station_sched.entries if e.train_id == train_id), None
            )
            if station_entry is None:
                continue

            for field in ("planned_arrival", "planned_departure", "expected_arrival", "expected_departure"):
                ts_val: datetime | None = getattr(entry, field, None)
                ss_val: datetime | None = getattr(station_entry, field, None)
                if ts_val != ss_val and (ts_val is not None or ss_val is not None):
                    diff_min = 0.0
                    if ts_val and ss_val:
                        diff_min = abs((ts_val - ss_val).total_seconds() / 60)
                    discrepancies.append(
                        ScheduleDiscrepancy(
                            train_id=train_id,
                            field=field,
                            train_schedule_value=ts_val,
                            station_schedule_value=ss_val,
                            difference_minutes=diff_min,
                        )
                    )
        return discrepancies

    def find_time_window(
        self,
        track_id: TrackId,
        duration_minutes: int,
        earliest_start: datetime,
    ) -> TimeWindow | None:
        """Find the earliest free time window of given duration on a track."""
        windows = self._track_windows.get(track_id, [])
        windows_sorted = sorted(windows, key=lambda x: x[0].start)

        candidate_start = earliest_start
        for tw, _ in windows_sorted:
            # If our candidate window ends before this occupied window starts, it's free
            candidate_end = candidate_start + timedelta(minutes=duration_minutes)
            if candidate_end <= tw.start:
                return TimeWindow(start=candidate_start, end=candidate_end)
            # Push past this occupied window
            if tw.end > candidate_start:
                candidate_start = tw.end

        # No conflicts — use earliest_start
        return TimeWindow(
            start=candidate_start,
            end=candidate_start + timedelta(minutes=duration_minutes),
        )

    def register_track_window(
        self, track_id: TrackId, time_window: TimeWindow, train_id: TrainId
    ) -> None:
        self._track_windows.setdefault(track_id, []).append((time_window, train_id))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _sync_to_station_schedule(
        self, train_id: TrainId, station_id: StationId
    ) -> None:
        schedule = self._schedules.get(train_id)
        if not schedule:
            return
        station_sched = self.get_station_schedule(station_id)
        train = self._trains.get(train_id)
        train_index = train.train_index if train else str(train_id)

        entry_for_station = next(
            (e for e in schedule.entries if e.station_id == station_id), None
        )
        if not entry_for_station:
            return

        station_entry = next(
            (e for e in station_sched.entries if e.train_id == train_id), None
        )
        if station_entry is None:
            station_sched.entries.append(
                StationScheduleEntry(
                    train_index=train_index,
                    train_id=train_id,
                    planned_arrival=entry_for_station.planned_arrival,
                    planned_departure=entry_for_station.planned_departure,
                    expected_arrival=entry_for_station.expected_arrival,
                    expected_departure=entry_for_station.expected_departure,
                )
            )
        else:
            station_entry.planned_arrival = entry_for_station.planned_arrival
            station_entry.planned_departure = entry_for_station.planned_departure
            station_entry.expected_arrival = entry_for_station.expected_arrival
            station_entry.expected_departure = entry_for_station.expected_departure
