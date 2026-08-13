"""
Capability: finalize_turn (Fase 1.c).

Actualiza sticky sources / last_entities en el host via callable.
No escribe memoria de aprendizaje (ADR-0009 write diferido).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from src.kernel.state import ExecutionState

# (state) -> None  side-effect controlado en Composition boundary
FinalizeFn = Callable[[ExecutionState], None]


class FinalizeTurnCapability:
    name = "finalize_turn"

    def __init__(self, finalize_fn: Optional[FinalizeFn] = None) -> None:
        self._finalize = finalize_fn

    def execute(
        self, state: ExecutionState, params: Optional[Dict[str, Any]] = None
    ) -> ExecutionState:
        if self._finalize is not None:
            try:
                self._finalize(state)
            except Exception as exc:
                state.add_trace("capability.finalize_turn", f"error:{exc}")
                state.metadata["finalized"] = True
                return state
        state.metadata["finalized"] = True
        # memory_hits count for facade
        if "memory_hits_count" in state.metadata:
            pass
        state.add_trace("capability.finalize_turn", "ok")
        return state
