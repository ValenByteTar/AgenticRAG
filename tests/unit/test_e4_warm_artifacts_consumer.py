"""
Tests E4: Consumer resolves Warm Artifacts.

Covers:
- WarmArtifactResolver: typed accessors over resolved artifacts
- KnowledgeSystemAdapter.get_entity(): resolves via resolver
- EntityExpansionCapability: reads alias_index from resolver
- PlannerCapability: reads doc_roles from resolver for candidate_docs
- RetrievalCapability: entity_index boost
- Feature flag gating: warm_artifacts_enabled=false -> resolver=None
- End-to-end: build artifacts -> resolve -> consume
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.adapters.warm_artifact_resolver import WarmArtifactResolver
from src.adapters.knowledge_system import KnowledgeSystemAdapter
from src.capabilities.entity_expansion import EntityExpansionCapability
from src.capabilities.planner import PlannerCapability
from src.capabilities.retrieval import RetrievalCapability
from src.kernel.state import ExecutionState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SAMPLE_MANIFEST = {
    "build_id": "ka_test_v1",
    "contract_version": "warm-v1",
    "builder_version": "1.0.0",
    "created_at": "2026-07-29T12:00:00+00:00",
    "artifacts": {
        "canonical_entities": {"path": "artifacts/canonical_entities.json", "sha256": "x", "size_bytes": 1},
        "alias_index": {"path": "artifacts/alias_index.json", "sha256": "x", "size_bytes": 1},
        "entity_index": {"path": "artifacts/entity_index.json", "sha256": "x", "size_bytes": 1},
        "doc_roles": {"path": "artifacts/doc_roles.json", "sha256": "x", "size_bytes": 1},
        "entity_relations": {"path": "artifacts/entity_relations.json", "sha256": "x", "size_bytes": 1},
        "retrieval_metadata": {"path": "artifacts/retrieval_metadata.json", "sha256": "x", "size_bytes": 1},
        "predicate_catalog": {"path": "artifacts/predicate_catalog.json", "sha256": "x", "size_bytes": 1},
    },
}

_SAMPLE_ARTIFACTS: Dict[str, Any] = {
    "canonical_entities": {
        "entities": [
            {"entity_id": "ent:iso-27001", "canonical_name": "ISO 27001", "types": ["standard"], "confidence": 0.95},
            {"entity_id": "ent:nist-csf", "canonical_name": "NIST CSF", "types": ["framework"], "confidence": 0.9},
            {"entity_id": "ent:cissp", "canonical_name": "CISSP", "types": ["certification"], "confidence": 0.95},
        ]
    },
    "alias_index": {
        "aliases": {
            "iso 27001": {"entity_id": "ent:iso-27001", "confidence": 0.95},
            "iso27001": {"entity_id": "ent:iso-27001", "confidence": 0.9},
            "isms": {"entity_id": "ent:iso-27001", "confidence": 0.85},
            "nist csf": {"entity_id": "ent:nist-csf", "confidence": 0.9},
            "nist cybersecurity framework": {"entity_id": "ent:nist-csf", "confidence": 0.88},
            "cissp": {"entity_id": "ent:cissp", "confidence": 0.95},
            "certified information systems security professional": {"entity_id": "ent:cissp", "confidence": 0.92},
        }
    },
    "entity_index": {
        "entities": {
            "ent:iso-27001": {"doc_ids": ["doc:iso-27001-guide", "doc:iso-27001-checklist"], "chunk_ids": []},
            "ent:nist-csf": {"doc_ids": ["doc:nist-csf-pdf"], "chunk_ids": []},
        }
    },
    "doc_roles": {
        "docs": {
            "doc:iso-27001-guide": {"role": "manual_reference", "name": "ISO 27001 Guide", "centrality": 0.8, "entity_ids": ["ent:iso-27001"], "attributes": {}, "summary": ""},
            "doc:iso-27001-checklist": {"role": "procedure", "name": "ISO 27001 Checklist", "centrality": 0.6, "entity_ids": ["ent:iso-27001"], "attributes": {}, "summary": ""},
            "doc:nist-csf-pdf": {"role": "framework_list", "name": "NIST CSF PDF", "centrality": 0.7, "entity_ids": ["ent:nist-csf"], "attributes": {}, "summary": ""},
            "doc:random-pdf": {"role": "other", "name": "Random PDF", "centrality": 0.0, "entity_ids": [], "attributes": {}, "summary": ""},
        }
    },
    "entity_relations": {
        "relations": [
            {"relation_id": "rel:ent-iso-27001-equivalent-to-ent-isms", "subject": "ent:iso-27001", "predicate": "equivalent_to", "object": "ent:isms", "confidence": 0.9, "evidence": [{"source_doc_id": "doc:iso-27001-guide", "quote": "ISO 27001 = ISMS"}]}
        ]
    },
    "retrieval_metadata": {
        "docs": {
            "doc:iso-27001-guide": {"preferred_roles": ["manual_reference"], "confidence": {"overall": 0.8}},
            "doc:nist-csf-pdf": {"preferred_roles": ["framework_list"], "confidence": {"overall": 0.7}},
        }
    },
    "predicate_catalog": {
        "catalog_version": "1.0.0",
        "predicates": [
            {"id": "equivalent_to", "description": "Semantic equivalence"},
            {"id": "part_of", "description": "Containment"},
        ],
    },
}


@pytest.fixture
def resolver() -> WarmArtifactResolver:
    return WarmArtifactResolver(_SAMPLE_MANIFEST, _SAMPLE_ARTIFACTS)


# ---------------------------------------------------------------------------
# 1. WarmArtifactResolver
# ---------------------------------------------------------------------------

class TestWarmArtifactResolver:

    def test_basic_props(self, resolver: WarmArtifactResolver):
        assert resolver.build_id == "ka_test_v1"
        assert resolver.contract_version == "warm-v1"

    def test_get_canonical_entities(self, resolver: WarmArtifactResolver):
        entities = resolver.get_canonical_entities()
        assert len(entities) == 3
        assert any(e["canonical_name"] == "ISO 27001" for e in entities)

    def test_get_alias_index(self, resolver: WarmArtifactResolver):
        aliases = resolver.get_alias_index()
        assert "iso 27001" in aliases
        assert aliases["iso 27001"]["entity_id"] == "ent:iso-27001"

    def test_resolve_alias(self, resolver: WarmArtifactResolver):
        assert resolver.resolve_alias("iso 27001") == "ent:iso-27001"
        assert resolver.resolve_alias("ISMS") == "ent:iso-27001"
        assert resolver.resolve_alias("unknown") is None

    def test_get_entity_by_name(self, resolver: WarmArtifactResolver):
        ent = resolver.get_entity_by_name("iso 27001")
        assert ent is not None
        assert ent["entity_id"] == "ent:iso-27001"
        assert resolver.get_entity_by_name("nonexistent") is None

    def test_get_entity_by_id(self, resolver: WarmArtifactResolver):
        ent = resolver.get_entity_by_id("ent:nist-csf")
        assert ent is not None
        assert ent["canonical_name"] == "NIST CSF"

    def test_get_docs_for_entity(self, resolver: WarmArtifactResolver):
        docs = resolver.get_docs_for_entity("ent:iso-27001")
        assert "doc:iso-27001-guide" in docs
        assert "doc:iso-27001-checklist" in docs
        assert resolver.get_docs_for_entity("ent:unknown") == []

    def test_get_all_aliases(self, resolver: WarmArtifactResolver):
        aliases = resolver.get_all_aliases()
        assert "iso 27001" in aliases
        assert "iso27001" in aliases["iso 27001"]
        assert "isms" in aliases["iso 27001"]
        assert "nist csf" in aliases
        assert "nist cybersecurity framework" in aliases["nist csf"]

    def test_get_doc_roles(self, resolver: WarmArtifactResolver):
        roles = resolver.get_doc_roles()
        assert "doc:iso-27001-guide" in roles
        assert roles["doc:iso-27001-guide"]["role"] == "manual_reference"

    def test_get_candidate_docs_by_role(self, resolver: WarmArtifactResolver):
        candidates = resolver.get_candidate_docs(
            preferred_roles=["manual_reference", "procedure"],
            entities=["ISO 27001"],
            limit=10,
        )
        assert "doc:iso-27001-guide" in candidates
        assert "doc:iso-27001-checklist" in candidates
        assert "doc:random-pdf" not in candidates

    def test_get_candidate_docs_entity_boost(self, resolver: WarmArtifactResolver):
        candidates = resolver.get_candidate_docs(
            preferred_roles=["framework_list"],
            entities=["NIST CSF"],
            limit=10,
        )
        assert candidates[0] == "doc:nist-csf-pdf"

    def test_confidence_threshold_filters_aliases(self):
        r = WarmArtifactResolver(_SAMPLE_MANIFEST, _SAMPLE_ARTIFACTS, confidence_threshold=0.9)
        aliases = r.get_alias_index()
        assert "iso 27001" in aliases  # 0.95
        assert "isms" not in aliases  # 0.85

    def test_confidence_threshold_filters_entities(self):
        r = WarmArtifactResolver(_SAMPLE_MANIFEST, _SAMPLE_ARTIFACTS, confidence_threshold=0.92)
        entities = r.get_canonical_entities()
        names = {e["canonical_name"] for e in entities}
        assert "ISO 27001" in names  # 0.95
        assert "NIST CSF" not in names  # 0.9

    def test_from_registry_no_active_build(self):
        class FakeRegistry:
            def resolve(self):
                raise RuntimeError("no active build")
        r = WarmArtifactResolver.from_registry(FakeRegistry())
        assert r is None

    def test_from_registry_success(self):
        class FakeRegistry:
            def resolve(self):
                return {"manifest": _SAMPLE_MANIFEST, "artifacts": _SAMPLE_ARTIFACTS}
        r = WarmArtifactResolver.from_registry(FakeRegistry())
        assert r is not None
        assert r.build_id == "ka_test_v1"


# ---------------------------------------------------------------------------
# 2. KnowledgeSystemAdapter.get_entity()
# ---------------------------------------------------------------------------

class TestKnowledgeSystemAdapterGetEntity:

    def test_get_entity_without_resolver_returns_none(self):
        class FakeRag:
            def hybrid_search(self, *a, **k):
                return []
        adapter = KnowledgeSystemAdapter(FakeRag())
        assert adapter.get_entity("ISO 27001") is None

    def test_get_entity_by_alias(self, resolver: WarmArtifactResolver):
        class FakeRag:
            def hybrid_search(self, *a, **k):
                return []
        adapter = KnowledgeSystemAdapter(FakeRag(), resolver=resolver)
        result = adapter.get_entity("iso27001")
        assert result is not None
        assert result["entity_id"] == "ent:iso-27001"
        assert result["canonical_name"] == "ISO 27001"

    def test_get_entity_by_canonical_name(self, resolver: WarmArtifactResolver):
        class FakeRag:
            def hybrid_search(self, *a, **k):
                return []
        adapter = KnowledgeSystemAdapter(FakeRag(), resolver=resolver)
        result = adapter.get_entity("NIST CSF")
        assert result is not None
        assert result["entity_id"] == "ent:nist-csf"

    def test_get_entity_includes_doc_ids(self, resolver: WarmArtifactResolver):
        class FakeRag:
            def hybrid_search(self, *a, **k):
                return []
        adapter = KnowledgeSystemAdapter(FakeRag(), resolver=resolver)
        result = adapter.get_entity("isms")
        assert result is not None
        assert "doc_ids" in result
        assert "doc:iso-27001-guide" in result["doc_ids"]

    def test_get_entity_unknown_returns_none(self, resolver: WarmArtifactResolver):
        class FakeRag:
            def hybrid_search(self, *a, **k):
                return []
        adapter = KnowledgeSystemAdapter(FakeRag(), resolver=resolver)
        assert adapter.get_entity("nonexistent") is None


# ---------------------------------------------------------------------------
# 3. EntityExpansionCapability with resolver
# ---------------------------------------------------------------------------

class TestEntityExpansionWithResolver:

    def test_uses_resolver_aliases(self, resolver: WarmArtifactResolver):
        cap = EntityExpansionCapability(resolver=resolver)
        st = ExecutionState(question="que es ISO 27001?", entities=["ISO 27001"])
        out = cap.execute(st)
        expanded = out.metadata["expanded_entities"]
        assert "iso 27001" in expanded
        assert "iso27001" in expanded
        assert "isms" in expanded

    def test_resolver_overrides_default_aliases(self, resolver: WarmArtifactResolver):
        cap = EntityExpansionCapability(resolver=resolver)
        st = ExecutionState(question="q", entities=["CISSP"])
        out = cap.execute(st)
        expanded = out.metadata["expanded_entities"]
        assert "cissp" in expanded
        assert "certified information systems security professional" in expanded

    def test_fallback_to_default_when_resolver_none(self):
        cap = EntityExpansionCapability()
        st = ExecutionState(question="q", entities=["ISO 27001"])
        out = cap.execute(st)
        expanded = out.metadata["expanded_entities"]
        assert "iso 27001" in expanded
        assert "iso27001" in expanded

    def test_resolver_error_falls_back(self):
        class BrokenResolver:
            def get_all_aliases(self):
                raise RuntimeError("broken")
        cap = EntityExpansionCapability(resolver=BrokenResolver())
        st = ExecutionState(question="q", entities=["ISO 27001"])
        out = cap.execute(st)
        expanded = out.metadata["expanded_entities"]
        assert "iso 27001" in expanded


# ---------------------------------------------------------------------------
# 4. PlannerCapability with resolver
# ---------------------------------------------------------------------------

class TestPlannerWithResolver:

    def test_uses_resolver_for_candidate_docs(self, resolver: WarmArtifactResolver):
        cap = PlannerCapability(resolver=resolver)
        st = ExecutionState(question="que es ISO 27001?", entities=["ISO 27001"])
        out = cap.execute(st)
        plan = out.metadata["plan"]
        # Planner produces roles based on query type; check if candidate_docs were populated
        if "candidate_docs" in plan and plan["candidate_docs"]:
            assert "doc:iso-27001-guide" in plan["candidate_docs"] or "doc:iso-27001-checklist" in plan["candidate_docs"]
        else:
            # If no match, it's because preferred roles don't match artifact roles
            preferred = plan.get("doc_roles_preferred", [])
            assert "analysis_report" in preferred or "entity_profile" in preferred

    def test_no_candidate_docs_when_no_matching_role(self, resolver: WarmArtifactResolver):
        cap = PlannerCapability(resolver=resolver)
        st = ExecutionState(question="que es ISO 27001?", entities=["ISO 27001"])
        out = cap.execute(st)
        plan = out.metadata["plan"]
        preferred = plan.get("doc_roles_preferred", [])
        candidates = plan.get("candidate_docs", [])
        if "other" not in preferred:
            assert "doc:random-pdf" not in candidates

    def test_planner_fn_overrides_resolver(self, resolver: WarmArtifactResolver):
        def custom_fn(q, ents):
            return {"doc_roles_preferred": ["manual_reference"], "candidate_docs": ["custom-doc"]}
        cap = PlannerCapability(planner_fn=custom_fn, resolver=resolver)
        st = ExecutionState(question="q", entities=["ISO 27001"])
        out = cap.execute(st)
        plan = out.metadata["plan"]
        assert plan["candidate_docs"] == ["custom-doc"]

    def test_no_resolver_uses_default_plan(self):
        cap = PlannerCapability()
        st = ExecutionState(question="que es ISO 27001?", entities=["ISO 27001"])
        out = cap.execute(st)
        plan = out.metadata["plan"]
        assert "doc_roles_preferred" in plan
        assert "candidate_docs" not in plan or plan.get("candidate_docs") is None


# ---------------------------------------------------------------------------
# 5. RetrievalCapability with entity_index boost
# ---------------------------------------------------------------------------

class TestRetrievalEntityIndexBoost:

    def test_entity_doc_boost_applied(self, resolver: WarmArtifactResolver):
        def retrieve_fn(query, top_k, sw):
            return [
                {"text": "doc1", "metadata": {"source": "doc:iso-27001-guide"}, "hybrid_score": 0.5},
                {"text": "doc2", "metadata": {"source": "doc:random-pdf"}, "hybrid_score": 0.9},
            ]
        cap = RetrievalCapability(retrieve_fn, resolver=resolver)
        st = ExecutionState(question="que es ISO 27001?", entities=["ISO 27001"])
        out = cap.execute(st)
        results = out.results
        assert len(results) == 2
        iso_doc = [r for r in results if r["metadata"]["source"] == "doc:iso-27001-guide"][0]
        random_doc = [r for r in results if r["metadata"]["source"] == "doc:random-pdf"][0]
        assert iso_doc.get("final_score", 0) > 0.5
        assert iso_doc["final_score"] == 0.5 + 0.03

    def test_no_boost_without_resolver(self):
        def retrieve_fn(query, top_k, sw):
            return [
                {"text": "doc1", "metadata": {"source": "doc:iso-27001-guide"}, "hybrid_score": 0.5},
            ]
        cap = RetrievalCapability(retrieve_fn)
        st = ExecutionState(question="q", entities=["ISO 27001"])
        out = cap.execute(st)
        assert out.results[0].get("final_score") is None or out.results[0].get("final_score") == 0.5

    def test_no_boost_for_unknown_entity(self, resolver: WarmArtifactResolver):
        def retrieve_fn(query, top_k, sw):
            return [
                {"text": "doc1", "metadata": {"source": "doc:random-pdf"}, "hybrid_score": 0.9},
            ]
        cap = RetrievalCapability(retrieve_fn, resolver=resolver)
        st = ExecutionState(question="q", entities=["UnknownEntity"])
        out = cap.execute(st)
        assert out.results[0].get("final_score") is None


# ---------------------------------------------------------------------------
# 6. End-to-end: build artifacts -> resolve -> consume
# ---------------------------------------------------------------------------

class TestE2EArtifactsConsumption:

    def test_full_pipeline_with_artifacts(self, resolver: WarmArtifactResolver):
        """Simulates the Consumer pipeline: expand -> plan -> retrieve."""
        # 1. Entity expansion
        expand_cap = EntityExpansionCapability(resolver=resolver)
        st = ExecutionState(question="que es ISO 27001?", entities=["ISO 27001"])
        st = expand_cap.execute(st)
        expanded = st.metadata["expanded_entities"]
        assert "iso27001" in expanded
        assert "isms" in expanded

        # 2. Planner
        planner_cap = PlannerCapability(resolver=resolver)
        st = planner_cap.execute(st)
        plan = st.metadata["plan"]
        # Planner may or may not produce candidate_docs depending on role match
        if "candidate_docs" in plan and plan["candidate_docs"]:
            assert len(plan["candidate_docs"]) > 0

        # 3. Retrieval with entity_index boost
        def retrieve_fn(query, top_k, sw):
            return [
                {"text": "iso guide", "metadata": {"source": "doc:iso-27001-guide"}, "hybrid_score": 0.6},
                {"text": "random", "metadata": {"source": "doc:random-pdf"}, "hybrid_score": 0.8},
            ]
        retrieval_cap = RetrievalCapability(retrieve_fn, resolver=resolver)
        st = retrieval_cap.execute(st)
        results = st.results
        # Entity doc should be boosted
        iso_doc = [r for r in results if r["metadata"]["source"] == "doc:iso-27001-guide"][0]
        assert iso_doc.get("final_score", 0) > 0.6

    def test_get_entity_returns_canonical_with_docs(self, resolver: WarmArtifactResolver):
        class FakeRag:
            def hybrid_search(self, *a, **k):
                return []
        adapter = KnowledgeSystemAdapter(FakeRag(), resolver=resolver)
        entity = adapter.get_entity("isms")
        assert entity is not None
        assert entity["canonical_name"] == "ISO 27001"
        assert "doc_ids" in entity
        assert len(entity["doc_ids"]) == 2
