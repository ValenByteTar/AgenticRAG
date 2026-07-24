"""
Policy: gating por senal ASSESS (ADR-0013, ADR-0006).

Si EvaluationSignal(name=assess) fallo -> decline.
No ejecuta capabilities.
"""

from __future__ import annotations

from typing import Optional

from src.kernel.state import ActionDecision, ExecutionState

_DEFAULT_DECLINE = (
    "No se encontro informacion en los documentos para esa consulta."
)


class AssessGatePolicy:
    name = "assess_gate"

    def __init__(self, decline_message: str = _DEFAULT_DECLINE) -> None:
        self._decline_message = decline_message

    def decide(self, state: ExecutionState) -> Optional[ActionDecision]:
        if state.done or state.answer:
            return None
        sig = state.latest_signal("assess")
        if sig is None:
            return None
        if sig.passed is False:
            return ActionDecision(
                action="decline",
                terminate=True,
                reason=sig.reason or "assess_failed",
                params={"message": self._decline_message},
            )
        return None
