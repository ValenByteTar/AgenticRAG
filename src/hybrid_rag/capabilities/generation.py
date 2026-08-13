"""
Capability: generation (ADR-0012).

Genera respuesta via callable inyectado (tipicamente HybridRAG.generate_with_ollama
o ModelProvider). No instancia dependencias (P13).

Fase 3: soporta streaming via token_callback y cancel_checker pasados desde ExecutionState.
Fase 4: soporta repair via repair_hint en params (re-generacion con instrucciones estrictas).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from src.kernel.state import ExecutionState

# (question, context, length_mode, **kwargs) -> str
GenerateFn = Callable[..., str]


class GenerationCapability:
    name = "generation"

    def __init__(self, generate_fn: GenerateFn) -> None:
        if generate_fn is None:
            raise ValueError("generate_fn es obligatorio")
        self._generate = generate_fn

    def execute(
        self, state: ExecutionState, params: Optional[Dict[str, Any]] = None
    ) -> ExecutionState:
        params = params or {}
        if not state.use_llm and not params.get("force"):
            # Sin LLM: respuesta extractiva minima a partir del contexto
            state.answer = (state.context or "")[:2000]
            state.add_trace("capability.generation", "extractive_no_llm")
            return state

        length_mode = params.get("length_mode", state.length_mode)
        stream_kwargs: Dict[str, Any] = {}
        if state.token_callback is not None:
            stream_kwargs["token_callback"] = state.token_callback
        if state.cancel_checker is not None:
            stream_kwargs["cancel_checker"] = state.cancel_checker
        if stream_kwargs:
            stream_kwargs["stream"] = True

        # Fase 4: repair hint para re-generacion
        repair_hint = params.get("repair_hint")
        if repair_hint:
            stream_kwargs["repair_hint"] = repair_hint
            # Reset verified para que verify se re-ejecute tras repair
            state.metadata["verified"] = False
            state.metadata["repair_count"] = params.get("repair_count", 1)

        try:
            answer = self._generate(
                state.question, state.context or "", length_mode, **stream_kwargs
            ) or ""
        except TypeError:
            # Fallback: generate_fn no acepta kwargs extras
            try:
                answer = self._generate(
                    state.question, state.context or "", length_mode,
                    **{k: v for k, v in stream_kwargs.items() if k in ("stream", "token_callback", "cancel_checker")}
                ) or ""
            except TypeError:
                answer = self._generate(state.question, state.context or "", length_mode) or ""

        state.answer = answer
        state.llm_calls = int(state.llm_calls or 0) + 1
        state.add_trace(
            "capability.generation",
            f"chars={len(state.answer)}",
            {
                "llm_calls": state.llm_calls,
                "length_mode": length_mode,
                "streaming": bool(stream_kwargs),
                "repair": bool(repair_hint),
            },
        )
        return state
