"""Tests for E5: LLM extractor, semantic validation, quarantine, confidence combining.

E5 requirements:
    - LLM extractor produces same KIR format as deterministic extractors
    - Semantic validation detects contradictions, collisions, role inconsistencies
    - Claims without evidence go to quarantine (Cold), never Warm
    - Confidence policy combines deterministic + LLM extractor weights
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

from knowledge_builder.kir import (
    AliasClaim,
    DocumentClaim,
    EntityClaim,
    EvidenceItem,
    KIR,
    RelationClaim,
    normalize_text,
)
from knowledge_builder.frontend.llm_entity_extractor import (
    LLMEntityExtractor,
    _EXTRACTION_PROMPT,
    _EXTRACTOR_ID,
)
from knowledge_builder.validate.semantic_validator import SemanticValidator
from knowledge_builder.model.confidence import WeightedPolicy


# --------------------------------------------------------------------------- #
# LLM Extractor Tests
# --------------------------------------------------------------------------- #


class TestLLMEntityExtractor:
    """Tests for LLMEntityExtractor (E5)."""

    def test_extractor_id(self):
        assert _EXTRACTOR_ID == "llm:granite-4.1-8b"

    def test_prompt_placeholder_replacement(self):
        """Prompt uses str.replace, not .format() — avoids JSON brace conflicts."""
        text = "ISO 27001 is a standard"
        prompt = _EXTRACTION_PROMPT.replace("{text}", text)
        assert "ISO 27001 is a standard" in prompt
        # Should NOT raise KeyError from .format()
        with pytest.raises(KeyError):
            _EXTRACTION_PROMPT.format(text=text)

    def test_parse_json_response_valid(self):
        data = LLMEntityExtractor._parse_json_response('{"entities": [], "aliases": []}')
        assert data is not None
        assert "entities" in data

    def test_parse_json_response_code_fence(self):
        resp = '```json\n{"entities": [], "aliases": []}\n```'
        data = LLMEntityExtractor._parse_json_response(resp)
        assert data is not None
        assert "entities" in data

    def test_parse_json_response_with_text_around(self):
        resp = 'Here is the analysis:\n{"entities": [], "aliases": []}\nDone.'
        data = LLMEntityExtractor._parse_json_response(resp)
        assert data is not None
        assert "entities" in data

    def test_parse_json_response_invalid(self):
        data = LLMEntityExtractor._parse_json_response("not json at all")
        assert data is None

    def test_parse_json_response_empty(self):
        assert LLMEntityExtractor._parse_json_response("") is None
        assert LLMEntityExtractor._parse_json_response(None) is None

    def test_chunk_text_short(self):
        extractor = LLMEntityExtractor()
        chunks = extractor._chunk_text("short text", 100)
        assert len(chunks) == 1

    def test_chunk_text_long(self):
        extractor = LLMEntityExtractor()
        text = "\n\n".join([f"Paragraph {i} " * 50 for i in range(10)])
        chunks = extractor._chunk_text(text, 200)
        assert len(chunks) > 1

    def test_extract_produces_kir(self, tmp_path):
        """LLM extractor produces valid KIR with evidence on all claims."""
        doc = tmp_path / "test.txt"
        doc.write_text("ISO 27001 is a standard. Also known as ISO27K.", encoding="utf-8")

        extractor = LLMEntityExtractor(docs_dir=tmp_path, max_docs=1)

        # Mock the LLM call
        mock_response = json.dumps({
            "entities": [
                {"name": "ISO 27001", "types": ["standard"], "confidence": 0.9, "quote": "ISO 27001 is a standard"}
            ],
            "aliases": [
                {"alias": "ISO27K", "canonical": "ISO 27001", "confidence": 0.8, "quote": "Also known as ISO27K"}
            ],
            "relations": [
                {"subject": "ISO 27001", "predicate": "related_to", "object": "NIST CSF", "confidence": 0.7, "quote": "related"}
            ],
            "doc_role": "standard_profile",
            "doc_summary": "About ISO 27001",
        })

        extractor._call_llm = lambda prompt: mock_response

        kir = extractor.extract()

        assert len(kir.entity_claims) > 0
        assert all(isinstance(c, EntityClaim) for c in kir.entity_claims)
        assert all(c.extractor_id == _EXTRACTOR_ID for c in kir.entity_claims)
        assert all(c.evidence for c in kir.entity_claims)
        assert all(c.confidence > 0 for c in kir.entity_claims)

        assert len(kir.alias_claims) > 0
        assert all(isinstance(c, AliasClaim) for c in kir.alias_claims)

        assert len(kir.relation_claims) > 0
        assert all(isinstance(c, RelationClaim) for c in kir.relation_claims)

        assert len(kir.document_claims) > 0
        assert all(isinstance(c, DocumentClaim) for c in kir.document_claims)

    def test_extract_empty_response(self, tmp_path):
        doc = tmp_path / "test.txt"
        doc.write_text("some text", encoding="utf-8")

        extractor = LLMEntityExtractor(docs_dir=tmp_path, max_docs=1)
        extractor._call_llm = lambda prompt: ""

        kir = extractor.extract()
        assert kir.claim_count() == 0

    def test_extract_no_docs(self):
        extractor = LLMEntityExtractor(docs_dir=Path("/nonexistent"))
        kir = extractor.extract()
        assert kir.claim_count() == 0


# --------------------------------------------------------------------------- #
# Semantic Validator Tests
# --------------------------------------------------------------------------- #


class TestSemanticValidator:
    """Tests for SemanticValidator (E5)."""

    def test_role_consistency_valid(self):
        validator = SemanticValidator(use_llm=False)
        kir = KIR()
        kir.document_claims.append(DocumentClaim(
            source_path="doc.pdf", name="doc.pdf", role="standard_profile",
            extractor_id="test", confidence=0.9,
            evidence=[EvidenceItem(source_doc_id="doc:doc", quote="test")],
        ))
        result = validator.validate(kir)
        assert len(result["errors"]) == 0

    def test_role_consistency_invalid(self):
        validator = SemanticValidator(use_llm=False)
        kir = KIR()
        kir.document_claims.append(DocumentClaim(
            source_path="doc.pdf", name="doc.pdf", role="invalid_role",
            extractor_id="test", confidence=0.9,
            evidence=[EvidenceItem(source_doc_id="doc:doc", quote="test")],
        ))
        result = validator.validate(kir)
        assert any("role fuera de taxonomia" in w for w in result["warnings"])

    def test_canonical_collision(self):
        validator = SemanticValidator(use_llm=False)
        kir = KIR()
        kir.entity_claims.append(EntityClaim(
            surface_form="ISO 27001", canonical_name="iso 27001",
            extractor_id="test", confidence=0.9,
            raw={"entity_id": "ent:iso-27001"},
            evidence=[EvidenceItem(source_doc_id="doc:doc", quote="test")],
        ))
        kir.entity_claims.append(EntityClaim(
            surface_form="ISO 27001", canonical_name="iso 27001",
            extractor_id="test", confidence=0.8,
            raw={"entity_id": "ent:iso-27001-dup"},
            evidence=[EvidenceItem(source_doc_id="doc:doc", quote="test")],
        ))
        result = validator.validate(kir)
        assert any("canonical collision" in w for w in result["warnings"])

    def test_alias_contradiction(self):
        validator = SemanticValidator(use_llm=False)
        kir = KIR()
        kir.alias_claims.append(AliasClaim(
            alias="isms", canonical_name="iso 27001",
            extractor_id="test", confidence=0.9,
            evidence=[EvidenceItem(source_doc_id="doc:doc", quote="test")],
        ))
        kir.alias_claims.append(AliasClaim(
            alias="isms", canonical_name="information security management system",
            extractor_id="test", confidence=0.9,
            evidence=[EvidenceItem(source_doc_id="doc:doc", quote="test")],
        ))
        result = validator.validate(kir)
        assert len(result["errors"]) > 0
        assert any("alias contradiction" in e for e in result["errors"])

    def test_self_referencing_relation(self):
        validator = SemanticValidator(use_llm=False)
        kir = KIR()
        kir.relation_claims.append(RelationClaim(
            subject_name="iso 27001", predicate="related_to", object_name="iso 27001",
            extractor_id="test", confidence=0.9,
            evidence=[EvidenceItem(source_doc_id="doc:doc", quote="test")],
        ))
        result = validator.validate(kir)
        assert any("self-referencing" in w for w in result["warnings"])

    def test_quarantine_no_evidence(self):
        validator = SemanticValidator(use_llm=False)
        kir = KIR()
        kir.entity_claims.append(EntityClaim(
            surface_form="ISO 27001", canonical_name="iso 27001",
            extractor_id="test", confidence=0.9,
            evidence=[],
        ))
        result = validator.validate(kir)
        assert len(result["quarantined"]) > 0
        assert any("sin evidencia" in q for q in result["quarantined"])

    def test_evidence_passes(self):
        validator = SemanticValidator(use_llm=False)
        kir = KIR()
        kir.entity_claims.append(EntityClaim(
            surface_form="ISO 27001", canonical_name="iso 27001",
            extractor_id="test", confidence=0.9,
            evidence=[EvidenceItem(source_doc_id="doc:doc", quote="test")],
        ))
        result = validator.validate(kir)
        assert len(result["quarantined"]) == 0
        assert result["passed"] > 0


# --------------------------------------------------------------------------- #
# Confidence Policy Tests
# --------------------------------------------------------------------------- #


class TestConfidencePolicy:
    """Tests for confidence policy combining deterministic + LLM extractors."""

    def test_weighted_policy_llm_weight(self):
        policy = WeightedPolicy()
        # LLM extractor has weight 0.85 in _EXTRACTOR_WEIGHTS
        assert policy.weights.get("llm:granite-4.1-8b") == 0.85

    def test_weighted_policy_combines(self):
        policy = WeightedPolicy()
        # Deterministic: 0.95 * 0.95 = 0.9025
        # LLM: 0.9 * 0.85 = 0.765
        # Weighted: (0.9025 + 0.765) / (0.95 + 0.85) = 0.9264
        result = policy.combine(
            [0.95, 0.9],
            ["deterministic:equivalences-text", "llm:granite-4.1-8b"],
        )
        assert 0.85 < result <= 1.0

    def test_weighted_policy_llm_only(self):
        policy = WeightedPolicy()
        result = policy.combine([0.9], ["llm:granite-4.1-8b"])
        assert result == 0.9

    def test_weighted_policy_unknown_extractor(self):
        policy = WeightedPolicy()
        result = policy.combine([0.8], ["unknown:extractor"])
        assert result == 0.8  # default weight 0.5


# --------------------------------------------------------------------------- #
# Compiler Integration Tests
# --------------------------------------------------------------------------- #


class TestCompilerE5Integration:
    """Tests for E5 integration in KnowledgeCompiler."""

    def test_compiler_accepts_llm_params(self):
        from knowledge_builder.compiler import KnowledgeCompiler

        compiler = KnowledgeCompiler(
            equivalences_text="A = B\n",
            entity_aliases={"iso 27001": ["iso27k"]},
            use_llm_extractor=True,
            llm_model="ibm/granite4.1:8b-q4_K_M",
            llm_max_docs=1,
            use_semantic_validation=True,
        )
        assert compiler.use_llm_extractor is True
        assert compiler.use_semantic_validation is True

    def test_compiler_semantic_validation_runs(self):
        """Semantic validation runs but doesn't block build."""
        from knowledge_builder.compiler import KnowledgeCompiler

        compiler = KnowledgeCompiler(
            equivalences_text="A = B\n",
            entity_aliases={"iso 27001": ["iso27k"]},
            use_semantic_validation=True,
            build_id="test",
        )
        result = compiler.compile()
        assert result is not None
        assert result.validation is not None

    def test_compile_result_includes_semantic_validation(self):
        """Cold artifacts include semantic validation results when enabled."""
        from knowledge_builder.compiler import KnowledgeCompiler

        compiler = KnowledgeCompiler(
            equivalences_text="A = B\n",
            entity_aliases={"iso 27001": ["iso27k"]},
            use_semantic_validation=True,
            build_id="test",
        )
        result = compiler.compile()
        assert "semantic_validation" in result.cold_artifacts
