"""DeduplicationPass — elimina claims duplicados de multiples extractores (RES-002 §5).

Cuando multiples extractores producen el mismo claim, se aplica la
Confidence Policy para combinar y se conserva un unico claim.

La policy es inyectable (no es un pass fijo). Por defecto: ``weighted``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..kir import (
    AliasClaim,
    DocumentClaim,
    EntityClaim,
    EvidenceItem,
    KIR,
    RelationClaim,
    normalize_text,
    slugify,
)
from .base import KnowledgePass


class DeduplicationPass(KnowledgePass):
    """Elimina duplicados y combina confidence de multiples extractores."""

    def __init__(self, confidence_policy=None):
        self.confidence_policy = confidence_policy

    def run(self, kir: KIR) -> KIR:
        out = KIR(metadata=dict(kir.metadata))
        out.entity_claims = self._dedup_entities(kir.entity_claims)
        out.alias_claims = self._dedup_aliases(kir.alias_claims)
        out.document_claims = self._dedup_documents(kir.document_claims)
        out.relation_claims = self._dedup_relations(kir.relation_claims)
        return out

    def _combine_confidence(self, claims: List[Any]) -> float:
        confidences = [c.confidence for c in claims if c.confidence > 0]
        if not confidences:
            return 0.0
        if self.confidence_policy:
            return self.confidence_policy.combine(confidences, [c.extractor_id for c in claims])
        return max(confidences)

    @staticmethod
    def _merge_evidence(claims: List[Any]) -> List[EvidenceItem]:
        seen: set = set()
        out: List[EvidenceItem] = []
        for c in claims:
            for ev in c.evidence:
                key = (ev.source_doc_id, ev.quote)
                if key not in seen:
                    seen.add(key)
                    out.append(ev)
        return out

    @staticmethod
    def _merge_types(claims: List[EntityClaim]) -> List[str]:
        types: List[str] = []
        for c in claims:
            for t in c.entity_types:
                if t not in types:
                    types.append(t)
        return types

    def _dedup_entities(self, claims: List[EntityClaim]) -> List[EntityClaim]:
        groups: Dict[str, List[EntityClaim]] = {}
        for c in claims:
            key = normalize_text(c.canonical_name)
            groups.setdefault(key, []).append(c)
        out: List[EntityClaim] = []
        for key, group in groups.items():
            if len(group) == 1:
                out.append(group[0])
                continue
            merged = EntityClaim(
                surface_form=group[0].surface_form,
                canonical_name=group[0].canonical_name,
                entity_types=self._merge_types(group),
                extractor_id=",".join(sorted(set(c.extractor_id for c in group))),
                confidence=self._combine_confidence(group),
                evidence=self._merge_evidence(group),
                raw={**dict(group[0].raw), "merged_from": [c.extractor_id for c in group]},
            )
            out.append(merged)
        return out

    def _dedup_aliases(self, claims: List[AliasClaim]) -> List[AliasClaim]:
        groups: Dict[Tuple[str, str], List[AliasClaim]] = {}
        for c in claims:
            key = (normalize_text(c.alias), normalize_text(c.canonical_name))
            groups.setdefault(key, []).append(c)
        out: List[AliasClaim] = []
        for key, group in groups.items():
            if len(group) == 1:
                out.append(group[0])
                continue
            merged = AliasClaim(
                alias=group[0].alias,
                canonical_name=group[0].canonical_name,
                extractor_id=",".join(sorted(set(c.extractor_id for c in group))),
                confidence=self._combine_confidence(group),
                evidence=self._merge_evidence(group),
                raw={**dict(group[0].raw), "merged_from": [c.extractor_id for c in group]},
            )
            out.append(merged)
        return out

    def _dedup_documents(self, claims: List[DocumentClaim]) -> List[DocumentClaim]:
        groups: Dict[str, List[DocumentClaim]] = {}
        for c in claims:
            key = slugify(c.name)
            groups.setdefault(key, []).append(c)
        out: List[DocumentClaim] = []
        for key, group in groups.items():
            if len(group) == 1:
                out.append(group[0])
                continue
            best = max(group, key=lambda c: c.confidence)
            merged = DocumentClaim(
                source_path=best.source_path,
                name=best.name,
                role=best.role,
                attributes=list(dict.fromkeys(
                    a for c in group for a in c.attributes
                )),
                centrality=max(c.centrality for c in group),
                entity_mentions=list(dict.fromkeys(
                    e for c in group for e in c.entity_mentions
                )),
                summary=best.summary,
                extractor_id=",".join(sorted(set(c.extractor_id for c in group))),
                confidence=self._combine_confidence(group),
                evidence=self._merge_evidence(group),
                raw={**dict(best.raw), "merged_from": [c.extractor_id for c in group]},
            )
            out.append(merged)
        return out

    def _dedup_relations(self, claims: List[RelationClaim]) -> List[RelationClaim]:
        groups: Dict[Tuple[str, str, str], List[RelationClaim]] = {}
        for c in claims:
            key = (normalize_text(c.subject_name), normalize_text(c.predicate), normalize_text(c.object_name))
            groups.setdefault(key, []).append(c)
        out: List[RelationClaim] = []
        for key, group in groups.items():
            if len(group) == 1:
                out.append(group[0])
                continue
            merged = RelationClaim(
                subject_name=group[0].subject_name,
                predicate=group[0].predicate,
                object_name=group[0].object_name,
                extractor_id=",".join(sorted(set(c.extractor_id for c in group))),
                confidence=self._combine_confidence(group),
                evidence=self._merge_evidence(group),
                raw={**dict(group[0].raw), "merged_from": [c.extractor_id for c in group]},
            )
            out.append(merged)
        return out
