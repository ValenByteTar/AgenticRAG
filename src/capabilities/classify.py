"""
Capability: classify (ADR-0012).

Clasifica la query y escribe metadata en ExecutionState.
No decide el flujo (Policy decide).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from src.kernel.state import ExecutionState

# (question, length_mode, top_k) -> dict de clasificacion
ClassifyFn = Callable[[str, Optional[str], int], Dict[str, Any]]


class ClassifyCapability:
    name = "classify"

    def __init__(self, classify_fn: ClassifyFn) -> None:
        if classify_fn is None:
            raise ValueError("classify_fn es obligatorio")
        self._classify = classify_fn

    def execute(
        self, state: ExecutionState, params: Optional[Dict[str, Any]] = None
    ) -> ExecutionState:
        params = params or {}
        length_mode = params.get("length_mode", state.length_mode)
        top_k = int(params.get("top_k", state.top_k) or state.top_k)
        info = self._classify(state.question, length_mode, top_k) or {}
        state.metadata["classified"] = True
        state.metadata["classification"] = dict(info)
        if info.get("out_of_domain"):
            state.metadata["out_of_domain"] = True
            if info.get("ood_message"):
                state.metadata["ood_message"] = info.get("ood_message")
        if info.get("length_mode") is not None:
            state.length_mode = info.get("length_mode")
        if info.get("top_k") is not None:
            try:
                state.top_k = int(info.get("top_k"))
            except Exception:
                pass
        entities = info.get("entities")
        if entities:
            state.entities = list(entities)
        state.add_trace(
            "capability.classify",
            "ood" if state.metadata.get("out_of_domain") else "ok",
            {
                "length_mode": state.length_mode,
                "top_k": state.top_k,
                "out_of_domain": bool(state.metadata.get("out_of_domain")),
            },
        )
        return state
