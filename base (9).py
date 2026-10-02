from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseAgent(ABC):
    """Abstract base class for all AI agents.

    Concrete agents receive a specialised Decision Context and return
    a structured Decision / Plan object.  The actual LLM call (or stub)
    is hidden behind this interface.
    """

    @abstractmethod
    def evaluate(self, context: Any) -> Any:
        """Evaluate the given context and return a structured decision.

        Args:
            context: A specialised context object (AcceptanceDecisionContext,
                     ServicePlanningContext, etc.)

        Returns:
            A structured decision / plan object (AcceptanceDecision,
            MaintenancePlan, etc.)
        """
        ...
