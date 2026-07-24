"""
InfraPolus Kernel.

Nucleo estable: contratos, ExecutionState, Controller-runtime,
Capability Registry, Policy Engine, Observability hooks, Composition Root.

El Kernel conoce contratos, jamas implementaciones (ADR-0016).
"""

from src.kernel.state import ExecutionState, EvaluationSignal, ActionDecision, TraceEvent
from src.kernel.contracts import (
    Capability,
    Step,
    Policy,
    ModelProvider,
    KnowledgeSystem,
    MemoryPort,
    Tool,
    Controller,
    Evaluator,
)
from src.kernel.registry import CapabilityRegistry
from src.kernel.policy_engine import PolicyEngine
from src.kernel.controller import KernelController
from src.kernel.observability import TraceSink, InMemoryTraceSink
from src.kernel.composition import CompositionRoot

__all__ = [
    "ExecutionState",
    "EvaluationSignal",
    "ActionDecision",
    "TraceEvent",
    "Capability",
    "Step",
    "Policy",
    "ModelProvider",
    "KnowledgeSystem",
    "MemoryPort",
    "Tool",
    "Controller",
    "Evaluator",
    "CapabilityRegistry",
    "PolicyEngine",
    "KernelController",
    "TraceSink",
    "InMemoryTraceSink",
    "CompositionRoot",
]
