"""Knowledge Model — validated KIR, layered (RES-002 §7).

El subconjunto de KIR que sobrevive validation. No es un archivo.
Es la estructura interna sobre la cual se razona, valida y proyecta.

Layers (E3: Document + Entity):
    Layer 1  Document Layer  -> doc_roles
    Layer 2  Entity Layer    -> canonical_entities, alias_index, entity_index

Layers futuras:
    Layer 3  Concept Layer   (E7)
    Layer 4  Relation Layer  (E7)
    Layer 5  Retrieval Layer (E6)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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


@dataclass
class CanonicalEntity:
    """Entidad canonica en el Knowledge Model."""
    entity_id: str
    canonical_name: str
    types: List[str] = field(default_factory=list)
    confidence: float = 0.0
    extractor_ids: List[str] = field(default_factory=list)
    evidence: List[EvidenceItem] = field(default_factory=list)

    def to_artifact(self, builder_version: str) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "canonical_name": self.canonical_name,
            "types": list(self.types),
            "confidence": round(self.confidence, 4),
            "validated": True,
            "builder_version": builder_version,
            "generated_by": {
                "extractor_id": ",".join(self.extractor_ids) if self.extractor_ids else "unknown",
            },
        }


@dataclass
class AliasEntry:
    """Alias -> entidad canonica en el Knowledge Model."""
    alias: str
    entity_id: str
    confidence: float = 0.0
    extractor_ids: List[str] = field(default_factory=list)
    evidence: List[EvidenceItem] = field(default_factory=list)

    def to_artifact(self, builder_version: str) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "confidence": round(self.confidence, 4),
            "validated": True,
            "builder_version": builder_version,
            "generated_by": {
                "extractor_id": ",".join(self.extractor_ids) if self.extractor_ids else "unknown",
            },
        }


@dataclass
class EntityIndexEntry:
    """Indice entidad -> documentos/chunks."""
    entity_id: str
    doc_ids: List[str] = field(default_factory=list)
    chunk_ids: List[str] = field(default_factory=list)
    confidence: float = 0.0
    extractor_ids: List[str] = field(default_factory=list)

    def to_artifact(self, builder_version: str) -> Dict[str, Any]:
        return {
            "doc_ids": list(self.doc_ids),
            "chunk_ids": list(self.chunk_ids),
            "confidence": round(self.confidence, 4),
            "validated": True,
            "builder_version": builder_version,
            "generated_by": {
                "extractor_id": ",".join(self.extractor_ids) if self.extractor_ids else "unknown",
            },
        }


@dataclass
class DocumentRole:
    """Rol de un documento en el Knowledge Model."""
    doc_id: str
    role: str
    name: str
    centrality: float = 0.0
    entity_ids: List[str] = field(default_factory=list)
    attributes: List[str] = field(default_factory=list)
    summary: str = ""
    confidence: float = 0.0
    extractor_ids: List[str] = field(default_factory=list)
    evidence: List[EvidenceItem] = field(default_factory=list)

    def to_artifact(self, builder_version: str) -> Dict[str, Any]:
        return {
            "role": self.role,
            "name": self.name,
            "centrality": round(self.centrality, 4),
            "entity_ids": list(self.entity_ids),
            "attributes": list(self.attributes),
            "summary": self.summary,
            "confidence": round(self.confidence, 4),
            "validated": True,
            "builder_version": builder_version,
            "generated_by": {
                "extractor_id": ",".join(self.extractor_ids) if self.extractor_ids else "unknown",
            },
        }


@dataclass
class RelationEntry:
    """Relacion tipada en el Knowledge Model."""
    relation_id: str
    subject_id: str
    predicate: str
    object_id: str
    confidence: float = 0.0
    attributes: List[str] = field(default_factory=list)
    extractor_ids: List[str] = field(default_factory=list)
    evidence: List[EvidenceItem] = field(default_factory=list)

    def to_artifact(self, builder_version: str) -> Dict[str, Any]:
        d = {
            "relation_id": self.relation_id,
            "subject": self.subject_id,
            "predicate": self.predicate,
            "object": self.object_id,
            "confidence": round(self.confidence, 4),
            "attributes": list(self.attributes),
            "validated": True,
            "evidence": [e.to_dict() for e in self.evidence],
            "builder_version": builder_version,
            "generated_by": {
                "extractor_id": ",".join(self.extractor_ids) if self.extractor_ids else "unknown",
            },
        }
        return d


@dataclass
class KnowledgeModel:
    """Knowledge Model — validated KIR, layered (RES-002 §7).

    Layers pobladas en E3:
        - Document Layer: document_roles
        - Entity Layer: canonical_entities, aliases, entity_index

    Layers declaradas pero vacias en E3 (DEC-011):
        - Relation Layer: relations (E7)
        - Retrieval Layer: retrieval_metadata (E6)
    """
    # Layer 2: Entity
    canonical_entities: List[CanonicalEntity] = field(default_factory=list)
    aliases: List[AliasEntry] = field(default_factory=list)
    entity_index: List[EntityIndexEntry] = field(default_factory=list)

    # Layer 1: Document
    document_roles: List[DocumentRole] = field(default_factory=list)

    # Layer 4: Relation (E7 — vacio en E3)
    relations: List[RelationEntry] = field(default_factory=list)

    # Metadata
    builder_version: str = "1.0.0"
    build_metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_kir(cls, kir: KIR, builder_version: str = "1.0.0") -> "KnowledgeModel":
        """Construye el Knowledge Model desde KIR validado y canonicalizado."""
        model = cls(builder_version=builder_version)
        model._build_entity_layer(kir)
        model._build_document_layer(kir)
        model._build_relation_layer(kir)
        model.build_metadata = dict(kir.metadata)
        return model

    def _build_entity_layer(self, kir: KIR) -> None:
        canonical_map: Dict[str, str] = kir.metadata.get("canonical_map", {})

        # Canonical entities
        seen_ids: Dict[str, CanonicalEntity] = {}
        for c in kir.entity_claims:
            key = normalize_text(c.canonical_name)
            eid = c.raw.get("entity_id") or canonical_map.get(key) or f"ent:{slugify(c.canonical_name)}"
            if eid in seen_ids:
                ent = seen_ids[eid]
                for t in c.entity_types:
                    if t not in ent.types:
                        ent.types.append(t)
                ent.confidence = max(ent.confidence, c.confidence)
                for eid_ext in c.extractor_id.split(","):
                    if eid_ext not in ent.extractor_ids:
                        ent.extractor_ids.append(eid_ext)
                ent.evidence.extend(c.evidence)
            else:
                seen_ids[eid] = CanonicalEntity(
                    entity_id=eid,
                    canonical_name=c.canonical_name,
                    types=list(c.entity_types) if c.entity_types else ["concept"],
                    confidence=c.confidence,
                    extractor_ids=[x for x in c.extractor_id.split(",") if x],
                    evidence=list(c.evidence),
                )
        self.canonical_entities = list(seen_ids.values())

        # Aliases
        alias_seen: Dict[str, AliasEntry] = {}
        for c in kir.alias_claims:
            key = normalize_text(c.alias)
            eid = c.raw.get("entity_id") or canonical_map.get(normalize_text(c.canonical_name), "")
            if key in alias_seen:
                alias_seen[key].confidence = max(alias_seen[key].confidence, c.confidence)
                for eid_ext in c.extractor_id.split(","):
                    if eid_ext not in alias_seen[key].extractor_ids:
                        alias_seen[key].extractor_ids.append(eid_ext)
            else:
                alias_seen[key] = AliasEntry(
                    alias=c.alias,
                    entity_id=eid,
                    confidence=c.confidence,
                    extractor_ids=[x for x in c.extractor_id.split(",") if x],
                    evidence=list(c.evidence),
                )
        self.aliases = list(alias_seen.values())

        # Stub canonical entities for aliases whose entity_id has no corresponding entity claim.
        # An alias implicitly declares the existence of its canonical entity.
        for alias_entry in self.aliases:
            eid = alias_entry.entity_id
            if eid and eid not in seen_ids:
                seen_ids[eid] = CanonicalEntity(
                    entity_id=eid,
                    canonical_name=alias_entry.alias,
                    types=["concept"],
                    confidence=alias_entry.confidence * 0.5,
                    extractor_ids=list(alias_entry.extractor_ids),
                    evidence=list(alias_entry.evidence),
                )
        self.canonical_entities = list(seen_ids.values())

        # Entity index (entity -> docs)
        entity_docs: Dict[str, set] = {}
        entity_conf: Dict[str, float] = {}
        entity_extractors: Dict[str, set] = {}
        for dc in kir.document_claims:
            doc_id = dc.raw.get("doc_id") or f"doc:{slugify(dc.name)}"
            for ent_name in dc.entity_mentions:
                ent_key = normalize_text(ent_name)
                eid = canonical_map.get(ent_key, f"ent:{slugify(ent_name)}")
                entity_docs.setdefault(eid, set()).add(doc_id)
                entity_conf[eid] = max(entity_conf.get(eid, 0.0), dc.confidence)
                entity_extractors.setdefault(eid, set()).add(dc.extractor_id)

        for eid, docs in entity_docs.items():
            self.entity_index.append(EntityIndexEntry(
                entity_id=eid,
                doc_ids=sorted(docs),
                chunk_ids=[],
                confidence=entity_conf.get(eid, 0.0),
                extractor_ids=sorted(entity_extractors.get(eid, set())),
            ))

    def _build_document_layer(self, kir: KIR) -> None:
        canonical_map: Dict[str, str] = kir.metadata.get("canonical_map", {})
        doc_seen: Dict[str, DocumentRole] = {}
        for c in kir.document_claims:
            doc_id = c.raw.get("doc_id") or f"doc:{slugify(c.name)}"
            if doc_id in doc_seen:
                existing = doc_seen[doc_id]
                existing.centrality = max(existing.centrality, c.centrality)
                for a in c.attributes:
                    if a not in existing.attributes:
                        existing.attributes.append(a)
                for eid_ext in c.extractor_id.split(","):
                    if eid_ext not in existing.extractor_ids:
                        existing.extractor_ids.append(eid_ext)
                existing.evidence.extend(c.evidence)
            else:
                entity_ids = []
                for ent_name in c.entity_mentions:
                    ent_key = normalize_text(ent_name)
                    eid = canonical_map.get(ent_key, f"ent:{slugify(ent_name)}")
                    if eid not in entity_ids:
                        entity_ids.append(eid)
                doc_seen[doc_id] = DocumentRole(
                    doc_id=doc_id,
                    role=c.role,
                    name=c.name,
                    centrality=c.centrality,
                    entity_ids=entity_ids,
                    attributes=list(c.attributes),
                    summary=c.summary,
                    confidence=c.confidence,
                    extractor_ids=[x for x in c.extractor_id.split(",") if x],
                    evidence=list(c.evidence),
                )
        self.document_roles = list(doc_seen.values())

    def _build_relation_layer(self, kir: KIR) -> None:
        canonical_map: Dict[str, str] = kir.metadata.get("canonical_map", {})
        rel_seen: Dict[str, RelationEntry] = {}
        for c in kir.relation_claims:
            subj_id = c.raw.get("subject_id") or canonical_map.get(normalize_text(c.subject_name), "")
            obj_id = c.raw.get("object_id") or canonical_map.get(normalize_text(c.object_name), "")
            if not subj_id or not obj_id:
                continue
            rel_key = f"{subj_id}:{c.predicate}:{obj_id}"
            if rel_key in rel_seen:
                rel_seen[rel_key].confidence = max(rel_seen[rel_key].confidence, c.confidence)
                rel_seen[rel_key].evidence.extend(c.evidence)
            else:
                rel_seen[rel_key] = RelationEntry(
                    relation_id=f"rel:{slugify(subj_id)}-{slugify(c.predicate)}-{slugify(obj_id)}",
                    subject_id=subj_id,
                    predicate=c.predicate,
                    object_id=obj_id,
                    confidence=c.confidence,
                    attributes=list(c.attributes),
                    extractor_ids=[x for x in c.extractor_id.split(",") if x],
                    evidence=list(c.evidence),
                )
        self.relations = list(rel_seen.values())

    def stats(self) -> Dict[str, int]:
        return {
            "canonical_entities": len(self.canonical_entities),
            "aliases": len(self.aliases),
            "entity_index": len(self.entity_index),
            "document_roles": len(self.document_roles),
            "relations": len(self.relations),
        }
