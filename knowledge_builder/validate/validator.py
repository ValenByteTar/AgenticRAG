"""IR Validation — Structural + Evidence (RES-002 §6).

No se publica directamente la salida cruda de Extract.
Toda candidatura a formar parte del Knowledge Model publicable pasa
por validacion formal.

Structural Validation (§6.1):
    - ids presentes y unicos
    - referencias resolubles (entity_id, doc_id)
    - predicados pertenecientes al catalogo controlado
    - ausencia de campos prohibidos en proyecciones Warm

Evidence Validation (§6.3):
    - toda entidad, alias o relacion debe tener evidencia
    - si no hay evidencia suficiente: descartar o cuarentena (Cold)

Semantic Validation (§6.2) — se activa en E5 con LLM:
    - consistencia de roles, contradicciones, colisiones de canonicos
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

from ..kir import KIR, normalize_text, slugify


@dataclass
class ValidationResult:
    """Resultado de validacion de KIR."""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    quarantined: List[str] = field(default_factory=list)
    passed: int = 0
    rejected: int = 0

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "quarantined": list(self.quarantined),
            "passed": self.passed,
            "rejected": self.rejected,
        }


class KIRValidator:
    """Valida KIR antes de construir el Knowledge Model."""

    def __init__(self, predicate_catalog: List[str] | None = None):
        self.predicates = set(predicate_catalog or [])

    def validate(self, kir: KIR) -> ValidationResult:
        result = ValidationResult()
        self._validate_entities(kir, result)
        self._validate_aliases(kir, result)
        self._validate_documents(kir, result)
        self._validate_relations(kir, result)
        return result

    def _validate_entities(self, kir: KIR, result: ValidationResult) -> None:
        seen_ids: Set[str] = set()
        for c in kir.entity_claims:
            eid = c.raw.get("entity_id", "")
            if not eid:
                result.errors.append(f"entity_claim sin entity_id: {c.canonical_name}")
                result.rejected += 1
                continue
            if eid in seen_ids:
                result.warnings.append(f"entity_claim duplicado (se mergea en Dedup): {eid}")
            else:
                seen_ids.add(eid)
            if not c.canonical_name:
                result.errors.append(f"entity_claim sin canonical_name: {eid}")
                result.rejected += 1
                continue
            if not c.evidence:
                result.quarantined.append(f"entity sin evidencia: {eid}")
                result.warnings.append(f"entity sin evidencia: {eid}")
            else:
                result.passed += 1

    def _validate_aliases(self, kir: KIR, result: ValidationResult) -> None:
        seen: Set[str] = set()
        for c in kir.alias_claims:
            eid = c.raw.get("entity_id", "")
            if not eid:
                result.errors.append(f"alias_claim sin entity_id: {c.alias} -> {c.canonical_name}")
                result.rejected += 1
                continue
            key = f"{normalize_text(c.alias)}:{eid}"
            if key in seen:
                result.warnings.append(f"alias_claim duplicado: {key}")
            else:
                seen.add(key)
            if not c.alias:
                result.errors.append(f"alias_claim sin alias: {eid}")
                result.rejected += 1
                continue
            if not c.evidence:
                result.quarantined.append(f"alias sin evidencia: {c.alias}")
                result.warnings.append(f"alias sin evidencia: {c.alias}")
            else:
                result.passed += 1

    def _validate_documents(self, kir: KIR, result: ValidationResult) -> None:
        seen: Set[str] = set()
        for c in kir.document_claims:
            doc_id = c.raw.get("doc_id", "")
            if not doc_id:
                result.errors.append(f"document_claim sin doc_id: {c.name}")
                result.rejected += 1
                continue
            if doc_id in seen:
                result.warnings.append(f"document_claim duplicado: {doc_id}")
            else:
                seen.add(doc_id)
            if not c.name:
                result.errors.append(f"document_claim sin name: {doc_id}")
                result.rejected += 1
                continue
            if not c.evidence:
                result.quarantined.append(f"document sin evidencia: {doc_id}")
                result.warnings.append(f"document sin evidencia: {doc_id}")
            else:
                result.passed += 1

    def _validate_relations(self, kir: KIR, result: ValidationResult) -> None:
        for c in kir.relation_claims:
            if not c.subject_name or not c.object_name:
                result.errors.append(f"relation_claim sin subject/object: {c.predicate}")
                result.rejected += 1
                continue
            if self.predicates and c.predicate not in self.predicates:
                result.errors.append(
                    f"relation_claim predicado fuera de catalogo: {c.predicate}"
                )
                result.rejected += 1
                continue
            if not c.evidence:
                result.quarantined.append(
                    f"relation sin evidencia: {c.subject_name} {c.predicate} {c.object_name}"
                )
                result.warnings.append(
                    f"relation sin evidencia: {c.subject_name} {c.predicate} {c.object_name}"
                )
            else:
                result.passed += 1
