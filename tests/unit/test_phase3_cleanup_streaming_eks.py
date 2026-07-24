"""
Tests para los 3 items pendientes de Fases 0-3:
1. Limpieza de dominio electrico residual
2. Streaming en camino kernel
3. EKS index generation
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.kernel.state import ExecutionState
from src.bootstrap import new_execution_state
from src.capabilities.generation import GenerationCapability


# ---------------------------------------------------------------------------
# 1. Limpieza de dominio electrico residual
# ---------------------------------------------------------------------------


class TestElectricDomainCleanup:
    """Verifica que rag_hybrid.py no contiene referencias al dominio electrico."""

    @pytest.fixture
    def rag_source(self):
        rag_path = Path(__file__).resolve().parent.parent.parent / "rag_hybrid.py"
        return rag_path.read_text(encoding="utf-8")

    @pytest.mark.parametrize("term", [
        "centrales_map",
        "centrales_loaded",
        "_is_centrales_list_request",
        "CAMMESA",
        "Pampetrol",
        "aerogenerador",
        "fotovoltaica",
    ])
    def test_no_electric_terms(self, rag_source, term):
        assert term not in rag_source, f"Termino electrico residual encontrado: {term}"

    def test_domain_map_exists(self, rag_source):
        assert "domain_map" in rag_source, "domain_map deberia existir como reemplazo generico"

    def test_is_listing_request_renamed(self, rag_source):
        assert "_is_listing_request" in rag_source, "Metodo renombrado _is_listing_request deberia existir"


# ---------------------------------------------------------------------------
# 2. Streaming en camino kernel
# ---------------------------------------------------------------------------


class TestKernelStreaming:
    """Verifica que el camino kernel soporta streaming via token_callback y cancel_checker."""

    def test_execution_state_has_streaming_fields(self):
        state = ExecutionState(question="test")
        assert hasattr(state, "token_callback")
        assert hasattr(state, "cancel_checker")
        assert state.token_callback is None
        assert state.cancel_checker is None

    def test_execution_state_streaming_not_serialized(self):
        state = ExecutionState(question="test")
        state.token_callback = lambda x: None
        state.cancel_checker = lambda: False
        d = state.to_dict()
        assert "token_callback" not in d
        assert "cancel_checker" not in d

    def test_generation_capability_passes_streaming_kwargs(self):
        tokens_received = []
        def mock_generate(question, context, length_mode, **kwargs):
            if kwargs.get("token_callback"):
                kwargs["token_callback"]("Hello ")
                kwargs["token_callback"]("world!")
            return "Hello world!"

        cap = GenerationCapability(mock_generate)
        state = new_execution_state("test question", use_llm=True)
        state.context = "some context"
        state.token_callback = lambda chunk: tokens_received.append(chunk)

        result = cap.execute(state)
        assert result.answer == "Hello world!"
        assert tokens_received == ["Hello ", "world!"]

    def test_generation_capability_stream_flag_set(self):
        received_kwargs = {}
        def mock_generate(question, context, length_mode, **kwargs):
            received_kwargs.update(kwargs)
            return "answer"

        cap = GenerationCapability(mock_generate)
        state = new_execution_state("test", use_llm=True)
        state.context = "ctx"
        state.token_callback = lambda x: None

        cap.execute(state)
        assert received_kwargs.get("stream") is True
        assert "token_callback" in received_kwargs

    def test_generation_capability_no_streaming_without_callbacks(self):
        received_kwargs = {}
        def mock_generate(question, context, length_mode, **kwargs):
            received_kwargs.update(kwargs)
            return "answer"

        cap = GenerationCapability(mock_generate)
        state = new_execution_state("test", use_llm=True)
        state.context = "ctx"

        cap.execute(state)
        assert "stream" not in received_kwargs
        assert "token_callback" not in received_kwargs

    def test_generation_capability_fallback_on_type_error(self):
        def mock_generate_no_kwargs(question, context, length_mode):
            return "fallback answer"

        cap = GenerationCapability(mock_generate_no_kwargs)
        state = new_execution_state("test", use_llm=True)
        state.context = "ctx"
        state.token_callback = lambda x: None

        result = cap.execute(state)
        assert result.answer == "fallback answer"

    def test_generation_capability_cancel_checker_passed(self):
        cancel_called = []
        def mock_generate(question, context, length_mode, **kwargs):
            cancel_called.append(kwargs.get("cancel_checker"))
            return "answer"

        cap = GenerationCapability(mock_generate)
        state = new_execution_state("test", use_llm=True)
        state.context = "ctx"
        cancel_fn = lambda: False
        state.cancel_checker = cancel_fn

        cap.execute(state)
        assert cancel_called[0] is cancel_fn

    def test_query_via_kernel_accepts_streaming_params(self):
        """Verifica que query_via_kernel acepta token_callback y cancel_checker."""
        from src.bootstrap import build_kernel_bundle
        from src.kernel.observability import InMemoryTraceSink

        call_count = {"generate": 0}
        tokens = []

        def retrieve(query, top_k, sw):
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

        def generate(question, context, length_mode, **kwargs):
            call_count["generate"] += 1
            if kwargs.get("token_callback"):
                kwargs["token_callback"]("chunk1")
                kwargs["token_callback"]("chunk2")
            return "NIST CSF framework controls evidence context generated"

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
            trace_sink=InMemoryTraceSink(),
            extras={"max_iterations": 12, "max_llm_calls": 2},
        )

        state = new_execution_state("que es NIST CSF?", use_llm=True, max_iterations=12, max_llm_calls=2)
        state.token_callback = lambda chunk: tokens.append(chunk)
        state.cancel_checker = lambda: False

        out = bundle.controller.run(state)
        assert out.answer == "NIST CSF framework controls evidence context generated"
        assert tokens == ["chunk1", "chunk2"]
        assert call_count["generate"] >= 1


# ---------------------------------------------------------------------------
# 3. EKS Index generation
# ---------------------------------------------------------------------------


class TestEksIndex:
    """Verifica que el indice EKS se genera correctamente."""

    @pytest.fixture
    def knowledge_dir(self):
        return Path(__file__).resolve().parent.parent.parent / "knowledge"

    def test_index_md_exists(self, knowledge_dir):
        assert (knowledge_dir / "INDEX.md").exists(), "INDEX.md deberia existir"

    def test_index_json_exists(self, knowledge_dir):
        assert (knowledge_dir / "_eks_index.json").exists(), "_eks_index.json deberia existir"

    def test_index_json_valid(self, knowledge_dir):
        data = json.loads((knowledge_dir / "_eks_index.json").read_text(encoding="utf-8"))
        assert "generated" in data
        assert "count" in data
        assert "entries" in data
        assert isinstance(data["entries"], list)
        assert data["count"] == len(data["entries"])

    def test_index_entries_have_required_fields(self, knowledge_dir):
        data = json.loads((knowledge_dir / "_eks_index.json").read_text(encoding="utf-8"))
        required = {"id", "category", "status", "title", "path"}
        for entry in data["entries"]:
            missing = required - set(entry.keys())
            assert not missing, f"Entry {entry.get('id', '?')} missing fields: {missing}"

    def test_index_md_has_table(self, knowledge_dir):
        content = (knowledge_dir / "INDEX.md").read_text(encoding="utf-8")
        assert "| ID |" in content
        assert "Cross-references" in content

    def test_generate_script_exists(self):
        script = Path(__file__).resolve().parent.parent.parent / "scripts" / "generate_eks_index.py"
        assert script.exists(), "scripts/generate_eks_index.py deberia existir"
