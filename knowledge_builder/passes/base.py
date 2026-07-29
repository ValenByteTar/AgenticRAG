"""KnowledgePass — interfaz base para todos los passes (RES-002 §5).

Todo lo que transforma KIR es un pass. Los passes son plugins.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..kir import KIR


class KnowledgePass(ABC):
    """Interfaz base: run(kir) -> kir."""

    @abstractmethod
    def run(self, kir: KIR) -> KIR:
        """Transforma KIR y retorna el resultado. No muta el original."""
        ...

    @property
    def name(self) -> str:
        return self.__class__.__name__
