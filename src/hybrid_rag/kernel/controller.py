"""
Controller-runtime (ADR-0002, ADR-0003).

Solo ejecuta la accion decidida por PolicyEngine.
No conoce capabilities concretas: resuelve via CapabilityRegistry.
"""

from __future__ import annotations

import time
from typing import Optional

from src.kernel.observability import NullTraceSink, TraceSink
from src.kernel.policy_engine import PolicyEngine
from src.kernel.registry import CapabilityRegistry
from src.kernel.state import ActionDecision, ExecutionState, TraceEvent


class KernelController:
    """
    Primera implementacion del Controller (FSM de bucle acotado).

    Cadena: Policy decide -> Controller ejecuta -> Registry resuelve -> Capability trabaja.
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        policy_engine: PolicyEngine,
        trace_sink: Optional[TraceSink] = None,
    ) -> None:
        self._registry = registry
        self._policies = policy_engine
        self._traces = trace_sink or NullTraceSink()

    def run(self, state: ExecutionState) -> ExecutionState:
        t0 = time.time()
        self._emit(state, "controller.start", f"run_id={state.run_id}")

        while not state.done:
            if state.budget_exhausted():
                state.done = True
                state.add_trace("controller.budget", "presupuesto agotado")
                break

            state.iteration += 1
            decision = self._policies.decide(state)
            state.last_decision = decision
            self._emit(
                state,
                "policy.decision",
                decision.reason or decision.action,
                {
                    "action": decision.action,
                    "capability_ref": decision.capability_ref,
                    "terminate": decision.terminate,
                    "iteration": state.iteration,
                },
            )

            if decision.terminate or decision.action in ("terminate", "done", "decline"):
                if decision.action == "decline":
                    state.decline = True
                    if not state.answer:
                        state.answer = decision.params.get(
                            "message",
                            "No se encontro informacion en los documentos para esa consulta.",
                        )
                state.done = True
                break

            if decision.action == "invoke" or decision.capability_ref:
                cap_name = decision.capability_ref or decision.action
                state = self._invoke(state, cap_name, decision)
            else:
                state.error = f"decision sin capability_ref: {decision.action}"
                state.done = True
                self._emit(state, "controller.error", state.error)
                break

        state.timing_ms["t_total_s"] = round(time.time() - t0, 3)
        self._emit(state, "controller.end", f"iterations={state.iteration}")
        return state

    def _invoke(self, state: ExecutionState, cap_name: str, decision: ActionDecision) -> ExecutionState:
        t0 = time.time()
        try:
            capability = self._registry.resolve(cap_name)
        except KeyError as exc:
            state.error = str(exc)
            state.done = True
            self._emit(state, "registry.miss", str(exc))
            return state

        self._emit(state, "capability.start", cap_name, {"params": decision.params})
        try:
            state = capability.execute(state, decision.params or {})
        except Exception as exc:
            state.error = f"capability {cap_name} fallo: {exc}"
            state.done = True
            self._emit(state, "capability.error", state.error)
            return state

        dt = round((time.time() - t0) * 1000, 1)
        state.timing_ms[f"cap_{cap_name}_ms"] = dt
        self._emit(state, "capability.end", cap_name, {"duration_ms": dt})
        return state

    def _emit(self, state: ExecutionState, kind: str, message: str = "", data=None) -> None:
        ev = TraceEvent(kind=kind, message=message, data=data or {})
        self._traces.emit(ev, state)
