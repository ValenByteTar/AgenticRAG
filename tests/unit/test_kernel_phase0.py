"""
Tests Fase 0 del Kernel InfraPolus.

Valida contratos, Registry, PolicyEngine, Controller y CompositionRoot
sin depender de Ollama, embeddings ni Chroma.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from src.kernel import (
    ActionDecision,
    CapabilityRegistry,
    CompositionRoot,
    EvaluationSignal,
    ExecutionState,
    InMemoryTraceSink,
    KernelController,
    PolicyEngine,
)
from src.policies.linear_rag import LinearRagPolicy


class _StubCapability:
    def __init__(self, name: str, field: str, value: Any) -> None:
        self.name = name
        self._field = field
        self._value = value

    def execute(self, state: ExecutionState, params: Optional[Dict[str, Any]] = None) -> ExecutionState:
        setattr(state, self._field, self._value)
        if self._field == "results":
            state.results = list(self._value)
        return state


class _EchoCapability:
    name = "echo"

    def execute(self, state: ExecutionState, params: Optional[Dict[str, Any]] = None) -> ExecutionState:
        state.answer = f"echo:{state.question}"
        state.done = True
        return state


class _AlwaysInvokeEcho:
    name = "always_echo"

    def decide(self, state: ExecutionState) -> Optional[ActionDecision]:
        if state.answer:
            return ActionDecision(action="done", terminate=True, reason="done")
        return ActionDecision(
            action="invoke",
            capability_ref="echo",
            reason="invoke_echo",
        )


def test_execution_state_serializable():
    st = ExecutionState(question="que es nist?")
    st.add_signal(EvaluationSignal(name="assess", score=0.8, passed=True))
    st.add_trace("test", "ok")
    d = st.to_dict()
    assert d["question"] == "que es nist?"
    assert d["signals"][0]["name"] == "assess"
    assert "run_id" in d
    qr = st.to_query_result()
    assert "answer" in qr and "sources" in qr and "timing_breakdown" in qr


def test_registry_register_resolve():
    reg = CapabilityRegistry()
    cap = _EchoCapability()
    reg.register(cap)
    assert reg.has("echo")
    assert reg.resolve("echo") is cap
    with pytest.raises(KeyError):
        reg.resolve("missing")


def test_policy_engine_first_match_and_budget():
    engine = PolicyEngine([LinearRagPolicy()])
    st = ExecutionState(question="x", max_iterations=1, iteration=1)
    d = engine.decide(st)
    assert d.terminate and d.reason == "budget_exhausted"

    st2 = ExecutionState(question="x")
    d2 = engine.decide(st2)
    assert d2.capability_ref == "classify"


def test_linear_policy_sequence():
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
    # Fase 4: verify despues de generation, antes de finalize
    assert p.decide(st).capability_ref == "verify"
    st.metadata["verified"] = True
    assert p.decide(st).capability_ref == "finalize_turn"
    st.metadata["finalized"] = True
    assert p.decide(st).terminate


def test_controller_invokes_via_registry_only():
    root = CompositionRoot(trace_sink=InMemoryTraceSink())
    root.register_capability(_EchoCapability())
    root.add_policy(_AlwaysInvokeEcho())
    bundle = root.build()

    st = ExecutionState(question="hola")
    out = bundle.controller.run(st)
    assert out.answer == "echo:hola"
    assert out.done
    kinds = [t.kind for t in out.traces]
    assert "policy.decision" in kinds
    assert "capability.start" in kinds
    assert "controller.end" in kinds


def test_controller_unknown_capability_terminates():
    engine = PolicyEngine([_AlwaysInvokeEcho()])
    ctrl = KernelController(CapabilityRegistry(), engine, InMemoryTraceSink())
    st = ExecutionState(question="x")
    out = ctrl.run(st)
    assert out.done
    assert out.error and "no registrada" in out.error


def test_composition_root_wires_model_provider_slot():
    class _FakeProvider:
        name = "fake"
        model = "m"

        def generate(self, prompt, *, options=None, timeout=None):
            return "ok"

        def stream(self, prompt, *, options=None, timeout=None):
            yield "ok"

        def is_available(self):
            return True

    root = CompositionRoot()
    root.set_model_provider(_FakeProvider())
    b = root.build()
    assert b.model_provider is not None
    assert b.model_provider.generate("p") == "ok"


class _ClassifyStub:
    name = "classify"

    def execute(self, state: ExecutionState, params=None) -> ExecutionState:
        state.metadata["classified"] = True
        return state


class _AssessStub:
    name = "assess"

    def execute(self, state: ExecutionState, params=None) -> ExecutionState:
        state.metadata["assessed"] = True
        state.add_signal(EvaluationSignal(name="assess", score=1.0, passed=True, reason="ok"))
        return state


class _MemoryReadStub:
    name = "memory_read"

    def execute(self, state: ExecutionState, params=None) -> ExecutionState:
        state.metadata["memory_read"] = True
        state.metadata["memory_hits"] = []
        state.metadata["memory_hits_count"] = 0
        return state


class _VerifyStub:
    name = "verify"

    def execute(self, state: ExecutionState, params=None) -> ExecutionState:
        from src.kernel.state import EvaluationSignal
        state.add_signal(EvaluationSignal(name="verify", score=0.9, passed=True, reason="stub"))
        state.metadata["verified"] = True
        return state


class _PlannerStub:
    name = "planner"

    def execute(self, state: ExecutionState, params=None) -> ExecutionState:
        state.metadata["planned"] = True
        state.metadata["plan"] = {"doc_roles_preferred": ["entity_profile"]}
        return state


class _EntityExpansionStub:
    name = "entity_expansion"

    def execute(self, state: ExecutionState, params=None) -> ExecutionState:
        state.metadata["entity_expansion"] = True
        state.metadata["expanded_entities"] = list(state.entities or [])
        return state


class _FinalizeStub:
    name = "finalize_turn"

    def execute(self, state: ExecutionState, params=None) -> ExecutionState:
        state.metadata["finalized"] = True
        return state


def test_linear_rag_end_to_end_with_stubs():
    root = CompositionRoot(trace_sink=InMemoryTraceSink())
    root.register_capability(_ClassifyStub())
    root.register_capability(_MemoryReadStub())
    root.register_capability(_PlannerStub())
    root.register_capability(_EntityExpansionStub())
    root.register_capability(_StubCapability("retrieval", "results", [{"id": 1, "text": "doc"}]))
    root.register_capability(_StubCapability("build_context", "context", "CTX"))
    root.register_capability(_AssessStub())
    root.register_capability(_StubCapability("generation", "answer", "RESPUESTA"))
    root.register_capability(_VerifyStub())
    root.register_capability(_FinalizeStub())
    root.add_policy(LinearRagPolicy())
    bundle = root.build()

    st = ExecutionState(question="que es iso 27001?", use_llm=True, max_iterations=14)
    out = bundle.controller.run(st)
    assert out.answer == "RESPUESTA"
    assert out.context == "CTX"
    assert out.results and out.done
    assert out.iteration >= 9
    assert out.metadata.get("assessed") is True
    assert out.metadata.get("verified") is True
    assert out.metadata.get("finalized") is True
