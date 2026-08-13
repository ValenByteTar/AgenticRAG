"""
Capability: memory_read (ADR-0009, ADR-0012).

Lectura de memoria de usuario via MemoryPort o callable inyectado.
Solo lectura; no escribe (write diferido / verificado).
Provenance: cuando se usa MemoryPort, cada record incluye provenance metadata.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Union

from src.kernel.state import ExecutionState

# (query, limit) -> list[dict] con al menos question/answer opcionales
MemoryReadFn = Callable[[str, int], List[Dict[str, Any]]]


class MemoryReadCapability:
    name = "memory_read"

    def __init__(
        self,
        read_fn: Optional[Union[MemoryReadFn, Any]] = None,
        *,
        limit: int = 3,
    ) -> None:
        self._read = read_fn
        self._limit = int(limit)

    def execute(
        self, state: ExecutionState, params: Optional[Dict[str, Any]] = None
    ) -> ExecutionState:
        params = params or {}
        limit = int(params.get("limit", self._limit) or self._limit)
        hits: List[Dict[str, Any]] = []
        if self._read is not None:
            try:
                if hasattr(self._read, "read"):
                    hits = list(self._read.read(state.question, limit) or [])
                else:
                    hits = list(self._read(state.question, limit) or [])
            except Exception as exc:
                state.add_trace("capability.memory_read", f"error:{exc}")
                hits = []
        state.metadata["memory_read"] = True
        state.metadata["memory_hits"] = hits
        state.metadata["memory_hits_count"] = len(hits)
        state.add_trace(
            "capability.memory_read",
            f"n={len(hits)}",
            {"limit": limit},
        )
        return state
