"""
ExecutionState y tipos de senal/decision (ADR-0004, ADR-0006, ADR-0013).

Estado explicito y serializable. Sin estado oculto (P5).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional
import time
import uuid


@dataclass
class EvaluationSignal:
    """
    Senal producida por Evaluation (offline u online).
    Evaluation produce senales; no decide (ADR-0006).
    """

    name: str
    score: float = 0.0
    passed: Optional[bool] = None
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    source: str = "online"  # "online" | "offline"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ActionDecision:
    """
    Decision emitida por una Policy / PolicyEngine.
    Policy decide; no ejecuta (ADR-0013).
    """

    action: str
    capability_ref: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    terminate: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TraceEvent:
    """Evento de observabilidad (ADR-0005)."""

    kind: str
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)
    duration_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionState:
    """
    Estado de una ejecucion de consulta (ADR-0004).

    Transporta pregunta, resultados, senales, presupuesto y trazas.
    Los Steps solo leen/escriben este objeto.
    """

    question: str
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    # Entrada / contexto de consulta
    length_mode: Optional[str] = None
    top_k: int = 50
    semantic_weight: float = 0.6
    use_llm: bool = True
    entities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Resultados intermedios
    results: List[Dict[str, Any]] = field(default_factory=list)
    context: str = ""
    answer: str = ""
    sources: List[Dict[str, Any]] = field(default_factory=list)

    # Evaluation -> Policy
    signals: List[EvaluationSignal] = field(default_factory=list)
    last_decision: Optional[ActionDecision] = None

    # Presupuesto (P10)
    max_iterations: int = 8
    iteration: int = 0
    max_llm_calls: int = 6
    llm_calls: int = 0

    # Observability
    traces: List[TraceEvent] = field(default_factory=list)
    timing_ms: Dict[str, float] = field(default_factory=dict)

    # Control de terminacion
    done: bool = False
    decline: bool = False
    error: Optional[str] = None

    # Streaming (transient — no se serializa)
    token_callback: Optional[Callable[[str], None]] = None
    cancel_checker: Optional[Callable[[], bool]] = None

    def add_signal(self, signal: EvaluationSignal) -> None:
        self.signals.append(signal)

    def latest_signal(self, name: Optional[str] = None) -> Optional[EvaluationSignal]:
        if not self.signals:
            return None
        if name is None:
            return self.signals[-1]
        for s in reversed(self.signals):
            if s.name == name:
                return s
        return None

    def add_trace(self, kind: str, message: str = "", data: Optional[Dict[str, Any]] = None,
                  duration_ms: Optional[float] = None) -> TraceEvent:
        ev = TraceEvent(kind=kind, message=message, data=data or {}, duration_ms=duration_ms)
        self.traces.append(ev)
        return ev

    def budget_exhausted(self) -> bool:
        return self.iteration >= self.max_iterations or self.llm_calls >= self.max_llm_calls

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "run_id": self.run_id,
            "length_mode": self.length_mode,
            "top_k": self.top_k,
            "semantic_weight": self.semantic_weight,
            "use_llm": self.use_llm,
            "entities": list(self.entities),
            "metadata": dict(self.metadata),
            "results": list(self.results),
            "context": self.context,
            "answer": self.answer,
            "sources": list(self.sources),
            "signals": [s.to_dict() for s in self.signals],
            "last_decision": self.last_decision.to_dict() if self.last_decision else None,
            "max_iterations": self.max_iterations,
            "iteration": self.iteration,
            "max_llm_calls": self.max_llm_calls,
            "llm_calls": self.llm_calls,
            "traces": [t.to_dict() for t in self.traces],
            "timing_ms": dict(self.timing_ms),
            "done": self.done,
            "decline": self.decline,
            "error": self.error,
            # token_callback y cancel_checker son transient: no se serializan
        }

    def to_query_result(self) -> Dict[str, Any]:
        """Fachada estable de retorno (ADR-0010) compatible con HybridRAG.query()."""
        raw = self.metadata.get("_raw_linear_dict")
        if raw is not None and isinstance(raw, dict):
            out = dict(raw)
            out["answer"] = self.answer
            out["sources"] = self.sources
            return out
        mh = self.metadata.get("memory_hits_count")
        if mh is None:
            hits = self.metadata.get("memory_hits")
            mh = len(hits) if isinstance(hits, list) else int(hits or 0)
        return {
            "question": self.question,
            "results": self.results,
            "context": self.context,
            "answer": self.answer,
            "sources": self.sources,
            "method": "kernel",
            "memory_hits": int(mh or 0),
            "time": float(self.timing_ms.get("t_total_s", 0.0) or 0.0),
            "timing_breakdown": dict(self.timing_ms),
            "run_id": self.run_id,
            "traces": [t.to_dict() for t in self.traces],
        }


@dataclass
class ExecutionResult:
    """
    Resultado de ejecucion tipado (ADR-0020).
    Contrato unico de ejecucion del sistema.
    """

    answer: str
    sources: List[Dict[str, Any]]
    execution_state: ExecutionState

    def to_query_result(self) -> Dict[str, Any]:
        """Shim de compatibilidad con la fachada dict historica query() (ADR-0010 / ADR-0020)."""
        res = self.execution_state.to_query_result()
        res["answer"] = self.answer
        res["sources"] = self.sources
        return res


class LinearStateAdapter:
    """
    Adaptador transitorio (ADR-0020) para construir ExecutionState parcial desde
    el retorno dict del camino lineal monolito (_query_linear_impl).

    Condicion de cierre: borrado en el mismo commit que BM-005 cuando kernel.enabled=true sea default.
    """

    @staticmethod
    def build_state(question: str, result_dict: Dict[str, Any]) -> ExecutionState:
        state = ExecutionState(
            question=question,
            answer=result_dict.get("answer", "") or "",
            sources=result_dict.get("sources", []) or [],
            results=result_dict.get("results", []) or [],
            context=result_dict.get("context", "") or "",
            timing_ms=dict(result_dict.get("timing_breakdown", {}) or {}),
            run_id=result_dict.get("run_id", "") or "",
            done=True,
        )
        state.metadata["state_fidelity"] = "partial"
        state.metadata["_raw_linear_dict"] = result_dict
        state.signals = []
        return state

