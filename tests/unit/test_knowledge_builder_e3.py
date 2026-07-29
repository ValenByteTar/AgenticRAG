"""Tests del Knowledge Builder E3 — compiler pipeline end-to-end.

Cubre:
    - KIR: estructura, merge, claim_count, extractor_ids
    - Extractors: EquivalencesExtractor, EntityAliasesExtractor, DocCardsExtractor
    - Passes: NormalizePass, CanonicalizePass, DeduplicationPass
    - Confidence Policy: Max, Mean, Weighted, Bayesian
    - Validation: structural + evidence
    - Knowledge Model: layers Document + Entity
    - Warm Codegen: 7 artifacts conformes a warm-v1
    - End-to-end: compile + contract validation + publish + promote
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

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
from knowledge_builder.frontend import (
    DocCardsExtractor,
    EntityAliasesExtractor,
    EquivalencesExtractor,
)
from knowledge_builder.passes import (
    CanonicalizePass,
    DeduplicationPass,
    KnowledgePass,
    NormalizePass,
)
from knowledge_builder.model import (
    BayesianPolicy,
    ConfidencePolicy,
    KnowledgeModel,
    MaxPolicy,
    MeanPolicy,
    WeightedPolicy,
    get_policy,
)
from knowledge_builder.validate import KIRValidator, ValidationResult
from knowledge_builder.backend import ColdCodegen, WarmCodegen
from knowledge_builder.compiler import KnowledgeCompiler, CompileResult
from knowledge_builder.diff_report import DiffReportGenerator

from src.contract.validator import validate_build
from src.artifact_registry.registry import ArtifactRegistry


# --------------------------------------------------------------------------- #
# Test data
# --------------------------------------------------------------------------- #

SAMPLE_EQUIVALENCES = """Tabla de equivalencias

CISO = Chief Information Security Officer

CISSP = Certified Information Systems Security Professional

SOC = Security Operations Center = Centro de Operaciones de Seguridad

ISO 27001 = ISO/IEC 27001 = Information Security Management System = ISMS = SGSI
"""

SAMPLE_ALIASES = {
    "iso 27001": ["iso 27001", "iso27001", "iso 27k", "isms"],
    "cissp": ["cissp", "certified information systems security professional", "(isc)2"],
}

SAMPLE_DOC_ROLES = {
    "docs": {
        "ISO 27001 Standard.pdf": {
            "name": "ISO 27001 Standard",
            "role": "entity_profile",
            "centrality": 0.92,
            "entities_index": ["ISO 27001", "ISMS"],
            "attributes_index": ["controls", "risk assessment", "annex a"],
            "summary": "International standard for information security management systems.",
            "quality": 0.7,
        },
        "ISMS Implementation Guide.pdf": {
            "name": "ISMS Implementation Guide",
            "role": "procedure",
            "centrality": 0.6,
            "entities_index": ["ISO 27001", "ISMS"],
            "attributes_index": ["implementation", "isms"],
            "summary": "Guide for implementing an ISMS.",
            "quality": 0.7,
        },
    }
}


# --------------------------------------------------------------------------- #
# KIR tests
# --------------------------------------------------------------------------- #

class TestKIR:
    def test_kir_empty(self):
        kir = KIR()
        assert kir.claim_count() == 0
        assert kir.extractor_ids() == []

    def test_kir_merge(self):
        kir1 = KIR(entity_claims=[EntityClaim(
            surface_form="ISO 27001", canonical_name="iso 27001",
            extractor_id="deterministic:equivalences-text", confidence=0.9,
        )])
        kir2 = KIR(entity_claims=[EntityClaim(
            surface_form="CISSP", canonical_name="cissp",
            extractor_id="deterministic:entity-aliases-dict", confidence=0.9,
        )])
        kir1.merge(kir2)
        assert kir1.claim_count() == 2
        assert len(kir1.extractor_ids()) == 2

    def test_kir_to_dict(self):
        kir = KIR(entity_claims=[EntityClaim(
            surface_form="ISO 27001", canonical_name="iso 27001",
            entity_types=["framework", "standard"],
            extractor_id="test", confidence=0.9,
            evidence=[EvidenceItem(quote="test")],
        )])
        d = kir.to_dict()
        assert "entity_claims" in d
        assert len(d["entity_claims"]) == 1
        assert d["entity_claims"][0]["canonical_name"] == "iso 27001"

    def test_normalize_text(self):
        assert normalize_text("ISO 27001") == "iso 27001"
        assert normalize_text("  Multiple   Spaces  ") == "multiple spaces"
        assert normalize_text("Café") == "cafe"

    def test_slugify(self):
        assert slugify("ISO 27001") == "iso-27001"
        assert slugify("ISMS Implementation Guide") == "isms-implementation-guide"


# --------------------------------------------------------------------------- #
# Extractor tests
# --------------------------------------------------------------------------- #

class TestEquivalencesExtractor:
    def test_extract_produces_kir(self):
        ext = EquivalencesExtractor(SAMPLE_EQUIVALENCES)
        kir = ext.extract()
        assert kir.claim_count() > 0
        assert "deterministic:equivalences-text" in kir.extractor_ids()

    def test_entity_claims_present(self):
        ext = EquivalencesExtractor(SAMPLE_EQUIVALENCES)
        kir = ext.extract()
        canonicals = {c.canonical_name for c in kir.entity_claims}
        assert len(canonicals) > 0
        assert "information security management system" in canonicals

    def test_alias_claims_present(self):
        ext = EquivalencesExtractor(SAMPLE_EQUIVALENCES)
        kir = ext.extract()
        aliases = {c.alias for c in kir.alias_claims}
        assert len(aliases) > 0

    def test_relation_claims_present(self):
        ext = EquivalencesExtractor(SAMPLE_EQUIVALENCES)
        kir = ext.extract()
        assert len(kir.relation_claims) > 0
        assert all(r.predicate == "equivalent_to" for r in kir.relation_claims)

    def test_deterministic(self):
        ext1 = EquivalencesExtractor(SAMPLE_EQUIVALENCES)
        ext2 = EquivalencesExtractor(SAMPLE_EQUIVALENCES)
        k1 = ext1.extract()
        k2 = ext2.extract()
        assert k1.claim_count() == k2.claim_count()


class TestEntityAliasesExtractor:
    def test_extract_produces_kir(self):
        ext = EntityAliasesExtractor(SAMPLE_ALIASES)
        kir = ext.extract()
        assert len(kir.entity_claims) == 2
        assert len(kir.alias_claims) > 0

    def test_canonical_entities(self):
        ext = EntityAliasesExtractor(SAMPLE_ALIASES)
        kir = ext.extract()
        canonicals = {c.canonical_name for c in kir.entity_claims}
        assert "iso 27001" in canonicals
        assert "cissp" in canonicals

    def test_aliases_point_to_canonical(self):
        ext = EntityAliasesExtractor(SAMPLE_ALIASES)
        kir = ext.extract()
        for alias in kir.alias_claims:
            assert alias.alias != alias.canonical_name


class TestDocCardsExtractor:
    def test_extract_produces_kir(self):
        ext = DocCardsExtractor(doc_roles=SAMPLE_DOC_ROLES)
        kir = ext.extract()
        assert len(kir.document_claims) == 2
        assert len(kir.entity_claims) > 0

    def test_document_roles(self):
        ext = DocCardsExtractor(doc_roles=SAMPLE_DOC_ROLES)
        kir = ext.extract()
        roles = {c.role for c in kir.document_claims}
        assert "entity_profile" in roles
        assert "procedure" in roles

    def test_entity_mentions(self):
        ext = DocCardsExtractor(doc_roles=SAMPLE_DOC_ROLES)
        kir = ext.extract()
        mentions = {c.canonical_name for c in kir.entity_claims}
        assert "iso 27001" in mentions


# --------------------------------------------------------------------------- #
# Passes tests
# --------------------------------------------------------------------------- #

class TestNormalizePass:
    def test_normalizes_casing(self):
        kir = KIR(entity_claims=[EntityClaim(
            surface_form="ISO 27001", canonical_name="ISO 27001",
            entity_types=["Framework", "Standard"],
            extractor_id="test", confidence=0.9,
        )])
        result = NormalizePass().run(kir)
        assert result.entity_claims[0].canonical_name == "iso 27001"
        assert "framework" in result.entity_claims[0].entity_types

    def test_does_not_mutate_original(self):
        kir = KIR(entity_claims=[EntityClaim(
            surface_form="ISO 27001", canonical_name="ISO 27001",
            extractor_id="test", confidence=0.9,
        )])
        NormalizePass().run(kir)
        assert kir.entity_claims[0].canonical_name == "ISO 27001"


class TestCanonicalizePass:
    def test_assigns_entity_ids(self):
        kir = KIR(entity_claims=[EntityClaim(
            surface_form="iso 27001", canonical_name="iso 27001",
            extractor_id="test", confidence=0.9,
        )])
        result = CanonicalizePass().run(kir)
        eid = result.entity_claims[0].raw.get("entity_id", "")
        assert eid.startswith("ent:")
        assert "iso-27001" in eid

    def test_assigns_doc_ids(self):
        kir = KIR(document_claims=[DocumentClaim(
            source_path="test.pdf", name="ISO 27001 Standard",
            extractor_id="test", confidence=0.7,
        )])
        result = CanonicalizePass().run(kir)
        did = result.document_claims[0].raw.get("doc_id", "")
        assert did.startswith("doc:")
        assert "iso-27001-standard" in did

    def test_canonical_map_in_metadata(self):
        kir = KIR(entity_claims=[EntityClaim(
            surface_form="iso 27001", canonical_name="iso 27001",
            extractor_id="test", confidence=0.9,
        )])
        result = CanonicalizePass().run(kir)
        assert "canonical_map" in result.metadata


class TestDeduplicationPass:
    def test_dedup_entities(self):
        kir = KIR(entity_claims=[
            EntityClaim(surface_form="iso 27001", canonical_name="iso 27001",
                       extractor_id="ext1", confidence=0.9),
            EntityClaim(surface_form="ISO 27001", canonical_name="iso 27001",
                       extractor_id="ext2", confidence=0.95),
        ])
        result = DeduplicationPass().run(kir)
        assert len(result.entity_claims) == 1

    def test_dedup_with_confidence_policy(self):
        policy = MaxPolicy()
        kir = KIR(entity_claims=[
            EntityClaim(surface_form="iso 27001", canonical_name="iso 27001",
                       extractor_id="ext1", confidence=0.9),
            EntityClaim(surface_form="ISO 27001", canonical_name="iso 27001",
                       extractor_id="ext2", confidence=0.95),
        ])
        result = DeduplicationPass(confidence_policy=policy).run(kir)
        assert result.entity_claims[0].confidence == 0.95

    def test_dedup_aliases(self):
        kir = KIR(alias_claims=[
            AliasClaim(alias="iso27001", canonical_name="iso 27001",
                      extractor_id="ext1", confidence=0.9),
            AliasClaim(alias="iso27001", canonical_name="iso 27001",
                      extractor_id="ext2", confidence=0.95),
        ])
        result = DeduplicationPass().run(kir)
        assert len(result.alias_claims) == 1

    def test_dedup_relations(self):
        kir = KIR(relation_claims=[
            RelationClaim(subject_name="iso 27001", predicate="equivalent_to",
                         object_name="isms", extractor_id="ext1", confidence=0.9),
            RelationClaim(subject_name="iso 27001", predicate="equivalent_to",
                         object_name="isms", extractor_id="ext2", confidence=0.95),
        ])
        result = DeduplicationPass().run(kir)
        assert len(result.relation_claims) == 1


# --------------------------------------------------------------------------- #
# Confidence Policy tests
# --------------------------------------------------------------------------- #

class TestConfidencePolicy:
    def test_max_policy(self):
        assert MaxPolicy().combine([0.8, 0.95, 0.7], ["a", "b", "c"]) == 0.95

    def test_mean_policy(self):
        assert MeanPolicy().combine([0.8, 0.9], ["a", "b"]) == pytest.approx(0.85)

    def test_weighted_policy(self):
        policy = WeightedPolicy()
        result = policy.combine(
            [0.9, 0.7],
            ["deterministic:equivalences-text", "deterministic:doc-cards"],
        )
        assert 0.7 < result < 0.9

    def test_bayesian_policy(self):
        result = BayesianPolicy().combine([0.9, 0.8], ["a", "b"])
        assert result > 0.9
        assert result <= 1.0

    def test_factory(self):
        assert isinstance(get_policy("max"), MaxPolicy)
        assert isinstance(get_policy("mean"), MeanPolicy)
        assert isinstance(get_policy("weighted"), WeightedPolicy)
        assert isinstance(get_policy("bayesian"), BayesianPolicy)

    def test_factory_unknown(self):
        with pytest.raises(ValueError):
            get_policy("unknown")


# --------------------------------------------------------------------------- #
# Validation tests
# --------------------------------------------------------------------------- #

class TestValidation:
    def test_valid_kir(self):
        kir = KIR(entity_claims=[EntityClaim(
            surface_form="iso 27001", canonical_name="iso 27001",
            extractor_id="test", confidence=0.9,
            evidence=[EvidenceItem(quote="test")],
            raw={"entity_id": "ent:iso-27001"},
        )])
        validator = KIRValidator()
        result = validator.validate(kir)
        assert result.is_valid
        assert result.passed > 0

    def test_missing_entity_id(self):
        kir = KIR(entity_claims=[EntityClaim(
            surface_form="iso 27001", canonical_name="iso 27001",
            extractor_id="test", confidence=0.9,
        )])
        validator = KIRValidator()
        result = validator.validate(kir)
        assert not result.is_valid
        assert any("entity_id" in e for e in result.errors)

    def test_predicate_outside_catalog(self):
        kir = KIR(relation_claims=[RelationClaim(
            subject_name="a", predicate="invented_predicate", object_name="b",
            extractor_id="test", confidence=0.9,
            evidence=[EvidenceItem(quote="test")],
        )])
        validator = KIRValidator(predicate_catalog=["equivalent_to", "defines"])
        result = validator.validate(kir)
        assert not result.is_valid
        assert any("catalogo" in e for e in result.errors)

    def test_quarantine_no_evidence(self):
        kir = KIR(entity_claims=[EntityClaim(
            surface_form="iso 27001", canonical_name="iso 27001",
            extractor_id="test", confidence=0.9,
            raw={"entity_id": "ent:iso-27001"},
        )])
        validator = KIRValidator()
        result = validator.validate(kir)
        assert len(result.quarantined) > 0
        assert result.is_valid


# --------------------------------------------------------------------------- #
# Knowledge Model tests
# --------------------------------------------------------------------------- #

class TestKnowledgeModel:
    def test_from_kir(self):
        kir = KIR(
            entity_claims=[EntityClaim(
                surface_form="iso 27001", canonical_name="iso 27001",
                entity_types=["framework"],
                extractor_id="test", confidence=0.9,
                evidence=[EvidenceItem(quote="test")],
                raw={"entity_id": "ent:iso-27001"},
            )],
            alias_claims=[AliasClaim(
                alias="iso27001", canonical_name="iso 27001",
                extractor_id="test", confidence=0.95,
                raw={"entity_id": "ent:iso-27001"},
            )],
            document_claims=[DocumentClaim(
                source_path="test.pdf", name="ISO 27001 Standard",
                role="entity_profile", centrality=0.9,
                entity_mentions=["iso 27001"],
                extractor_id="test", confidence=0.7,
                evidence=[EvidenceItem(quote="test")],
                raw={"doc_id": "doc:iso-27001-standard"},
            )],
            metadata={"canonical_map": {"iso 27001": "ent:iso-27001"}},
        )
        model = KnowledgeModel.from_kir(kir)
        assert len(model.canonical_entities) == 1
        assert len(model.aliases) == 1
        assert len(model.document_roles) == 1
        assert model.canonical_entities[0].entity_id == "ent:iso-27001"

    def test_stats(self):
        kir = KIR(entity_claims=[EntityClaim(
            surface_form="iso 27001", canonical_name="iso 27001",
            extractor_id="test", confidence=0.9,
            raw={"entity_id": "ent:iso-27001"},
        )])
        model = KnowledgeModel.from_kir(kir)
        stats = model.stats()
        assert stats["canonical_entities"] == 1


# --------------------------------------------------------------------------- #
# Warm Codegen tests
# --------------------------------------------------------------------------- #

class TestWarmCodegen:
    def test_generates_7_artifacts(self):
        kir = KIR(entity_claims=[EntityClaim(
            surface_form="iso 27001", canonical_name="iso 27001",
            entity_types=["framework"],
            extractor_id="test", confidence=0.9,
            evidence=[EvidenceItem(quote="test")],
            raw={"entity_id": "ent:iso-27001"},
        )])
        model = KnowledgeModel.from_kir(kir)
        codegen = WarmCodegen(builder_version="1.0.0")
        output = codegen.generate(model, build_id="ka_v1.0.0")
        assert len(output["artifacts"]) == 7
        assert "manifest" in output
        assert set(output["artifacts"].keys()) == {
            "canonical_entities", "alias_index", "entity_index",
            "doc_roles", "entity_relations", "retrieval_metadata",
            "predicate_catalog",
        }

    def test_manifest_has_required_fields(self):
        kir = KIR()
        model = KnowledgeModel.from_kir(kir)
        codegen = WarmCodegen()
        output = codegen.generate(model, build_id="ka_v1.0.0")
        manifest = output["manifest"]
        assert manifest["build_id"] == "ka_v1.0.0"
        assert manifest["contract_version"] == "warm-v1"
        assert manifest["builder_version"] == "1.0.0"
        assert "created_at" in manifest
        assert len(manifest["artifacts"]) == 7

    def test_predicate_catalog_has_13_predicates(self):
        kir = KIR()
        model = KnowledgeModel.from_kir(kir)
        codegen = WarmCodegen()
        output = codegen.generate(model)
        catalog = output["artifacts"]["predicate_catalog"]
        assert len(catalog["predicates"]) == 13


# --------------------------------------------------------------------------- #
# End-to-end compiler tests
# --------------------------------------------------------------------------- #

class TestCompilerEndToEnd:
    def test_compile_produces_valid_result(self):
        compiler = KnowledgeCompiler(
            equivalences_text=SAMPLE_EQUIVALENCES,
            entity_aliases=SAMPLE_ALIASES,
            doc_roles=SAMPLE_DOC_ROLES,
            build_id="ka_v1.0.0-test",
        )
        result = compiler.compile()
        assert result.is_valid
        assert len(result.artifacts) == 7
        assert result.kir_claim_count > 0
        assert len(result.extractor_ids) == 3

    def test_compiled_artifacts_pass_contract_validation(self):
        compiler = KnowledgeCompiler(
            equivalences_text=SAMPLE_EQUIVALENCES,
            entity_aliases=SAMPLE_ALIASES,
            doc_roles=SAMPLE_DOC_ROLES,
            build_id="ka_v1.0.0-test",
        )
        result = compiler.compile()
        errors = validate_build(result.manifest, result.artifacts)
        assert errors == [], f"Contract validation errors: {errors[:5]}"

    def test_publish_and_promote(self):
        tmpdir = tempfile.mkdtemp()
        try:
            registry = ArtifactRegistry(Path(tmpdir))
            compiler = KnowledgeCompiler(
                equivalences_text=SAMPLE_EQUIVALENCES,
                entity_aliases=SAMPLE_ALIASES,
                doc_roles=SAMPLE_DOC_ROLES,
                build_id="ka_v1.0.0-test",
            )
            result = compiler.compile()
            build_id = compiler.publish(result, registry, promote=True)
            assert build_id == "ka_v1.0.0-test"

            manifest = registry.get_manifest()
            assert manifest["build_id"] == "ka_v1.0.0-test"
            assert manifest["contract_version"] == "warm-v1"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_diff_report(self):
        compiler = KnowledgeCompiler(
            equivalences_text=SAMPLE_EQUIVALENCES,
            entity_aliases=SAMPLE_ALIASES,
            doc_roles=SAMPLE_DOC_ROLES,
            build_id="ka_v1.0.0-test",
        )
        result = compiler.compile()
        gen = DiffReportGenerator()
        report = gen.generate(result)
        assert "DIFF REPORT" in report
        assert "EQUIVALENCES" in report
        assert "ENTITY_ALIASES" in report


# --------------------------------------------------------------------------- #
# Cold Codegen tests
# --------------------------------------------------------------------------- #

class TestColdCodegen:
    def test_generate_cold_artifacts(self):
        kir = KIR(entity_claims=[EntityClaim(
            surface_form="iso 27001", canonical_name="iso 27001",
            extractor_id="test", confidence=0.9,
        )])
        validation = ValidationResult(passed=1)
        codegen = ColdCodegen()
        cold = codegen.generate(kir, validation, build_metadata={"test": True})
        assert "kir_snapshot" in cold
        assert "validation_report" in cold
        assert "build_metadata" in cold

    def test_write_to_dir(self):
        tmpdir = tempfile.mkdtemp()
        try:
            kir = KIR()
            validation = ValidationResult()
            codegen = ColdCodegen(output_dir=Path(tmpdir))
            cold = codegen.generate(kir, validation)
            cold_dir = codegen.write_to_dir(cold, "ka_test")
            assert cold_dir.exists()
            assert (cold_dir / "kir_snapshot.json").exists()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
