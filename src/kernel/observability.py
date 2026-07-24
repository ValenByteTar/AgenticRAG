"""
Observability substrate (ADR-0005).

Hooks de traza. No es una capability; atraviesa todos los planos.
"""

from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable

from src.kernel.state import ExecutionState, TraceEvent


@runtime_checkable
class TraceSink(Protocol):
    def emit(self, event: TraceEvent, state: Optional[ExecutionState] = None) -> None:
        ...


class InMemoryTraceSink:
    """Sink simple en memoria; util para tests y export al benchmark."""

    def __init__(self) -> None:
        self.events: List[TraceEvent] = []

    def emit(self, event: TraceEvent, state: Optional[ExecutionState] = None) -> None:
        self.events.append(event)
        if state is not None:
            state.traces.append(event)

    def clear(self) -> None:
        self.events.clear()

    def by_kind(self, kind: str) -> List[TraceEvent]:
        return [e for e in self.events if e.kind == kind]


class NullTraceSink:
    """No-op sink."""

    def emit(self, event: TraceEvent, state: Optional[ExecutionState] = None) -> None:
        if state is not None:
            state.traces.append(event)
