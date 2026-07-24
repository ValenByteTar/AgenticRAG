"""
Tests Fase 2: ASSESS enriquecido + RetrySignalPolicy.

Valida:
- Entity coverage en metadata del signal
- Source diversity en metadata
- Context density en metadata
- Entity coverage = 0 → hard fail (con floor > 0)
- RetrySignalPolicy activa retry cuando entity_coverage_low
- RetrySignalPolicy no activa retry si ya paso max_retries
- Flujo e2e: assess pass → retry → re-retrieve → re-assess → generate
- AssessGatePolicy sigue funcionando con signals enriquecidos
"""

from __future__ import annotations

from src.evaluation.assess_evidence import (
    AssessEvidenceEvaluator,
    _entity_coverage,
    _source_diversity,
    _context_density,
)
from src.kernel.state import EvaluationSignal, ExecutionState, ActionDecision
from src.policies.assess_gate import AssessGatePolicy
from src.policies.retry_signal import RetrySignalPolicy


# --- Unit tests helpers ---

def test_entity_coverage_full():
    ratio, matched, total = _entity_coverage(
        ["NIST", "ISO 27001"], "NIST CSF and ISO 27001 controls framework"
    )
    assert total == 2
    assert matched == 2
    assert ratio == 1.0


def test_entity_coverage_partial():
    ratio, matched, total = _entity_coverage(
        ["NIST", "PCI DSS"], "NIST CSF framework document"
    )
    assert total == 2
    assert matched == 1
    assert ratio == 0.5


def test_entity_coverage_zero():
    ratio, matched, total = _entity_coverage(
        ["NIST", "ISO"], "completely unrelated text about cooking"
    )
    assert total == 2
    assert matched == 0
    assert ratio == 0.0


def test_entity_coverage_empty_entities():
    ratio, matched, total = _entity_coverage([], "some context")
    assert ratio == 1.0
    assert total == 0


def test_source_diversity_multiple():
    results = [
        {"metadata": {"source": "a.pdf"}},
        {"metadata": {"source": "b.pdf"}},
        {"metadata": {"source": "a.pdf"}},
    ]
    assert _source_diversity(results) == 2


def test_source_diversity_single():
    results = [
        {"metadata": {"source": "a.pdf"}},
        {"metadata": {"source": "a.pdf"}},
    ]
    assert _source_diversity(results) == 1


def test_context_density_basic():
    ctx = "NIST CSF framework controls ISO 27001 security risk management"
    d = _context_density(ctx)
    assert 0.0 < d <= 1.0


def test_context_density_repetitive():
    ctx = "NIST NIST NIST NIST NIST NIST NIST NIST"
    d = _context_density(ctx)
    assert d < 0.2


# --- Evaluator enriched ---

def test_assess_passes_with_enriched_metadata():
    ev = AssessEvidenceEvaluator()
    st = ExecutionState(question="que es nist?")
    st.entities = ["NIST"]
    st.results = [
        {
            "text": "NIST CSF document " * 10,
            "metadata": {"source": "nist.pdf", "page": 1},
            "hybrid_score": 0.9,
            "rerank_score": 0.85,
            "final_score": 0.88,
        }
    ]
    st.context = "NIST CSF framework controls evidence " * 10
    sig = ev.evaluate(st)
    assert sig.passed is True
    meta = sig.metadata
    assert "entity_coverage_ratio" in meta
    assert meta["entity_coverage_ratio"] == 1.0
    assert meta["entity_coverage_matched"] == 1
    assert meta["entity_coverage_total"] == 1
    assert meta["source_diversity"] == 1
    assert "context_density" in meta
    assert "assess_precision_proxy" in meta
    assert meta["entity_coverage_low"] is False


def test_assess_entity_coverage_zero_hard_fail():
    ev = AssessEvidenceEvaluator(entity_coverage_floor=0.01)
    st = ExecutionState(question="que es pci dss?")
    st.entities = ["PCI", "DSS"]
    st.results = [
        {
            "text": "some unrelated text " * 20,
            "metadata": {"source": "doc.pdf", "page": 1},
            "hybrid_score": 0.9,
            "rerank_score": 0.85,
            "final_score": 0.88,
        }
    ]
    st.context = "completely unrelated content about cooking recipes " * 10
    sig = ev.evaluate(st)
    assert sig.passed is False
    assert "entity coverage 0/2" in sig.reason


def test_assess_entity_coverage_zero_no_floor_still_passes():
    ev = AssessEvidenceEvaluator(entity_coverage_floor=0.0)
    st = ExecutionState(question="que es pci dss?")
    st.entities = ["PCI", "DSS"]
    st.results = [
        {
            "text": "some text " * 20,
            "metadata": {"source": "doc.pdf", "page": 1},
            "hybrid_score": 0.9,
            "rerank_score": 0.85,
            "final_score": 0.88,
        }
    ]
    st.context = "completely unrelated content about cooking " * 10
    sig = ev.evaluate(st)
    assert sig.passed is True
    assert sig.metadata["entity_coverage_ratio"] == 0.0
    assert sig.metadata["entity_coverage_low"] is True


def test_assess_source_diversity_low_flag():
    ev = AssessEvidenceEvaluator()
    st = ExecutionState(question="que es iso?")
    st.results = [
        {
            "text": "ISO 27001 controls " * 10,
            "metadata": {"source": "iso.pdf", "page": i},
            "hybrid_score": 0.9,
            "rerank_score": 0.85,
            "final_score": 0.88,
        }
        for i in range(5)
    ]
    st.context = "ISO 27001 security controls framework " * 10
    sig = ev.evaluate(st)
    assert sig.passed is True
    assert sig.metadata["source_diversity"] == 1
    assert sig.metadata["source_diversity_low"] is True


# --- RetrySignalPolicy ---

def test_retry_policy_fires_on_low_entity_coverage():
    p = RetrySignalPolicy(max_retries=1)
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


def test_retry_policy_fires_on_low_diversity():
    p = RetrySignalPolicy(max_retries=1)
    st = ExecutionState(question="q")
    st.add_signal(EvaluationSignal(
        name="assess",
        score=0.5,
        passed=True,
        reason="ok",
        metadata={"source_diversity_low": True, "source_diversity": 1},
    ))
    d = p.decide(st)
    assert d is not None
    assert d.action == "retry"


def test_retry_policy_no_fire_on_good_signals():
    p = RetrySignalPolicy(max_retries=1)
    st = ExecutionState(question="q")
    st.add_signal(EvaluationSignal(
        name="assess",
        score=0.9,
        passed=True,
        reason="ok",
        metadata={"entity_coverage_low": False, "source_diversity_low": False},
    ))
    d = p.decide(st)
    assert d is None


def test_retry_policy_no_fire_on_max_retries():
    p = RetrySignalPolicy(max_retries=1)
    st = ExecutionState(question="q")
    st.metadata["retry_count"] = 1
    st.add_signal(EvaluationSignal(
        name="assess",
        score=0.5,
        passed=True,
        reason="ok",
        metadata={"entity_coverage_low": True, "entity_coverage_ratio": 0.25},
    ))
    d = p.decide(st)
    assert d is None


def test_retry_policy_no_fire_on_assess_fail():
    p = RetrySignalPolicy(max_retries=1)
    st = ExecutionState(question="q")
    st.add_signal(EvaluationSignal(
        name="assess",
        score=0.0,
        passed=False,
        reason="fail",
        metadata={},
    ))
    d = p.decide(st)
    assert d is None


def test_retry_policy_no_fire_when_answer_present():
    p = RetrySignalPolicy(max_retries=1)
    st = ExecutionState(question="q")
    st.answer = "ans"
    st.add_signal(EvaluationSignal(
        name="assess",
        score=0.5,
        passed=True,
        reason="ok",
        metadata={"entity_coverage_low": True},
    ))
    d = p.decide(st)
    assert d is None


# --- E2E retry flow ---

def test_e2e_retry_flow_with_enriched_assess():
    from src.bootstrap import build_kernel_bundle, new_execution_state
    from src.kernel.observability import InMemoryTraceSink

    call_count = {"retrieve": 0}

    def retrieve(query, top_k, sw):
        call_count["retrieve"] += 1
        if call_count["retrieve"] == 1:
            # First pass: good scores but wrong content (entity coverage low)
            return [
                {
                    "text": "unrelated content " * 20,
                    "metadata": {"source": "doc1.pdf", "page": 1},
                    "hybrid_score": 0.9,
                    "rerank_score": 0.85,
                    "final_score": 0.88,
                }
            ]
        # Second pass (retry): now has the entity
        return [
            {
                "text": "NIST CSF framework controls " * 10,
                "metadata": {"source": "nist.pdf", "page": 1},
                "hybrid_score": 0.92,
                "rerank_score": 0.88,
                "final_score": 0.90,
            }
        ]

    def build_ctx(q, rs, lm):
        texts = " ".join(r.get("text", "") for r in rs)
        return texts[:8000]

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

    two_stage_calls = {"n": 0}

    def two_stage_retrieve(query, entities, top_k, sw):
        two_stage_calls["n"] += 1
        if two_stage_calls["n"] == 1:
            # First pass: bad content (triggers retry)
            return [
                {
                    "text": "unrelated content " * 20,
                    "metadata": {"source": "doc1.pdf", "page": 1},
                    "hybrid_score": 0.9,
                    "rerank_score": 0.85,
                    "final_score": 0.88,
                }
            ]
        # Retry 2: good content
        return [
            {
                "text": "NIST CSF framework controls " * 10,
                "metadata": {"source": "nist.pdf", "page": 1},
                "hybrid_score": 0.92,
                "rerank_score": 0.88,
                "final_score": 0.90,
            }
        ]

    bundle = build_kernel_bundle(
        retrieve_fn=retrieve,
        build_context_fn=build_ctx,
        generate_fn=generate,
        classify_fn=classify,
        memory_read_fn=mem_read,
        finalize_fn=finalize,
        two_stage_retrieve_fn=two_stage_retrieve,
        trace_sink=InMemoryTraceSink(),
        extras={"max_iterations": 15, "max_llm_calls": 4},
    )
    st = new_execution_state("que es NIST?", use_llm=True, max_iterations=15)
    out = bundle.controller.run(st)

    assert out.done
    assert out.answer == "NIST CSF framework controls evidence context"
    # Two_stage runs first (entities detected) + retry 2; retrieve runs on retry 1
    assert call_count["retrieve"] == 1
    assert two_stage_calls["n"] == 2
    assert out.metadata.get("retry_count") == 2
    assert out.metadata.get("finalized") is True

    # Check that the final assess signal has good entity coverage
    assess_sigs = [s for s in out.signals if s.name == "assess"]
    assert len(assess_sigs) >= 2
    final_assess = assess_sigs[-1]
    assert final_assess.passed is True
    assert final_assess.metadata.get("entity_coverage_ratio", 0) > 0.0


def test_assess_gate_still_declines_on_hard_fail():
    from src.bootstrap import build_kernel_bundle, new_execution_state
    from src.kernel.observability import InMemoryTraceSink

    def retrieve(query, top_k, sw):
        return [
            {
                "text": "x " * 20,
                "metadata": {"source": "doc.pdf", "page": 1},
                "hybrid_score": 0.1,
                "rerank_score": 0.01,
                "final_score": 0.01,
            }
        ]

    def build_ctx(q, rs, lm):
        return "x " * 50

    def generate(q, c, lm):
        return "SHOULD_NOT_REACH"

    def classify(q, lm, top_k):
        return {"out_of_domain": False, "length_mode": lm, "top_k": top_k}

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
        trace_sink=InMemoryTraceSink(),
        extras={"max_iterations": 12, "max_llm_calls": 4},
    )
    st = new_execution_state("test", use_llm=True, max_iterations=12)
    out = bundle.controller.run(st)

    assert out.done
    assert out.decline
    assert out.answer != "SHOULD_NOT_REACH"
    assert out.metadata.get("finalized") is None
