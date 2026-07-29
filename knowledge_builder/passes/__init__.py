"""IR Passes (Middle-End) — RES-002 §5.

Knowledge Pass API: todo lo que transforma KIR es un pass.

    class KnowledgePass:
        def run(self, kir: KIR) -> KIR:
            ...

Los passes son plugins: componibles, reordenables y extensibles.
Un nuevo pass se agrega sin tocar el resto del compiler.

Passes iniciales:
    - NormalizePass:      casing, whitespace, acentos, tipos
    - CanonicalizePass:   alias -> canonico, ids estables, predicados del catalogo
    - DeduplicationPass:  eliminar claims duplicados de multiples extractores
"""

from __future__ import annotations

from .base import KnowledgePass
from .normalize import NormalizePass
from .canonicalize import CanonicalizePass
from .dedup import DeduplicationPass

__all__ = [
    "KnowledgePass",
    "NormalizePass",
    "CanonicalizePass",
    "DeduplicationPass",
]
