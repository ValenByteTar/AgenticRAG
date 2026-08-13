"""WarmArtifactResolver — Resolution Protocol client for the Consumer (RES-001 §5.3).

Wraps ``ArtifactRegistry.resolve()`` and provides typed accessors for each
Warm Artifact. The Consumer never accesses the filesystem directly; it
always goes through this resolver.

Design decisions (RES-003 §2):
    - Eager load: all artifacts loaded at construction time.
    - Confidence thresholds are configurable per accessor.
    - If the registry has no active build or integrity fails, the resolver
      is ``None`` and the Consumer falls back to hardcoded behavior.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple


class WarmArtifactResolver:
    """Typed accessor over resolved Warm Artifacts.

    Usage::

        registry = ArtifactRegistry(root)
        resolver = WarmArtifactResolver.from_registry(registry)
        if resolver is not None:
            aliases = resolver.get_all_aliases()
    """

    def __init__(
        self,
        manifest: Mapping[str, Any],
        artifacts: Mapping[str, Any],
        *,
        confidence_threshold: float = 0.0,
    ) -> None:
        self._manifest = dict(manifest)
        self._artifacts = dict(artifacts)
        self._confidence_threshold = confidence_threshold

        self._canonical_by_name: Dict[str, Dict[str, Any]] = {}
        self._canonical_by_id: Dict[str, Dict[str, Any]] = {}
        self._alias_to_entity: Dict[str, Dict[str, Any]] = {}
        self._entity_to_docs: Dict[str, List[str]] = {}
        self._doc_roles_by_id: Dict[str, Dict[str, Any]] = {}
        self._doc_roles_by_name: Dict[str, Dict[str, Any]] = {}
        self._retrieval_meta: Dict[str, Dict[str, Any]] = {}

        self._index_artifacts()

    @classmethod
    def from_registry(
        cls, registry: Any, **kwargs: Any
    ) -> Optional["WarmArtifactResolver"]:
        """Create a resolver from an ArtifactRegistry's active build.

        Returns ``None`` if there is no active build or integrity fails.
        """
        try:
            resolved = registry.resolve()
            return cls(
                manifest=resolved["manifest"],
                artifacts=resolved["artifacts"],
                **kwargs,
            )
        except Exception:
            return None

    @property
    def manifest(self) -> Dict[str, Any]:
        return dict(self._manifest)

    @property
    def build_id(self) -> str:
        return self._manifest.get("build_id", "")

    @property
    def contract_version(self) -> str:
        return self._manifest.get("contract_version", "")

    @property
    def confidence_threshold(self) -> float:
        return self._confidence_threshold

    def get_canonical_entities(self) -> List[Dict[str, Any]]:
        data = self._artifacts.get("canonical_entities", {}).get("entities", [])
        if self._confidence_threshold <= 0:
            return list(data)
        return [
            e for e in data if e.get("confidence", 0) >= self._confidence_threshold
        ]

    def get_alias_index(self) -> Dict[str, Dict[str, Any]]:
        raw = self._artifacts.get("alias_index", {}).get("aliases", {})
        if self._confidence_threshold <= 0:
            return dict(raw)
        return {
            k: v
            for k, v in raw.items()
            if v.get("confidence", 0) >= self._confidence_threshold
        }

    def get_entity_index(self) -> Dict[str, Dict[str, Any]]:
        raw = self._artifacts.get("entity_index", {}).get("entities", {})
        return dict(raw)

    def get_doc_roles(self) -> Dict[str, Dict[str, Any]]:
        raw = self._artifacts.get("doc_roles", {}).get("docs", {})
        return dict(raw)

    def get_entity_relations(self) -> List[Dict[str, Any]]:
        raw = self._artifacts.get("entity_relations", {}).get("relations", [])
        return list(raw)

    def get_retrieval_metadata(self) -> Dict[str, Dict[str, Any]]:
        raw = self._artifacts.get("retrieval_metadata", {}).get("docs", {})
        return dict(raw)

    def get_predicate_catalog(self) -> List[Dict[str, Any]]:
        raw = self._artifacts.get("predicate_catalog", {}).get("predicates", [])
        return list(raw)

    def resolve_alias(self, alias: str) -> Optional[str]:
        entry = self._alias_to_entity.get(alias.lower().strip())
        if entry is None:
            return None
        return entry.get("entity_id")

    def get_entity_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        return self._canonical_by_name.get(name.lower().strip())

    def get_entity_by_id(self, entity_id: str) -> Optional[Dict[str, Any]]:
        return self._canonical_by_id.get(entity_id)

    def get_docs_for_entity(self, entity_id: str) -> List[str]:
        return self._entity_to_docs.get(entity_id, [])

    def get_doc_role(self, doc_id_or_name: str) -> Optional[Dict[str, Any]]:
        key = doc_id_or_name.lower().strip()
        if key in self._doc_roles_by_id:
            return self._doc_roles_by_id[key]
        return self._doc_roles_by_name.get(key)

    def get_all_aliases(self) -> Dict[str, List[str]]:
        """Returns alias map: canonical_name -> [alias1, alias2, ...]."""
        result: Dict[str, List[str]] = {}
        for alias, entry in self._alias_to_entity.items():
            eid = entry.get("entity_id", "")
            entity = self._canonical_by_id.get(eid)
            if entity is None:
                continue
            canonical_name = (entity.get("canonical_name") or "").lower().strip()
            if not canonical_name:
                continue
            if canonical_name not in result:
                result[canonical_name] = []
            if alias != canonical_name:
                result[canonical_name].append(alias)
        return result

    def get_candidate_docs(
        self,
        preferred_roles: List[str],
        entities: Optional[List[str]] = None,
        limit: int = 60,
    ) -> List[str]:
        """Select candidate doc_ids by preferred roles and entity mentions."""
        role_set = {r.lower() for r in (preferred_roles or [])}
        entity_ids = set()
        for e in entities or []:
            eid = self.resolve_alias(e)
            if eid:
                entity_ids.add(eid)
            else:
                entity = self.get_entity_by_name(e)
                if entity:
                    entity_ids.add(entity.get("entity_id", ""))

        candidates: List[Tuple[float, str]] = []
        for doc_id, doc in self._doc_roles_by_id.items():
            role = (doc.get("role") or "").lower()
            if role not in role_set:
                continue
            centrality = float(doc.get("centrality", 0) or 0)
            doc_entity_ids = set(doc.get("entity_ids", []))
            if entity_ids and doc_entity_ids & entity_ids:
                centrality += 0.1
            candidates.append((centrality, doc_id))

        candidates.sort(key=lambda x: x[0], reverse=True)
        return [doc_id for _, doc_id in candidates[:limit]]

    def _index_artifacts(self) -> None:
        for ent in self._artifacts.get("canonical_entities", {}).get("entities", []):
            eid = ent.get("entity_id", "")
            name = (ent.get("canonical_name") or "").lower().strip()
            if eid:
                self._canonical_by_id[eid] = ent
            if name:
                self._canonical_by_name[name] = ent

        for alias, entry in (
            self._artifacts.get("alias_index", {}).get("aliases", {}).items()
        ):
            self._alias_to_entity[alias.lower().strip()] = entry

        for eid, entry in (
            self._artifacts.get("entity_index", {}).get("entities", {}).items()
        ):
            doc_ids = entry.get("doc_ids", [])
            if doc_ids:
                self._entity_to_docs[eid] = list(doc_ids)

        for doc_id, doc in (
            self._artifacts.get("doc_roles", {}).get("docs", {}).items()
        ):
            self._doc_roles_by_id[doc_id] = doc
            name = (doc.get("name") or "").lower().strip()
            if name:
                self._doc_roles_by_name[name] = doc

        for doc_id, meta in (
            self._artifacts.get("retrieval_metadata", {}).get("docs", {}).items()
        ):
            self._retrieval_meta[doc_id] = meta
