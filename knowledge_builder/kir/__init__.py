"""Knowledge Intermediate Representation (KIR) — lossless IR (RES-002 §4).

KIR es el punto de convergencia: multiples extractores producen exactamente
el mismo formato. No se persiste como contrato. Es interno del compiler.

Propiedad fundamental: KIR es lossless. Toda transformacion posterior
(normalize, canonicalize, validate, codegen) debe poder justificarse
remontandose al KIR original.

Estructura:

    KIR
      |-- entity_claims:   List[EntityClaim]     (Layer 2: Entity)
      |-- alias_claims:    List[AliasClaim]       (Layer 2: Entity)
      |-- document_claims: List[DocumentClaim]    (Layer 1: Document)
      |-- relation_claims: List[RelationClaim]    (Layer 4: Relation)
      |-- metadata:        dict                   (build metadata)

Cada claim preserva:
    - extractor_id:  que extractor lo produjo
    - confidence:    confianza del extractor
    - evidence:      evidencia del corpus
    - raw:           datos originales del extractor (lossless)
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# --------------------------------------------------------------------------- #
# Claim dataclasses
# --------------------------------------------------------------------------- #

@dataclass
class EvidenceItem:
    """Evidencia de un claim contra el corpus."""
    source_doc_id: str = ""
    source_chunk_ids: List[str] = field(default_factory=list)
    quote: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"source_doc_id": self.source_doc_id}
        if self.source_chunk_ids:
            d["source_chunk_ids"] = list(self.source_chunk_ids)
        if self.quote:
            d["quote"] = self.quote
        return d


@dataclass
class EntityClaim:
    """Entidad canonica candidata detectada por un extractor."""
    surface_form: str
    canonical_name: str
    entity_types: List[str] = field(default_factory=list)
    extractor_id: str = ""
    confidence: float = 0.0
    evidence: List[EvidenceItem] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def claim_type(self) -> str:
        return "entity"


@dataclass
class AliasClaim:
    """Alias que apunta a una entidad canonica."""
    alias: str
    canonical_name: str
    extractor_id: str = ""
    confidence: float = 0.0
    evidence: List[EvidenceItem] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def claim_type(self) -> str:
        return "alias"


@dataclass
class DocumentClaim:
    """Conocimiento sobre un documento (rol, atributos, centralidad)."""
    source_path: str
    name: str
    role: str = "other"
    attributes: List[str] = field(default_factory=list)
    centrality: float = 0.0
    entity_mentions: List[str] = field(default_factory=list)
    summary: str = ""
    extractor_id: str = ""
    confidence: float = 0.0
    evidence: List[EvidenceItem] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def claim_type(self) -> str:
        return "document"


@dataclass
class RelationClaim:
    """Triple subject/predicate/object con evidencia."""
    subject_name: str
    predicate: str
    object_name: str
    extractor_id: str = ""
    confidence: float = 0.0
    evidence: List[EvidenceItem] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def claim_type(self) -> str:
        return "relation"


# --------------------------------------------------------------------------- #
# KIR container
# --------------------------------------------------------------------------- #

@dataclass
class KIR:
    """Knowledge Intermediate Representation — lossless."""
    entity_claims: List[EntityClaim] = field(default_factory=list)
    alias_claims: List[AliasClaim] = field(default_factory=list)
    document_claims: List[DocumentClaim] = field(default_factory=list)
    relation_claims: List[RelationClaim] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def merge(self, other: "KIR") -> "KIR":
        """Merge another KIR into this one (for multiple extractors)."""
        self.entity_claims.extend(other.entity_claims)
        self.alias_claims.extend(other.alias_claims)
        self.document_claims.extend(other.document_claims)
        self.relation_claims.extend(other.relation_claims)
        for key, val in other.metadata.items():
            if key not in self.metadata:
                self.metadata[key] = val
        return self

    def claim_count(self) -> int:
        return (
            len(self.entity_claims)
            + len(self.alias_claims)
            + len(self.document_claims)
            + len(self.relation_claims)
        )

    def extractor_ids(self) -> List[str]:
        ids: set = set()
        for c in self.entity_claims:
            ids.add(c.extractor_id)
        for c in self.alias_claims:
            ids.add(c.extractor_id)
        for c in self.document_claims:
            ids.add(c.extractor_id)
        for c in self.relation_claims:
            ids.add(c.extractor_id)
        return sorted(ids)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize KIR to dict (for Cold artifacts / debugging)."""
        def _ev(ev_list: List[EvidenceItem]) -> List[Dict[str, Any]]:
            return [e.to_dict() for e in ev_list]

        return {
            "metadata": dict(self.metadata),
            "entity_claims": [
                {
                    "surface_form": c.surface_form,
                    "canonical_name": c.canonical_name,
                    "entity_types": list(c.entity_types),
                    "extractor_id": c.extractor_id,
                    "confidence": c.confidence,
                    "evidence": _ev(c.evidence),
                    "raw": dict(c.raw),
                }
                for c in self.entity_claims
            ],
            "alias_claims": [
                {
                    "alias": c.alias,
                    "canonical_name": c.canonical_name,
                    "extractor_id": c.extractor_id,
                    "confidence": c.confidence,
                    "evidence": _ev(c.evidence),
                    "raw": dict(c.raw),
                }
                for c in self.alias_claims
            ],
            "document_claims": [
                {
                    "source_path": c.source_path,
                    "name": c.name,
                    "role": c.role,
                    "attributes": list(c.attributes),
                    "centrality": c.centrality,
                    "entity_mentions": list(c.entity_mentions),
                    "summary": c.summary,
                    "extractor_id": c.extractor_id,
                    "confidence": c.confidence,
                    "evidence": _ev(c.evidence),
                    "raw": dict(c.raw),
                }
                for c in self.document_claims
            ],
            "relation_claims": [
                {
                    "subject_name": c.subject_name,
                    "predicate": c.predicate,
                    "object_name": c.object_name,
                    "extractor_id": c.extractor_id,
                    "confidence": c.confidence,
                    "evidence": _ev(c.evidence),
                    "raw": dict(c.raw),
                }
                for c in self.relation_claims
            ],
        }


# --------------------------------------------------------------------------- #
# Normalization helpers (used by passes)
# --------------------------------------------------------------------------- #

def normalize_text(s: str) -> str:
    """Lowercase, strip accents, normalize whitespace."""
    if not isinstance(s, str):
        return ""
    s = s.strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s


def slugify(s: str) -> str:
    """Convert a string to a slug suitable for entity_id or doc_id."""
    n = normalize_text(s)
    n = re.sub(r"[^a-z0-9]+", "-", n)
    n = n.strip("-")
    return n or "unknown"
