"""Cold Codegen — dumpea internals para auditoria (RES-002 §8).

Cold Artifacts son solo internos al build. No se referencian en el manifest.
Incluyen:
    - KIR snapshot (lossless)
    - Validation report
    - Extractor outputs individuales
    - Build metadata
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping

from ..kir import KIR
from ..validate.validator import ValidationResult


class ColdCodegen:
    """Genera Cold Artifacts para auditoria y debugging."""

    def __init__(self, output_dir: Path | str | None = None):
        self.output_dir = Path(output_dir) if output_dir else None

    def generate(
        self,
        kir: KIR,
        validation: ValidationResult,
        build_metadata: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Genera Cold Artifacts en memoria.

        Returns:
            Dict con ``kir_snapshot``, ``validation_report``, ``build_metadata``.
        """
        return {
            "kir_snapshot": kir.to_dict(),
            "validation_report": validation.to_dict(),
            "build_metadata": dict(build_metadata or {}),
        }

    def write_to_dir(self, cold_artifacts: Mapping[str, Any], build_id: str) -> Path:
        """Escribe Cold Artifacts a disco si output_dir esta configurado."""
        if not self.output_dir:
            raise ValueError("output_dir no configurado")
        cold_dir = self.output_dir / build_id / "cold"
        cold_dir.mkdir(parents=True, exist_ok=True)
        for name, data in cold_artifacts.items():
            path = cold_dir / f"{name}.json"
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return cold_dir
