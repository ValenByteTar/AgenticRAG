"""
Contratos del Kernel (ADR-0016).

Interfaces estables. El Kernel conoce estos contratos, jamas implementaciones (P2).
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Protocol, runtime_checkable

from src.kernel.state import ActionDecision, EvaluationSignal, ExecutionState


@runtime_checkable
class Step(Protocol):
    """Unidad minima de trabajo sobre ExecutionState."""

    name: str

    def run(self, state: ExecutionState) -> ExecutionState:
        ...


@runtime_checkable
class Capability(Protocol):
    """
    Capacidad registrada (ADR-0012).
    Vive fuera del Kernel; se resuelve por el Registry.
    """

    name: str

    def execute(self, state: ExecutionState, params: Optional[Dict[str, Any]] = None) -> ExecutionState:
        ...


@runtime_checkable
class Policy(Protocol):
    """
    Policy pura: interpreta senales + estado y devuelve decision (ADR-0013).
    Una policy = una decision. No ejecuta, no llama capabilities.
    """

    name: str

    def decide(self, state: ExecutionState) -> Optional[ActionDecision]:
        ...


@runtime_checkable
class Evaluator(Protocol):
    """
    Evaluation online (ADR-0006): produce EvaluationSignal, no decide.
    """

    name: str

    def evaluate(self, state: ExecutionState) -> EvaluationSignal:
        ...


@runtime_checkable
class ModelProvider(Protocol):
    """Proveedor de modelos (ADR-0007)."""

    name: str
    model: str

    def generate(
        self,
        prompt: str,
        *,
        options: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> str:
        ...

    def stream(
        self,
        prompt: str,
        *,
        options: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Iterator[str]:
        ...

    def is_available(self) -> bool:
        ...


@runtime_checkable
class KnowledgeSystem(Protocol):
    """
    Subsistema de conocimiento (ADR-0015).
    Frontera reservada; esquema interno diferido.
    """

    def retrieve(self, query: str, **kwargs: Any) -> List[Dict[str, Any]]:
        ...

    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        ...


@runtime_checkable
class MemoryPort(Protocol):
    """Contrato de memoria (ADR-0009). Nombre MemoryPort para no chocar con typing."""

    def read(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        ...

    def write(self, record: Dict[str, Any]) -> bool:
        ...


@runtime_checkable
class Tool(Protocol):
    """Herramienta tipada (ADR-0009)."""

    name: str

    def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ...


@runtime_checkable
class Controller(Protocol):
    """
    Runtime del Controller (ADR-0002).
    Solo ejecuta acciones decididas; no conoce capabilities concretas.
    """

    def run(self, state: ExecutionState) -> ExecutionState:
        ...
