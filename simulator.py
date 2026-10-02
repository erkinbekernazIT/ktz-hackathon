"""
Smart Station — Mock Station Simulator
Runs as a background asyncio task.
Tick rate: 1 second. Manages trains, tracks, schedule, history buffer.
"""
from __future__ import annotations

import asyncio
import random
import time
import uuid
from collections import deque
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Callable, Optional

from models import (
    Train, Track, Conflict, EventEntry, StationSnapshot,
    TrainStatus, TrackStatus, TrainType, ConflictType, EventType, Direction
)


# ─────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────

def _now_str(delta_min: int = 0) -> str:
    return (datetime.now() + timedelta(minutes=delta_min)).strftime("%H:%M")


def _uid() -> str:
    return str(uuid.uuid4())[:8]


# ─────────────────────────────────────────
#  INITIAL TRAIN TEMPLATES
# ─────────────────────────────────────────

TRAIN_TEMPLATES = [
    {"number": "101А", "type": TrainType.EXPRESS,   "route": "Алматы–Астана",   "direction": Direction.DEPARTURE},
    {"number": "205Б", "type": TrainType.PASSENGER, "route": "Алматы–Шымкент", "direction": Direction.ARRIVAL},
    {"number": "312В", "type": TrainType.FREIGHT,   "route": "Алматы–Актобе",  "direction": Direction.TRANSIT},
    {"number": "418Г", "type": TrainType.LOCAL,     "route": "Алматы–Талдыкорган", "direction": Direction.ARRIVAL},
    {"number": "501Д", "type": TrainType.PASSENGER, "route": "Алматы–Тараз",   "direction": Direction.DEPARTURE},
    {"number": "604Е", "type": TrainType.EXPRESS,   "route": "Алматы–Семей",   "direction": Direction.TRANSIT},
    {"number": "703Ж", "type": TrainType.FREIGHT,   "route": "Алматы–Усть-Каменогорск", "direction": Direction.ARRIVAL},
    {"number": "812З", "type": TrainType.LOCAL,     "route": "Алматы–Капшагай", "direction": Direction.DEPARTURE},
]

DESTINATIONS = {
    Direction.ARRIVAL:   ["Прибытие на станцию",  "Алматы-1 вокзал"],
    Direction.DEPARTURE: ["Выход со станции",      "Маршрутный узел"],
    Direction.TRANSIT:   ["Транзитный путь",       "Сортировочный узел"],
}

STATUS_CYCLE = {
    Direction.ARRIVAL: [
        TrainStatus.MOVING, TrainStatus.ARRIVING, TrainStatus.WAITING,
        TrainStatus.STOPPED, TrainStatus.DEPARTING,
    ],
    Direction.DEPARTURE: [
        TrainStatus.WAITING, TrainStatus.STOPPED,
        TrainStatus.DEPARTING, TrainStatus.MOVING,
    ],
    Direction.TRANSIT: [
        TrainStatus.MOVING, TrainStatus.WAITING, TrainStatus.MOVING,
    ],
}

SPEED_BY_STATUS = {
    TrainStatus.MOVING:    (40, 80),
    TrainStatus.ARRIVING:  (10, 35),
    TrainStatus.DEPARTING: (5,  25),
    TrainStatus.WAITING:   (0,   0),
    TrainStatus.STOPPED:   (0,   0),
    TrainStatus.DELAYED:   (0,   0),
    TrainStatus.CONFLICT:  (0,   0),
}

OPERATION_BY_STATUS = {
    TrainStatus.MOVING:    "Движение по маршруту",
    TrainStatus.ARRIVING:  "Манёвр прибытия",
    TrainStatus.DEPARTING: "Манёвр отправления",
    TrainStatus.WAITING:   "Ожидание на пути",
    TrainStatus.STOPPED:   "Стоянка. Посадка/высадка пассажиров",
    TrainStatus.DELAYED:   "Задержан — ожидание решения",
    TrainStatus.CONFLICT:  "Конфликт маршрута — блокировка",
}


# ─────────────────────────────────────────
#  SIMULATOR
# ─────────────────────────────────────────

class StationSimulator:
    """
    Core simulation engine.
    Maintains trains, tracks, conflicts, event log, history buffer.
    Fires on_state_update(snapshot) callback every tick.
    """

    HISTORY_SECONDS = 900   # 15 minutes of snapshots
    TICK_INTERVAL   = 1.0   # seconds

    def __init__(self) -> None:
        self.running: bool = False
        self.paused:  bool = False
        self._task:   Optional[asyncio.Task] = None

        self.trains:    dict[str, Train]    = {}
        self.tracks:    dict[int, Track]    = {}
        self.conflicts: dict[str, Conflict] = {}
        self.events:    list[EventEntry]    = []
        self.history:   deque[StationSnapshot] = deque(maxlen=self.HISTORY_SECONDS)

        # ticks since each train entered current status
        self._status_ticks: dict[str, int] = {}
        # status sequence position
        self._status_idx:   dict[str, int] = {}
        # position velocity (units/tick, 0.0–1.0 track range)
        self._velocity:     dict[str, float] = {}

        # callback registered by main.py
        self.on_state_update: Optional[Callable] = None
        # callback when conflict detected
        self.on_conflict: Optional[Callable] = None

        self._init_tracks()
        self._init_trains()

    # ── INITIALISATION ──────────────────────

    def _init_tracks(self) -> None:
        configs = [
            (1, "Путь №1", True,  "in"),
            (2, "Путь №2", True,  "out"),
            (3, "Путь №3", True,  "both"),
            (4, "Путь №4", False, "both"),
            (5, "Путь №5", True,  "both"),
            (6, "Путь №6", False, "out"),
        ]
        for tid, name, has_platform, direction in configs:
            self.tracks[tid] = Track(
                id=tid, name=name,
                status=TrackStatus.FREE,
                platform=has_platform,
                direction=direction,
            )

    def _init_trains(self) -> None:
        available_tracks = list(self.tracks.keys())
        random.shuffle(available_tracks)

        for i, tpl in enumerate(TRAIN_TEMPLATES):
            tid = f"train_{i+1}"
            track_id = available_tracks[i % len(available_tracks)]

            direction = tpl["direction"]
            si = 0
            status_seq = STATUS_CYCLE.get(direction, [TrainStatus.MOVING])
            status = status_seq[si]

            spd_range = SPEED_BY_STATUS.get(status, (0, 60))
            speed = round(random.uniform(*spd_range), 1)

            delay = random.choices([0, 0, 0, random.randint(1, 12)], weights=[6, 4, 3, 1])[0]

            now_offset = random.randint(-15, 30)
            train = Train(
                id=tid,
                number=tpl["number"],
                type=tpl["type"],
                route=tpl["route"],
                direction=direction,
                track_id=track_id,
                next_stop=DESTINATIONS[direction][0],
                planned_arrival=_now_str(now_offset),
                expected_arrival=_now_str(now_offset + delay),
                planned_departure=_now_str(now_offset + 10),
                expected_departure=_now_str(now_offset + 10 + delay),
                delay_min=delay,
                speed_kmh=speed,
                status=status,
                operation=OPERATION_BY_STATUS[status],
                position_x=round(random.uniform(0.05, 0.95), 3),
                passengers=random.randint(0, 450) if tpl["type"] != TrainType.FREIGHT else 0,
            )
            self.trains[tid] = train
            self._status_ticks[tid] = 0
            self._status_idx[tid]   = si
            self._velocity[tid]     = speed / 3600 * 0.05  # normalised

            # occupy track
            self.tracks[track_id].status      = TrackStatus.OCCUPIED
            self.tracks[track_id].occupied_by = tid

        self._log_event(EventType.SYSTEM, "Симулятор инициализирован. Станция готова к работе.")

    # ── PUBLIC API ──────────────────────────

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self.running = True
        self.paused  = False
        self._task   = asyncio.create_task(self._loop())
        self._log_event(EventType.SYSTEM, "Симуляция запущена")

    async def stop(self) -> None:
        self.running = False
        if self._task:
            self._task.cancel()
        self._log_event(EventType.SYSTEM, "Симуляция остановлена")

    def pause(self) -> None:
        self.paused = True
        self._log_event(EventType.SYSTEM, "Симуляция на паузе")

    def resume(self) -> None:
        self.paused = False
        self._log_event(EventType.SYSTEM, "Симуляция возобновлена")

    def get_snapshot(self) -> StationSnapshot:
        return self._build_snapshot()

    def get_history_at(self, offset_sec: int) -> Optional[StationSnapshot]:
        """Return snapshot closest to `offset_sec` seconds ago."""
        if not self.history:
            return None
        target = time.time() - offset_sec
        best = min(self.history, key=lambda s: abs(s.ts - target))
        return best

    # ── CONFLICT TRIGGERS ───────────────────

    def trigger_close_track(self, track_id: int) -> Conflict:
        track = self.tracks.get(track_id)
        if not track:
            raise ValueError(f"Track {track_id} not found")

        track.status = TrackStatus.CLOSED
        self._log_event(EventType.WARNING,
                        f"Путь №{track_id} закрыт",
                        track_id=track_id)

        # find trains planned for this track
        affected = [t for t in self.trains.values() if t.track_id == track_id]
        for t in affected:
            t.status    = TrainStatus.CONFLICT
            t.operation = OPERATION_BY_STATUS[TrainStatus.CONFLICT]
            track.status = TrackStatus.CONFLICT

        conflict = Conflict(
            id=_uid(),
            type=ConflictType.TRACK_CLOSED,
            severity="high",
            track_id=track_id,
            train_id=affected[0].id if affected else None,
            description=(
                f"Путь №{track_id} закрыт. "
                + (f"Поезд №{affected[0].number} заблокирован." if affected else "")
            ),
        )
        self.conflicts[conflict.id] = conflict
        self._log_event(EventType.CONFLICT,
                        f"Конфликт: путь №{track_id} закрыт",
                        detail=conflict.description,
                        track_id=track_id,
                        train_id=affected[0].id if affected else None)
        if self.on_conflict:
            asyncio.create_task(self.on_conflict(conflict))
        return conflict

    def trigger_delay_train(self, train_id: str, extra_min: int = 10) -> Conflict:
        train = self.trains.get(train_id)
        if not train:
            raise ValueError(f"Train {train_id} not found")
        train.delay_min += extra_min
        train.status     = TrainStatus.DELAYED
        train.operation  = OPERATION_BY_STATUS[TrainStatus.DELAYED]
        train.speed_kmh  = 0.0
        self._log_event(EventType.WARNING,
                        f"Поезд №{train.number} задержан на {extra_min} мин",
                        train_id=train_id)
        conflict = Conflict(
            id=_uid(),
            type=ConflictType.DELAY_CASCADE,
            severity="medium",
            track_id=train.track_id,
            train_id=train_id,
            description=f"Поезд №{train.number} задержан на {extra_min} мин. Возможна каскадная задержка.",
        )
        self.conflicts[conflict.id] = conflict
        if self.on_conflict:
            asyncio.create_task(self.on_conflict(conflict))
        return conflict

    def trigger_equipment_fail(self) -> Conflict:
        track_id = random.choice(list(self.tracks.keys()))
        track    = self.tracks[track_id]
        track.status = TrackStatus.MAINTENANCE
        self._log_event(EventType.WARNING,
                        f"Отказ оборудования на пути №{track_id}",
                        track_id=track_id)
        conflict = Conflict(
            id=_uid(),
            type=ConflictType.EQUIPMENT_FAIL,
            severity="high",
            track_id=track_id,
            description=f"Зафиксирован отказ оборудования на пути №{track_id}. Требуется техническое обслуживание.",
        )
        self.conflicts[conflict.id] = conflict
        if self.on_conflict:
            asyncio.create_task(self.on_conflict(conflict))
        return conflict

    def trigger_route_conflict(self) -> Conflict:
        trains = list(self.trains.values())
        if len(trains) < 2:
            return self.trigger_equipment_fail()
        t1, t2 = random.sample(trains, 2)
        # forcefully put them on same track
        t2.track_id = t1.track_id
        for t in (t1, t2):
            t.status    = TrainStatus.CONFLICT
            t.operation = OPERATION_BY_STATUS[TrainStatus.CONFLICT]
        if t1.track_id:
            self.tracks[t1.track_id].status = TrackStatus.CONFLICT
        conflict = Conflict(
            id=_uid(),
            type=ConflictType.ROUTE_CONFLICT,
            severity="high",
            track_id=t1.track_id,
            train_id=t1.id,
            description=(
                f"Конфликт маршрутов: поезда №{t1.number} и №{t2.number} "
                f"назначены на путь №{t1.track_id}."
            ),
        )
        self.conflicts[conflict.id] = conflict
        self._log_event(EventType.CONFLICT, conflict.description,
                        track_id=t1.track_id, train_id=t1.id)
        if self.on_conflict:
            asyncio.create_task(self.on_conflict(conflict))
        return conflict

    def trigger_resource_lack(self) -> Conflict:
        conflict = Conflict(
            id=_uid(),
            type=ConflictType.RESOURCE_LACK,
            severity="medium",
            description="Нехватка свободных путей. Очередь прибывающих поездов превышает норму.",
        )
        self.conflicts[conflict.id] = conflict
        self._log_event(EventType.WARNING, conflict.description)
        if self.on_conflict:
            asyncio.create_task(self.on_conflict(conflict))
        return conflict

    # ── APPLY AI PLAN ───────────────────────

    def apply_plan(self, conflict_id: str, action: str,
                   target_train_id: Optional[str],
                   target_track_id: Optional[int],
                   extra_delay_min: int) -> None:
        conflict = self.conflicts.get(conflict_id)
        if not conflict:
            return

        if action == "reroute" and target_train_id and target_track_id:
            train = self.trains.get(target_train_id)
            if train:
                old_track = train.track_id
                # free old track
                if old_track and old_track in self.tracks:
                    self.tracks[old_track].status      = TrackStatus.FREE
                    self.tracks[old_track].occupied_by = None
                # assign new track
                train.track_id  = target_track_id
                train.status    = TrainStatus.MOVING
                train.operation = f"Перенаправлен на путь №{target_track_id}"
                train.delay_min += extra_delay_min
                train.speed_kmh = round(random.uniform(20, 50), 1)
                if target_track_id in self.tracks:
                    self.tracks[target_track_id].status      = TrackStatus.OCCUPIED
                    self.tracks[target_track_id].occupied_by = target_train_id
                self._log_event(EventType.DISPATCH,
                                f"Поезд №{train.number} перенаправлен на путь №{target_track_id}",
                                train_id=target_train_id, track_id=target_track_id)

        elif action == "wait" and target_train_id:
            train = self.trains.get(target_train_id)
            if train:
                train.status    = TrainStatus.WAITING
                train.speed_kmh = 0.0
                train.delay_min += extra_delay_min
                train.operation = "Ожидание освобождения пути"
                self._log_event(EventType.DISPATCH,
                                f"Поезд №{train.number} переведён в режим ожидания",
                                train_id=target_train_id)

        elif action == "reorder":
            # shift all delayed trains by extra_delay
            for t in self.trains.values():
                if t.delay_min > 0:
                    t.delay_min = max(0, t.delay_min - 2)
            self._log_event(EventType.DISPATCH,
                            "Порядок движения перестроен. Задержки скорректированы.")

        elif action == "delay" and target_train_id:
            train = self.trains.get(target_train_id)
            if train:
                train.delay_min += extra_delay_min
                train.status     = TrainStatus.DELAYED
                self._log_event(EventType.DISPATCH,
                                f"Поезд №{train.number}: принудительная задержка +{extra_delay_min} мин",
                                train_id=target_train_id)

        # resolve conflict
        conflict.resolved    = True
        conflict.resolved_at = time.time()
        conflict.resolution  = f"Применён вариант: {action}"

        # restore track if it was just closed and no more trains conflict
        if conflict.track_id and conflict.type == ConflictType.TRACK_CLOSED:
            if action == "reroute":
                # track stays closed but no train is blocked
                pass

        self._log_event(EventType.AI,
                        f"Конфликт {conflict_id[:6]} разрешён. Новый план применён.")

    # ── TICK LOOP ───────────────────────────

    async def _loop(self) -> None:
        while self.running:
            await asyncio.sleep(self.TICK_INTERVAL)
            if self.paused:
                continue
            try:
                self._tick()
                snap = self._build_snapshot()
                self.history.append(snap)
                if self.on_state_update:
                    await self.on_state_update(snap)
            except Exception as exc:
                print(f"[SIM ERROR] {exc}")

    def _tick(self) -> None:
        """Advance simulation by one second."""
        for tid, train in list(self.trains.items()):
            self._status_ticks[tid] = self._status_ticks.get(tid, 0) + 1
            ticks = self._status_ticks[tid]

            if train.status in (TrainStatus.CONFLICT,):
                continue  # frozen until resolved

            direction  = train.direction
            status_seq = STATUS_CYCLE.get(direction, [TrainStatus.MOVING])
            si         = self._status_idx.get(tid, 0)
            cur_status = status_seq[si]

            # How long to stay in this status (seconds)
            dwell = self._dwell_time(cur_status)

            if ticks >= dwell:
                # advance to next status
                si = (si + 1) % len(status_seq)
                self._status_idx[tid]   = si
                self._status_ticks[tid] = 0
                new_status = status_seq[si]
                train.status    = new_status
                train.operation = OPERATION_BY_STATUS[new_status]

                spd_range       = SPEED_BY_STATUS.get(new_status, (0, 60))
                train.speed_kmh = round(random.uniform(*spd_range), 1)

                # when departing, free track after dwell
                if new_status == TrainStatus.MOVING and train.track_id:
                    if direction == Direction.DEPARTURE:
                        self._handle_departure(tid, train)

                # when arriving, occupy a track
                if new_status == TrainStatus.ARRIVING:
                    self._handle_arrival(tid, train)

            else:
                # small speed variation
                if train.status not in (TrainStatus.WAITING, TrainStatus.STOPPED, TrainStatus.DELAYED):
                    base_range = SPEED_BY_STATUS.get(train.status, (0, 60))
                    delta = random.uniform(-2, 2)
                    train.speed_kmh = round(
                        max(base_range[0], min(base_range[1], train.speed_kmh + delta)), 1
                    )

            # update position
            if train.speed_kmh > 0:
                vel = train.speed_kmh / 3600 * 0.08
                if direction == Direction.ARRIVAL:
                    train.position_x = min(0.95, train.position_x + vel)
                elif direction == Direction.DEPARTURE:
                    train.position_x = max(0.05, train.position_x - vel)
                else:
                    train.position_x = (train.position_x + vel) % 0.9 + 0.05

            # occasionally add small random delay
            if random.random() < 0.003 and train.status == TrainStatus.MOVING:
                extra = random.randint(1, 3)
                train.delay_min += extra
                train.status     = TrainStatus.DELAYED
                train.speed_kmh  = 0.0
                self._log_event(EventType.WARNING,
                                f"Поезд №{train.number} задержан +{extra} мин",
                                train_id=tid)

        # occasionally spawn a new train
        if random.random() < 0.008 and len(self.trains) < 12:
            self._spawn_train()

    def _dwell_time(self, status: TrainStatus) -> int:
        """Seconds to remain in a given status."""
        return {
            TrainStatus.MOVING:    random.randint(25, 60),
            TrainStatus.ARRIVING:  random.randint(8,  20),
            TrainStatus.DEPARTING: random.randint(5,  15),
            TrainStatus.WAITING:   random.randint(15, 45),
            TrainStatus.STOPPED:   random.randint(10, 30),
            TrainStatus.DELAYED:   random.randint(8,  20),
        }.get(status, 20)

    def _handle_arrival(self, tid: str, train: Train) -> None:
        free_tracks = [t for t in self.tracks.values()
                       if t.status == TrackStatus.FREE]
        if free_tracks:
            track = random.choice(free_tracks)
            # free old track
            if train.track_id and train.track_id in self.tracks:
                old = self.tracks[train.track_id]
                old.status      = TrackStatus.FREE
                old.occupied_by = None
            train.track_id            = track.id
            track.status              = TrackStatus.OCCUPIED
            track.occupied_by         = tid
            self._log_event(EventType.INFO,
                            f"Поезд №{train.number} прибыл на путь №{track.id}",
                            train_id=tid, track_id=track.id)

    def _handle_departure(self, tid: str, train: Train) -> None:
        if train.track_id and train.track_id in self.tracks:
            self.tracks[train.track_id].status      = TrackStatus.FREE
            self.tracks[train.track_id].occupied_by = None
        self._log_event(EventType.INFO,
                        f"Поезд №{train.number} отправился",
                        train_id=tid)
        # 30 % chance: remove from station (departed completely)
        if random.random() < 0.30:
            del self.trains[tid]
            self._status_ticks.pop(tid, None)
            self._status_idx.pop(tid, None)
            self._velocity.pop(tid, None)

    def _spawn_train(self) -> None:
        tpl = random.choice(TRAIN_TEMPLATES)
        tid = f"train_{_uid()}"
        free_tracks = [t for t in self.tracks.values() if t.status == TrackStatus.FREE]
        if not free_tracks:
            return
        track = random.choice(free_tracks)
        direction = random.choice(list(Direction))
        delay     = random.choices([0, 0, random.randint(1, 8)], weights=[5, 3, 2])[0]
        status    = TrainStatus.ARRIVING
        train = Train(
            id=tid, number=tpl["number"] + "+" ,
            type=tpl["type"], route=tpl["route"],
            direction=direction, track_id=track.id,
            next_stop=DESTINATIONS[direction][0],
            planned_arrival=_now_str(random.randint(0, 20)),
            expected_arrival=_now_str(random.randint(0, 20) + delay),
            planned_departure=_now_str(random.randint(5, 30)),
            expected_departure=_now_str(random.randint(5, 30) + delay),
            delay_min=delay, speed_kmh=20.0,
            status=status, operation=OPERATION_BY_STATUS[status],
            position_x=0.05 if direction == Direction.ARRIVAL else 0.95,
            passengers=random.randint(0, 300),
        )
        self.trains[tid] = train
        self._status_ticks[tid] = 0
        self._status_idx[tid]   = 0
        track.status      = TrackStatus.OCCUPIED
        track.occupied_by = tid
        self._log_event(EventType.INFO,
                        f"Поезд №{train.number} входит на станцию (путь №{track.id})",
                        train_id=tid, track_id=track.id)

    # ── SNAPSHOT ────────────────────────────

    def _build_snapshot(self) -> StationSnapshot:
        trains   = list(self.trains.values())
        tracks   = list(self.tracks.values())
        active_c = [c for c in self.conflicts.values() if not c.resolved]

        delayed  = sum(1 for t in trains if t.delay_min > 0)
        occupied = sum(1 for t in tracks if t.status == TrackStatus.OCCUPIED)

        # efficiency = 100 - 5*conflicts - 2*delayed - track_closures*3
        closed = sum(1 for t in tracks if t.status in (TrackStatus.CLOSED, TrackStatus.MAINTENANCE))
        eff = max(50.0, 100.0 - len(active_c) * 5 - delayed * 2 - closed * 3)

        return StationSnapshot(
            ts=time.time(),
            trains=deepcopy(trains),
            tracks=deepcopy(tracks),
            conflicts=deepcopy(list(self.conflicts.values())),
            events=deepcopy(self.events[-50:]),
            efficiency_pct=round(eff, 1),
            total_trains=len(trains),
            occupied_tracks=occupied,
            delayed_trains=delayed,
            active_conflicts=len(active_c),
        )

    # ── EVENT LOG ───────────────────────────

    def _log_event(self, etype: EventType, message: str,
                   detail: str = None,
                   train_id: str = None,
                   track_id: int = None) -> None:
        entry = EventEntry(
            id=_uid(), ts=time.time(),
            type=etype, message=message,
            detail=detail, train_id=train_id, track_id=track_id,
        )
        self.events.append(entry)
        # keep last 200 events
        if len(self.events) > 200:
            self.events = self.events[-200:]
