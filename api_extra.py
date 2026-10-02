"""
src/api_extra.py — дополнительные endpoints модуля Railway Station Manager
для интерфейса Smart Station (поиск, бронирование и освобождение маршрутов).

Использует существующие сервисы Глеба: RoutingService, StationStateService,
GraphEngine. Подключается в src/main.py строкой:
    from src.api_extra import router as extra_router; app.include_router(extra_router)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.domain.planning.models import TimeWindow
from src.domain.train.models import TrainType
from src.domain.train.views import RoutingTrainView
from src.domain.types import NodeId, RouteId, TrainId

router = APIRouter(tags=["routes"])


def _seq():
    from src.main import _state  # ленивый импорт: избегаем циклической зависимости
    if not _state.ready or _state.startup is None:
        raise HTTPException(503, "Railway Station Manager not ready")
    return _state.startup


class RouteRequest(BaseModel):
    train_id: str = "T-001"
    from_node: str
    to_node: str
    train_type: TrainType = TrainType.PASSENGER
    length_m: float = 400
    weight_t: float = 1200
    window_min: int = 30


class ReserveRequest(BaseModel):
    train_id: str
    path: list[str]
    window_min: int = 30


def _route_to_dict(route, graph) -> dict[str, Any]:
    return {
        "id": route.id,
        "train_id": route.train_id,
        "path": list(route.path),
        "length_m": sum(graph.tracks[t].length_m for t in route.path if t in graph.tracks),
        "status": getattr(route.status, "value", str(route.status)),
        "window": {"start": route.time_window.start.isoformat(), "end": route.time_window.end.isoformat()},
    }


@router.get("/station/state", summary="Live state: occupancy + active routes")
async def station_state() -> dict[str, Any]:
    seq = _seq()
    st = seq.station_state_service.get_current_state(seq.station_id)
    graph = seq.station.graph
    return {
        "station_id": seq.station_id,
        "station_name": seq.station.name,
        "tracks": [
            {
                "id": tid,
                "occupied": bool(st.track_occupancy.get(tid) and st.track_occupancy[tid].is_occupied),
                "train_id": (st.track_occupancy[tid].occupying_train_id if st.track_occupancy.get(tid) else None),
                "blocked": tid in st.blocked_elements,
            }
            for tid in graph.tracks
        ],
        "active_routes": [_route_to_dict(r, graph) for r in st.active_routes.values()],
    }


@router.post("/routes/candidates", summary="Find candidate routes for a train")
async def candidates(req: RouteRequest) -> dict[str, Any]:
    seq = _seq()
    graph = seq.station.graph
    if req.from_node not in graph.nodes or req.to_node not in graph.nodes:
        raise HTTPException(400, "Unknown node")
    now = datetime.now(timezone.utc)
    window = TimeWindow(start=now, end=now + timedelta(minutes=req.window_min))
    train = RoutingTrainView(
        train_id=TrainId(req.train_id), length_m=req.length_m,
        weight_t=req.weight_t, train_type=req.train_type,
    )
    state = seq.station_state_service.get_current_state(seq.station_id)
    found = seq.routing_service.find_candidate_routes(
        graph, state, train, NodeId(req.from_node), NodeId(req.to_node), window
    )
    found.sort(key=lambda c: (-c.feasibility_score, len(c.route.path)))
    return {
        "train_id": req.train_id,
        "count": len(found),
        "candidates": [
            {**_route_to_dict(c.route, graph), "score": round(c.feasibility_score, 2),
             "receiving_track": c.receiving_track_id}
            for c in found[:6]
        ],
    }


@router.post("/routes/reserve", summary="Reserve a route (occupy its tracks)")
async def reserve(req: ReserveRequest) -> dict[str, Any]:
    seq = _seq()
    graph = seq.station.graph
    from uuid import uuid4
    from src.domain.planning.models import Route
    for t in req.path:
        if t not in graph.tracks:
            raise HTTPException(400, f"Unknown track {t}")
    state = seq.station_state_service.get_current_state(seq.station_id)
    busy = [t for t in req.path if state.track_occupancy.get(t) and state.track_occupancy[t].is_occupied]
    if busy:
        raise HTTPException(409, f"Tracks already occupied: {', '.join(busy)}")
    now = datetime.now(timezone.utc)
    route = Route(
        id=RouteId(str(uuid4())), train_id=TrainId(req.train_id), path=req.path,
        time_window=TimeWindow(start=now, end=now + timedelta(minutes=req.window_min)),
    )
    seq.station_state_service.apply_route_reservation(route)
    return {"ok": True, "route": _route_to_dict(route, graph)}


@router.post("/routes/{route_id}/release", summary="Release a reserved route")
async def release(route_id: str) -> dict[str, Any]:
    seq = _seq()
    try:
        seq.station_state_service.release_route_reservation(RouteId(route_id))
    except KeyError:
        raise HTTPException(404, "Route not found")
    return {"ok": True}
