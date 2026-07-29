"""NormalizePass — normalizacion de KIR (RES-002 §5).

Normaliza:
    - Casing: canonical_name y alias en forma normalizada (lowercase, sin acentos)
    - Whitespace: espacios multiples -> uno
    - Tipos de entidad: deduplicados, normalizados
    - Surface forms: preservadas pero normalizadas para comparacion
"""

from __future__ import annotations

from ..kir import (
    AliasClaim,
    DocumentClaim,
    EntityClaim,
    EvidenceItem,
    KIR,
    RelationClaim,
    normalize_text,
)
from .base import KnowledgePass


class NormalizePass(KnowledgePass):
    """Normaliza casing, whitespace, acentos en todos los claims de KIR."""

    def run(self, kir: KIR) -> KIR:
        out = KIR(metadata=dict(kir.metadata))
        out.entity_claims = [self._norm_entity(c) for c in kir.entity_claims]
        out.alias_claims = [self._norm_alias(c) for c in kir.alias_claims]
        out.document_claims = [self._norm_document(c) for c in kir.document_claims]
        out.relation_claims = [self._norm_relation(c) for c in kir.relation_claims]
        return out

    @staticmethod
    def _norm_entity(c: EntityClaim) -> EntityClaim:
        return EntityClaim(
            surface_form=normalize_text(c.surface_form),
            canonical_name=normalize_text(c.canonical_name),
            entity_types=list(dict.fromkeys(
                normalize_text(t) for t in c.entity_types if t
            )),
            extractor_id=c.extractor_id,
            confidence=c.confidence,
            evidence=list(c.evidence),
            raw=dict(c.raw),
        )

    @staticmethod
    def _norm_alias(c: AliasClaim) -> AliasClaim:
        return AliasClaim(
            alias=normalize_text(c.alias),
            canonical_name=normalize_text(c.canonical_name),
            extractor_id=c.extractor_id,
            confidence=c.confidence,
            evidence=list(c.evidence),
            raw=dict(c.raw),
        )

    @staticmethod
    def _norm_document(c: DocumentClaim) -> DocumentClaim:
        return DocumentClaim(
            source_path=c.source_path,
            name=c.name.strip(),
            role=normalize_text(c.role),
            attributes=[normalize_text(a) for a in c.attributes if a],
            centrality=c.centrality,
            entity_mentions=[normalize_text(e) for e in c.entity_mentions if e],
            summary=c.summary.strip(),
            extractor_id=c.extractor_id,
            confidence=c.confidence,
            evidence=list(c.evidence),
            raw=dict(c.raw),
        )

    @staticmethod
    def _norm_relation(c: RelationClaim) -> RelationClaim:
        return RelationClaim(
            subject_name=normalize_text(c.subject_name),
            predicate=normalize_text(c.predicate),
            object_name=normalize_text(c.object_name),
            extractor_id=c.extractor_id,
            confidence=c.confidence,
            evidence=list(c.evidence),
            raw=dict(c.raw),
        )
