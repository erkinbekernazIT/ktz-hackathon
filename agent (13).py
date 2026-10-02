from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from src.agents.base import BaseAgent
from src.agents.acceptance.context import AcceptanceDecisionContext
from src.agents.acceptance.decision import (
    AcceptanceAction,
    AcceptanceDecision,
    RequiredAction,
    TrainImpact,
)
from src.domain.types import TrackId, TrainId
from src.infrastructure.llm.client import LLMClient, LLMError, create_llm_client

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a railway station dispatcher assistant (AcceptanceDecisionAgent).
Analyse the acceptance context and choose the best action among the
pre-computed candidate routes. You MUST NOT invent routes that are not
listed — pick by zero-based index from candidate_routes.

Respond with a single JSON object only (no markdown), schema:
{
  "recommended_action": "Accept" | "AcceptWithConditions" | "Delay" | "Reject" | "NeedMoreInformation",
  "selected_route_index": <int or null>,
  "reasoning": "<string>",
  "expected_impact": [{"train_id": "<id>", "impact_description": "<str>", "delay_minutes": <int>}],
  "required_actions": [{"action_type": "<str>", "description": "<str>", "target_entity": "<str>", "priority": <int>}]
}
"""


class AcceptanceAgent(BaseAgent):
    """Acceptance Decision Agent backed by Groq LLM (with deterministic fallback).

    - Empty candidate_routes → NO_FEASIBLE_ROUTE (no LLM call).
    - Otherwise → LLM chooses among candidates; on LLM failure → NEED_MORE_INFORMATION.
    - Pass ``use_llm=False`` or a stub client for offline / tests.
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        *,
        use_llm: bool = True,
    ) -> None:
        if llm_client is not None:
            self._llm = llm_client
        elif use_llm:
            self._llm = create_llm_client()
        else:
            self._llm = create_llm_client(use_stub=True)

    def evaluate(self, context: AcceptanceDecisionContext) -> AcceptanceDecision:  # type: ignore[override]
        now = datetime.now(timezone.utc)

        if not context.candidate_routes:
            return AcceptanceDecision(
                train_id=context.train.train_id,
                timestamp=now,
                recommended_action=AcceptanceAction.NO_FEASIBLE_ROUTE,
                reasoning="No feasible routes available",
                identified_conflicts=[],
                expected_impact=[],
                alternatives=[],
                required_actions=[],
            )

        from src.infrastructure.llm.client import LLMClientStub

        if isinstance(self._llm, LLMClientStub):
            return self._stub_evaluate(context, now)

        try:
            return self._llm_evaluate(context, now)
        except (LLMError, ValueError, KeyError, json.JSONDecodeError) as exc:
            logger.error("AcceptanceAgent LLM evaluation failed: %s", exc)
            return AcceptanceDecision(
                train_id=context.train.train_id,
                timestamp=now,
                recommended_action=AcceptanceAction.NEED_MORE_INFORMATION,
                reasoning=f"LLM unavailable or returned invalid output: {exc}",
                identified_conflicts=[],
                expected_impact=[],
                alternatives=list(context.candidate_routes),
                required_actions=[
                    RequiredAction(
                        action_type="NotifyDispatcher",
                        description="Manual acceptance review required — LLM failed",
                        priority=1,
                    )
                ],
            )

    def _llm_evaluate(
        self, context: AcceptanceDecisionContext, now: datetime
    ) -> AcceptanceDecision:
        prompt = self._build_prompt(context)
        raw = self._llm.complete(
            prompt,
            system=_SYSTEM_PROMPT,
            response_json=True,
            temperature=0.1,
        )
        data = json.loads(raw)
        return self._parse_decision(data, context, now)

    def _stub_evaluate(
        self, context: AcceptanceDecisionContext, now: datetime
    ) -> AcceptanceDecision:
        best = context.candidate_routes[0]
        return AcceptanceDecision(
            train_id=context.train.train_id,
            timestamp=now,
            recommended_action=AcceptanceAction.ACCEPT,
            selected_route=best.route,
            receiving_track_id=best.receiving_track_id,
            time_window=best.time_window,
            reasoning=(
                f"Selected route {best.route.id!r} with feasibility score "
                f"{best.feasibility_score:.2f} [STUB]"
            ),
            identified_conflicts=[],
            expected_impact=[],
            alternatives=list(context.candidate_routes[1:]),
            required_actions=[],
        )

    def _build_prompt(self, context: AcceptanceDecisionContext) -> str:
        candidates = []
        for i, cr in enumerate(context.candidate_routes):
            candidates.append(
                {
                    "index": i,
                    "route_id": str(cr.route.id),
                    "path": [str(t) for t in cr.route.path],
                    "receiving_track_id": str(cr.receiving_track_id),
                    "feasibility_score": cr.feasibility_score,
                    "time_window": {
                        "start": cr.time_window.start.isoformat(),
                        "end": cr.time_window.end.isoformat(),
                    },
                    "projected_consequences": cr.projected_consequences,
                }
            )

        payload = {
            "train": {
                "train_id": str(context.train.train_id),
                "train_type": context.train.train_type.value,
                "length_m": context.train.length_m,
                "weight_t": context.train.weight_t,
                "priority": context.train.priority,
                "eta": context.eta.isoformat(),
            },
            "train_status": context.train_state.status.value,
            "free_tracks": [str(t) for t in context.free_tracks],
            "blocked_elements": list(context.blocked_elements),
            "candidate_routes": candidates,
        }
        return (
            "Evaluate train acceptance and return JSON per the schema.\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

    def _parse_decision(
        self,
        data: dict,
        context: AcceptanceDecisionContext,
        now: datetime,
    ) -> AcceptanceDecision:
        action_raw = data.get("recommended_action", "NeedMoreInformation")
        try:
            action = AcceptanceAction(action_raw)
        except ValueError:
            action = AcceptanceAction.NEED_MORE_INFORMATION

        selected_route = None
        receiving_track_id = None
        time_window = None
        alternatives = list(context.candidate_routes)

        idx = data.get("selected_route_index")
        if idx is not None and action in (
            AcceptanceAction.ACCEPT,
            AcceptanceAction.ACCEPT_WITH_CONDITIONS,
        ):
            idx = int(idx)
            if 0 <= idx < len(context.candidate_routes):
                chosen = context.candidate_routes[idx]
                selected_route = chosen.route
                receiving_track_id = chosen.receiving_track_id
                time_window = chosen.time_window
                alternatives = [
                    cr for i, cr in enumerate(context.candidate_routes) if i != idx
                ]

        impact = []
        for item in data.get("expected_impact") or []:
            impact.append(
                TrainImpact(
                    train_id=TrainId(str(item.get("train_id", ""))),
                    impact_description=str(item.get("impact_description", "")),
                    delay_minutes=int(item.get("delay_minutes", 0)),
                )
            )

        required = []
        for item in data.get("required_actions") or []:
            required.append(
                RequiredAction(
                    action_type=str(item.get("action_type", "")),
                    description=str(item.get("description", "")),
                    target_entity=str(item.get("target_entity", "")),
                    priority=int(item.get("priority", 5)),
                )
            )

        return AcceptanceDecision(
            train_id=context.train.train_id,
            timestamp=now,
            recommended_action=action,
            selected_route=selected_route,
            receiving_track_id=receiving_track_id
            if receiving_track_id is not None
            else (TrackId(str(data["receiving_track_id"])) if data.get("receiving_track_id") else None),
            time_window=time_window,
            reasoning=str(data.get("reasoning", "")),
            identified_conflicts=[],
            expected_impact=impact,
            alternatives=alternatives,
            required_actions=required,
        )
