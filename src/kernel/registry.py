"""
Capability Registry (ADR-0012).

Resuelve referencias a capabilities. No decide (P14).
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from src.kernel.contracts import Capability


class CapabilityRegistry:
    """Registro/resolucion de capabilities. Vive en el Kernel."""

    def __init__(self) -> None:
        self._caps: Dict[str, Capability] = {}

    def register(self, capability: Capability) -> None:
        name = getattr(capability, "name", None)
        if not name or not isinstance(name, str):
            raise ValueError("Capability debe exponer name: str")
        self._caps[name] = capability

    def unregister(self, name: str) -> None:
        self._caps.pop(name, None)

    def resolve(self, name: str) -> Capability:
        try:
            return self._caps[name]
        except KeyError as exc:
            raise KeyError(f"Capability no registrada: {name}") from exc

    def has(self, name: str) -> bool:
        return name in self._caps

    def names(self) -> List[str]:
        return sorted(self._caps.keys())

    def all(self) -> Iterable[Capability]:
        return self._caps.values()

    def clear(self) -> None:
        self._caps.clear()
