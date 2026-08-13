"""
Policy Engine (ADR-0013).

Evalua policies puras y produce una ActionDecision.
Policies deciden; no ejecutan.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from src.kernel.contracts import Policy
from src.kernel.state import ActionDecision, ExecutionState


class PolicyEngine:
    """
    Motor de policies del Kernel.

    Estrategia: primera policy que devuelve decision no-nula gana
    (orden de registro = prioridad). Policies pequenias y con scope.
    """

    def __init__(self, policies: Optional[Sequence[Policy]] = None) -> None:
        self._policies: List[Policy] = list(policies or [])

    def add(self, policy: Policy) -> None:
        self._policies.append(policy)

    def extend(self, policies: Sequence[Policy]) -> None:
        self._policies.extend(policies)

    def clear(self) -> None:
        self._policies.clear()

    @property
    def policies(self) -> List[Policy]:
        return list(self._policies)

    def decide(self, state: ExecutionState) -> ActionDecision:
        """
        Interpreta senales + estado. Si ninguna policy decide,
        devuelve terminate para garantizar parada (P10).
        """
        if state.budget_exhausted():
            return ActionDecision(
                action="terminate",
                terminate=True,
                reason="budget_exhausted",
            )
        for policy in self._policies:
            decision = policy.decide(state)
            if decision is not None:
                return decision
        return ActionDecision(
            action="terminate",
            terminate=True,
            reason="no_policy_matched",
        )
