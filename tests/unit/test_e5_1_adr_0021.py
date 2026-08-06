"""Tests for E5.1 — ADR-0021 implementation.

Covers:
    - KIR cache hit/miss and invalidation by hash
    - Phase separation (extract/compile/validate/publish)
    - Backward compatibility of compile()
    - Predicate catalog v2 (9 predicates)
    - Predicate fallback mapping (natural language -> v2)
    - Domain-agnostic prompt (no cybersec, no catalog mention)
    - KIR serialization round-trip (to_dict / from_dict)
    - Universal roles v2
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from knowledge_builder.kir import (
    AliasClaim,
    DocumentClaim,
    EntityClaim,
    EvidenceItem,
    KIR,
    RelationClaim,
    normalize_text,
    slugify,
)
from knowledge_builder.passes.canonicalize import CanonicalizePass, _PREDICATE_FALLBACK, _ROLE_TAXONOMY
from knowledge_builder.backend.warm_codegen import WarmCodegen
from knowledge_builder.compiler import KnowledgeCompiler, CompileResult
from knowledge_builder.validate.semantic_validator import _VALID_PREDICATES, _VALID_ROLES


# --------------------------------------------------------------------------- #
# KIR serialization round-trip
# --------------------------------------------------------------------------- #

class TestKIRSerialization:
    def test_kir_to_dict_from_dict_roundtrip(self):
        kir = KIR(metadata={"extractor": "test"})
        kir.entity_claims.append(EntityClaim(
            surface_form="ISO 27001",
            canonical_name="iso 27001",
            entity_types=["framework"],
            extractor_id="test",
            confidence=0.9,
            evidence=[EvidenceItem(source_doc_id="doc:iso-27001", quote="ISO 27001 is a standard")],
            raw={"entity_id": "ent:iso-27001", "source": "test"},
        ))
        kir.alias_claims.append(AliasClaim(
            alias="isms",
            canonical_name="iso 27001",
            extractor_id="test",
            confidence=0.8,
            evidence=[EvidenceItem(source_doc_id="doc:iso-27001", quote="also known as ISMS")],
            raw={"entity_id": "ent:iso-27001"},
        ))
        kir.document_claims.append(DocumentClaim(
            source_path="iso-27001.pdf",
            name="ISO 27001",
            role="entity_profile",
            centrality=0.9,
            summary="ISO 27001 standard",
            extractor_id="test",
            confidence=0.7,
            evidence=[EvidenceItem(source_doc_id="doc:iso-27001", quote="ISO 27001")],
            raw={"doc_id": "doc:iso-27001"},
        ))
        kir.relation_claims.append(RelationClaim(
            subject_name="iso 27001",
            predicate="governs",
            object_name="information security",
            extractor_id="test",
            confidence=0.8,
            evidence=[EvidenceItem(source_doc_id="doc:iso-27001", quote="ISO 27001 governs infosec")],
            raw={"subject_id": "ent:iso-27001", "object_id": "ent:information-security"},
        ))

        d = kir.to_dict()
        kir2 = KIR.from_dict(d)

        assert len(kir2.entity_claims) == 1
        assert kir2.entity_claims[0].canonical_name == "iso 27001"
        assert kir2.entity_claims[0].confidence == 0.9
        assert kir2.entity_claims[0].raw["entity_id"] == "ent:iso-27001"
        assert len(kir2.entity_claims[0].evidence) == 1
        assert kir2.entity_claims[0].evidence[0].quote == "ISO 27001 is a standard"

        assert len(kir2.alias_claims) == 1
        assert kir2.alias_claims[0].alias == "isms"

        assert len(kir2.document_claims) == 1
        assert kir2.document_claims[0].role == "entity_profile"
        assert kir2.document_claims[0].centrality == 0.9

        assert len(kir2.relation_claims) == 1
        assert kir2.relation_claims[0].predicate == "governs"

    def test_kir_from_dict_empty(self):
        kir = KIR.from_dict({})
        assert len(kir.entity_claims) == 0
        assert len(kir.alias_claims) == 0
        assert len(kir.document_claims) == 0
        assert len(kir.relation_claims) == 0


# --------------------------------------------------------------------------- #
# Predicate catalog v2
# --------------------------------------------------------------------------- #

class TestPredicateCatalogV2:
    def test_catalog_has_9_predicates(self):
        codegen = WarmCodegen()
        ids = codegen.predicate_ids
        assert len(ids) == 9

    def test_catalog_version_is_2_0_0(self):
        kir = KIR()
        from knowledge_builder.model.knowledge_model import KnowledgeModel
        model = KnowledgeModel.from_kir(kir)
        codegen = WarmCodegen()
        output = codegen.generate(model)
        assert output["artifacts"]["predicate_catalog"]["catalog_version"] == "2.0.0"

    def test_catalog_contains_exact_predicates(self):
        codegen = WarmCodegen()
        expected = {"equivalent_to", "depends_on", "implements", "extends", "references", "governs", "contains", "uses", "creates"}
        assert set(codegen.predicate_ids) == expected

    def test_semantic_validator_uses_v2_predicates(self):
        assert _VALID_PREDICATES == {"equivalent_to", "depends_on", "implements", "extends", "references", "governs", "contains", "uses", "creates"}

    def test_no_v1_predicates_in_catalog(self):
        codegen = WarmCodegen()
        v1_predicates = {"defines", "belongs_to", "supersedes", "part_of", "located_in", "certifies", "compares_with"}
        assert v1_predicates.isdisjoint(set(codegen.predicate_ids))


# --------------------------------------------------------------------------- #
# Predicate fallback mapping
# --------------------------------------------------------------------------- #

class TestPredicateFallback:
    def test_v1_predicates_map_to_v2(self):
        catalog = ["equivalent_to", "depends_on", "implements", "extends", "references", "governs", "contains", "uses", "creates"]
        canon = CanonicalizePass(predicate_catalog=catalog)

        kir = KIR()
        kir.relation_claims.append(RelationClaim(
            subject_name="a", predicate="defines", object_name="b",
            extractor_id="test", confidence=0.8,
            evidence=[EvidenceItem(quote="test")],
        ))
        result = canon.run(kir)
        assert result.relation_claims[0].predicate == "creates"

    def test_belongs_to_maps_to_contains(self):
        catalog = ["equivalent_to", "depends_on", "implements", "extends", "references", "governs", "contains", "uses", "creates"]
        canon = CanonicalizePass(predicate_catalog=catalog)

        kir = KIR()
        kir.relation_claims.append(RelationClaim(
            subject_name="a", predicate="belongs_to", object_name="b",
            extractor_id="test", confidence=0.8,
            evidence=[EvidenceItem(quote="test")],
        ))
        result = canon.run(kir)
        assert result.relation_claims[0].predicate == "contains"

    def test_certifies_maps_to_governs(self):
        catalog = ["equivalent_to", "depends_on", "implements", "extends", "references", "governs", "contains", "uses", "creates"]
        canon = CanonicalizePass(predicate_catalog=catalog)

        kir = KIR()
        kir.relation_claims.append(RelationClaim(
            subject_name="a", predicate="certifies", object_name="b",
            extractor_id="test", confidence=0.8,
            evidence=[EvidenceItem(quote="test")],
        ))
        result = canon.run(kir)
        assert result.relation_claims[0].predicate == "governs"

    def test_supersedes_maps_to_extends(self):
        catalog = ["equivalent_to", "depends_on", "implements", "extends", "references", "governs", "contains", "uses", "creates"]
        canon = CanonicalizePass(predicate_catalog=catalog)

        kir = KIR()
        kir.relation_claims.append(RelationClaim(
            subject_name="a", predicate="supersedes", object_name="b",
            extractor_id="test", confidence=0.8,
            evidence=[EvidenceItem(quote="test")],
        ))
        result = canon.run(kir)
        assert result.relation_claims[0].predicate == "extends"

    def test_unknown_predicate_defaults_to_references(self):
        catalog = ["equivalent_to", "depends_on", "implements", "extends", "references", "governs", "contains", "uses", "creates"]
        canon = CanonicalizePass(predicate_catalog=catalog)

        kir = KIR()
        kir.relation_claims.append(RelationClaim(
            subject_name="a", predicate="totally_unknown_predicate", object_name="b",
            extractor_id="test", confidence=0.8,
            evidence=[EvidenceItem(quote="test")],
        ))
        result = canon.run(kir)
        assert result.relation_claims[0].predicate == "references"

    def test_natural_language_predicates_map(self):
        catalog = ["equivalent_to", "depends_on", "implements", "extends", "references", "governs", "contains", "uses", "creates"]
        canon = CanonicalizePass(predicate_catalog=catalog)

        kir = KIR()
        kir.relation_claims.append(RelationClaim(
            subject_name="a", predicate="is part of", object_name="b",
            extractor_id="test", confidence=0.8,
            evidence=[EvidenceItem(quote="test")],
        ))
        result = canon.run(kir)
        assert result.relation_claims[0].predicate == "contains"

    def test_uses_is_in_catalog_not_fallback(self):
        catalog = ["equivalent_to", "depends_on", "implements", "extends", "references", "governs", "contains", "uses", "creates"]
        canon = CanonicalizePass(predicate_catalog=catalog)

        kir = KIR()
        kir.relation_claims.append(RelationClaim(
            subject_name="a", predicate="uses", object_name="b",
            extractor_id="test", confidence=0.8,
            evidence=[EvidenceItem(quote="test")],
        ))
        result = canon.run(kir)
        assert result.relation_claims[0].predicate == "uses"


# --------------------------------------------------------------------------- #
# Universal roles v2
# --------------------------------------------------------------------------- #

class TestUniversalRolesV2:
    def test_cybersec_roles_map_to_universal(self):
        assert _ROLE_TAXONOMY["framework_list"] == "list"
        assert _ROLE_TAXONOMY["cert_list"] == "list"
        assert _ROLE_TAXONOMY["standard_profile"] == "entity_profile"
        assert _ROLE_TAXONOMY["procedure"] == "guide"
        assert _ROLE_TAXONOMY["manual_reference"] == "reference"
        assert _ROLE_TAXONOMY["security_ops"] == "guide"
        assert _ROLE_TAXONOMY["analysis_report"] == "analysis"
        assert _ROLE_TAXONOMY["threat_intel"] == "analysis"
        assert _ROLE_TAXONOMY["policy_compliance"] == "reference"

    def test_universal_roles_are_self_mapped(self):
        for role in ["list", "entity_profile", "guide", "reference", "analysis", "other"]:
            assert _ROLE_TAXONOMY[role] == role

    def test_semantic_validator_uses_v2_roles(self):
        assert _VALID_ROLES == {"list", "entity_profile", "guide", "reference", "analysis", "other"}

    def test_canonicalize_maps_cybersec_role(self):
        canon = CanonicalizePass(predicate_catalog=["equivalent_to"])
        kir = KIR()
        kir.document_claims.append(DocumentClaim(
            source_path="test.pdf", name="Test", role="framework_list",
            extractor_id="test", confidence=0.7,
            evidence=[EvidenceItem(quote="test")],
        ))
        result = canon.run(kir)
        assert result.document_claims[0].role == "list"


# --------------------------------------------------------------------------- #
# Domain-agnostic prompt
# --------------------------------------------------------------------------- #

class TestDomainAgnosticPrompt:
    def test_prompt_does_not_mention_cybersecurity(self):
        from knowledge_builder.frontend.llm_entity_extractor import _EXTRACTION_PROMPT
        assert "cybersecurity" not in _EXTRACTION_PROMPT.lower()
        assert "cyber" not in _EXTRACTION_PROMPT.lower()

    def test_prompt_does_not_mention_predicate_catalog(self):
        from knowledge_builder.frontend.llm_entity_extractor import _EXTRACTION_PROMPT
        assert "defines" not in _EXTRACTION_PROMPT or "defines" in _EXTRACTION_PROMPT.lower().split("creates")[0]
        assert "MUST be from this exact list" not in _EXTRACTION_PROMPT

    def test_prompt_mentions_natural_language_predicates(self):
        from knowledge_builder.frontend.llm_entity_extractor import _EXTRACTION_PROMPT
        assert "natural language" in _EXTRACTION_PROMPT.lower()

    def test_prompt_uses_universal_roles(self):
        from knowledge_builder.frontend.llm_entity_extractor import _EXTRACTION_PROMPT
        for role in ["list", "entity_profile", "guide", "reference", "analysis", "other"]:
            assert role in _EXTRACTION_PROMPT

    def test_prompt_does_not_mention_cybersec_roles(self):
        from knowledge_builder.frontend.llm_entity_extractor import _EXTRACTION_PROMPT
        for role in ["framework_list", "cert_list", "standard_profile", "security_ops", "threat_intel", "policy_compliance"]:
            assert role not in _EXTRACTION_PROMPT


# --------------------------------------------------------------------------- #
# KIR Cache (extractor level)
# --------------------------------------------------------------------------- #

class TestKIRCache:
    def test_cache_hit_avoids_llm_call(self, tmp_path):
        from knowledge_builder.frontend.llm_entity_extractor import LLMEntityExtractor

        cache_dir = tmp_path / "cache"
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        doc_text = "This is a test document about entities and relations."
        doc_path = docs_dir / "test-doc.txt"
        doc_path.write_text(doc_text, encoding="utf-8")

        extractor = LLMEntityExtractor(
            model="test-model",
            docs_dir=docs_dir,
            cache_dir=cache_dir,
            use_cache=True,
            verbose=False,
        )

        chunk_hash = extractor._chunk_hash(doc_text)
        doc_slug = slugify("test-doc.pdf")

        cache_doc_dir = cache_dir / doc_slug
        cache_doc_dir.mkdir(parents=True)
        (cache_doc_dir / "meta.json").write_text(json.dumps({
            "doc_name": "test-doc.pdf",
            "model": "test-model",
            "chunks": {"0": {"hash": chunk_hash, "processed_at": 0}},
        }), encoding="utf-8")

        cached_kir = KIR(metadata={"extractor": "llm:granite-4.1-3b"})
        cached_kir.entity_claims.append(EntityClaim(
            surface_form="Test Entity",
            canonical_name="test entity",
            entity_types=["concept"],
            extractor_id="llm:granite-4.1-3b",
            confidence=0.9,
            evidence=[EvidenceItem(source_doc_id="doc:test-doc", quote="test")],
        ))
        (cache_doc_dir / "chunk_0.kir.json").write_text(
            json.dumps(cached_kir.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        with patch.object(extractor, "_call_llm") as mock_llm:
            result = extractor.extract()
            mock_llm.assert_not_called()

        assert len(result.entity_claims) == 1
        assert result.entity_claims[0].canonical_name == "test entity"

    def test_cache_miss_calls_llm(self, tmp_path):
        from knowledge_builder.frontend.llm_entity_extractor import LLMEntityExtractor

        cache_dir = tmp_path / "cache"
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        doc_path = docs_dir / "test-doc.txt"
        doc_path.write_text("Test document content.", encoding="utf-8")

        extractor = LLMEntityExtractor(
            model="test-model",
            docs_dir=docs_dir,
            cache_dir=cache_dir,
            use_cache=True,
            verbose=False,
        )

        mock_response = json.dumps({
            "entities": [{"name": "Entity A", "types": ["concept"], "confidence": 0.9, "quote": "test"}],
            "aliases": [],
            "relations": [],
            "doc_role": "other",
            "doc_summary": "Test doc",
        })

        with patch.object(extractor, "_call_llm", return_value=mock_response):
            result = extractor.extract()

        assert len(result.entity_claims) == 1
        cache_file = cache_dir / slugify("test-doc.pdf") / "chunk_0.kir.json"
        assert cache_file.exists()

    def test_cache_invalidation_by_hash(self, tmp_path):
        from knowledge_builder.frontend.llm_entity_extractor import LLMEntityExtractor

        cache_dir = tmp_path / "cache"
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        doc_path = docs_dir / "test-doc.txt"
        doc_path.write_text("Original content.", encoding="utf-8")

        extractor = LLMEntityExtractor(
            model="test-model",
            docs_dir=docs_dir,
            cache_dir=cache_dir,
            use_cache=True,
            verbose=False,
        )

        mock_response = json.dumps({
            "entities": [{"name": "Entity A", "types": ["concept"], "confidence": 0.9, "quote": "test"}],
            "aliases": [], "relations": [], "doc_role": "other", "doc_summary": "Test",
        })

        with patch.object(extractor, "_call_llm", return_value=mock_response):
            extractor.extract()

        doc_path.write_text("Modified content that is different.", encoding="utf-8")

        with patch.object(extractor, "_call_llm", return_value=mock_response) as mock_llm:
            extractor.extract()
            assert mock_llm.called

    def test_cache_cross_model_reuse(self, tmp_path):
        """Cache validates by hash only, not by model — cross-model reuse (RES-007)."""
        from knowledge_builder.frontend.llm_entity_extractor import LLMEntityExtractor

        cache_dir = tmp_path / "cache"
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        doc_path = docs_dir / "test-doc.txt"
        doc_path.write_text("Test content.", encoding="utf-8")

        extractor1 = LLMEntityExtractor(
            model="model-a", docs_dir=docs_dir, cache_dir=cache_dir, use_cache=True,
        )

        mock_response = json.dumps({
            "entities": [{"name": "A", "types": ["c"], "confidence": 0.9, "quote": "t"}],
            "aliases": [], "relations": [], "doc_role": "other", "doc_summary": "T",
        })

        with patch.object(extractor1, "_call_llm", return_value=mock_response):
            extractor1.extract()

        extractor2 = LLMEntityExtractor(
            model="model-b", docs_dir=docs_dir, cache_dir=cache_dir, use_cache=True,
        )

        with patch.object(extractor2, "_call_llm", return_value=mock_response) as mock_llm:
            extractor2.extract()
            assert not mock_llm.called  # cache hit — same hash, different model

    def test_no_cache_always_calls_llm(self, tmp_path):
        from knowledge_builder.frontend.llm_entity_extractor import LLMEntityExtractor

        cache_dir = tmp_path / "cache"
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        doc_path = docs_dir / "test-doc.txt"
        doc_path.write_text("Test content.", encoding="utf-8")

        extractor = LLMEntityExtractor(
            model="test-model", docs_dir=docs_dir, cache_dir=cache_dir,
            use_cache=False, verbose=False,
        )

        mock_response = json.dumps({
            "entities": [{"name": "A", "types": ["c"], "confidence": 0.9, "quote": "t"}],
            "aliases": [], "relations": [], "doc_role": "other", "doc_summary": "T",
        })

        with patch.object(extractor, "_call_llm", return_value=mock_response) as mock_llm:
            extractor.extract()
            assert mock_llm.called


# --------------------------------------------------------------------------- #
# Phase separation (compiler level)
# --------------------------------------------------------------------------- #

class TestPhaseSeparation:
    def _make_compiler(self, **kwargs):
        return KnowledgeCompiler(
            equivalences_text="ISO 27001 = ISMS\nNIST CSF = NIST Cybersecurity Framework",
            entity_aliases={"iso 27001": ["iso 27001", "isms"]},
            **kwargs,
        )

    def test_extract_only_produces_kir(self):
        compiler = self._make_compiler()
        kir = compiler.extract_only()
        assert kir.claim_count() > 0
        assert len(kir.entity_claims) > 0

    def test_compile_only_produces_model_without_codegen(self):
        compiler = self._make_compiler()
        kir = compiler.extract_only()
        model, validation, cold_data = compiler.compile_only(kir)
        assert model.stats()["canonical_entities"] > 0
        assert validation.is_valid
        assert "kir" in cold_data
        assert "validation" in cold_data

    def test_validate_only_returns_report(self):
        compiler = self._make_compiler()
        kir = compiler.extract_only()
        model, validation, cold_data = compiler.compile_only(kir)
        report = compiler.validate_only(model, validation)
        assert report["is_valid"] is True
        assert "model_stats" in report
        assert report["model_stats"]["canonical_entities"] > 0

    def test_publish_only_produces_artifacts(self, tmp_path):
        compiler = self._make_compiler()
        kir = compiler.extract_only()
        model, validation, cold_data = compiler.compile_only(kir)

        from src.artifact_registry.registry import ArtifactRegistry
        registry = ArtifactRegistry(tmp_path / "registry")

        build_id, manifest, artifacts, cold_artifacts = compiler.publish_only(
            model, cold_data, registry, promote=True
        )
        assert build_id is not None
        assert len(artifacts) == 7
        assert "predicate_catalog" in artifacts
        assert artifacts["predicate_catalog"]["catalog_version"] == "2.0.0"

    def test_compile_backward_compatible(self):
        compiler = self._make_compiler()
        result = compiler.compile()
        assert isinstance(result, CompileResult)
        assert result.kir_claim_count > 0
        assert len(result.artifacts) == 7
        assert result.validation.is_valid

    def test_compile_does_not_call_llm_in_compile_only(self):
        compiler = self._make_compiler(use_llm_extractor=False)
        kir = compiler.extract_only()
        model, validation, cold_data = compiler.compile_only(kir)
        assert "kir" in cold_data
        assert cold_data["kir"]["metadata"] is not None
