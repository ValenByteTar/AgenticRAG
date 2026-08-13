"""
Capability: two_stage_retrieval (ADR-0012, Fase 3).

Two-stage entity search inspirado en el monolito:
- Etapa 1: buscar docs especificos de la entidad
- Etapa 2: buscar respuesta en contexto ampliado + combinar con boost

Se activa cuando retry_signal decide re-retrieval con entity focus.
No conoce HybridRAG; usa callable inyectado (P13).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from src.kernel.state import ExecutionState

# (query, entities, top_k, semantic_weight) -> list[dict]
EntitySearchFn = Callable[[str, List[str], int, float], List[Dict[str, Any]]]


class TwoStageRetrievalCapability:
    name = "two_stage_retrieval"

    def __init__(self, entity_search_fn: EntitySearchFn) -> None:
        if entity_search_fn is None:
            raise ValueError("entity_search_fn es obligatorio")
        self._entity_search = entity_search_fn

    def execute(
        self, state: ExecutionState, params: Optional[Dict[str, Any]] = None
    ) -> ExecutionState:
        params = params or {}
        top_k = int(params.get("top_k", state.top_k) or state.top_k)
        sw = float(params.get("semantic_weight", state.semantic_weight) or state.semantic_weight)
        query = str(params.get("query") or state.question)

        entities = list(params.get("entities") or state.entities or [])
        if not entities:
            cls_meta = state.metadata.get("classification") or {}
            entities = list(cls_meta.get("entities") or [])

        if not entities:
            state.add_trace(
                "capability.two_stage_retrieval",
                "skipped: no entities",
                {"entities": []},
            )
            return state

        # F6: inject expanded_entities into search query
        expanded = state.metadata.get("expanded_entities") or []
        if expanded:
            existing = set(query.lower().split())
            extra = [e for e in expanded if e.lower() not in existing]
            if extra:
                query = f"{query} {' '.join(extra)}"

        results = self._entity_search(query, entities, top_k, sw) or []
        state.results = list(results)

        retry_count = int(params.get("retry_count", state.metadata.get("retry_count", 0)) or 0)
        if "retry_count" in params:
            state.metadata["retry_count"] = retry_count
            state.context = ""
            state.metadata.pop("assessed", None)

        state.metadata["two_stage_executed"] = True
        state.add_trace(
            "capability.two_stage_retrieval",
            f"n={len(state.results)} entities={len(entities)}",
            {
                "top_k": top_k,
                "semantic_weight": sw,
                "entities": entities[:5],
                "retry": bool("retry_count" in params),
            },
        )
        return state
