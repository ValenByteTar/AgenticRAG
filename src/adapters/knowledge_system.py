"""
KnowledgeSystemAdapter: implementacion concreta del contrato KnowledgeSystem (ADR-0015).

Envuelve hybrid_search + rerank bajo el contrato.
El esquema interno (entidades, relaciones, provenance, versiones) queda diferido (P11).
Esta es una frontera reservada, no un store plano.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class KnowledgeSystemAdapter:
    """
    Adapter que satisface KnowledgeSystem (ADR-0015) sobre una instancia RAG.

    retrieve() delega a hybrid_search + rerank.
    get_entity() es un stub que retorna None (esquema interno diferido).
    """

    def __init__(self, rag: Any) -> None:
        self._rag = rag

    def retrieve(self, query: str, **kwargs: Any) -> List[Dict[str, Any]]:
        top_k = int(kwargs.get("top_k", 50) or 50)
        semantic_weight = float(kwargs.get("semantic_weight", 0.6) or 0.6)
        try:
            results = self._rag.hybrid_search(
                query, top_k=top_k, semantic_weight=semantic_weight
            ) or []
        except Exception:
            return []
        try:
            if hasattr(self._rag, "_rerank_results"):
                results = self._rag._rerank_results(query, results, top_k=top_k) or results
            else:
                engine = getattr(self._rag, "_retrieval", None)
                if engine is not None and hasattr(engine, "rerank_results"):
                    results = engine.rerank_results(query, results, top_k=top_k) or results
                else:
                    results = list(results)[:top_k]
        except Exception:
            results = list(results)[:top_k]
        return list(results)

    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        return None
