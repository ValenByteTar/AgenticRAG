"""Warm Codegen — serializa el Knowledge Model a Warm Artifacts (RES-002 §8).

Produce los 7 artifacts declarados en warm-v1 (DEC-011):
    1. canonical_entities   (Layer 2: Entity)
    2. alias_index           (Layer 2: Entity)
    3. entity_index          (Layer 2: Entity)
    4. doc_roles             (Layer 1: Document)
    5. entity_relations      (Layer 4: Relation — vacio en E3, E7 lo puebla)
    6. retrieval_metadata    (Layer 5: Retrieval — vacio en E3, E6 lo puebla)
    7. predicate_catalog     (catalogo controlado)

E3: artifacts 1-4 poblados, 5-6 declarados pero vacios (DEC-011).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from src.artifact_registry.registry import compute_checksums
from ..model.knowledge_model import KnowledgeModel


_PREDICATE_CATALOG = [
    {"id": "equivalent_to", "description": "A is equivalent to B"},
    {"id": "depends_on", "description": "A depends on B"},
    {"id": "implements", "description": "A implements B"},
    {"id": "extends", "description": "A extends B"},
    {"id": "references", "description": "A references B"},
    {"id": "governs", "description": "A governs/regulates B"},
    {"id": "contains", "description": "A contains B"},
    {"id": "uses", "description": "A uses B"},
    {"id": "creates", "description": "A creates/defines B"},
]

_PREDICATE_IDS = [p["id"] for p in _PREDICATE_CATALOG]


class WarmCodegen:
    """Serializa el Knowledge Model a 7 Warm Artifacts + manifest."""

    def __init__(self, builder_version: str = "1.0.0"):
        self.builder_version = builder_version

    def generate(self, model: KnowledgeModel, build_id: str = "ka_v1.0.0") -> Dict[str, Any]:
        """Genera los 7 artifacts y el manifest.

        Returns:
            Dict con ``"artifacts"`` (name -> data) y ``"manifest"``.
        """
        artifacts: Dict[str, Any] = {}

        artifacts["canonical_entities"] = self._gen_canonical_entities(model)
        artifacts["alias_index"] = self._gen_alias_index(model)
        artifacts["entity_index"] = self._gen_entity_index(model)
        artifacts["doc_roles"] = self._gen_doc_roles(model)
        artifacts["entity_relations"] = self._gen_entity_relations(model)
        artifacts["retrieval_metadata"] = self._gen_retrieval_metadata(model)
        artifacts["predicate_catalog"] = self._gen_predicate_catalog()

        manifest = self._build_manifest(artifacts, build_id)
        return {"artifacts": artifacts, "manifest": manifest}

    def _gen_canonical_entities(self, model: KnowledgeModel) -> Dict[str, Any]:
        entities = []
        for ent in model.canonical_entities:
            d = ent.to_artifact(self.builder_version)
            entities.append(d)
        return {"entities": entities}

    def _gen_alias_index(self, model: KnowledgeModel) -> Dict[str, Any]:
        aliases: Dict[str, Any] = {}
        for alias in model.aliases:
            aliases[alias.alias] = alias.to_artifact(self.builder_version)
        return {"aliases": aliases}

    def _gen_entity_index(self, model: KnowledgeModel) -> Dict[str, Any]:
        entities: Dict[str, Any] = {}
        for entry in model.entity_index:
            entities[entry.entity_id] = entry.to_artifact(self.builder_version)
        return {"entities": entities}

    def _gen_doc_roles(self, model: KnowledgeModel) -> Dict[str, Any]:
        docs: Dict[str, Any] = {}
        for doc in model.document_roles:
            docs[doc.doc_id] = doc.to_artifact(self.builder_version)
        return {"docs": docs}

    def _gen_entity_relations(self, model: KnowledgeModel) -> Dict[str, Any]:
        relations = []
        for rel in model.relations:
            relations.append(rel.to_artifact(self.builder_version))
        return {"relations": relations}

    def _gen_retrieval_metadata(self, model: KnowledgeModel) -> Dict[str, Any]:
        docs: Dict[str, Any] = {}
        for doc in model.document_roles:
            if doc.role in ("entity_profile", "list"):
                preferred = [doc.role]
                two_stage = True
                scoping = "candidate_docs"
                boost = 0.05
            elif doc.role in ("guide", "reference"):
                preferred = [doc.role]
                two_stage = False
                scoping = "soft_boost"
                boost = 0.03
            else:
                preferred = [doc.role]
                two_stage = False
                scoping = "none"
                boost = 0.0
            docs[doc.doc_id] = {
                "preferred_roles": preferred,
                "two_stage_eligible": two_stage,
                "scoping_preference": scoping,
                "boost_weight": boost,
                "attributes": list(doc.attributes),
                "confidence": doc.confidence,
                "validated": True,
                "builder_version": self.builder_version,
                "generated_by": {
                    "extractor_id": ",".join(doc.extractor_ids) if doc.extractor_ids else "pipeline:doc-cards",
                },
            }
        return {"docs": docs}

    def _gen_predicate_catalog(self) -> Dict[str, Any]:
        return {
            "catalog_version": "2.0.0",
            "predicates": list(_PREDICATE_CATALOG),
        }

    def _build_manifest(self, artifacts: Dict[str, Any], build_id: str) -> Dict[str, Any]:
        checksums = compute_checksums(artifacts)
        manifest_artifacts: Dict[str, Any] = {}
        for name, data in artifacts.items():
            content = json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2).encode("utf-8")
            manifest_artifacts[name] = {
                "sha256": checksums[name],
                "path": f"artifacts/{name}.json",
                "size_bytes": len(content),
            }
        return {
            "build_id": build_id,
            "contract_version": "warm-v1",
            "builder_version": self.builder_version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "artifacts": manifest_artifacts,
        }

    @property
    def predicate_ids(self) -> list:
        return list(_PREDICATE_IDS)
