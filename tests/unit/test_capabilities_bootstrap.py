"""
Tests de capabilities + bootstrap (pre-Fase 1).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.bootstrap import build_kernel_bundle, new_execution_state
from src.capabilities import (
    BuildContextCapability,
    GenerationCapability,
    RetrievalCapability,
)
from src.kernel import CompositionRoot, ExecutionState, InMemoryTraceSink
from src.policies import LinearRagPolicy


def test_retrieval_capability_injects_results():
    def retrieve(q, top_k, sw):
        assert q == "iso"
        assert top_k == 5
        return [{"text": "a", "metadata": {"source": "s.pdf"}}]

    cap = RetrievalCapability(retrieve)
    st = ExecutionState(question="iso", top_k=5)
    out = cap.execute(st)
    assert len(out.results) == 1
    assert out.results[0]["metadata"]["source"] == "s.pdf"


def test_build_context_and_generation_capabilities():
    bc = BuildContextCapability(lambda q, rs, lm: f"CTX:{len(rs)}:{lm}")
    gen = GenerationCapability(lambda q, c, lm: f"ANS:{c}")
    st = ExecutionState(question="q", results=[{"t": 1}], use_llm=True, length_mode="long")
    st = bc.execute(st)
    assert st.context == "CTX:1:long"
    st = gen.execute(st)
    assert st.answer == "ANS:CTX:1:long"
    assert st.llm_calls == 1


def test_generation_extractive_without_llm():
    gen = GenerationCapability(lambda q, c, lm: "should_not_run")
    st = ExecutionState(question="q", context="hello world " * 50, use_llm=False)
    st = gen.execute(st)
    assert st.answer.startswith("hello")
    assert st.llm_calls == 0


def test_bootstrap_build_kernel_bundle_e2e():
    def retrieve(q, top_k, sw):
        return [
            {
                "document": "doc text enough context for assess gate to pass factual checks",
                "metadata": {"source": "a.pdf", "page": 1},
                "hybrid_score": 0.8,
                "rerank_score": 0.7,
                "final_score": 0.75,
            }
        ]

    def build_ctx(q, rs, lm):
        return (
            "CONTEXT_BODY with sufficient length for assess. "
            "NIST CSF framework controls and ISO 27001 requirements documented here. "
            * 3
        )

    def generate(q, c, lm):
        assert "CONTEXT_BODY" in c
        return "NIST CSF framework controls and ISO 27001 requirements documented in CONTEXT_BODY evidence"

    def classify(q, lm, top_k):
        return {"out_of_domain": False, "length_mode": lm, "top_k": top_k}

    bundle = build_kernel_bundle(
        retrieve_fn=retrieve,
        build_context_fn=build_ctx,
        generate_fn=generate,
        classify_fn=classify,
        trace_sink=InMemoryTraceSink(),
    )
    st = new_execution_state("que es nist?", top_k=10, use_llm=True, max_iterations=12)
    out = bundle.controller.run(st)
    assert out.done
    assert out.answer.startswith("NIST CSF framework")
    assert "CONTEXT_BODY" in out.context
    assert out.results
    names = set(bundle.registry.names())
    assert names == {
        "assess",
        "build_context",
        "classify",
        "entity_expansion",
        "finalize_turn",
        "generation",
        "memory_read",
        "planner",
        "retrieval",
        "two_stage_retrieval",
        "verify",
    }
    assert out.metadata.get("assessed") is True
    assert out.metadata.get("memory_read") is True
    assert out.metadata.get("finalized") is True
    assert out.latest_signal("assess") is not None
    assert out.latest_signal("assess").passed is True


def test_bootstrap_from_rag_adapter():
    class FakeRag:
        def __init__(self):
            self.model_provider = None
            self.config = {
                "kernel": {"max_iterations": 12, "max_llm_calls": 4},
                "reranker": {"candidate_pool": 5},
            }
            self.flags = {"enable_postprocess": False}
            self.memory = None
            self._sticky_sources = None
            self.last_entities = []

        def hybrid_search(self, query, top_k=50, semantic_weight=0.6):
            return [
                {
                    "document": "evidence context documented requirements controls " * 10,
                    "metadata": {"source": "s"},
                    "hybrid_score": 0.9,
                    "rerank_score": 0.8,
                    "final_score": 0.85,
                }
            ]

        def _rerank_results(self, query, results, top_k=10):
            return list(results)[:top_k]

        def generate_with_ollama(self, *args, **kwargs):
            q = args[0] if args else kwargs.get("query") or kwargs.get("question") or ""
            ctx = args[1] if len(args) > 1 else kwargs.get("context", "")
            # Return answer with overlap to context for verify groundedness
            return f"R:{q[:10]} evidence context documented requirements controls"

        def _is_out_of_domain(self, q):
            return False

        def _classify_query(self, q, lm, top_k):
            return {"length_mode": lm, "top_k": top_k}

    from src.bootstrap import build_kernel_bundle_from_rag

    bundle = build_kernel_bundle_from_rag(FakeRag())
    st = new_execution_state("pregunta", use_llm=True, max_iterations=12)
    out = bundle.controller.run(st)
    assert out.done
    assert out.answer.startswith("R:")
    assert out.metadata.get("finalized") is True

