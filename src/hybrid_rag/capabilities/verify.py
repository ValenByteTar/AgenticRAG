"""
Capability adapter: verify.

Corre un Evaluator de groundedness (ADR-0006) post-generacion
y adjunta EvaluationSignal al state.
No decide; solo materializa la senal para que Policy la interprete.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol

from src.kernel.state import EvaluationSignal, ExecutionState


class _VerifierProto(Protocol):
    name: str

    def evaluate(self, state: ExecutionState) -> EvaluationSignal:
        ...


class VerifyCapability:
    name = "verify"

    def __init__(self, evaluator: _VerifierProto) -> None:
        if evaluator is None:
            raise ValueError("evaluator es obligatorio")
        self._evaluator = evaluator

    def execute(
        self, state: ExecutionState, params: Optional[Dict[str, Any]] = None
    ) -> ExecutionState:
        signal = self._evaluator.evaluate(state)
        state.add_signal(signal)
        state.metadata["verified"] = True
        state.add_trace(
            "capability.verify",
            signal.reason or ("pass" if signal.passed else "fail"),
            {
                "passed": signal.passed,
                "score": signal.score,
                "metadata": dict(signal.metadata or {}),
            },
        )
        return state
