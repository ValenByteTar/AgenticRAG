"""
Tests Fase 6: Planner + Entity Expansion + Tunings.

Cobertura:
  1. PlannerCapability: deteccion de tipo de query, roles, semantic_weight.
  2. EntityExpansionCapability: expansion con gazetteer, dedup, sin entidades.
  3. E2E: cadena completa con planner + entity_expansion.
  4. Tuning: adaptive reranker pool.
  5. Tuning: repair_hint mejorado.
  6. Tuning: groundedness floor ajustado.
"""

from __future__ import annotations

from src.capabilities.entity_expansion import EntityExpansionCapability
from src.capabilities.planner import PlannerCapability
from src.kernel.state import ExecutionState, EvaluationSignal
from src.bootstrap import build_kernel_bundle, new_execution_state
from src.kernel.observability import InMemoryTraceSink
from src.policies.verify_repair import VerifyRepairPolicy
from src.evaluation.verify_groundedness import VerifyGroundednessEvaluator


# ---------------------------------------------------------------------------
# 1. PlannerCapability
# ---------------------------------------------------------------------------


class TestPlannerCapability:

    def test_conceptual_query(self):
        cap = PlannerCapability()
        st = ExecutionState(question="que es NIST CSF?", entities=["NIST"])
        out = cap.execute(st)
        assert out.metadata["planned"] is True
        plan = out.metadata["plan"]
        assert plan["is_conceptual"] is True
        assert plan["is_comparison"] is False
        assert "analysis" in plan["doc_roles_preferred"]
        assert out.semantic_weight == 0.7

    def test_comparison_query(self):
        cap = PlannerCapability()
        st = ExecutionState(question="compara ISO 27001 con NIST CSF", entities=["ISO 27001", "NIST CSF"])
        out = cap.execute(st)
        plan = out.metadata["plan"]
        assert plan["is_comparison"] is True
        assert plan["is_multi_doc"] is True
        assert "entity_profile" in plan["doc_roles_preferred"]
        assert out.semantic_weight == 0.5

    def test_procedural_query(self):
        cap = PlannerCapability()
        st = ExecutionState(question="como implementar ISO 27001?", entities=["ISO 27001"])
        out = cap.execute(st)
        plan = out.metadata["plan"]
        assert plan["is_procedural"] is True
        assert "guide" in plan["doc_roles_preferred"]
        assert out.semantic_weight == 0.5

    def test_simple_numeric_query(self):
        cap = PlannerCapability()
        st = ExecutionState(question="cuantos controles tiene ISO 27001?", entities=["ISO 27001"])
        out = cap.execute(st)
        plan = out.metadata["plan"]
        assert plan["is_simple_numeric"] is True
        assert out.semantic_weight == 0.4

    def test_no_entities_default_roles(self):
        cap = PlannerCapability()
        st = ExecutionState(question="lista todos los frameworks")
        out = cap.execute(st)
        plan = out.metadata["plan"]
        assert "list" in plan["doc_roles_preferred"]

    def test_does_not_override_top_k(self):
        cap = PlannerCapability()
        st = ExecutionState(question="que es NIST?", top_k=5)
        out = cap.execute(st)
        assert out.top_k == 5  # top_k preserved

    def test_custom_planner_fn(self):
        def custom_fn(q, ents):
            return {"doc_roles_preferred": ["custom_role"], "semantic_weight": 0.55, "is_comparison": False}
        cap = PlannerCapability(planner_fn=custom_fn)
        st = ExecutionState(question="q")
        out = cap.execute(st)
        assert out.metadata["plan"]["doc_roles_preferred"] == ["custom_role"]
        assert out.semantic_weight == 0.55


# ---------------------------------------------------------------------------
# 2. EntityExpansionCapability
# ---------------------------------------------------------------------------


class TestEntityExpansionCapability:

    def test_expand_iso_27001(self):
        cap = EntityExpansionCapability()
        st = ExecutionState(question="que es ISO 27001?", entities=["ISO 27001"])
        out = cap.execute(st)
        expanded = out.metadata["expanded_entities"]
        assert "iso 27001" in expanded
        assert "iso27001" in expanded
        assert "iso 27k" in expanded
        assert "isms" in expanded

    def test_expand_nist_csf(self):
        cap = EntityExpansionCapability()
        st = ExecutionState(question="que es NIST CSF?", entities=["NIST CSF"])
        out = cap.execute(st)
        expanded = out.metadata["expanded_entities"]
        assert "nist csf" in expanded
        assert "nist cybersecurity framework" in expanded

    def test_no_entities(self):
        cap = EntityExpansionCapability()
        st = ExecutionState(question="lista todos los frameworks")
        out = cap.execute(st)
        assert out.metadata["entity_expansion"] is True
        assert out.metadata["expanded_entities"] == []

    def test_dedup(self):
        cap = EntityExpansionCapability()
        st = ExecutionState(question="q", entities=["ISO 27001", "iso 27001"])
        out = cap.execute(st)
        expanded = out.metadata["expanded_entities"]
        # Should dedup case-insensitive
        lowered = [e.lower() for e in expanded]
        assert len(lowered) == len(set(lowered))

    def test_custom_expand_fn(self):
        def custom_fn(q, ents):
            return ents + ["custom_alias"]
        cap = EntityExpansionCapability(expand_fn=custom_fn)
        st = ExecutionState(question="q", entities=["NIST"])
        out = cap.execute(st)
        assert "custom_alias" in out.metadata["expanded_entities"]

    def test_unknown_entity_passthrough(self):
        cap = EntityExpansionCapability()
        st = ExecutionState(question="q", entities=["UnknownEntity"])
        out = cap.execute(st)
        assert "unknownentity" in out.metadata["expanded_entities"]


# ---------------------------------------------------------------------------
# 3. E2E: cadena completa con planner + entity_expansion
# ---------------------------------------------------------------------------


class TestE2EPlannerEntityExpansion:

    def test_full_chain_with_planner_and_expansion(self):
        def retrieve(q, top_k, sw):
            return [{"text": "NIST CSF ISO 27001 cybersecurity controls evidence " * 10,
                      "metadata": {"source": "nist.pdf", "page": 1},
                      "hybrid_score": 0.9, "rerank_score": 0.85, "final_score": 0.88}]

        def build_ctx(q, rs, lm):
            return " ".join(r.get("text", "") for r in rs)[:8000]

        def generate(q, c, lm, **kw):
            return "NIST CSF framework controls evidence cybersecurity"

        def classify(q, lm, top_k):
            return {"out_of_domain": False, "length_mode": lm, "top_k": top_k, "entities": ["NIST CSF"]}

        def finalize(state):
            state.metadata["finalized"] = True

        bundle = build_kernel_bundle(
            retrieve_fn=retrieve,
            build_context_fn=build_ctx,
            generate_fn=generate,
            classify_fn=classify,
            finalize_fn=finalize,
            trace_sink=InMemoryTraceSink(),
            extras={"max_iterations": 15, "max_llm_calls": 4},
        )
        st = new_execution_state("que es NIST CSF?", use_llm=True, max_iterations=15)
        out = bundle.controller.run(st)

        assert out.done
        assert out.metadata.get("planned") is True
        assert out.metadata.get("entity_expansion") is True
        assert out.metadata.get("finalized") is True
        # Entity expansion should have expanded NIST CSF
        expanded = out.metadata.get("expanded_entities") or []
        assert "nist cybersecurity framework" in expanded

    def test_comparison_query_gets_lower_semantic_weight(self):
        def retrieve(q, top_k, sw):
            return [{"text": "ISO 27001 NIST CSF comparison controls evidence " * 10,
                      "metadata": {"source": "comp.pdf", "page": 1},
                      "hybrid_score": 0.9, "rerank_score": 0.85, "final_score": 0.88}]

        def build_ctx(q, rs, lm):
            return " ".join(r.get("text", "") for r in rs)[:8000]

        def generate(q, c, lm, **kw):
            return "ISO 27001 NIST CSF comparison controls evidence framework"

        def classify(q, lm, top_k):
            return {"out_of_domain": False, "length_mode": lm, "top_k": top_k, "entities": ["ISO 27001", "NIST CSF"]}

        def finalize(state):
            state.metadata["finalized"] = True

        bundle = build_kernel_bundle(
            retrieve_fn=retrieve,
            build_context_fn=build_ctx,
            generate_fn=generate,
            classify_fn=classify,
            finalize_fn=finalize,
            trace_sink=InMemoryTraceSink(),
            extras={"max_iterations": 15, "max_llm_calls": 4},
        )
        st = new_execution_state("compara ISO 27001 con NIST CSF", use_llm=True, max_iterations=15)
        out = bundle.controller.run(st)

        assert out.done
        assert out.metadata.get("is_comparison") is True
        # semantic_weight should be 0.5 for comparison
        plan = out.metadata.get("plan") or {}
        assert plan.get("semantic_weight") == 0.5


# ---------------------------------------------------------------------------
# 4. Tuning: adaptive reranker pool
# ---------------------------------------------------------------------------


class TestAdaptiveRerankerPool:

    def test_short_query_smaller_pool(self):
        from src.bootstrap import build_kernel_bundle_from_rag

        class FakeRag:
            def __init__(self):
                self.model_provider = None
                self.memory = None
                self.flags = {"enable_postprocess": False, "sticky_sources_ttl": 2}
                self.config = {"kernel": {"max_iterations": 12, "max_llm_calls": 4},
                               "reranker": {"candidate_pool": 35}}
                self.last_entities = []
                self._sticky_sources = None
                self.calls = []

            def hybrid_search(self, query, top_k=50, semantic_weight=0.6):
                self.calls.append(f"hybrid:{top_k}")
                return [{"text": "NIST CSF framework controls evidence " * 10,
                          "metadata": {"source": "nist.pdf", "page": 1},
                          "hybrid_score": 0.9, "rerank_score": 0.85, "final_score": 0.88}]

            def _rerank_results(self, query, results, top_k=10):
                self.calls.append(f"rerank:{top_k}")
                return list(results)[:top_k]

            def generate_with_ollama(self, *args, **kwargs):
                return "NIST CSF framework controls evidence cybersecurity"

            def _is_out_of_domain(self, q):
                return False

            def _classify_query(self, q, lm, top_k):
                return {"length_mode": lm, "top_k": top_k, "out_of_domain": False, "entities": []}

        rag = FakeRag()
        bundle = build_kernel_bundle_from_rag(rag)
        st = new_execution_state("que es nist?", top_k=5, use_llm=True, max_iterations=12)
        out = bundle.controller.run(st)
        assert out.done
        # Short query (<60 chars) -> pool=min(35,10)=10, fetch_k=max(5,10)=10
        assert any(c.startswith("hybrid:10") for c in rag.calls)


# ---------------------------------------------------------------------------
# 5. Tuning: repair_hint mejorado
# ---------------------------------------------------------------------------


class TestRepairHintImproved:

    def test_repair_hint_contains_directed_instructions(self):
        policy = VerifyRepairPolicy()
        hint = policy._repair_hint
        assert "REPARACION REQUERIDA" in hint
        assert "Instrucciones dirigidas" in hint
        assert "no hay informacion suficiente" in hint
        assert "Cita fuentes" in hint
        assert "[Conocimiento general]" in hint


# ---------------------------------------------------------------------------
# 6. Tuning: groundedness floor ajustado
# ---------------------------------------------------------------------------


class TestGroundednessFloorAdjusted:

    def test_default_floor_is_025(self):
        evaluator = VerifyGroundednessEvaluator()
        assert evaluator._groundedness_floor == 0.25

    def test_floor_025_allows_borderline_answer(self):
        evaluator = VerifyGroundednessEvaluator()
        # Create a state with ratio between 0.25 and 0.3
        st = ExecutionState(question="q")
        st.answer = "NIST CSF framework controls evidence cybersecurity"
        st.context = "NIST CSF framework controls evidence cybersecurity " * 5
        st.results = [{"text": "test", "metadata": {"source": "s.pdf"}}]
        sig = evaluator.evaluate(st)
        # Should pass because ratio >= 0.25
        assert sig.passed is True


# ---------------------------------------------------------------------------
# 7. Integration: entity_extractor + memory.get_synonyms wiring
# ---------------------------------------------------------------------------


class TestEntityExtractorWiring:

    def test_expand_fn_uses_rag_entity_aliases(self):
        from src.bootstrap import build_kernel_bundle_from_rag

        class FakeRag:
            def __init__(self):
                self.model_provider = None
                self.memory = None
                self.flags = {"enable_postprocess": False, "sticky_sources_ttl": 2}
                self.config = {"kernel": {"max_iterations": 12, "max_llm_calls": 4},
                               "reranker": {"candidate_pool": 5}}
                self.last_entities = []
                self._sticky_sources = None
                self.entity_aliases = {
                    "iso 27001": ["iso 27001", "iso27001", "iso 27k", "isms"],
                }
                self.entity_extractor = None

            def hybrid_search(self, query, top_k=50, semantic_weight=0.6, **kw):
                return [{"text": "ISO 27001 controls evidence " * 10,
                          "metadata": {"source": "iso.pdf", "page": 1},
                          "hybrid_score": 0.9, "rerank_score": 0.85, "final_score": 0.88}]

            def _rerank_results(self, query, results, top_k=10):
                return list(results)[:top_k]

            def generate_with_ollama(self, *args, **kwargs):
                return "ISO 27001 controls evidence framework"

            def _is_out_of_domain(self, q):
                return False

            def _classify_query(self, q, lm, top_k):
                return {"length_mode": lm, "top_k": top_k, "out_of_domain": False, "entities": ["ISO 27001"]}

        rag = FakeRag()
        bundle = build_kernel_bundle_from_rag(rag)
        st = new_execution_state("que es ISO 27001?", use_llm=True, max_iterations=12)
        out = bundle.controller.run(st)

        assert out.done
        expanded = out.metadata.get("expanded_entities") or []
        assert "iso27001" in expanded
        assert "iso 27k" in expanded
        assert "isms" in expanded

    def test_expand_fn_uses_memory_synonyms(self):
        from src.bootstrap import build_kernel_bundle_from_rag

        class FakeMem:
            def search_memory(self, query, limit=5):
                return []
            def get_synonyms(self, term):
                if "nist" in term.lower():
                    return ["nist", "national institute of standards and technology"]
                return [term]
            def add_knowledge(self, *a, **k):
                pass

        class FakeRag:
            def __init__(self):
                self.model_provider = None
                self.memory = FakeMem()
                self.flags = {"enable_postprocess": False, "sticky_sources_ttl": 2}
                self.config = {"kernel": {"max_iterations": 12, "max_llm_calls": 4},
                               "reranker": {"candidate_pool": 5}}
                self.last_entities = []
                self._sticky_sources = None
                self.entity_aliases = {}
                self.entity_extractor = None

            def hybrid_search(self, query, top_k=50, semantic_weight=0.6, **kw):
                return [{"text": "NIST CSF framework controls evidence " * 10,
                          "metadata": {"source": "nist.pdf", "page": 1},
                          "hybrid_score": 0.9, "rerank_score": 0.85, "final_score": 0.88}]

            def _rerank_results(self, query, results, top_k=10):
                return list(results)[:top_k]

            def generate_with_ollama(self, *args, **kwargs):
                return "NIST CSF framework controls evidence cybersecurity"

            def _is_out_of_domain(self, q):
                return False

            def _classify_query(self, q, lm, top_k):
                return {"length_mode": lm, "top_k": top_k, "out_of_domain": False, "entities": ["NIST"]}

        rag = FakeRag()
        bundle = build_kernel_bundle_from_rag(rag)
        st = new_execution_state("que es NIST?", use_llm=True, max_iterations=12)
        out = bundle.controller.run(st)

        assert out.done
        expanded = out.metadata.get("expanded_entities") or []
        assert "national institute of standards and technology" in expanded


# ---------------------------------------------------------------------------
# 8. Integration: doc_roles + candidate_docs wiring
# ---------------------------------------------------------------------------


class TestDocRolesWiring:

    def test_planner_fn_produces_candidate_docs(self):
        from src.bootstrap import build_kernel_bundle_from_rag

        class FakeRag:
            def __init__(self):
                self.model_provider = None
                self.memory = None
                self.flags = {"enable_postprocess": False, "sticky_sources_ttl": 2}
                self.config = {"kernel": {"max_iterations": 12, "max_llm_calls": 4},
                               "reranker": {"candidate_pool": 5}, "use_doc_roles": True}
                self.last_entities = []
                self._sticky_sources = None
                self.entity_aliases = {}
                self.entity_extractor = None
                self.doc_roles = {
                    "docs": {
                        "doc:iso-27001": {"role": "entity_profile", "name": "ISO 27001", "centrality": 0.8, "entities_index": ["iso 27001"], "canonical_doc_id": "doc:iso-27001"},
                        "doc:nist-csf": {"role": "analysis", "name": "NIST CSF", "centrality": 0.7, "entities_index": ["nist csf"], "canonical_doc_id": "doc:nist-csf"},
                        "doc:procedures": {"role": "guide", "name": "Procedures", "centrality": 0.5, "entities_index": [], "canonical_doc_id": "doc:procedures"},
                    }
                }
                self.search_calls = []

            def hybrid_search(self, query, top_k=50, semantic_weight=0.6, **kw):
                self.search_calls.append({"query": query})
                return [{"text": "ISO 27001 NIST CSF controls evidence " * 10,
                          "metadata": {"source": "iso27001.pdf", "page": 1},
                          "hybrid_score": 0.9, "rerank_score": 0.85, "final_score": 0.88}]

            def _rerank_results(self, query, results, top_k=10):
                return list(results)[:top_k]

            def generate_with_ollama(self, *args, **kwargs):
                return "ISO 27001 NIST CSF controls evidence framework"

            def _is_out_of_domain(self, q):
                return False

            def _classify_query(self, q, lm, top_k):
                return {"length_mode": lm, "top_k": top_k, "out_of_domain": False, "entities": ["ISO 27001"]}

        rag = FakeRag()
        bundle = build_kernel_bundle_from_rag(rag)
        st = new_execution_state("que es ISO 27001?", use_llm=True, max_iterations=12)
        out = bundle.controller.run(st)

        assert out.done
        # Planner should have produced candidate_docs
        candidate_docs = out.metadata.get("candidate_docs")
        assert candidate_docs is not None
        assert len(candidate_docs) > 0
        # doc:iso-27001 should be in candidates (entity_profile role matches, canonical_doc_id key)
        assert "doc:iso-27001" in candidate_docs
        # hybrid_search should have been called (no hard scoping, soft boost only)
        assert len(rag.search_calls) > 0

    def test_doc_roles_disabled_when_use_doc_roles_false(self):
        from src.bootstrap import build_kernel_bundle_from_rag

        class FakeRag:
            def __init__(self):
                self.model_provider = None
                self.memory = None
                self.flags = {"enable_postprocess": False, "sticky_sources_ttl": 2}
                self.config = {"kernel": {"max_iterations": 12, "max_llm_calls": 4},
                               "reranker": {"candidate_pool": 5}, "use_doc_roles": False}
                self.last_entities = []
                self._sticky_sources = None
                self.entity_aliases = {}
                self.entity_extractor = None
                self.doc_roles = {"docs": {"iso27001.pdf": {"role": "entity_profile", "centrality": 0.8}}}

            def hybrid_search(self, query, top_k=50, semantic_weight=0.6, **kw):
                return [{"text": "ISO 27001 controls evidence " * 10,
                          "metadata": {"source": "iso27001.pdf", "page": 1},
                          "hybrid_score": 0.9, "rerank_score": 0.85, "final_score": 0.88}]

            def _rerank_results(self, query, results, top_k=10):
                return list(results)[:top_k]

            def generate_with_ollama(self, *args, **kwargs):
                return "ISO 27001 controls evidence framework"

            def _is_out_of_domain(self, q):
                return False

            def _classify_query(self, q, lm, top_k):
                return {"length_mode": lm, "top_k": top_k, "out_of_domain": False, "entities": ["ISO 27001"]}

        rag = FakeRag()
        bundle = build_kernel_bundle_from_rag(rag)
        st = new_execution_state("que es ISO 27001?", use_llm=True, max_iterations=12)
        out = bundle.controller.run(st)

        assert out.done
        # candidate_docs should NOT be set when use_doc_roles is False
        assert out.metadata.get("candidate_docs") is None
