"""
Tests Fase 1: fachada query() + kernel.enabled + adapter bootstrap con rerank.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.bootstrap import build_kernel_bundle_from_rag, new_execution_state
from src.kernel.state import ExecutionState


class _FakeRagPhase1:
    def __init__(self) -> None:
        self.model_provider = None
        self.use_llm = True
        self.kernel_enabled = False
        self.flags = {"enable_postprocess": True}
        self.config = {
            "kernel": {"enabled": False, "max_iterations": 12, "max_llm_calls": 4},
            "reranker": {"candidate_pool": 12},
        }
        self._kernel_bundle = None
        self.calls: List[str] = []
        self.memory = None
        self._sticky_sources = None
        self.last_entities = []
        self.flags = {"enable_postprocess": True, "sticky_sources_ttl": 2}

    def hybrid_search(self, query, top_k=50, semantic_weight=0.6):
        self.calls.append(f"hybrid:{top_k}")
        # devolver mas que top_k final para validar pool
        return [
            {
                "text": f"chunk-{i} NIST CSF ISO 27001 cybersecurity controls evidence block.",
                "metadata": {"source": f"doc{i}.pdf", "page": i},
                "hybrid_score": 1.0 - (i * 0.01),
            }
            for i in range(1, int(top_k) + 1)
        ]

    def _rerank_results(self, query, results, top_k=10):
        self.calls.append(f"rerank:{top_k}")
        out = list(results)[: int(top_k)]
        for r in out:
            r["final_score"] = r.get("hybrid_score", 0.5)
            r["rerank_score"] = 0.9
        return out

    def generate_with_ollama(self, *args, **kwargs):
        self.calls.append("generate")
        # soportar posicional (question, context) o query=
        if args:
            q = args[0]
            ctx = args[1] if len(args) > 1 else kwargs.get("context", "")
        else:
            q = kwargs.get("query") or kwargs.get("question") or ""
            ctx = kwargs.get("context", "")
        return f"ANS:{q[:20]}:{len(ctx)} NIST CSF ISO 27001 cybersecurity controls evidence framework"

    def _postprocess_answer(self, question, answer, context):
        self.calls.append("postprocess")
        return f"{answer}|pp"

    def _is_out_of_domain(self, q):
        return False

    def _classify_query(self, q, lm, top_k):
        return {"length_mode": lm, "top_k": top_k, "out_of_domain": False}

    # Metodos minimos para reutilizar query_via_kernel / _get_kernel_bundle del real
    def _get_kernel_bundle(self):
        if self._kernel_bundle is None:
            self._kernel_bundle = build_kernel_bundle_from_rag(self)
        return self._kernel_bundle

    def query_via_kernel(
        self,
        question: str,
        top_k: int = 50,
        semantic_weight: float = 0.6,
        use_llm: bool = None,
        length_mode: str = None,
    ) -> dict:
        if use_llm is None:
            use_llm = self.use_llm
        bundle = self._get_kernel_bundle()
        extras = getattr(bundle, "extras", {}) or {}
        state = new_execution_state(
            question,
            top_k=top_k,
            semantic_weight=semantic_weight,
            use_llm=use_llm,
            length_mode=length_mode,
            max_iterations=int(extras.get("max_iterations", 8) or 8),
            max_llm_calls=int(extras.get("max_llm_calls", 6) or 6),
        )
        out = bundle.controller.run(state)
        if not out.sources and out.results:
            out.sources = [
                {
                    "source": (r.get("metadata") or {}).get("source", ""),
                    "page": (r.get("metadata") or {}).get("page"),
                    "score": r.get("final_score") or r.get("rerank_score"),
                }
                for r in out.results
            ]
        result = out.to_query_result()
        result["method"] = "kernel_linear"
        result.setdefault("memory_hits", 0)
        return result


def test_bootstrap_retrieve_calls_rerank_with_pool():
    rag = _FakeRagPhase1()
    bundle = build_kernel_bundle_from_rag(rag)
    st = new_execution_state("que es nist?", top_k=5, use_llm=True)
    out = bundle.controller.run(st)
    assert out.done
    assert out.answer.startswith("ANS:")
    assert out.answer.endswith("|pp")
    assert len(out.results) == 5
    assert any(c.startswith("hybrid:10") for c in rag.calls)  # adaptive pool: min(12,10)=10 for short query
    assert "rerank:5" in rag.calls
    assert "postprocess" in rag.calls


def test_query_via_kernel_facade_contract_keys():
    rag = _FakeRagPhase1()
    result = rag.query_via_kernel("iso 27001", top_k=3, use_llm=True)
    for key in (
        "question",
        "results",
        "context",
        "answer",
        "sources",
        "method",
        "memory_hits",
        "time",
        "timing_breakdown",
    ):
        assert key in result
    assert result["method"] == "kernel_linear"
    assert result["answer"]
    assert len(result["results"]) == 3
    assert result["sources"]


def test_facade_dispatch_kernel_enabled_flag():
    """Simula el despacho de HybridRAG.query sin cargar el monolito."""

    class Facade(_FakeRagPhase1):
        def query(self, question, top_k=50, semantic_weight=0.6, use_llm=None, **kwargs):
            if use_llm is None:
                use_llm = self.use_llm
            if getattr(self, "kernel_enabled", False):
                return self.query_via_kernel(
                    question,
                    top_k=top_k,
                    semantic_weight=semantic_weight,
                    use_llm=use_llm,
                    length_mode=kwargs.get("length_mode"),
                )
            return {
                "question": question,
                "results": [],
                "context": "",
                "answer": "LINEAR",
                "sources": [],
                "method": "hybrid_with_memory",
                "memory_hits": 0,
                "time": 0.0,
                "timing_breakdown": {},
            }

    f = Facade()
    f.kernel_enabled = False
    r0 = f.query("x")
    assert r0["method"] == "hybrid_with_memory"
    assert r0["answer"] == "LINEAR"

    f.kernel_enabled = True
    r1 = f.query("x", top_k=4)
    assert r1["method"] == "kernel_linear"
    assert r1["answer"].startswith("ANS:")
    assert len(r1["results"]) == 4


def test_linear_policy_still_retrieve_context_generate():
    from src.policies.linear_rag import LinearRagPolicy

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
    st.context = "c"
    assert p.decide(st).capability_ref == "assess"
    st.metadata["assessed"] = True
    assert p.decide(st).capability_ref == "generation"
    st.answer = "a"
    # Fase 4: verify despues de generation
    assert p.decide(st).capability_ref == "verify"
    st.metadata["verified"] = True
    assert p.decide(st).capability_ref == "finalize_turn"


def test_assess_gate_declines_on_failed_signal():
    from src.bootstrap import build_kernel_bundle
    from src.evaluation.assess_evidence import AssessEvidenceEvaluator
    from src.kernel.observability import InMemoryTraceSink
    from src.kernel.state import EvaluationSignal

    class FailAssess:
        name = "assess"

        def evaluate(self, state):
            return EvaluationSignal(
                name="assess", score=0.0, passed=False, reason="forced_fail"
            )

    def retrieve(q, top_k, sw):
        return [{"text": "t", "metadata": {"source": "s"}, "rerank_score": 0.01}]

    def build_ctx(q, rs, lm):
        return "short"

    def generate(q, c, lm):
        return "SHOULD_NOT_RUN"

    def classify(q, lm, top_k):
        return {"out_of_domain": False, "top_k": top_k, "length_mode": lm}

    bundle = build_kernel_bundle(
        retrieve_fn=retrieve,
        build_context_fn=build_ctx,
        generate_fn=generate,
        classify_fn=classify,
        assess_evaluator=FailAssess(),
        trace_sink=InMemoryTraceSink(),
    )
    st = new_execution_state("q", use_llm=True)
    out = bundle.controller.run(st)
    assert out.done
    assert out.decline
    assert "No se encontro" in (out.answer or "")
    assert "SHOULD_NOT_RUN" not in (out.answer or "")


def test_ood_classify_declines_without_retrieval():
    from src.bootstrap import build_kernel_bundle
    from src.kernel.observability import InMemoryTraceSink

    called = {"retrieve": 0}

    def retrieve(q, top_k, sw):
        called["retrieve"] += 1
        return []

    def build_ctx(q, rs, lm):
        return ""

    def generate(q, c, lm):
        return "nope"

    def classify(q, lm, top_k):
        return {
            "out_of_domain": True,
            "ood_message": "OOD_BLOCK",
            "top_k": top_k,
            "length_mode": lm,
        }

    bundle = build_kernel_bundle(
        retrieve_fn=retrieve,
        build_context_fn=build_ctx,
        generate_fn=generate,
        classify_fn=classify,
        trace_sink=InMemoryTraceSink(),
    )
    st = new_execution_state("receta de pan", use_llm=True)
    out = bundle.controller.run(st)
    assert out.done
    assert out.decline
    assert out.answer == "OOD_BLOCK"
    assert called["retrieve"] == 0


def test_assess_evaluator_rerank_floor():
    from src.evaluation.assess_evidence import AssessEvidenceEvaluator

    ev = AssessEvidenceEvaluator(rerank_floor=0.1, hybrid_rescue=0.5)
    st = ExecutionState(question="q")
    st.results = [{"rerank_score": 0.05, "hybrid_score": 0.1, "final_score": 0.1}]
    st.context = "x" * 100
    sig = ev.evaluate(st)
    assert sig.passed is False
    assert "rerank" in (sig.reason or "")


def test_memory_read_injected_into_context_and_finalize_sticky():
    from src.bootstrap import build_kernel_bundle_from_rag, new_execution_state

    class Mem:
        def search_memory(self, query, limit=3):
            return [{"question": "q-mem", "answer": "a-mem-nist"}]

    class Rag:
        def __init__(self):
            self.model_provider = None
            self.memory = Mem()
            self.flags = {"enable_postprocess": False, "sticky_sources_ttl": 3}
            self.config = {
                "kernel": {"max_iterations": 12, "max_llm_calls": 4},
                "reranker": {"candidate_pool": 5},
            }
            self.last_entities = []
            self._sticky_sources = None

        def hybrid_search(self, query, top_k=50, semantic_weight=0.6):
            return [
                {
                    "text": "NIST CSF document chunk " * 10,
                    "metadata": {"source": "nist.pdf", "page": 1},
                    "hybrid_score": 0.9,
                    "rerank_score": 0.85,
                    "final_score": 0.88,
                }
            ]

        def _rerank_results(self, query, results, top_k=10):
            return list(results)[:top_k]

        def generate_with_ollama(self, *args, **kwargs):
            return "NIST CSF document chunk cybersecurity controls evidence framework"

        def _is_out_of_domain(self, q):
            return False

        def _classify_query(self, q, lm, top_k):
            return {
                "length_mode": lm,
                "top_k": top_k,
                "out_of_domain": False,
                "entities": ["nist"],
            }

    rag = Rag()
    bundle = build_kernel_bundle_from_rag(rag)
    st = new_execution_state("que es nist?", use_llm=True, max_iterations=12)
    out = bundle.controller.run(st)
    assert out.done
    assert out.answer == "NIST CSF document chunk cybersecurity controls evidence framework"
    assert "[MEM1]" in (out.context or "")
    assert "a-mem-nist" in (out.context or "")
    assert out.metadata.get("memory_hits_count") == 1
    assert out.to_query_result()["memory_hits"] == 1
    assert out.metadata.get("finalized") is True
    sticky = getattr(rag, "_sticky_sources", None)
    assert sticky is not None
    assert "nist.pdf" in sticky.get("sources", [])
    assert int(sticky.get("ttl", 0)) == 2
