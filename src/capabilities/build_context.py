"""
Capability: build_context (ADR-0012).

Construye el string de contexto a partir de results via callable inyectado.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from src.kernel.state import ExecutionState

# (question, results, length_mode) -> str
BuildContextFn = Callable[[str, List[Dict[str, Any]], Optional[str]], str]


class BuildContextCapability:
    name = "build_context"

    def __init__(self, build_fn: BuildContextFn) -> None:
        if build_fn is None:
            raise ValueError("build_fn es obligatorio")
        self._build = build_fn

    def execute(
        self, state: ExecutionState, params: Optional[Dict[str, Any]] = None
    ) -> ExecutionState:
        params = params or {}
        length_mode = params.get("length_mode", state.length_mode)
        ctx = self._build(state.question, state.results or [], length_mode) or ""
        # Prefijo compacto de memory hits (paridad monolito: memory antes del corpus)
        hits = state.metadata.get("memory_hits") or []
        if hits:
            try:
                mem_lines = []
                for i, m in enumerate(hits[:5], 1):
                    q = str(m.get("question") or "")[:50]
                    a = str(m.get("answer") or m.get("text") or "")[:150]
                    mem_lines.append(f"[MEM{i}] Q:{q} A:{a}")
                if mem_lines:
                    ctx = "\n".join(mem_lines) + "\n---\n" + ctx
            except Exception:
                pass
        state.context = ctx
        state.add_trace(
            "capability.build_context",
            f"chars={len(state.context)}",
            {
                "length_mode": length_mode,
                "memory_hits": int(state.metadata.get("memory_hits_count") or 0),
            },
        )
        return state
