"""
src/main.py — Composition root для Railway Station Manager FastAPI backend.

Запуск (dev):
    uvicorn src.main:app --reload

Запуск (production):
    uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 1

Переменные окружения:
    TOPOLOGY_CONFIG   — путь к JSON/YAML файлу топологии
                        (default: config/station_topology.example.json)
    GROQ_API_KEY      — Groq API key (если не задан, используется LLMClientStub)
    LOG_LEVEL         — уровень логирования (default: INFO)
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("railway.main")

# ---------------------------------------------------------------------------
# Infrastructure imports (existing modules only — no duplication)
# ---------------------------------------------------------------------------
from src.startup import StartupSequence
from src.infrastructure.llm import create_llm_client
from src.agents.acceptance.agent import AcceptanceAgent
from src.agents.service_planning.agent import ServicePlanningAgent

# ---------------------------------------------------------------------------
# Application state container
# ---------------------------------------------------------------------------

class AppState:
    """Holds all initialised components for the lifetime of the application."""
    startup: StartupSequence | None = None
    acceptance_agent: AcceptanceAgent | None = None
    service_planning_agent: ServicePlanningAgent | None = None
    ready: bool = False
    started_at: datetime | None = None


_state = AppState()


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler — runs startup logic then yields."""
    # ---- STARTUP ----
    topology_path = os.getenv(
        "TOPOLOGY_CONFIG", "config/station_topology.example.json"
    )
    log.info("Railway Station Manager — starting up")
    log.info("Topology config: %s", topology_path)

    # 1. LLM client (uses GROQ_API_KEY if present, else stub)
    llm_client = create_llm_client()
    log.info("LLM client: %s", type(llm_client).__name__)

    # 2. StartupSequence — loads topology, validates graph, inits all services
    seq = StartupSequence(llm_client=llm_client)
    ok = seq.run(topology_path)
    if not ok:
        log.critical(
            "Station startup failed — disconnected nodes: %s",
            seq.disconnected_nodes,
        )
        raise RuntimeError(
            f"Station topology is not valid: disconnected nodes {seq.disconnected_nodes}"
        )

    # 3. Agents — use existing classes, inject the shared LLM client
    acceptance_agent = AcceptanceAgent()
    service_planning_agent = ServicePlanningAgent(llm_client=llm_client)

    # 4. Store in application state
    _state.startup = seq
    _state.acceptance_agent = acceptance_agent
    _state.service_planning_agent = service_planning_agent
    _state.ready = True
    _state.started_at = datetime.now(timezone.utc)

    log.info(
        "Station '%s' (%s) ready — %d nodes, %d tracks",
        seq.station.name,
        seq.station_id,
        len(seq.station.graph.nodes),
        len(seq.station.graph.tracks),
    )
    log.info("Application ready")

    yield  # ---- application runs here ----

    # ---- SHUTDOWN ----
    log.info("Railway Station Manager — shutting down")
    _state.ready = False


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Railway Station Manager",
    description=(
        "Automated backend for railway station path and schedule management. "
        "Provides deterministic planning services and AI-assisted decision making."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Dependency helper — exposes AppState to routers
# ---------------------------------------------------------------------------

# Доп. маршруты для интерфейса Smart Station (поиск/бронь маршрутов)
from src.api_extra import router as _extra_router  # noqa: E402
app.include_router(_extra_router)


def get_app_state() -> AppState:
    return _state


# ---------------------------------------------------------------------------
# Built-in health / status endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["system"], summary="Health check")
async def health() -> dict[str, Any]:
    """Returns 200 when the application is fully initialised."""
    if not _state.ready:
        return JSONResponse(
            status_code=503,
            content={"status": "starting", "ready": False},
        )
    return {"status": "ok", "ready": True}


@app.get("/status", tags=["system"], summary="Application status")
async def status() -> dict[str, Any]:
    """Returns runtime status including station info and component health."""
    if not _state.ready or _state.startup is None:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "ready": False},
        )

    seq = _state.startup
    station = seq.station

    occupied = seq.occupancy_service.get_all_occupied_tracks(seq.station_id)

    return {
        "status": "ok",
        "ready": True,
        "started_at": _state.started_at.isoformat() if _state.started_at else None,
        "station": {
            "id": station.id,
            "name": station.name,
            "nodes": len(station.graph.nodes),
            "tracks": len(station.graph.tracks),
        },
        "occupancy": {
            "occupied_tracks": len(occupied),
            "free_tracks": len(station.graph.tracks) - len(occupied),
        },
        "components": {
            "llm_client": type(seq.llm_client).__name__,
            "acceptance_agent": type(_state.acceptance_agent).__name__,
            "service_planning_agent": type(_state.service_planning_agent).__name__,
            "routing_service": type(seq.routing_service).__name__,
            "conflict_service": type(seq.conflict_service).__name__,
            "station_state_service": type(seq.station_state_service).__name__,
        },
    }


@app.get("/station/topology", tags=["station"], summary="Station topology")
async def get_topology() -> dict[str, Any]:
    """Returns the station graph: all nodes and tracks."""
    if not _state.ready or _state.startup is None:
        return JSONResponse(status_code=503, content={"detail": "not ready"})

    graph = _state.startup.station.graph
    return {
        "station_id": _state.startup.station_id,
        "nodes": [
            {
                "id": node_id,
                "type": node.node_type.value,
                "name": node.name,
                "position": {"x": node.position.x, "y": node.position.y}
                if node.position else None,
            }
            for node_id, node in graph.nodes.items()
        ],
        "tracks": [
            {
                "id": track_id,
                "from": track.source_node_id,
                "to": track.target_node_id,
                "length_m": track.length_m,
                "max_weight_t": track.max_weight_t,
                "allowed_types": track.allowed_train_types,
                "bidirectional": track.is_bidirectional,
            }
            for track_id, track in graph.tracks.items()
        ],
    }


@app.get("/station/occupancy", tags=["station"], summary="Current track occupancy")
async def get_occupancy() -> dict[str, Any]:
    """Returns current occupancy state of all tracks."""
    if not _state.ready or _state.startup is None:
        return JSONResponse(status_code=503, content={"detail": "not ready"})

    seq = _state.startup
    occupied = seq.occupancy_service.get_all_occupied_tracks(seq.station_id)

    return {
        "station_id": seq.station_id,
        "occupied": [
            {
                "track_id": o.track_id,
                "train_id": o.occupying_train_id,
                "since": o.occupied_since.isoformat() if o.occupied_since else None,
            }
            for o in occupied
        ],
        "total_tracks": len(seq.station.graph.tracks),
        "occupied_count": len(occupied),
        "free_count": len(seq.station.graph.tracks) - len(occupied),
    }
