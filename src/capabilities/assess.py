"""
Capability adapter: assess.

Corre un Evaluator (ADR-0006) y adjunta EvaluationSignal al state.
No decide; solo materializa la senal para que Policy la interprete.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol

from src.kernel.state import EvaluationSignal, ExecutionState


class _EvaluatorProto(Protocol):
    name: str

    def evaluate(self, state: ExecutionState) -> EvaluationSignal:
        ...


class AssessCapability:
    name = "assess"

    def __init__(self, evaluator: _EvaluatorProto) -> None:
        if evaluator is None:
            raise ValueError("evaluator es obligatorio")
        self._evaluator = evaluator

    def execute(
        self, state: ExecutionState, params: Optional[Dict[str, Any]] = None
    ) -> ExecutionState:
        signal = self._evaluator.evaluate(state)
        state.add_signal(signal)
        state.metadata["assessed"] = True
        state.add_trace(
            "capability.assess",
            signal.reason or ("pass" if signal.passed else "fail"),
            {
                "passed": signal.passed,
                "score": signal.score,
                "metadata": dict(signal.metadata or {}),
            },
        )
        return state
