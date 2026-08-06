"""CanonicalizePass — canonicalizacion de KIR (RES-002 §5).

Asigna:
    - entity_id estables: ``ent:{slug(canonical_name)}``
    - doc_id estables: ``doc:{slug(name)}``
    - Predicados de relacion al catalogo controlado
    - Taxonomia de roles normalizada
    - Alias -> entidad canonica resuelta

Este pass NO elimina claims (eso es DeduplicationPass).
Solo asigna formas estables y resuelve referencias.
"""

from __future__ import annotations

from typing import Dict, List, Set

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


_ROLE_TAXONOMY: Dict[str, str] = {
    "framework_list": "list",
    "cert_list": "list",
    "standard_profile": "entity_profile",
    "entity_profile": "entity_profile",
    "procedure": "guide",
    "manual_reference": "reference",
    "security_ops": "guide",
    "analysis_report": "analysis",
    "threat_intel": "analysis",
    "policy_compliance": "reference",
    "list": "list",
    "guide": "guide",
    "reference": "reference",
    "analysis": "analysis",
    "other": "other",
}


_PREDICATE_FALLBACK: Dict[str, str] = {
    "related_to": "references",
    "requires": "depends_on",
    "contradicts": "references",
    "provides": "creates",
    "includes": "contains",
    "contains": "contains",
    "describes": "references",
    "covers": "references",
    "applies_to": "references",
    "supports": "implements",
    "aligned_with": "equivalent_to",
    "complies_with": "governs",
    "defines": "creates",
    "belongs_to": "contains",
    "part_of": "contains",
    "supersedes": "extends",
    "located_in": "references",
    "certifies": "governs",
    "compares_with": "references",
    "is_certification_for": "governs",
    "is_used_by": "uses",
    "is_part_of": "contains",
    "is_located_in": "references",
    "is_composed_of": "contains",
    "is_based_on": "depends_on",
    "is_alternative_to": "equivalent_to",
    "is_derived_from": "depends_on",
    "is_type_of": "extends",
    "is_instance_of": "implements",
    "produces": "creates",
    "interacts_with": "references",
    "derived_from": "depends_on",
    "alternative_to": "equivalent_to",
    "created_by": "creates",
    "is part of": "contains",
    "is used by": "uses",
    "is based on": "depends_on",
    "is composed of": "contains",
    "is located in": "references",
    "is alternative to": "equivalent_to",
    "is derived from": "depends_on",
    "is type of": "extends",
    "is instance of": "implements",
    "is certification for": "governs",
    "is equivalent to": "equivalent_to",
    "depends on": "depends_on",
    "is governed by": "governs",
    "is contained in": "contains",
    "is created by": "creates",
    "is implemented by": "implements",
    "is extended by": "extends",
    "is referenced by": "references",
    "enforces": "governs",
    "mandates": "governs",
    "requires_compliance_with": "governs",
    "is_required_by": "depends_on",
    "replaces": "extends",
    "superseded_by": "extends",
    "based_on": "depends_on",
    "composed_of": "contains",
    "consists_of": "contains",
    "incorporates": "contains",
    "embeds": "contains",
    "utilizes": "uses",
    "consumes": "uses",
    "invokes": "uses",
    "calls": "uses",
    "is_called_by": "uses",
    "is_utilized_by": "uses",
    "implements_for": "implements",
    "specializes": "extends",
    "generalizes": "extends",
    "inherits_from": "extends",
    "is_inherited_by": "extends",
    "maps_to": "references",
    "corresponds_to": "references",
    "is_equivalent_to": "equivalent_to",
    "is_similar_to": "references",
    "is_related_to": "references",
    "is_associated_with": "references",
    "is_compatible_with": "references",
    "is_incompatible_with": "references",
    "precedes": "references",
    "follows": "references",
    "enables": "supports",
    "is_enabled_by": "depends_on",
    "facilitates": "supports",
    "is_facilitated_by": "depends_on",
    "is_defined_in": "references",
    "is_described_in": "references",
    "is_specified_in": "references",
    "documents": "references",
    "specifies": "creates",
    "establishes": "creates",
    "determines": "creates",
    "identifies": "creates",
    "categorizes": "references",
    "classifies": "references",
    "groups": "contains",
    "aggregates": "contains",
    "is_grouped_in": "contains",
    "is_aggregated_in": "contains",
}


class CanonicalizePass(KnowledgePass):
    """Asigna ids estables, resuelve aliases, mapea predicados al catalogo."""

    def __init__(self, predicate_catalog: List[str] | None = None):
        self.predicates = set(predicate_catalog or [])

    def run(self, kir: KIR) -> KIR:
        out = KIR(metadata=dict(kir.metadata))

        canonical_map: Dict[str, str] = {}
        for c in kir.entity_claims:
            key = normalize_text(c.canonical_name)
            if key and key not in canonical_map:
                canonical_map[key] = f"ent:{slugify(c.canonical_name)}"

        out.entity_claims = [
            self._canon_entity(c, canonical_map) for c in kir.entity_claims
        ]
        out.alias_claims = [
            self._canon_alias(c, canonical_map) for c in kir.alias_claims
        ]
        out.document_claims = [self._canon_document(c) for c in kir.document_claims]
        out.relation_claims = [
            self._canon_relation(c, canonical_map) for c in kir.relation_claims
        ]

        out.metadata["canonical_map"] = dict(canonical_map)
        return out

    @staticmethod
    def _canon_entity(c: EntityClaim, cmap: Dict[str, str]) -> EntityClaim:
        key = normalize_text(c.canonical_name)
        eid = cmap.get(key, f"ent:{slugify(c.canonical_name)}")
        return EntityClaim(
            surface_form=c.surface_form,
            canonical_name=c.canonical_name,
            entity_types=list(c.entity_types),
            extractor_id=c.extractor_id,
            confidence=c.confidence,
            evidence=list(c.evidence),
            raw={**dict(c.raw), "entity_id": eid},
        )

    @staticmethod
    def _canon_alias(c: AliasClaim, cmap: Dict[str, str]) -> AliasClaim:
        key = normalize_text(c.canonical_name)
        eid = cmap.get(key, f"ent:{slugify(c.canonical_name)}")
        return AliasClaim(
            alias=c.alias,
            canonical_name=c.canonical_name,
            extractor_id=c.extractor_id,
            confidence=c.confidence,
            evidence=list(c.evidence),
            raw={**dict(c.raw), "entity_id": eid},
        )

    @staticmethod
    def _canon_document(c: DocumentClaim) -> DocumentClaim:
        doc_id = f"doc:{slugify(c.name)}"
        role = _ROLE_TAXONOMY.get(c.role, "other")
        return DocumentClaim(
            source_path=c.source_path,
            name=c.name,
            role=role,
            attributes=list(c.attributes),
            centrality=c.centrality,
            entity_mentions=list(c.entity_mentions),
            summary=c.summary,
            extractor_id=c.extractor_id,
            confidence=c.confidence,
            evidence=list(c.evidence),
            raw={**dict(c.raw), "doc_id": doc_id},
        )

    def _canon_relation(self, c: RelationClaim, cmap: Dict[str, str]) -> RelationClaim:
        pred = normalize_text(c.predicate)
        original_pred = c.predicate
        fallback_applied = False
        if self.predicates and pred not in self.predicates:
            pred = _PREDICATE_FALLBACK.get(pred, pred)
            fallback_applied = True
            if pred not in self.predicates:
                pred = "references" if "references" in self.predicates else "equivalent_to"
        raw = {**dict(c.raw), "subject_id": cmap.get(c.subject_name, ""), "object_id": cmap.get(c.object_name, "")}
        if fallback_applied and original_pred:
            raw["original_predicate"] = original_pred
        return RelationClaim(
            subject_name=c.subject_name,
            predicate=pred,
            object_name=c.object_name,
            extractor_id=c.extractor_id,
            confidence=c.confidence,
            attributes=list(c.attributes),
            evidence=list(c.evidence),
            raw=raw,
        )
