"""
Smart Station — FastAPI Backend
Endpoints:
  GET  /                        → serve dispatcher.html
  GET  /api/state               → current station snapshot
  GET  /api/history?offset_sec= → snapshot from N seconds ago
  POST /api/trigger             → inject a conflict event
  POST /api/apply_plan          → validate + apply AI plan option
  POST /api/sim/pause           → pause simulator
  POST /api/sim/resume          → resume simulator
  GET  /api/conflicts           → list active conflicts
  GET  /api/ai/{conflict_id}    → get AI plan for conflict (cached)
  WS   /ws                      → live state stream (1 msg/sec)
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ai_planner import generate_plan, validate_plan
from models import (
    ApplyPlanRequest, StationSnapshot, TriggerEventRequest,
    WSMessage, EventType,
)
from simulator import StationSimulator

load_dotenv()

# ─────────────────────────────────────────
#  APP + SIMULATOR
# ─────────────────────────────────────────

app = FastAPI(title="Smart Station API", version="1.0.0")

sim = StationSimulator()

# ai_plans cache: conflict_id → AIResponse
_ai_cache: dict = {}

# connected WebSocket clients
_ws_clients: set[WebSocket] = set()


# ─────────────────────────────────────────
#  WS BROADCAST
# ─────────────────────────────────────────

async def _broadcast(msg: dict) -> None:
    dead = set()
    for ws in _ws_clients:
        try:
            await ws.send_text(json.dumps(msg, ensure_ascii=False, default=str))
        except Exception:
            dead.add(ws)
    _ws_clients.difference_update(dead)


def _snapshot_to_dict(snap: StationSnapshot) -> dict:
    return json.loads(snap.model_dump_json())


# ─────────────────────────────────────────
#  SIMULATOR CALLBACKS
# ─────────────────────────────────────────

async def _on_state(snap: StationSnapshot) -> None:
    await _broadcast({
        "type":    "state",
        "payload": _snapshot_to_dict(snap),
    })


async def _on_conflict(conflict) -> None:
    # 1. broadcast raw conflict immediately
    await _broadcast({
        "type":    "conflict",
        "payload": json.loads(conflict.model_dump_json()),
    })
    # 2. generate AI plan (async, non-blocking)
    asyncio.create_task(_generate_and_broadcast_plan(conflict))


async def _generate_and_broadcast_plan(conflict) -> None:
    snap = sim.get_snapshot()
    plan = await generate_plan(conflict, snap)
    _ai_cache[conflict.id] = plan
    sim._log_event(
        EventType.AI,
        f"AI сформировал {len(plan.options)} вариантов для конфликта {conflict.id[:6]}",
    )
    await _broadcast({
        "type":    "ai_response",
        "payload": json.loads(plan.model_dump_json()),
    })


# ─────────────────────────────────────────
#  STARTUP / SHUTDOWN
# ─────────────────────────────────────────

# ─────────────────────────────────────────
#  МОДУЛЬ ГЛЕБА: Railway Station Manager (../backend-gleb)
#  Подключается внутрь этого же сервера по адресу /gleb/...
#  (/gleb/status, /gleb/station/topology, /gleb/station/state,
#   /gleb/routes/candidates, /gleb/routes/reserve, /gleb/docs)
#  Если модуль не загрузился — основной сайт всё равно работает.
# ─────────────────────────────────────────
import sys as _sys
_GLEB_DIR = Path(__file__).resolve().parent.parent / "backend-gleb"
_gleb_app = None
_gleb_lifespan_cm = None
_gleb_error: Optional[str] = None
try:
    if _GLEB_DIR.exists():
        _sys.path.append(str(_GLEB_DIR))
        os.environ.setdefault(
            "TOPOLOGY_CONFIG", str(_GLEB_DIR / "config" / "station_topology.example.json")
        )
        from src.main import app as _gleb_app, lifespan as _gleb_lifespan  # noqa: E402
        app.mount("/gleb", _gleb_app, name="gleb")
    else:
        _gleb_error = "folder backend-gleb not found"
except Exception as _e:  # модуль не обязателен для демо
    _gleb_error = f"{type(_e).__name__}: {_e}"
    print(f"[GLEB] module not loaded: {_gleb_error}")


@app.get("/api/gleb/health")
async def gleb_health():
    if _gleb_app is None:
        return {"loaded": False, "error": _gleb_error}
    return {"loaded": True, "error": _gleb_error}


@app.on_event("startup")
async def startup() -> None:
    global _gleb_lifespan_cm, _gleb_error
    sim.on_state_update = _on_state
    sim.on_conflict     = _on_conflict
    await sim.start()
    # запустить инициализацию модуля Глеба (lifespan у вложенного приложения сам не вызывается)
    if _gleb_app is not None:
        try:
            _gleb_lifespan_cm = _gleb_lifespan(_gleb_app)
            await _gleb_lifespan_cm.__aenter__()
            print("[GLEB] Railway Station Manager started at /gleb")
        except Exception as e:
            _gleb_error = f"{type(e).__name__}: {e}"
            _gleb_lifespan_cm = None
            print(f"[GLEB] startup failed: {_gleb_error}")


@app.on_event("shutdown")
async def shutdown() -> None:
    await sim.stop()
    if _gleb_lifespan_cm is not None:
        try:
            await _gleb_lifespan_cm.__aexit__(None, None, None)
        except Exception:
            pass


# ─────────────────────────────────────────
#  STATIC: serve HTML
# ─────────────────────────────────────────

BASE_DIR = Path(__file__).parent


@app.get("/dispatcher", include_in_schema=False)
async def serve_dispatcher():
    f = BASE_DIR / "dispatcher.html"
    if f.exists():
        return FileResponse(str(f))
    raise HTTPException(404, "dispatcher.html not found")


@app.get("/", include_in_schema=False)
async def root():
    # Вход в систему начинается с приветствия (часть Саши)
    f = BASE_DIR / "welcome.html"
    if f.exists():
        return FileResponse(str(f))
    return await serve_dispatcher()


@app.get("/admin", include_in_schema=False)
async def serve_admin():
    f = BASE_DIR / "admin.html"
    if f.exists():
        return FileResponse(str(f))
    raise HTTPException(404, "admin.html not found")


@app.get("/admin-login", include_in_schema=False)
async def serve_admin_login():
    f = BASE_DIR / "admin-login.html"
    if f.exists():
        return FileResponse(str(f))
    raise HTTPException(404, "admin-login.html not found")


# ─────────────────────────────────────────
#  REST ENDPOINTS
# ─────────────────────────────────────────

@app.get("/api/state")
async def get_state():
    snap = sim.get_snapshot()
    return JSONResponse(_snapshot_to_dict(snap))


@app.get("/api/history")
async def get_history(offset_sec: int = 60):
    snap = sim.get_history_at(offset_sec)
    if not snap:
        raise HTTPException(404, "No history available yet")
    return JSONResponse(_snapshot_to_dict(snap))


@app.get("/api/conflicts")
async def get_conflicts():
    active = [c for c in sim.conflicts.values() if not c.resolved]
    return JSONResponse([json.loads(c.model_dump_json()) for c in active])


@app.get("/api/ai/{conflict_id}")
async def get_ai_plan(conflict_id: str):
    plan = _ai_cache.get(conflict_id)
    if not plan:
        conflict = sim.conflicts.get(conflict_id)
        if not conflict:
            raise HTTPException(404, f"Conflict {conflict_id} not found")
        snap = sim.get_snapshot()
        plan = await generate_plan(conflict, snap)
        _ai_cache[conflict_id] = plan
    return JSONResponse(json.loads(plan.model_dump_json()))


@app.post("/api/trigger")
async def trigger_event(req: TriggerEventRequest):
    """Inject a manual conflict event for demo purposes."""
    try:
        if req.event_type == "close_track":
            track_id = int(req.target_id) if req.target_id else 3
            conflict  = sim.trigger_close_track(track_id)
        elif req.event_type == "delay_train":
            if req.target_id:
                tid = req.target_id
            else:
                candidates = [t for t in sim.trains.values()
                              if t.delay_min == 0]
                if not candidates:
                    candidates = list(sim.trains.values())
                tid = candidates[0].id if candidates else None
            if not tid:
                raise HTTPException(400, "No trains available")
            conflict = sim.trigger_delay_train(tid, extra_min=10)
        elif req.event_type == "equip_fail":
            conflict = sim.trigger_equipment_fail()
        elif req.event_type == "route_conflict":
            conflict = sim.trigger_route_conflict()
        elif req.event_type == "resource_lack":
            conflict = sim.trigger_resource_lack()
        else:
            raise HTTPException(400, f"Unknown event_type: {req.event_type}")

        return JSONResponse({
            "status":      "triggered",
            "conflict_id": conflict.id,
            "description": conflict.description,
        })
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@app.post("/api/apply_plan")
async def apply_plan(req: ApplyPlanRequest):
    """Validate AI plan option and apply it to the simulator."""
    plan = _ai_cache.get(req.conflict_id)
    if not plan:
        raise HTTPException(404, f"No AI plan for conflict {req.conflict_id}")

    opts = [o for o in plan.options if o.index == req.option_index]
    if not opts:
        raise HTTPException(400, f"Option {req.option_index} not found")
    option = opts[0]

    # validate against current state
    snap = sim.get_snapshot()
    ok, reason = validate_plan(option, snap)
    if not ok:
        sim._log_event(
            EventType.WARNING,
            f"Вариант {req.option_index} отклонён валидатором: {reason}",
        )
        option.target_track_id = None

    sim.apply_plan(
        conflict_id=req.conflict_id,
        action=option.action,
        target_train_id=option.target_train_id,
        target_track_id=option.target_track_id,
        extra_delay_min=option.extra_delay_min,
    )

    await _broadcast({
        "type": "plan_applied",
        "payload": {
            "conflict_id":  req.conflict_id,
            "option_index": req.option_index,
            "option_title": option.title,
            "validated":    ok,
            "reason":       reason,
        },
    })

    new_snap = sim.get_snapshot()
    return JSONResponse({
        "status":         "applied",
        "conflict_id":    req.conflict_id,
        "option_index":   req.option_index,
        "option_title":   option.title,
        "new_efficiency": new_snap.efficiency_pct,
        "validated":      ok,
    })


@app.post("/api/sim/pause")
async def pause_sim():
    sim.pause()
    return {"status": "paused"}


@app.post("/api/sim/resume")
async def resume_sim():
    sim.resume()
    return {"status": "running"}


# ─────────────────────────────────────────
#  WEBSOCKET
# ─────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_clients.add(ws)

    snap = sim.get_snapshot()
    try:
        await ws.send_text(json.dumps({
            "type":    "state",
            "payload": _snapshot_to_dict(snap),
        }, ensure_ascii=False, default=str))

        for cid, plan in _ai_cache.items():
            await ws.send_text(json.dumps({
                "type":    "ai_response",
                "payload": json.loads(plan.model_dump_json()),
            }, ensure_ascii=False))

        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=30)
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
            except asyncio.TimeoutError:
                await ws.send_text(json.dumps({"type": "ping"}))

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        _ws_clients.discard(ws)


# ─────────────────────────────────────────
#  STATIC: все страницы (auth.html, station.html, manager.html, css/, js/ ...)
#  Подключается ПОСЛЕ всех API-маршрутов, чтобы их не перекрывать.
# ─────────────────────────────────────────
_ALLOWED_EXT = {".html", ".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".webp", ".woff", ".woff2", ".json"}


class SafeStatic(StaticFiles):
    """Отдаёт только файлы фронтенда. .env, *.py и скрытые файлы — никогда."""
    async def get_response(self, path, scope):
        parts = Path(path).parts
        if any(p.startswith(".") for p in parts) or (Path(path).suffix and Path(path).suffix.lower() not in _ALLOWED_EXT):
            raise HTTPException(404)
        return await super().get_response(path, scope)


app.mount("/", SafeStatic(directory=str(BASE_DIR), html=True), name="static")


# ─────────────────────────────────────────
#  RUN
# ─────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
