"""Back-end: Artifact Generation (RES-002 §8).

Analogico a codegen en un compiler real:
    - Warm codegen: serializa el Knowledge Model a Warm Artifacts (JSON)
    - Cold codegen: dumpea internals (KIR snapshots, validation reports)

El back-end es intercambiable: mismo Knowledge Model -> distintos formatos.
"""

from __future__ import annotations

from .warm_codegen import WarmCodegen
from .cold_codegen import ColdCodegen

__all__ = ["WarmCodegen", "ColdCodegen"]
