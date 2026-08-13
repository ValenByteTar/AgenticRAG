"""
Composition Root (ADR-0014).

Unico lugar que cablea implementaciones concretas.
Ningun otro componente crea sus dependencias (P13).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.kernel.controller import KernelController
from src.kernel.contracts import Capability, ModelProvider, Policy
from src.kernel.observability import InMemoryTraceSink, TraceSink
from src.kernel.policy_engine import PolicyEngine
from src.kernel.registry import CapabilityRegistry


@dataclass
class KernelBundle:
    """Objetos del Kernel ya cableados."""

    registry: CapabilityRegistry
    policy_engine: PolicyEngine
    controller: KernelController
    trace_sink: TraceSink
    model_provider: Optional[ModelProvider] = None
    extras: Dict[str, Any] = field(default_factory=dict)


class CompositionRoot:
    """
    Cablea el Kernel. No contiene logica de negocio.

    Uso tipico:
        root = CompositionRoot()
        root.register_capability(...)
        root.add_policy(...)
        root.set_model_provider(...)
        bundle = root.build()
    """

    def __init__(self, trace_sink: Optional[TraceSink] = None) -> None:
        self._registry = CapabilityRegistry()
        self._policies: List[Policy] = []
        self._trace_sink: TraceSink = trace_sink or InMemoryTraceSink()
        self._model_provider: Optional[ModelProvider] = None
        self._extras: Dict[str, Any] = {}

    def register_capability(self, capability: Capability) -> "CompositionRoot":
        self._registry.register(capability)
        return self

    def add_policy(self, policy: Policy) -> "CompositionRoot":
        self._policies.append(policy)
        return self

    def set_model_provider(self, provider: ModelProvider) -> "CompositionRoot":
        self._model_provider = provider
        return self

    def set_extra(self, key: str, value: Any) -> "CompositionRoot":
        self._extras[key] = value
        return self

    def build(self) -> KernelBundle:
        engine = PolicyEngine(self._policies)
        controller = KernelController(
            registry=self._registry,
            policy_engine=engine,
            trace_sink=self._trace_sink,
        )
        return KernelBundle(
            registry=self._registry,
            policy_engine=engine,
            controller=controller,
            trace_sink=self._trace_sink,
            model_provider=self._model_provider,
            extras=dict(self._extras),
        )
