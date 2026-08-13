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
    get_entity() resuelve contra canonical_entities + entity_index del
    WarmArtifactResolver cuando esta disponible (E4). Si no hay resolver,
    retorna None (fallback al comportamiento anterior).
    """

    def __init__(self, rag: Any, resolver: Any = None) -> None:
        self._rag = rag
        self._resolver = resolver

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
        """Resolve an entity by name or alias via WarmArtifactResolver (E4).

        Tries alias resolution first, then canonical name lookup.
        Returns the canonical entity dict with associated doc_ids from
        entity_index, or ``None`` if no resolver or entity not found.
        """
        if self._resolver is None:
            return None
        try:
            eid = self._resolver.resolve_alias(entity_id)
            entity = None
            if eid:
                entity = self._resolver.get_entity_by_id(eid)
            if entity is None:
                entity = self._resolver.get_entity_by_name(entity_id)
            if entity is None:
                return None
            result = dict(entity)
            eid = result.get("entity_id", "")
            if eid:
                doc_ids = self._resolver.get_docs_for_entity(eid)
                if doc_ids:
                    result["doc_ids"] = doc_ids
            return result
        except Exception:
            return None
