"""
Smart Station — AI Planner
Uses Groq API to analyse conflicts and generate structured resolution plans.
AI never writes to simulator directly — it returns a plan, main.py validates it,
then passes it to simulator.apply_plan().
"""
from __future__ import annotations

import json
import os
import random
import time
import uuid
from typing import Optional

from dotenv import load_dotenv
from models import (
    AIResponse, Conflict, ConflictType,
    PlanOption, StationSnapshot, Train, Track,
)

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = "llama-3.3-70b-versatile"   # Groq model id


# ─────────────────────────────────────────
#  GROQ CLIENT (thin async wrapper)
# ─────────────────────────────────────────

async def _call_groq(system_prompt: str, user_prompt: str) -> str:
    """
    Call Groq chat completion API.
    Falls back to deterministic local planner if key is missing or call fails.
    """
    if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key_here":
        raise RuntimeError("No Groq API key — using fallback planner")

    try:
        import httpx
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type":  "application/json",
        }
        body = {
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens":  1024,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise RuntimeError(f"Groq call failed: {exc}") from exc


# ─────────────────────────────────────────
#  SYSTEM PROMPT
# ─────────────────────────────────────────

SYSTEM_PROMPT = """
Ты — интеллектуальный планировщик движения поездов для железнодорожной станции «Алматы-1» (Smart Station, КТЖ).

Твоя задача: получить описание конфликта и текущее состояние станции, 
затем вернуть ровно 3 варианта решения в формате JSON.

Правила:
1. Вернуть ТОЛЬКО валидный JSON без лишнего текста.
2. Структура ответа:
{
  "summary": "краткое описание проблемы (1 предложение)",
  "options": [
    {
      "index": 1,
      "title": "краткое название варианта",
      "description": "подробное объяснение (1-2 предложения)",
      "action": "reroute|wait|reorder|delay",
      "target_train_id": "train_id или null",
      "target_track_id": номер_пути_или_null,
      "extra_delay_min": число_минут,
      "efficiency_pct": число_0_100,
      "risk_level": "low|medium|high"
    }
  ]
}
3. action может быть: reroute (перенаправить поезд), wait (ожидать), reorder (изменить порядок), delay (задержать).
4. Варианты должны быть реалистичными и различаться стратегией.
5. Не выдумывай train_id — используй только те id, что переданы в контексте.
6. efficiency_pct: лучший вариант ~90-96%, худший ~78-86%.
"""


# ─────────────────────────────────────────
#  CONTEXT BUILDER
# ─────────────────────────────────────────

def _build_context(conflict: Conflict, snapshot: StationSnapshot) -> str:
    """Serialize relevant state into a compact text block for the LLM."""
    free_tracks = [t for t in snapshot.tracks if t.status == "Свободен"]
    occupied    = [t for t in snapshot.tracks if t.status == "Занят"]
    trains_info = []
    for t in snapshot.trains[:8]:  # limit tokens
        trains_info.append(
            f"  id={t.id} №{t.number} путь={t.track_id} "
            f"статус={t.status} задержка={t.delay_min}мин скорость={t.speed_kmh}км/ч"
        )

    lines = [
        f"=== КОНФЛИКТ ===",
        f"id: {conflict.id}",
        f"тип: {conflict.type}",
        f"серьёзность: {conflict.severity}",
        f"путь: {conflict.track_id}",
        f"поезд: {conflict.train_id}",
        f"описание: {conflict.description}",
        f"",
        f"=== СОСТОЯНИЕ СТАНЦИИ ===",
        f"поездов всего: {snapshot.total_trains}",
        f"занятых путей: {snapshot.occupied_tracks}",
        f"задержанных: {snapshot.delayed_trains}",
        f"эффективность: {snapshot.efficiency_pct}%",
        f"",
        f"=== ПУТИ ===",
        f"свободные: {[t.id for t in free_tracks]}",
        f"занятые: {[(t.id, t.occupied_by) for t in occupied]}",
        f"",
        f"=== ПОЕЗДА ===",
    ] + trains_info

    return "\n".join(lines)


# ─────────────────────────────────────────
#  FALLBACK PLANNER (no API key needed)
# ─────────────────────────────────────────

def _fallback_plan(conflict: Conflict, snapshot: StationSnapshot) -> AIResponse:
    """
    Deterministic rule-based planner used when Groq is unavailable.
    Produces realistic-looking options based on conflict type.
    """
    train_id = conflict.train_id
    track_id = conflict.track_id
    train    = next((t for t in snapshot.trains if t.id == train_id), None)
    train_num = train.number if train else "N/A"

    free_tracks = [t for t in snapshot.tracks if t.status == "Свободен"]
    alt_track   = free_tracks[0].id if free_tracks else None

    ctype = conflict.type

    if ctype in (ConflictType.TRACK_CLOSED, ConflictType.ROUTE_CONFLICT):
        options = [
            PlanOption(
                index=1,
                title=f"Перенаправить на путь №{alt_track}" if alt_track else "Перенаправить на ближайший свободный",
                description=(
                    f"Перевести поезд №{train_num} на путь №{alt_track}. "
                    f"Минимальная задержка, оптимальный маршрут."
                ) if alt_track else "Перераспределить поезда по свободным путям.",
                action="reroute",
                target_train_id=train_id,
                target_track_id=alt_track,
                extra_delay_min=2,
                efficiency_pct=round(random.uniform(91, 96), 1),
                risk_level="low",
            ),
            PlanOption(
                index=2,
                title="Изменить порядок движения",
                description=(
                    f"Оставить маршрут поезда №{train_num}, "
                    f"скорректировать расписание остальных поездов."
                ),
                action="reorder",
                target_train_id=train_id,
                target_track_id=None,
                extra_delay_min=5,
                efficiency_pct=round(random.uniform(85, 91), 1),
                risk_level="medium",
            ),
            PlanOption(
                index=3,
                title=f"Ожидать освобождения пути №{track_id}",
                description=(
                    f"Держать поезд №{train_num} в режиме ожидания "
                    f"до освобождения пути №{track_id}."
                ),
                action="wait",
                target_train_id=train_id,
                target_track_id=track_id,
                extra_delay_min=8,
                efficiency_pct=round(random.uniform(78, 86), 1),
                risk_level="high",
            ),
        ]
        summary = (
            f"Путь №{track_id} заблокирован. "
            f"Поезд №{train_num} требует перепланирования маршрута."
        )

    elif ctype == ConflictType.DELAY_CASCADE:
        options = [
            PlanOption(
                index=1,
                title="Приоритет экспрессу",
                description="Дать приоритет скоростному поезду, задержать региональные рейсы.",
                action="reorder",
                target_train_id=train_id,
                target_track_id=None,
                extra_delay_min=3,
                efficiency_pct=round(random.uniform(90, 95), 1),
                risk_level="low",
            ),
            PlanOption(
                index=2,
                title="Равномерное распределение",
                description="Равномерно распределить задержку между всеми поездами на станции.",
                action="reorder",
                target_train_id=None,
                target_track_id=None,
                extra_delay_min=5,
                efficiency_pct=round(random.uniform(83, 90), 1),
                risk_level="medium",
            ),
            PlanOption(
                index=3,
                title="Принудительная задержка",
                description=f"Задержать поезд №{train_num} для нормализации расписания.",
                action="delay",
                target_train_id=train_id,
                target_track_id=None,
                extra_delay_min=10,
                efficiency_pct=round(random.uniform(76, 84), 1),
                risk_level="high",
            ),
        ]
        summary = f"Каскадная задержка от поезда №{train_num}. Требуется перераспределение."

    elif ctype == ConflictType.EQUIPMENT_FAIL:
        options = [
            PlanOption(
                index=1,
                title="Технический обход",
                description=f"Вывести все поезда с пути №{track_id}, начать техническое обслуживание.",
                action="reroute",
                target_train_id=train_id,
                target_track_id=alt_track,
                extra_delay_min=4,
                efficiency_pct=round(random.uniform(88, 93), 1),
                risk_level="low",
            ),
            PlanOption(
                index=2,
                title="Режим пониженной скорости",
                description=f"Разрешить движение по пути №{track_id} с ограничением скорости 15 км/ч.",
                action="reorder",
                target_train_id=None,
                target_track_id=track_id,
                extra_delay_min=7,
                efficiency_pct=round(random.uniform(81, 88), 1),
                risk_level="medium",
            ),
            PlanOption(
                index=3,
                title="Закрытие пути",
                description=f"Полное закрытие пути №{track_id} до завершения ремонта.",
                action="wait",
                target_train_id=train_id,
                target_track_id=None,
                extra_delay_min=15,
                efficiency_pct=round(random.uniform(70, 80), 1),
                risk_level="high",
            ),
        ]
        summary = f"Отказ оборудования на пути №{track_id}. Требуется вмешательство."

    else:  # RESOURCE_LACK, SCHEDULE_OVERLAP
        options = [
            PlanOption(
                index=1,
                title="Оптимизация расписания",
                description="Перераспределить поезда по свободным путям, сократить время стоянок.",
                action="reorder",
                target_train_id=None,
                target_track_id=None,
                extra_delay_min=2,
                efficiency_pct=round(random.uniform(89, 95), 1),
                risk_level="low",
            ),
            PlanOption(
                index=2,
                title="Частичная задержка",
                description="Задержать наименее приоритетные поезда для освобождения ресурсов.",
                action="delay",
                target_train_id=train_id,
                target_track_id=None,
                extra_delay_min=6,
                efficiency_pct=round(random.uniform(82, 89), 1),
                risk_level="medium",
            ),
            PlanOption(
                index=3,
                title="Ожидание",
                description="Все прибывающие поезда переводятся в режим ожидания вне станции.",
                action="wait",
                target_train_id=train_id,
                target_track_id=None,
                extra_delay_min=12,
                efficiency_pct=round(random.uniform(72, 82), 1),
                risk_level="high",
            ),
        ]
        summary = "Нехватка ресурсов станции. Требуется оптимизация распределения."

    return AIResponse(
        conflict_id=conflict.id,
        summary=summary,
        options=options,
        model_used="fallback-rule-engine",
    )


# ─────────────────────────────────────────
#  MAIN PLANNER ENTRY POINT
# ─────────────────────────────────────────

async def generate_plan(
    conflict: Conflict,
    snapshot: StationSnapshot,
) -> AIResponse:
    """
    Entry point called by main.py.
    Tries Groq first; falls back to rule-based planner on any error.
    """
    context = _build_context(conflict, snapshot)

    try:
        raw = await _call_groq(SYSTEM_PROMPT, context)
        data = json.loads(raw)

        options = []
        for i, opt in enumerate(data.get("options", [])[:3]):
            options.append(PlanOption(
                index=opt.get("index", i + 1),
                title=opt.get("title", f"Вариант {i+1}"),
                description=opt.get("description", ""),
                action=opt.get("action", "wait"),
                target_train_id=opt.get("target_train_id") or conflict.train_id,
                target_track_id=opt.get("target_track_id"),
                extra_delay_min=int(opt.get("extra_delay_min", 0)),
                efficiency_pct=float(opt.get("efficiency_pct", 85.0)),
                risk_level=opt.get("risk_level", "medium"),
            ))

        return AIResponse(
            conflict_id=conflict.id,
            summary=data.get("summary", "AI проанализировал конфликт."),
            options=options,
            model_used=GROQ_MODEL,
        )

    except Exception as exc:
        print(f"[AI] Groq unavailable ({exc}), using fallback planner")
        return _fallback_plan(conflict, snapshot)


# ─────────────────────────────────────────
#  PLAN VALIDATOR  (called before apply)
# ─────────────────────────────────────────

def validate_plan(
    option: PlanOption,
    snapshot: StationSnapshot,
) -> tuple[bool, str]:
    """
    Returns (is_valid, reason).
    Checks that target train/track actually exist in current snapshot.
    """
    if option.action == "reroute":
        if option.target_train_id:
            train = next((t for t in snapshot.trains
                          if t.id == option.target_train_id), None)
            if not train:
                return False, f"Поезд {option.target_train_id} не найден на станции"
        if option.target_track_id:
            track = next((t for t in snapshot.tracks
                          if t.id == option.target_track_id), None)
            if not track:
                return False, f"Путь №{option.target_track_id} не существует"
            if track.status not in ("Свободен",):
                return False, f"Путь №{option.target_track_id} недоступен (статус: {track.status})"

    elif option.action in ("wait", "delay"):
        if option.target_train_id:
            train = next((t for t in snapshot.trains
                          if t.id == option.target_train_id), None)
            if not train:
                return False, f"Поезд {option.target_train_id} не найден"

    return True, "OK"
