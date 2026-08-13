"""
Capability: planner (ADR-0012, Fase 6).

Planner determinista que analiza la query y produce un plan de retrieval:
  - detecta tipo de query (conceptual, procedural, comparison, simple_numeric)
  - asigna roles preferidos para scoping de documentos
  - detecta queries comparativas para balancear busqueda entre entidades
  - ajusta top_k y semantic_weight segun tipo de query

No usa LLM. Determinista basado en keywords y entidades.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from src.kernel.state import ExecutionState

PlannerFn = Callable[[str, List[str]], Dict[str, Any]]

_COMPLEX_KEYWORDS = {
    "compara", "comparar", "comparacion", "diferencia", "diferencias",
    "analiza", "analizar", "explica en detalle", "explica detalladamente",
    "relaciona", "relacion",
}

_COMPARISON_KEYWORDS = {
    "compara", "comparar", "comparacion", "diferencia", "diferencias",
    "vs", "versus",
}

_PROCEDURAL_KEYWORDS = {
    "como", "implementar", "configurar", "instalar", "audito", "auditar",
    "pasos", "procedimiento", "guia", "guía",
}

_CONCEPTUAL_KEYWORDS = {
    "que es", "que son", "define", "definicion", "concepto",
    "significa", "sigla", "acronimo",
}

_NUMERIC_KEYWORDS = {
    "cuant", "numero", "número", "version", "versión", "cvss", "severidad",
    "total", "cantidad",
}


class PlannerCapability:
    name = "planner"

    def __init__(self, planner_fn: Optional[PlannerFn] = None, *, resolver: Any = None) -> None:
        self._planner_fn = planner_fn
        self._resolver = resolver

    def execute(
        self, state: ExecutionState, params: Optional[Dict[str, Any]] = None
    ) -> ExecutionState:
        if self._planner_fn is not None:
            try:
                plan = self._planner_fn(state.question, list(state.entities or [])) or {}
            except Exception as exc:
                state.add_trace("capability.planner", f"error:{exc}")
                plan = self._default_plan(state.question, state.entities)
        else:
            plan = self._default_plan(state.question, state.entities)

        # E4: if resolver is available and no custom planner_fn provided candidate_docs,
        # use compiled doc_roles from WarmArtifactResolver
        if (
            self._resolver is not None
            and not plan.get("candidate_docs")
            and plan.get("doc_roles_preferred")
        ):
            try:
                candidates = self._resolver.get_candidate_docs(
                    preferred_roles=plan["doc_roles_preferred"],
                    entities=list(state.entities or []),
                    limit=60,
                )
                if candidates:
                    plan["candidate_docs"] = candidates
            except Exception:
                pass

        state.metadata["planned"] = True
        state.metadata["plan"] = plan

        # Aplicar ajustes de retrieval desde el plan
        # top_k no se overridea: el retrieval adapter ya maneja fetch_k=max(top_k, pool)
        if plan.get("semantic_weight") is not None:
            state.semantic_weight = float(plan["semantic_weight"])
        if plan.get("is_comparison"):
            state.metadata["is_comparison"] = True
        if plan.get("is_multi_doc"):
            state.metadata["is_multi_doc"] = True
        if plan.get("doc_roles_preferred"):
            state.metadata["doc_roles_preferred"] = plan["doc_roles_preferred"]
        if plan.get("candidate_docs"):
            state.metadata["candidate_docs"] = plan["candidate_docs"]

        state.add_trace(
            "capability.planner",
            f"roles={plan.get('doc_roles_preferred', [])}",
            {
                "is_comparison": plan.get("is_comparison", False),
                "is_multi_doc": plan.get("is_multi_doc", False),
                "semantic_weight": plan.get("semantic_weight"),
            },
        )
        return state

    def _default_plan(self, question: str, entities: List[str]) -> Dict[str, Any]:
        ql = (question or "").lower()
        n_entities = len(entities or [])

        is_comparison = any(k in ql for k in _COMPARISON_KEYWORDS) and (
            " con " in ql or " y " in ql or " vs " in ql or " versus " in ql
        )
        is_conceptual = any(k in ql for k in _CONCEPTUAL_KEYWORDS)
        is_procedural = any(k in ql for k in _PROCEDURAL_KEYWORDS)
        is_simple_numeric = any(k in ql for k in _NUMERIC_KEYWORDS)
        is_complex = any(k in ql for k in _COMPLEX_KEYWORDS)
        is_multi_doc = is_comparison or (is_complex and n_entities >= 2)

        # Roles preferidos (v2 taxonomy: list, entity_profile, guide, reference, analysis, other)
        if is_comparison:
            preferred = ["entity_profile", "analysis"]
        elif is_conceptual:
            preferred = ["analysis", "entity_profile"]
        elif is_procedural:
            preferred = ["guide", "analysis"]
        elif is_simple_numeric:
            preferred = ["analysis", "entity_profile"]
        elif n_entities > 0:
            preferred = ["entity_profile", "list"]
        else:
            preferred = ["list", "analysis"]

        # Ajustes de retrieval: solo semantic_weight (top_k lo maneja el retrieval adapter)
        semantic_weight = 0.6

        if is_multi_doc:
            semantic_weight = 0.5  # mas keyword para multi-doc
        elif is_simple_numeric:
            semantic_weight = 0.4  # mas keyword para numerico
        elif is_conceptual:
            semantic_weight = 0.7  # mas semantico para conceptual
        elif is_procedural:
            semantic_weight = 0.5

        return {
            "doc_roles_preferred": preferred,
            "is_comparison": is_comparison,
            "is_multi_doc": is_multi_doc,
            "is_conceptual": is_conceptual,
            "is_procedural": is_procedural,
            "is_simple_numeric": is_simple_numeric,
            "semantic_weight": semantic_weight,
        }
