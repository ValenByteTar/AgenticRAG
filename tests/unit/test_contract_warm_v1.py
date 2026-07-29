"""Tests del contrato warm-v1 (ADR-0018, RES-001 §7, DEC-011).

Gate E1 del plan de orquestacion:

- Los schemas validan los ejemplos literales de RES-001 §7.4.
- Artifacts declarados y vacios pasan validacion (fasing, DEC-011.3).
- Todo claim exige bloque de confianza con validated=true (I5).
- Relations exigen evidence y predicados del catalogo.
- Manifest con artifact no declarado es rechazado.
- Integridad referencial entre artifacts del build.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src.contract import (
    declared_artifacts,
    validate_artifact,
    validate_build,
    validate_manifest,
)

FIXTURES = Path(__file__).resolve().parents[1] / "contract" / "fixtures"

ARTIFACT_NAMES = [
    "canonical_entities",
    "alias_index",
    "entity_index",
    "doc_roles",
    "entity_relations",
    "retrieval_metadata",
    "predicate_catalog",
]


def _load_fixture(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture()
def build():
    manifest = _load_fixture("manifest")
    artifacts = {name: _load_fixture(name) for name in ARTIFACT_NAMES}
    return manifest, artifacts


class TestDeclaredArtifacts:
    def test_warm_v1_declara_siete_artifacts(self):
        assert declared_artifacts() == ARTIFACT_NAMES

    def test_version_desconocida_rechazada(self):
        with pytest.raises(ValueError):
            declared_artifacts("warm-v99")


class TestSchemaValidation:
    """Los ejemplos literales de RES-001 §7.4 (envueltos en envelope) validan."""

    @pytest.mark.parametrize("name", ARTIFACT_NAMES)
    def test_fixture_valida(self, name):
        assert validate_artifact(name, _load_fixture(name)) == []

    def test_manifest_valida(self):
        assert validate_manifest(_load_fixture("manifest")) == []

    def test_artifact_desconocido_rechazado(self):
        errors = validate_artifact("taxonomy", {"concepts": []})
        assert errors and "desconocido" in errors[0]


class TestEmptyArtifacts:
    """Fasing (DEC-011.3): declarado y vacio es valido."""

    @pytest.mark.parametrize(
        "name,empty",
        [
            ("canonical_entities", {"entities": []}),
            ("alias_index", {"aliases": {}}),
            ("entity_index", {"entities": {}}),
            ("doc_roles", {"docs": {}}),
            ("entity_relations", {"relations": []}),
            ("retrieval_metadata", {"docs": {}}),
        ],
    )
    def test_artifact_vacio_valido(self, name, empty):
        assert validate_artifact(name, empty) == []

    def test_build_con_relations_vacio_valido(self, build):
        manifest, artifacts = build
        artifacts["entity_relations"] = {"relations": []}
        artifacts["retrieval_metadata"] = {"docs": {}}
        assert validate_build(manifest, artifacts) == []


class TestConfidenceBlock:
    """I5 / ADR-0018.9: todo claim exige confianza y validated=true."""

    def test_validated_false_rechazado(self):
        data = _load_fixture("canonical_entities")
        data["entities"][0]["validated"] = False
        errors = validate_artifact("canonical_entities", data)
        assert errors

    def test_sin_generated_by_rechazado(self):
        data = _load_fixture("alias_index")
        del data["aliases"]["iso27001"]["generated_by"]
        errors = validate_artifact("alias_index", data)
        assert errors

    def test_confidence_fuera_de_rango_rechazada(self):
        data = _load_fixture("doc_roles")
        data["docs"]["doc:iso27001"]["confidence"] = 1.5
        errors = validate_artifact("doc_roles", data)
        assert errors


class TestRelations:
    def test_relation_sin_evidence_rechazada(self):
        data = _load_fixture("entity_relations")
        del data["relations"][0]["evidence"]
        errors = validate_artifact("entity_relations", data)
        assert errors

    def test_evidence_opcional_en_otros_claims(self):
        data = _load_fixture("canonical_entities")
        assert "evidence" not in data["entities"][0]
        assert validate_artifact("canonical_entities", data) == []

    def test_predicado_fuera_de_catalogo_rechazado_en_build(self, build):
        manifest, artifacts = build
        artifacts["entity_relations"]["relations"][0]["predicate"] = "invented_predicate"
        errors = validate_build(manifest, artifacts)
        assert any("predicado fuera de catalogo" in e for e in errors)


class TestManifest:
    def test_artifact_no_declarado_rechazado(self, build):
        manifest, artifacts = build
        manifest["artifacts"]["taxonomy"] = {
            "sha256": "a" * 64,
            "path": "artifacts/taxonomy.json",
        }
        errors = validate_build(manifest, artifacts)
        assert any("no declarado" in e for e in errors)

    def test_sha256_malformado_rechazado(self):
        manifest = _load_fixture("manifest")
        manifest["artifacts"]["canonical_entities"]["sha256"] = "xyz"
        errors = validate_manifest(manifest)
        assert errors

    def test_contract_version_incorrecta_rechazada(self):
        manifest = _load_fixture("manifest")
        manifest["contract_version"] = "warm-v2"
        errors = validate_manifest(manifest)
        assert errors

    def test_artifact_listado_sin_datos_rechazado(self, build):
        manifest, artifacts = build
        del artifacts["alias_index"]
        errors = validate_build(manifest, artifacts)
        assert any("sin datos" in e for e in errors)


class TestReferentialIntegrity:
    def test_build_fixture_completo_valido(self, build):
        manifest, artifacts = build
        assert validate_build(manifest, artifacts) == []

    def test_alias_con_entity_colgante_rechazado(self, build):
        manifest, artifacts = build
        artifacts["alias_index"]["aliases"]["iso 27k"]["entity_id"] = "ent:no-existe"
        errors = validate_build(manifest, artifacts)
        assert any("alias_index" in e and "sin canonical entity" in e for e in errors)

    def test_entity_index_con_clave_colgante_rechazado(self, build):
        manifest, artifacts = build
        artifacts["entity_index"]["entities"]["ent:fantasma"] = copy.deepcopy(
            artifacts["entity_index"]["entities"]["ent:iso-27001"]
        )
        errors = validate_build(manifest, artifacts)
        assert any("entity_index" in e and "sin canonical entity" in e for e in errors)

    def test_doc_roles_con_entity_colgante_rechazado(self, build):
        manifest, artifacts = build
        artifacts["doc_roles"]["docs"]["doc:iso27001"]["entity_ids"].append("ent:otro")
        errors = validate_build(manifest, artifacts)
        assert any("doc_roles" in e and "sin canonical entity" in e for e in errors)

    def test_relation_con_extremo_colgante_rechazado(self, build):
        manifest, artifacts = build
        artifacts["entity_relations"]["relations"][0]["object"] = "ent:fantasma"
        errors = validate_build(manifest, artifacts)
        assert any("entity_relations" in e and "object sin canonical entity" in e for e in errors)

    def test_retrieval_metadata_con_doc_colgante_rechazado(self, build):
        manifest, artifacts = build
        artifacts["retrieval_metadata"]["docs"]["doc:fantasma"] = copy.deepcopy(
            artifacts["retrieval_metadata"]["docs"]["doc:iso27001"]
        )
        errors = validate_build(manifest, artifacts)
        assert any("retrieval_metadata" in e and "sin doc_role" in e for e in errors)
