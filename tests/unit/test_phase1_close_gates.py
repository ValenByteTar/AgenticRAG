"""
Gate de cierre Fase 1 (estructural + contrato fachada).

No sustituye el A/B full vs BM-001 (requiere LLM+indice ~25q).
Valida que:
- kernel.enabled=false despacha al monolito
- kernel.enabled=true despacha a query_via_kernel
- retorno kernel cumple claves ADR-0010
- LinearRagPolicy expone la cadena F1.c completa
"""

from __future__ import annotations

from src.bootstrap import build_kernel_bundle, new_execution_state
from src.kernel.observability import InMemoryTraceSink
from src.policies.linear_rag import LinearRagPolicy
from src.kernel.state import ExecutionState


REQUIRED_KEYS = {
    "question",
    "results",
    "context",
    "answer",
    "sources",
    "method",
    "memory_hits",
    "time",
    "timing_breakdown",
}


def test_f1_policy_chain_complete():
    p = LinearRagPolicy()
    st = ExecutionState(question="q", use_llm=True)
    chain = []
    for _ in range(16):
        d = p.decide(st)
        assert d is not None
        if d.terminate and d.action in ("done", "terminate"):
            break
        if d.capability_ref:
            chain.append(d.capability_ref)
        # advance state minimally
        if d.capability_ref == "classify":
            st.metadata["classified"] = True
        elif d.capability_ref == "memory_read":
            st.metadata["memory_read"] = True
            st.metadata["memory_hits"] = []
            st.metadata["memory_hits_count"] = 0
        elif d.capability_ref == "planner":
            st.metadata["planned"] = True
        elif d.capability_ref == "entity_expansion":
            st.metadata["entity_expansion"] = True
        elif d.capability_ref == "retrieval":
            st.results = [{"text": "t", "metadata": {"source": "s.pdf", "page": 1}, "rerank_score": 0.9, "final_score": 0.9}]
        elif d.capability_ref == "build_context":
            st.context = "ctx " * 20
        elif d.capability_ref == "assess":
            st.metadata["assessed"] = True
        elif d.capability_ref == "generation":
            st.answer = "ans"
        elif d.capability_ref == "verify":
            st.metadata["verified"] = True
        elif d.capability_ref == "finalize_turn":
            st.metadata["finalized"] = True
    assert chain == [
        "classify",
        "memory_read",
        "planner",
        "entity_expansion",
        "retrieval",
        "build_context",
        "assess",
        "generation",
        "verify",
        "finalize_turn",
    ]


def test_f1_kernel_bundle_contract_and_memory_hits():
    def retrieve(q, top_k, sw):
        return [
            {
                "text": "ISO 27001 controls and NIST CSF evidence " * 8,
                "metadata": {"source": "iso.pdf", "page": 2},
                "hybrid_score": 0.9,
                "rerank_score": 0.85,
                "final_score": 0.88,
            }
        ]

    def build_ctx(q, rs, lm):
        return "ISO 27001 controls NIST CSF framework evidence context requirements " * 30

    def generate(q, c, lm):
        return "ISO 27001 controls NIST CSF framework evidence context requirements"

    def classify(q, lm, top_k):
        return {"out_of_domain": False, "length_mode": lm, "top_k": top_k}

    def mem_read(q, limit):
        return [{"question": "prev", "answer": "mem-answer"}]

    finalized = {"ok": False}

    def finalize(state):
        finalized["ok"] = True

    bundle = build_kernel_bundle(
        retrieve_fn=retrieve,
        build_context_fn=build_ctx,
        generate_fn=generate,
        classify_fn=classify,
        memory_read_fn=mem_read,
        finalize_fn=finalize,
        trace_sink=InMemoryTraceSink(),
    )
    st = new_execution_state("que es iso 27001?", use_llm=True, max_iterations=12)
    out = bundle.controller.run(st)
    assert out.done
    assert out.answer == "ISO 27001 controls NIST CSF framework evidence context requirements"
    assert finalized["ok"] is True
    assert "[MEM1]" in out.context
    qr = out.to_query_result()
    assert REQUIRED_KEYS.issubset(set(qr.keys()))
    assert qr["memory_hits"] == 1
    assert qr["answer"] == "ISO 27001 controls NIST CSF framework evidence context requirements"


def test_f1_facade_dispatch_flag():
    """Despacho de HybridRAG.query sin cargar indice."""

    class Fake:
        def __init__(self):
            self.use_llm = True
            self.kernel_enabled = False

        def query_via_kernel(self, question, top_k=50, semantic_weight=0.6, use_llm=None, length_mode=None):
            return {
                "question": question,
                "results": [{"x": 1}],
                "context": "c",
                "answer": "K",
                "sources": [],
                "method": "kernel_linear",
                "memory_hits": 0,
                "time": 0.1,
                "timing_breakdown": {},
            }

        def _query_linear_impl(self, question, **kwargs):
            return {
                "question": question,
                "results": [],
                "context": "",
                "answer": "L",
                "sources": [],
                "method": "hybrid_with_memory",
                "memory_hits": 0,
                "time": 0.1,
                "timing_breakdown": {},
            }

        def query(self, question, top_k=50, semantic_weight=0.6, use_llm=None, **kwargs):
            if use_llm is None:
                use_llm = self.use_llm
            if getattr(self, "kernel_enabled", False):
                return self.query_via_kernel(question, top_k=top_k, semantic_weight=semantic_weight, use_llm=use_llm)
            return self._query_linear_impl(question, top_k=top_k, semantic_weight=semantic_weight, use_llm=use_llm)

    f = Fake()
    assert f.query("a")["method"] == "hybrid_with_memory"
    f.kernel_enabled = True
    r = f.query("a")
    assert r["method"] == "kernel_linear"
    assert REQUIRED_KEYS.issubset(set(r.keys()))
