"""
Tests Fase 3: TwoStageRetrievalCapability + multi-retry + budget.

Valida:
- TwoStageRetrievalCapability ejecuta entity-focused search
- TwoStageRetrievalCapability skipped cuando no entities
- RetrySignalPolicy retry 1 -> retrieval con boost_diversity
- RetrySignalPolicy retry 2 -> two_stage_retrieval con entities
- RetrySignalPolicy respeta budget_exhausted
- RetrySignalPolicy max_retries=2 no excede
- E2E: retrieve -> assess (low coverage) -> retry1 (retrieval) -> assess (still low) -> retry2 (two_stage) -> assess (good) -> generate
- E2E: budget exhausted detiene retry
- AssessGate + RetrySignal + LinearRag interaccion correcta
"""

from __future__ import annotations

from src.kernel.state import EvaluationSignal, ExecutionState, ActionDecision
from src.policies.retry_signal import RetrySignalPolicy
from src.capabilities.two_stage_retrieval import TwoStageRetrievalCapability


# --- TwoStageRetrievalCapability ---

def test_two_stage_retrieval_with_entities():
    calls = {"entity_search": []}

    def entity_search(query, entities, top_k, sw):
        calls["entity_search"].append({"query": query, "entities": entities, "top_k": top_k, "sw": sw})
        return [
            {
                "text": "NIST CSF document " * 10,
                "metadata": {"source": "nist.pdf", "page": 1},
                "hybrid_score": 0.9,
                "rerank_score": 0.85,
                "final_score": 0.88,
            }
        ]

    cap = TwoStageRetrievalCapability(entity_search)
    st = ExecutionState(question="que es NIST?")
    st.entities = ["NIST"]
    st.results = []
    out = cap.execute(st, {"retry_count": 2})

    assert len(out.results) == 1
    assert out.metadata.get("two_stage_executed") is True
    assert out.metadata.get("retry_count") == 2
    assert out.context == ""
    assert "assessed" not in out.metadata
    assert len(calls["entity_search"]) == 1
    assert calls["entity_search"][0]["entities"] == ["NIST"]


def test_two_stage_retrieval_skipped_no_entities():
    def entity_search(query, entities, top_k, sw):
        raise AssertionError("Should not be called without entities")

    cap = TwoStageRetrievalCapability(entity_search)
    st = ExecutionState(question="test")
    st.entities = []
    out = cap.execute(st)

    assert len(out.results) == 0
    assert "two_stage_executed" not in out.metadata


def test_two_stage_retrieval_falls_back_to_classification_entities():
    def entity_search(query, entities, top_k, sw):
        assert "ISO" in entities
        return [{"text": "ISO 27001", "metadata": {"source": "iso.pdf", "page": 1}, "hybrid_score": 0.9}]

    cap = TwoStageRetrievalCapability(entity_search)
    st = ExecutionState(question="que es ISO?")
    st.entities = []
    st.metadata["classification"] = {"entities": ["ISO"]}
    out = cap.execute(st)

    assert len(out.results) == 1
    assert out.metadata.get("two_stage_executed") is True


# --- RetrySignalPolicy multi-retry ---

def test_retry_1_uses_retrieval_with_boost_diversity():
    p = RetrySignalPolicy(max_retries=2)
    st = ExecutionState(question="q")
    st.add_signal(EvaluationSignal(
        name="assess",
        score=0.5,
        passed=True,
        reason="ok",
        metadata={"entity_coverage_low": True, "entity_coverage_ratio": 0.25},
    ))
    d = p.decide(st)
    assert d is not None
    assert d.action == "retry"
    assert d.capability_ref == "retrieval"
    assert d.params["retry_count"] == 1
    assert d.params["boost_diversity"] is True
    assert d.params["relax_entity_filter"] is True


def test_retry_2_uses_two_stage_retrieval():
    p = RetrySignalPolicy(max_retries=2)
    st = ExecutionState(question="q")
    st.entities = ["NIST"]
    st.metadata["retry_count"] = 1
    st.add_signal(EvaluationSignal(
        name="assess",
        score=0.5,
        passed=True,
        reason="ok",
        metadata={"entity_coverage_low": True, "entity_coverage_ratio": 0.25},
    ))
    d = p.decide(st)
    assert d is not None
    assert d.action == "retry"
    assert d.capability_ref == "two_stage_retrieval"
    assert d.params["retry_count"] == 2
    assert d.params["entities"] == ["NIST"]


def test_retry_2_no_entities_falls_back_to_retrieval_widen():
    p = RetrySignalPolicy(max_retries=2)
    st = ExecutionState(question="q")
    st.entities = []
    st.metadata["retry_count"] = 1
    st.add_signal(EvaluationSignal(
        name="assess",
        score=0.5,
        passed=True,
        reason="ok",
        metadata={"source_diversity_low": True, "source_diversity": 1},
    ))
    d = p.decide(st)
    assert d is not None
    assert d.capability_ref == "retrieval"
    assert d.params["widen_top_k"] is True


def test_retry_respects_budget_exhausted():
    p = RetrySignalPolicy(max_retries=2)
    st = ExecutionState(question="q", max_iterations=2, max_llm_calls=6)
    st.iteration = 2
    st.add_signal(EvaluationSignal(
        name="assess",
        score=0.5,
        passed=True,
        reason="ok",
        metadata={"entity_coverage_low": True, "entity_coverage_ratio": 0.25},
    ))
    d = p.decide(st)
    assert d is None


def test_retry_max_retries_2_no_third_retry():
    p = RetrySignalPolicy(max_retries=2)
    st = ExecutionState(question="q")
    st.entities = ["NIST"]
    st.metadata["retry_count"] = 2
    st.add_signal(EvaluationSignal(
        name="assess",
        score=0.5,
        passed=True,
        reason="ok",
        metadata={"entity_coverage_low": True, "entity_coverage_ratio": 0.25},
    ))
    d = p.decide(st)
    assert d is None


# --- E2E multi-retry flow ---

def test_e2e_multi_retry_with_two_stage():
    from src.bootstrap import build_kernel_bundle, new_execution_state
    from src.kernel.observability import InMemoryTraceSink

    call_count = {"retrieve": 0, "two_stage": 0}

    def retrieve(query, top_k, sw):
        call_count["retrieve"] += 1
        # Always returns bad content (retry 1 fallback)
        return [
            {
                "text": "unrelated content " * 20,
                "metadata": {"source": "doc1.pdf", "page": 1},
                "hybrid_score": 0.9,
                "rerank_score": 0.85,
                "final_score": 0.88,
            }
        ]

    def two_stage_retrieve(query, entities, top_k, sw):
        call_count["two_stage"] += 1
        # First call (first pass): bad content; second call (retry 2): good content
        if call_count["two_stage"] == 1:
            return [
                {
                    "text": "unrelated content " * 20,
                    "metadata": {"source": "doc1.pdf", "page": 1},
                    "hybrid_score": 0.9,
                    "rerank_score": 0.85,
                    "final_score": 0.88,
                }
            ]
        return [
            {
                "text": "NIST CSF framework controls evidence " * 10,
                "metadata": {"source": "nist.pdf", "page": 1},
                "hybrid_score": 0.95,
                "rerank_score": 0.90,
                "final_score": 0.92,
            }
        ]

    def build_ctx(q, rs, lm):
        return " ".join(r.get("text", "") for r in rs)[:8000]

    def generate(q, c, lm):
        return "NIST CSF framework controls evidence context"

    def classify(q, lm, top_k):
        return {
            "out_of_domain": False,
            "length_mode": lm,
            "top_k": top_k,
            "entities": ["NIST"],
        }

    def mem_read(q, limit):
        return []

    def finalize(state):
        state.metadata["finalized"] = True

    bundle = build_kernel_bundle(
        retrieve_fn=retrieve,
        build_context_fn=build_ctx,
        generate_fn=generate,
        classify_fn=classify,
        memory_read_fn=mem_read,
        finalize_fn=finalize,
        two_stage_retrieve_fn=two_stage_retrieve,
        trace_sink=InMemoryTraceSink(),
        extras={"max_iterations": 20, "max_llm_calls": 4},
    )
    st = new_execution_state("que es NIST?", use_llm=True, max_iterations=20)
    out = bundle.controller.run(st)

    assert out.done
    assert out.answer == "NIST CSF framework controls evidence context"
    assert out.metadata.get("finalized") is True
    # Two_stage runs on first pass (entities detected) + retry 2; retrieve runs on retry 1
    assert call_count["retrieve"] == 1
    assert call_count["two_stage"] == 2
    assert out.metadata.get("retry_count") == 2

    # Final assess should have good entity coverage
    assess_sigs = [s for s in out.signals if s.name == "assess"]
    final_assess = assess_sigs[-1]
    assert final_assess.passed is True
    assert final_assess.metadata.get("entity_coverage_ratio", 0) > 0.0


def test_e2e_budget_stops_retry():
    from src.bootstrap import build_kernel_bundle, new_execution_state
    from src.kernel.observability import InMemoryTraceSink

    call_count = {"retrieve": 0}

    def retrieve(query, top_k, sw):
        call_count["retrieve"] += 1
        return [
            {
                "text": "unrelated " * 20,
                "metadata": {"source": "doc.pdf", "page": 1},
                "hybrid_score": 0.9,
                "rerank_score": 0.85,
                "final_score": 0.88,
            }
        ]

    def build_ctx(q, rs, lm):
        return " ".join(r.get("text", "") for r in rs)[:8000]

    def generate(q, c, lm):
        return "unrelated content evidence block"

    def classify(q, lm, top_k):
        return {"out_of_domain": False, "length_mode": lm, "top_k": top_k, "entities": ["X"]}

    def mem_read(q, limit):
        return []

    def finalize(state):
        state.metadata["finalized"] = True

    bundle = build_kernel_bundle(
        retrieve_fn=retrieve,
        build_context_fn=build_ctx,
        generate_fn=generate,
        classify_fn=classify,
        memory_read_fn=mem_read,
        finalize_fn=finalize,
        two_stage_retrieve_fn=lambda q, e, tk, sw: [],
        trace_sink=InMemoryTraceSink(),
        extras={"max_iterations": 8, "max_llm_calls": 2},
    )
    st = new_execution_state("test", use_llm=True, max_iterations=8, max_llm_calls=2)
    out = bundle.controller.run(st)

    # Budget should eventually stop the loop
    assert out.done
    # Should not have infinite-looped
    assert call_count["retrieve"] <= 3
