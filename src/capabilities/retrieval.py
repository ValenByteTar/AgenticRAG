"""
Capability: retrieval (ADR-0012).

Envuelve la busqueda hibrida existente via callable inyectado (P13).
No conoce HybridRAG ni el Controller.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from src.kernel.state import ExecutionState

# (query, top_k, semantic_weight, **kwargs) -> list[dict]
# kwargs may include allowed_sources: List[str] for doc scoping
RetrieveFn = Callable[..., List[Dict[str, Any]]]


class RetrievalCapability:
    name = "retrieval"

    def __init__(self, retrieve_fn: RetrieveFn, *, resolver: Any = None) -> None:
        if retrieve_fn is None:
            raise ValueError("retrieve_fn es obligatorio")
        self._retrieve = retrieve_fn
        self._resolver = resolver

    def execute(
        self, state: ExecutionState, params: Optional[Dict[str, Any]] = None
    ) -> ExecutionState:
        params = params or {}
        top_k = int(params.get("top_k", state.top_k) or state.top_k)
        sw = float(params.get("semantic_weight", state.semantic_weight) or state.semantic_weight)
        query = str(params.get("query") or state.question)

        # F3: widen_top_k on retry to cast a wider net
        if params.get("widen_top_k"):
            top_k = int(top_k * 1.5)

        # F3: boost_diversity lowers semantic_weight to favor lexical diversity
        if params.get("boost_diversity"):
            sw = max(0.3, sw - 0.15)

        # F6: inject expanded_entities into search query (closes data flow from EntityExpansionCapability)
        expanded = state.metadata.get("expanded_entities") or []
        if expanded:
            existing = set(query.lower().split())
            extra = [e for e in expanded if e.lower() not in existing]
            if extra:
                query = f"{query} {' '.join(extra)}"

        # F6: retrieve (query may now contain expanded entity aliases)
        results = self._retrieve(query, top_k, sw) or []

        # F6: soft boost for candidate_docs from planner (preference, not filter)
        candidate_docs = state.metadata.get("candidate_docs") or []
        if candidate_docs and results:
            candidate_set = {str(c).lower() for c in candidate_docs}
            for r in results:
                md = r.get("metadata") or {}
                src = str(md.get("source") or "").lower()
                if src in candidate_set:
                    base_score = r.get("final_score") or r.get("rerank_score") or r.get("hybrid_score") or 0.0
                    r["final_score"] = base_score + 0.05  # small boost
            results.sort(key=lambda r: r.get("final_score", 0), reverse=True)

        # E4: entity_index boost — boost results from docs associated with entities
        entity_doc_boost = False
        if self._resolver is not None and results:
            entity_doc_ids = set()
            for e in (state.entities or []):
                eid = self._resolver.resolve_alias(e)
                if eid:
                    entity_doc_ids.update(self._resolver.get_docs_for_entity(eid))
                else:
                    entity = self._resolver.get_entity_by_name(e)
                    if entity:
                        entity_doc_ids.update(
                            self._resolver.get_docs_for_entity(entity.get("entity_id", ""))
                        )
            if entity_doc_ids:
                entity_doc_lower = {d.lower() for d in entity_doc_ids}
                for r in results:
                    md = r.get("metadata") or {}
                    src = str(md.get("source") or "").lower()
                    if src in entity_doc_lower:
                        base_score = (
                            r.get("final_score")
                            or r.get("rerank_score")
                            or r.get("hybrid_score")
                            or 0.0
                        )
                        r["final_score"] = base_score + 0.03
                        entity_doc_boost = True
                if entity_doc_boost:
                    results.sort(key=lambda r: r.get("final_score", 0), reverse=True)

        state.results = list(results)
        state.metadata["retrieval_executed"] = True

        # F2: retry limpia estado stale para que build_context y assess re-executen
        if "retry_count" in params:
            state.metadata["retry_count"] = int(params.get("retry_count") or 0)
            state.context = ""
            state.metadata.pop("assessed", None)
            state.metadata.pop("retrieval_executed", None)

        state.add_trace(
            "capability.retrieval",
            f"n={len(state.results)}",
            {
                "top_k": top_k,
                "semantic_weight": sw,
                "retry": bool("retry_count" in params),
                "widen_top_k": bool(params.get("widen_top_k")),
                "boost_diversity": bool(params.get("boost_diversity")),
                "doc_boosted": bool(candidate_docs),
                "query_expanded": bool(expanded),
                "entity_doc_boost": entity_doc_boost,
            },
        )
        return state
