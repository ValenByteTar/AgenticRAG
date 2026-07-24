"""
Tests Fase 4: VERIFY (groundedness + citation fidelity) + VerifyRepairPolicy.

Cobertura:
  1. VerifyGroundednessEvaluator: groundedness, hedge, citations.
  2. VerifyCapability: adapter produce senal y marca metadata.
  3. VerifyRepairPolicy: repair budget, decline, bypass on pass.
  4. E2E: pipeline completo con verify + repair.
  5. LinearRagPolicy: verify en cadena.
"""

from __future__ import annotations

from src.evaluation.verify_groundedness import VerifyGroundednessEvaluator
from src.capabilities.verify import VerifyCapability
from src.policies.verify_repair import VerifyRepairPolicy
from src.policies.linear_rag import LinearRagPolicy
from src.kernel.state import EvaluationSignal, ExecutionState
from src.bootstrap import build_kernel_bundle, new_execution_state
from src.kernel.observability import InMemoryTraceSink


# ---------------------------------------------------------------------------
# 1. VerifyGroundednessEvaluator
# ---------------------------------------------------------------------------


class TestVerifyGroundednessEvaluator:

    def test_pass_with_good_overlap(self):
        ev = VerifyGroundednessEvaluator(groundedness_floor=0.3)
        st = ExecutionState(question="q")
        st.context = "NIST CSF framework controls evidence cybersecurity requirements"
        st.answer = "NIST CSF framework controls evidence requirements documented"
        sig = ev.evaluate(st)
        assert sig.passed is True
        assert sig.metadata["groundedness_ratio"] >= 0.3

    def test_fail_on_low_groundedness(self):
        ev = VerifyGroundednessEvaluator(groundedness_floor=0.3)
        st = ExecutionState(question="q")
        st.context = "completely different unrelated content about cooking recipes"
        st.answer = "NIST CSF framework controls evidence cybersecurity requirements"
        sig = ev.evaluate(st)
        assert sig.passed is False
        assert "groundedness" in sig.reason

    def test_fail_on_empty_answer(self):
        ev = VerifyGroundednessEvaluator()
        st = ExecutionState(question="q")
        st.context = "some context"
        st.answer = ""
        sig = ev.evaluate(st)
        assert sig.passed is False
        assert "vacio" in sig.reason

    def test_fail_on_short_answer(self):
        ev = VerifyGroundednessEvaluator(min_answer_chars=50)
        st = ExecutionState(question="q")
        st.context = "context " * 20
        st.answer = "short"
        sig = ev.evaluate(st)
        assert sig.passed is False
        assert "corto" in sig.reason

    def test_hedge_justified_when_assess_failed(self):
        ev = VerifyGroundednessEvaluator()
        st = ExecutionState(question="q")
        st.context = "some context about topic"
        st.answer = "no se menciona informacion sobre ese tema en los documentos"
        # No assess signal -> hedge is justified
        sig = ev.evaluate(st)
        assert sig.passed is True
        assert sig.metadata.get("hedge_phrase") is not None

    def test_hedge_unjustified_when_assess_passed(self):
        ev = VerifyGroundednessEvaluator()
        st = ExecutionState(question="q")
        st.context = "NIST CSF framework controls evidence cybersecurity requirements"
        st.answer = "no se menciona informacion sobre ese tema"
        # Add assess signal that passed
        st.add_signal(EvaluationSignal(name="assess", score=0.8, passed=True, reason="ok"))
        sig = ev.evaluate(st)
        assert sig.passed is False
        assert sig.metadata.get("unjustified_hedge") is True

    def test_citation_fidelity_valid(self):
        ev = VerifyGroundednessEvaluator(groundedness_floor=0.2)
        st = ExecutionState(question="q")
        st.context = "NIST CSF framework controls evidence cybersecurity requirements"
        st.answer = "NIST CSF framework controls evidence [1] and [2] cybersecurity requirements"
        st.results = [
            {"text": "doc1", "metadata": {"source": "a.pdf"}},
            {"text": "doc2", "metadata": {"source": "b.pdf"}},
        ]
        sig = ev.evaluate(st)
        assert sig.passed is True
        assert sig.metadata.get("citation_valid") == 2
        assert sig.metadata.get("citation_total") == 2

    def test_citation_fidelity_all_invalid(self):
        ev = VerifyGroundednessEvaluator(groundedness_floor=0.2)
        st = ExecutionState(question="q")
        st.context = "NIST CSF framework controls evidence cybersecurity requirements"
        st.answer = "NIST CSF framework controls evidence [5] and [6] cybersecurity"
        st.results = [
            {"text": "doc1", "metadata": {"source": "a.pdf"}},
        ]
        sig = ev.evaluate(st)
        assert sig.passed is False
        assert sig.metadata.get("citation_invalid_indices") == [5, 6]

    def test_citation_fidelity_partial_is_flag_not_hard_gate(self):
        ev = VerifyGroundednessEvaluator(groundedness_floor=0.2)
        st = ExecutionState(question="q")
        st.context = "NIST CSF framework controls evidence cybersecurity requirements"
        st.answer = "NIST CSF framework controls evidence [1] and [5] cybersecurity"
        st.results = [
            {"text": "doc1", "metadata": {"source": "a.pdf"}},
        ]
        sig = ev.evaluate(st)
        # [1] is valid, [5] is invalid -> partial, not hard fail
        assert sig.passed is True
        assert sig.metadata.get("citation_invalid_indices") == [5]


# ---------------------------------------------------------------------------
# 2. VerifyCapability
# ---------------------------------------------------------------------------


class TestVerifyCapability:

    def test_produces_signal_and_metadata(self):
        ev = VerifyGroundednessEvaluator(groundedness_floor=0.2)
        cap = VerifyCapability(ev)
        st = ExecutionState(question="q")
        st.context = "NIST CSF framework controls evidence"
        st.answer = "NIST CSF framework controls evidence documented"
        out = cap.execute(st)
        assert out.metadata.get("verified") is True
        sig = out.latest_signal("verify")
        assert sig is not None
        assert sig.name == "verify"

    def test_trace_emitted(self):
        ev = VerifyGroundednessEvaluator(groundedness_floor=0.2)
        cap = VerifyCapability(ev)
        st = ExecutionState(question="q")
        st.context = "NIST CSF framework controls evidence"
        st.answer = "NIST CSF framework controls evidence documented"
        out = cap.execute(st)
        kinds = [t.kind for t in out.traces]
        assert "capability.verify" in kinds


# ---------------------------------------------------------------------------
# 3. VerifyRepairPolicy
# ---------------------------------------------------------------------------


class TestVerifyRepairPolicy:

    def test_bypass_when_verify_passed(self):
        p = VerifyRepairPolicy(max_repairs=1)
        st = ExecutionState(question="q")
        st.metadata["verified"] = True
        st.add_signal(EvaluationSignal(name="verify", score=0.9, passed=True, reason="ok"))
        assert p.decide(st) is None

    def test_repair_on_first_fail(self):
        p = VerifyRepairPolicy(max_repairs=1)
        st = ExecutionState(question="q")
        st.metadata["verified"] = True
        st.add_signal(EvaluationSignal(name="verify", score=0.1, passed=False, reason="low groundedness"))
        d = p.decide(st)
        assert d is not None
        assert d.action == "retry"
        assert d.capability_ref == "generation"
        assert d.params.get("repair_count") == 1
        assert "repair_hint" in d.params

    def test_decline_when_budget_exhausted(self):
        p = VerifyRepairPolicy(max_repairs=1)
        st = ExecutionState(question="q")
        st.metadata["verified"] = True
        st.metadata["repair_count"] = 1
        st.add_signal(EvaluationSignal(name="verify", score=0.1, passed=False, reason="low"))
        d = p.decide(st)
        assert d is not None
        assert d.action == "decline"
        assert d.terminate is True

    def test_decline_when_general_budget_exhausted(self):
        p = VerifyRepairPolicy(max_repairs=3)
        st = ExecutionState(question="q", max_iterations=2)
        st.metadata["verified"] = True
        st.iteration = 2
        st.add_signal(EvaluationSignal(name="verify", score=0.1, passed=False, reason="low"))
        d = p.decide(st)
        assert d is not None
        assert d.action == "decline"

    def test_no_action_when_not_verified(self):
        p = VerifyRepairPolicy(max_repairs=1)
        st = ExecutionState(question="q")
        # verified not set
        assert p.decide(st) is None


# ---------------------------------------------------------------------------
# 4. E2E: pipeline with verify + repair
# ---------------------------------------------------------------------------


class TestE2EVerifyRepair:

    def test_verify_pass_and_finalize(self):
        call_count = {"generate": 0}

        def retrieve(q, top_k, sw):
            return [
                {
                    "text": "NIST CSF framework controls evidence cybersecurity " * 10,
                    "metadata": {"source": "nist.pdf", "page": 1},
                    "hybrid_score": 0.9,
                    "rerank_score": 0.85,
                    "final_score": 0.88,
                }
            ]

        def build_ctx(q, rs, lm):
            return " ".join(r.get("text", "") for r in rs)[:8000]

        def generate(q, c, lm, **kw):
            call_count["generate"] += 1
            return "NIST CSF framework controls evidence cybersecurity"

        def classify(q, lm, top_k):
            return {"out_of_domain": False, "length_mode": lm, "top_k": top_k, "entities": ["NIST"]}

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
            extras={"max_iterations": 15, "max_llm_calls": 4},
        )
        st = new_execution_state("que es NIST?", use_llm=True, max_iterations=15)
        out = bundle.controller.run(st)

        assert out.done
        assert out.answer == "NIST CSF framework controls evidence cybersecurity"
        assert out.metadata.get("finalized") is True
        assert out.metadata.get("verified") is True
        verify_sig = out.latest_signal("verify")
        assert verify_sig is not None
        assert verify_sig.passed is True
        assert call_count["generate"] == 1

    def test_verify_fail_triggers_repair_then_pass(self):
        call_count = {"generate": 0}

        def retrieve(q, top_k, sw):
            return [
                {
                    "text": "NIST CSF framework controls evidence cybersecurity " * 10,
                    "metadata": {"source": "nist.pdf", "page": 1},
                    "hybrid_score": 0.9,
                    "rerank_score": 0.85,
                    "final_score": 0.88,
                }
            ]

        def build_ctx(q, rs, lm):
            return " ".join(r.get("text", "") for r in rs)[:8000]

        def generate(q, c, lm, **kw):
            call_count["generate"] += 1
            if call_count["generate"] == 1:
                # First attempt: hallucinated answer (no overlap)
                return "completely unrelated cooking recipe pasta ingredients"
            # Second attempt (repair): grounded answer
            return "NIST CSF framework controls evidence cybersecurity"

        def classify(q, lm, top_k):
            return {"out_of_domain": False, "length_mode": lm, "top_k": top_k, "entities": ["NIST"]}

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
            extras={"max_iterations": 20, "max_llm_calls": 6},
        )
        st = new_execution_state("que es NIST?", use_llm=True, max_iterations=20, max_llm_calls=6)
        out = bundle.controller.run(st)

        assert out.done
        assert out.answer == "NIST CSF framework controls evidence cybersecurity"
        assert out.metadata.get("finalized") is True
        assert out.metadata.get("verified") is True
        assert out.metadata.get("repair_count") == 1
        assert call_count["generate"] == 2
        # Should have 2 verify signals (first fail, second pass)
        verify_sigs = [s for s in out.signals if s.name == "verify"]
        assert len(verify_sigs) >= 2
        assert verify_sigs[0].passed is False
        assert verify_sigs[-1].passed is True

    def test_verify_fail_repair_fail_then_decline(self):
        call_count = {"generate": 0}

        def retrieve(q, top_k, sw):
            return [
                {
                    "text": "NIST CSF framework controls evidence cybersecurity " * 10,
                    "metadata": {"source": "nist.pdf", "page": 1},
                    "hybrid_score": 0.9,
                    "rerank_score": 0.85,
                    "final_score": 0.88,
                }
            ]

        def build_ctx(q, rs, lm):
            return " ".join(r.get("text", "") for r in rs)[:8000]

        def generate(q, c, lm, **kw):
            call_count["generate"] += 1
            # Always hallucinate
            return "completely unrelated cooking recipe pasta ingredients"

        def classify(q, lm, top_k):
            return {"out_of_domain": False, "length_mode": lm, "top_k": top_k, "entities": ["NIST"]}

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
            extras={"max_iterations": 20, "max_llm_calls": 6},
        )
        st = new_execution_state("que es NIST?", use_llm=True, max_iterations=20, max_llm_calls=6)
        out = bundle.controller.run(st)

        assert out.done
        assert out.decline is True
        assert call_count["generate"] == 2  # initial + 1 repair
        assert out.metadata.get("repair_count") == 1


# ---------------------------------------------------------------------------
# 5. LinearRagPolicy: verify in chain
# ---------------------------------------------------------------------------


class TestLinearRagVerifyChain:

    def test_verify_after_generation_before_finalize(self):
        p = LinearRagPolicy()
        st = ExecutionState(question="q", use_llm=True)
        assert p.decide(st).capability_ref == "classify"
        st.metadata["classified"] = True
        assert p.decide(st).capability_ref == "memory_read"
        st.metadata["memory_read"] = True
        # Fase 6: planner y entity_expansion antes de retrieval
        assert p.decide(st).capability_ref == "planner"
        st.metadata["planned"] = True
        assert p.decide(st).capability_ref == "entity_expansion"
        st.metadata["entity_expansion"] = True
        assert p.decide(st).capability_ref == "retrieval"
        st.results = [{"text": "a"}]
        assert p.decide(st).capability_ref == "build_context"
        st.context = "ctx"
        assert p.decide(st).capability_ref == "assess"
        st.metadata["assessed"] = True
        assert p.decide(st).capability_ref == "generation"
        st.answer = "ans"
        assert p.decide(st).capability_ref == "verify"
        st.metadata["verified"] = True
        assert p.decide(st).capability_ref == "finalize_turn"
        st.metadata["finalized"] = True
        assert p.decide(st).terminate
