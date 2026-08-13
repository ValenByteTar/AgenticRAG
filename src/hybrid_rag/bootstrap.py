"""
Composition factory (ADR-0014).

Unico lugar de wiring de implementaciones concretas hacia el Kernel.
No contiene logica de negocio; solo ensambla.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from src.capabilities import (
    AssessCapability,
    BuildContextCapability,
    ClassifyCapability,
    EntityExpansionCapability,
    FinalizeTurnCapability,
    GenerationCapability,
    MemoryReadCapability,
    PlannerCapability,
    RetrievalCapability,
    TwoStageRetrievalCapability,
    VerifyCapability,
)
from src.evaluation.assess_evidence import AssessEvidenceEvaluator
from src.evaluation.verify_groundedness import VerifyGroundednessEvaluator
from src.kernel.composition import CompositionRoot, KernelBundle
from src.kernel.contracts import ModelProvider
from src.kernel.observability import InMemoryTraceSink, TraceSink
from src.kernel.state import ExecutionState
from src.policies.assess_gate import AssessGatePolicy
from src.policies.linear_rag import LinearRagPolicy
from src.policies.retry_signal import RetrySignalPolicy
from src.policies.verify_repair import VerifyRepairPolicy
from src.adapters import KnowledgeSystemAdapter, MemoryPortAdapter


def _default_classify(question: str, length_mode: Optional[str], top_k: int) -> Dict[str, Any]:
    """Classify minimo sin HybridRAG (tests / fallback)."""
    try:
        from query_classifier import QueryClassifier

        ood = bool(QueryClassifier().is_out_of_domain(question or ""))
    except Exception:
        ood = False
    return {
        "out_of_domain": ood,
        "length_mode": length_mode,
        "top_k": top_k,
    }


def build_kernel_bundle(
    *,
    retrieve_fn: Callable[[str, int, float], List[Dict[str, Any]]],
    build_context_fn: Callable[[str, List[Dict[str, Any]], Optional[str]], str],
    generate_fn: Callable[[str, str, Optional[str]], str],
    classify_fn: Optional[Callable[[str, Optional[str], int], Dict[str, Any]]] = None,
    memory_read_fn: Optional[Callable[[str, int], List[Dict[str, Any]]]] = None,
    finalize_fn: Optional[Callable[[ExecutionState], None]] = None,
    two_stage_retrieve_fn: Optional[Callable[[str, List[str], int, float], List[Dict[str, Any]]]] = None,
    assess_evaluator: Any = None,
    verify_evaluator: Any = None,
    memory_port: Any = None,
    knowledge_system: Any = None,
    planner_fn: Any = None,
    entity_expand_fn: Any = None,
    model_provider: Optional[ModelProvider] = None,
    trace_sink: Optional[TraceSink] = None,
    resolver: Any = None,
    extras: Optional[Dict[str, Any]] = None,
) -> KernelBundle:
    """
    Ensambla Registry + policies + Controller (Fase 1.c + Fase 4).

    Cadena policy: AssessGatePolicy -> RetrySignalPolicy -> VerifyRepairPolicy -> LinearRagPolicy.
    Capabilities: classify, memory_read, planner, entity_expansion, retrieval, two_stage_retrieval,
    build_context, assess, generation, verify, finalize_turn.

    Fase 5: memory_port y knowledge_system son adapters opcionales (ADR-0009, ADR-0015).
    Si memory_port se provee, MemoryReadCapability lo usa en lugar del callable.
    Fase 6: planner_fn y entity_expand_fn son opcionales; si no se proveen, se usan defaults deterministas.
    """
    root = CompositionRoot(trace_sink=trace_sink or InMemoryTraceSink())
    root.register_capability(ClassifyCapability(classify_fn or _default_classify))
    mem_read_source = memory_port or memory_read_fn
    root.register_capability(MemoryReadCapability(mem_read_source))
    root.register_capability(PlannerCapability(planner_fn, resolver=resolver))
    root.register_capability(EntityExpansionCapability(entity_expand_fn, resolver=resolver))
    root.register_capability(RetrievalCapability(retrieve_fn, resolver=resolver))
    # F6: always register two_stage_retrieval; fallback delegates to retrieve_fn
    if two_stage_retrieve_fn is not None:
        root.register_capability(TwoStageRetrievalCapability(two_stage_retrieve_fn))
    else:
        def _two_stage_fallback(query: str, entities: list, top_k: int, sw: float):
            return retrieve_fn(query, top_k, sw)
        root.register_capability(TwoStageRetrievalCapability(_two_stage_fallback))
    root.register_capability(BuildContextCapability(build_context_fn))
    root.register_capability(
        AssessCapability(assess_evaluator or AssessEvidenceEvaluator())
    )
    root.register_capability(GenerationCapability(generate_fn))
    root.register_capability(
        VerifyCapability(verify_evaluator or VerifyGroundednessEvaluator())
    )
    root.register_capability(FinalizeTurnCapability(finalize_fn))
    root.add_policy(AssessGatePolicy())
    root.add_policy(RetrySignalPolicy(max_retries=2))
    root.add_policy(VerifyRepairPolicy(max_repairs=1))
    root.add_policy(LinearRagPolicy())
    if model_provider is not None:
        root.set_model_provider(model_provider)
    if extras:
        for k, v in extras.items():
            root.set_extra(k, v)
    return root.build()


def build_kernel_bundle_from_rag(rag: Any, trace_sink: Optional[TraceSink] = None) -> KernelBundle:
    """
    Adapter de conveniencia: extrae callables desde una instancia HybridRAG.

    Vive en el Composition boundary (no en el Kernel). HybridRAG no se importa
    a nivel de modulo para evitar ciclos; se tipa como Any.

    Fase 1.c: retrieve(+sticky+rerank), memory_read, finalize sticky/entities.
    """

    def _retrieve(query: str, top_k: int, semantic_weight: float, **kw: Any) -> List[Dict[str, Any]]:
        sticky_results: List[Dict[str, Any]] = []
        try:
            sticky = getattr(rag, "_sticky_sources", None)
            if sticky and int(sticky.get("ttl", 0) or 0) > 0:
                docs = list(set(sticky.get("sources") or []))[:3]
                for doc_name in docs:
                    try:
                        if hasattr(rag, "_search_in_specific_doc"):
                            sticky_results.extend(
                                rag._search_in_specific_doc(doc_name, top_k=top_k) or []
                            )
                    except Exception:
                        continue
        except Exception:
            sticky_results = []

        try:
            reranker_cfg = (getattr(rag, "config", None) or {}).get("reranker") or {}
            default_pool = int(reranker_cfg.get("candidate_pool", 35) or 35)
        except Exception:
            default_pool = 35

        # Adaptive pool: smaller for simple queries, larger for complex/multi-doc
        ql = (query or "").lower()
        _complex_kw = {"compara", "comparar", "diferencia", "analiza", "explica en detalle", "relaciona"}
        _multi_kw = {" vs ", " versus ", " y ", " entre "}
        is_complex = any(k in ql for k in _complex_kw)
        is_multi = any(k in ql for k in _multi_kw) and is_complex
        if is_multi:
            pool = min(default_pool, 20)
        elif is_complex:
            pool = min(default_pool, 15)
        elif len(ql) < 60:
            pool = min(default_pool, 10)
        else:
            pool = min(default_pool, 15)
        fetch_k = max(int(top_k or 10), pool)
        results = rag.hybrid_search(
            query, top_k=fetch_k, semantic_weight=semantic_weight
        ) or []

        if sticky_results:
            seen = set()
            merged: List[Dict[str, Any]] = []
            for r in list(sticky_results) + list(results):
                md = r.get("metadata") or {}
                key = (str(md.get("source") or "").lower(), md.get("page", 0))
                if key in seen:
                    continue
                seen.add(key)
                merged.append(r)
            results = merged

        try:
            if hasattr(rag, "_rerank_results"):
                results = rag._rerank_results(query, results, top_k=top_k) or results
            else:
                engine = getattr(rag, "_retrieval", None)
                if engine is not None and hasattr(engine, "rerank_results"):
                    results = engine.rerank_results(query, results, top_k=top_k) or results
                else:
                    results = list(results)[: int(top_k or 10)]
        except Exception:
            results = list(results)[: int(top_k or 10)]
        return list(results or [])

    def _two_stage_retrieve(
        query: str, entities: List[str], top_k: int, semantic_weight: float
    ) -> List[Dict[str, Any]]:
        """Two-stage entity search adapter (Fase 3)."""
        try:
            if hasattr(rag, "_two_stage_entity_search"):
                return rag._two_stage_entity_search(query, entities, top_k, semantic_weight) or []
        except Exception:
            pass

        # Fallback: per-entity search + merge (simplified from monolith)
        all_results: List[Dict[str, Any]] = []
        for entity in entities[:3]:
            try:
                entity_query = f"{entity} {query}"
                entity_results = rag.hybrid_search(
                    entity_query, top_k=max(15, top_k // 2), semantic_weight=0.3
                ) or []
                for r in entity_results:
                    text_lower = (r.get("text") or "").lower()
                    src_lower = (r.get("metadata") or {}).get("source", "").lower()
                    if entity.lower() in text_lower or entity.lower() in src_lower:
                        r.setdefault("stage_boost", 1.20)
                        r["hybrid_score"] = r.get("hybrid_score", 0.5) * 1.20
                        all_results.append(r)
            except Exception:
                continue

        # Deduplicate by source+page
        seen = set()
        merged: List[Dict[str, Any]] = []
        for r in all_results:
            md = r.get("metadata") or {}
            key = (str(md.get("source") or "").lower(), md.get("page", 0))
            if key in seen:
                continue
            seen.add(key)
            merged.append(r)

        # Rerank if available
        try:
            if hasattr(rag, "_rerank_results"):
                merged = rag._rerank_results(query, merged, top_k=top_k) or merged
            else:
                engine = getattr(rag, "_retrieval", None)
                if engine is not None and hasattr(engine, "rerank_results"):
                    merged = engine.rerank_results(query, merged, top_k=top_k) or merged
                else:
                    merged = merged[:top_k]
        except Exception:
            merged = merged[:top_k]

        return merged[:top_k] if merged else []

    def _memory_read(query: str, limit: int) -> List[Dict[str, Any]]:
        mem = getattr(rag, "memory", None)
        if mem is None:
            return []
        try:
            if hasattr(mem, "search_memory"):
                return list(mem.search_memory(query, limit=limit) or [])
        except Exception:
            return []
        return []

    def _finalize(state: ExecutionState) -> None:
        try:
            flags = getattr(rag, "flags", None) or {}
            ttl = int(flags.get("sticky_sources_ttl", 2) or 2)
            srcs = []
            for r in state.results or []:
                md = r.get("metadata") or {}
                s = md.get("source") or r.get("source")
                if s:
                    srcs.append(s)
            seen = set()
            uniq = []
            for s in srcs:
                k = str(s).lower()
                if k in seen:
                    continue
                seen.add(k)
                uniq.append(s)
            if uniq:
                setattr(rag, "_sticky_sources", {"sources": uniq[:12], "ttl": ttl})
        except Exception:
            pass
        try:
            if state.entities:
                setattr(rag, "last_entities", list(state.entities))
                setattr(rag, "_sticky_entity", {"name": state.entities[0], "ttl": 3})
        except Exception:
            pass
        try:
            sticky = getattr(rag, "_sticky_sources", None)
            if sticky and int(sticky.get("ttl", 0) or 0) > 0:
                sticky["ttl"] = int(sticky["ttl"]) - 1
                if sticky["ttl"] <= 0:
                    try:
                        delattr(rag, "_sticky_sources")
                    except Exception:
                        pass
                else:
                    setattr(rag, "_sticky_sources", sticky)
        except Exception:
            pass
        try:
            conv = getattr(rag, "conversation", None)
            if conv is not None and hasattr(conv, "add_message"):
                try:
                    conv.add_message("user", state.question)
                    conv.add_message("assistant", state.answer or "")
                except TypeError:
                    pass
        except Exception:
            pass
        state.metadata.setdefault(
            "memory_hits_count",
            len(state.metadata.get("memory_hits") or []),
        )

    def _build_context(
        question: str, results: List[Dict[str, Any]], length_mode: Optional[str]
    ) -> str:
        cb = getattr(rag, "_context_builder", None) or getattr(rag, "context_builder", None)
        if cb is not None:
            for meth in ("build_context", "build_context_from_results"):
                if not hasattr(cb, meth):
                    continue
                fn = getattr(cb, meth)
                try:
                    if meth == "build_context":
                        return fn(question, results, length_mode=length_mode) or ""
                    return fn(results) or ""
                except TypeError:
                    try:
                        return fn(question, results) if meth == "build_context" else fn(results) or ""
                    except Exception:
                        continue
                except Exception:
                    continue
        parts = []
        for i, r in enumerate(results or [], 1):
            text = r.get("document") or r.get("text") or r.get("content") or ""
            src = (r.get("metadata") or {}).get("source") or r.get("source") or ""
            parts.append(f"[{i}] {src}\n{text}")
        return "\n\n".join(parts)

    def _generate(question: str, context: str, length_mode: Optional[str], **stream_kwargs) -> str:
        answer = ""
        stream = stream_kwargs.get("stream", False)
        token_callback = stream_kwargs.get("token_callback")
        cancel_checker = stream_kwargs.get("cancel_checker")
        repair_hint = stream_kwargs.get("repair_hint")

        # Fase 4: repair — prepend instrucciones estrictas al contexto
        if repair_hint and context:
            context = f"[INSTRUCCION DE REPARACION] {repair_hint}\n\n{context}"

        if hasattr(rag, "generate_with_ollama"):
            try:
                answer = rag.generate_with_ollama(
                    question, context, length_mode=length_mode,
                    stream=stream, token_callback=token_callback, cancel_checker=cancel_checker,
                ) or ""
            except TypeError:
                try:
                    answer = rag.generate_with_ollama(
                        query=question, context=context, length_mode=length_mode,
                        stream=stream, token_callback=token_callback, cancel_checker=cancel_checker,
                    ) or ""
                except TypeError:
                    answer = rag.generate_with_ollama(question, context) or ""
        elif getattr(rag, "model_provider", None) is not None:
            prompt = f"Contexto:\n{context}\n\nPregunta: {question}\nRespuesta:"
            answer = rag.model_provider.generate(prompt) or ""

        flags = getattr(rag, "flags", None) or {}
        if flags.get("enable_postprocess", True) and answer:
            try:
                if hasattr(rag, "_postprocess_answer"):
                    answer = rag._postprocess_answer(question, answer, context) or answer
            except Exception:
                pass
        return answer or ""

    def _classify(question: str, length_mode: Optional[str], top_k: int) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "out_of_domain": False,
            "length_mode": length_mode,
            "top_k": top_k,
        }
        try:
            if hasattr(rag, "_is_out_of_domain"):
                info["out_of_domain"] = bool(rag._is_out_of_domain(question))
            elif getattr(rag, "_query_clf", None) is not None:
                info["out_of_domain"] = bool(rag._query_clf.is_out_of_domain(question))
        except Exception:
            info["out_of_domain"] = False
        try:
            if hasattr(rag, "_classify_query"):
                cls = rag._classify_query(question, length_mode, top_k) or {}
                info.update(cls)
                if "length_mode" in cls:
                    info["length_mode"] = cls.get("length_mode")
                if "top_k" in cls:
                    info["top_k"] = cls.get("top_k")
        except Exception:
            pass
        if info.get("out_of_domain"):
            info["ood_message"] = (
                "Lo siento, esta consulta esta fuera del alcance de mi especialidad.\n\n"
                "Puedo responder consultas relacionadas con ciberseguridad, tecnologias "
                "de la informacion y frameworks de seguridad."
            )
        return info

    kcfg = {}
    try:
        kcfg = (getattr(rag, "config", None) or {}).get("kernel") or {}
    except Exception:
        kcfg = {}

    # E4: Warm Artifact resolution — feature flag gated (default: false)
    warm_enabled = bool(
        (getattr(rag, "config", None) or {}).get("knowledge", {}).get(
            "warm_artifacts_enabled", False
        )
    )
    resolver = None
    if warm_enabled:
        try:
            from src.adapters import WarmArtifactResolver

            registry_root = (
                (getattr(rag, "config", None) or {})
                .get("knowledge", {})
                .get("registry_root", "knowledge_artifacts")
            )
            from src.artifact_registry.registry import ArtifactRegistry

            registry = ArtifactRegistry(registry_root)
            resolver = WarmArtifactResolver.from_registry(
                registry,
                confidence_threshold=float(
                    (getattr(rag, "config", None) or {})
                    .get("knowledge", {})
                    .get("confidence_threshold", 0.0)
                ),
            )
        except Exception:
            resolver = None

    mem = getattr(rag, "memory", None)
    memory_port = MemoryPortAdapter(mem) if mem is not None else None
    knowledge_system = KnowledgeSystemAdapter(rag, resolver=resolver)

    # F6: wire entity_extractor + memory.get_synonyms as expand_fn
    entity_extractor = getattr(rag, "entity_extractor", None)
    entity_aliases = getattr(rag, "entity_aliases", None) or {}

    def _expand_entities(question: str, entities: list) -> list:
        from src.capabilities.entity_expansion import _DEFAULT_ALIASES
        expanded = set()
        for e in (entities or []):
            el = e.lower().strip()
            expanded.add(el)
            # 1. Try rag's entity_aliases gazetteer
            if el in entity_aliases:
                expanded.update(entity_aliases[el])
            # 2. Try default gazetteer (Fase 6 hardcoded aliases)
            if el in _DEFAULT_ALIASES:
                expanded.update(_DEFAULT_ALIASES[el])
            # 3. Try memory.get_synonyms
            if mem is not None and hasattr(mem, "get_synonyms"):
                try:
                    synonyms = mem.get_synonyms(e) or []
                    expanded.update(s.lower().strip() for s in synonyms)
                except Exception:
                    pass
            # 4. Try entity_extractor domain_entities
            if entity_extractor is not None:
                try:
                    de = getattr(entity_extractor, "domain_entities", {}) or {}
                    if el in de:
                        canonical, _ = de[el]
                        expanded.add(canonical)
                except Exception:
                    pass
        return list(expanded)

    # F6: wire doc_roles + select_docs_by_roles as planner_fn
    doc_roles = getattr(rag, "doc_roles", None) or {}
    use_doc_roles = bool((getattr(rag, "config", None) or {}).get("use_doc_roles", True))

    def _planner_fn(question: str, entities: list) -> dict:
        from src.capabilities.planner import PlannerCapability
        # Get default plan from deterministic planner
        cap = PlannerCapability()
        plan = cap._default_plan(question, entities or [])
        # If rag has doc_roles, use select_docs_by_roles for candidate_docs
        if use_doc_roles and doc_roles and isinstance(doc_roles, dict) and doc_roles.get("docs"):
            try:
                from doc_cards import select_docs_by_roles
                candidates = select_docs_by_roles(
                    doc_roles,
                    preferred_roles=plan.get("doc_roles_preferred", []),
                    entities=entities or [],
                    limit=60,
                )
                if candidates:
                    plan["candidate_docs"] = candidates
            except Exception:
                pass
        return plan

    return build_kernel_bundle(
        retrieve_fn=_retrieve,
        build_context_fn=_build_context,
        generate_fn=_generate,
        classify_fn=_classify,
        memory_read_fn=_memory_read,
        finalize_fn=_finalize,
        two_stage_retrieve_fn=_two_stage_retrieve,
        assess_evaluator=AssessEvidenceEvaluator(),
        verify_evaluator=VerifyGroundednessEvaluator(),
        memory_port=memory_port,
        knowledge_system=knowledge_system,
        planner_fn=_planner_fn if (use_doc_roles and doc_roles) else None,
        entity_expand_fn=_expand_entities,
        model_provider=getattr(rag, "model_provider", None),
        trace_sink=trace_sink,
        resolver=resolver,
        extras={
            "max_iterations": int(kcfg.get("max_iterations", 12) or 12),
            "max_llm_calls": int(kcfg.get("max_llm_calls", 6) or 6),
        },
    )


def new_execution_state(
    question: str,
    *,
    top_k: int = 50,
    semantic_weight: float = 0.6,
    use_llm: bool = True,
    length_mode: Optional[str] = None,
    max_iterations: int = 10,
    max_llm_calls: int = 6,
) -> ExecutionState:
    """Factory de ExecutionState con defaults de consulta (ADR-0004 / ADR-0010 / ADR-0020)."""
    st = ExecutionState(
        question=question,
        top_k=top_k,
        semantic_weight=semantic_weight,
        use_llm=use_llm,
        length_mode=length_mode,
        max_iterations=max_iterations,
        max_llm_calls=max_llm_calls,
    )
    st.metadata["state_fidelity"] = "full"
    return st
