"""Tests del Artifact Registry (RES-001 §5, DEC-012).

Gate E2 del plan de orquestacion:

- Round-trip E2E: publish -> staging -> promote -> resolve -> rollback.
- Corrupcion sha256 detectada (en disco y en publish).
- contract_version incompatible rechazada en publish y promote.
- Un solo build activo; promote anterior pasa a deprecated.
- Retencion: deprecated -> archived por conteo, archived -> purged por antiguedad.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.artifact_registry import (
    ArtifactRegistry,
    BuildNotFoundError,
    IntegrityError,
    RegistryError,
    ValidationError,
    compute_checksums,
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


def _make_build(build_id: str):
    """Build valido con checksums reales (compute_checksums)."""
    artifacts = {name: _load_fixture(name) for name in ARTIFACT_NAMES}
    checksums = compute_checksums(artifacts)
    manifest = _load_fixture("manifest")
    manifest["build_id"] = build_id
    for name in manifest["artifacts"]:
        manifest["artifacts"][name]["sha256"] = checksums[name]
    return manifest, artifacts


@pytest.fixture()
def registry(tmp_path):
    return ArtifactRegistry(root=tmp_path / "registry")


@pytest.fixture()
def published_build(registry):
    manifest, artifacts = _make_build("ka_v1.0.0")
    registry.publish(manifest, artifacts)
    return manifest, artifacts


class TestPublish:
    def test_publish_deja_build_en_staging(self, registry, published_build):
        builds = registry.list_builds(state="staging")
        assert [b.build_id for b in builds] == ["ka_v1.0.0"]

    def test_publish_sin_build_activo_todavia(self, registry, published_build):
        with pytest.raises(RegistryError, match="no hay build activo"):
            registry.resolve()

    def test_publish_duplicado_rechazado(self, registry, published_build):
        manifest, artifacts = published_build
        with pytest.raises(RegistryError, match="ya publicado"):
            registry.publish(manifest, artifacts)

    def test_publish_contract_invalido_rechazado(self, registry):
        manifest, artifacts = _make_build("ka_bad_contract")
        artifacts["entity_relations"]["relations"][0]["predicate"] = "invented"
        with pytest.raises(ValidationError, match="predicado fuera de catalogo"):
            registry.publish(manifest, artifacts)
        assert registry.list_builds() == []

    def test_publish_version_no_soportada_rechazada(self, registry):
        manifest, artifacts = _make_build("ka_v2")
        manifest["contract_version"] = "warm-v2"
        with pytest.raises(ValidationError, match="no soportada"):
            registry.publish(manifest, artifacts)

    def test_publish_checksum_declarado_incorrecto_rechazado(self, registry):
        manifest, artifacts = _make_build("ka_bad_sum")
        manifest["artifacts"]["alias_index"]["sha256"] = "0" * 64
        with pytest.raises(ValidationError, match="integrity"):
            registry.publish(manifest, artifacts)


class TestPromoteResolve:
    def test_round_trip_promote_resolve(self, registry, published_build):
        manifest, artifacts = published_build
        registry.promote("ka_v1.0.0", expected_contract_version="warm-v1")
        resolved = registry.resolve()
        assert resolved["manifest"]["build_id"] == "ka_v1.0.0"
        assert resolved["artifacts"] == artifacts

    def test_promote_desde_estado_incorrecto_rechazado(self, registry, published_build):
        registry.promote("ka_v1.0.0")
        with pytest.raises(RegistryError, match="staging"):
            registry.promote("ka_v1.0.0")

    def test_promote_version_esperada_incompatible_rechazada(self, registry, published_build):
        with pytest.raises(ValidationError, match="compatibility"):
            registry.promote("ka_v1.0.0", expected_contract_version="warm-v2")

    def test_promote_build_inexistente(self, registry):
        with pytest.raises(BuildNotFoundError):
            registry.promote("ka_fantasma")

    def test_un_solo_build_activo(self, registry, published_build):
        registry.promote("ka_v1.0.0")
        manifest2, artifacts2 = _make_build("ka_v1.1.0")
        registry.publish(manifest2, artifacts2)
        registry.promote("ka_v1.1.0")

        assert registry.resolve()["manifest"]["build_id"] == "ka_v1.1.0"
        deprecated = [b.build_id for b in registry.list_builds(state="deprecated")]
        assert deprecated == ["ka_v1.0.0"]


class TestRollback:
    def test_rollback_vuelve_al_build_previo(self, registry, published_build):
        registry.promote("ka_v1.0.0")
        manifest2, artifacts2 = _make_build("ka_v1.1.0")
        registry.publish(manifest2, artifacts2)
        registry.promote("ka_v1.1.0")

        target = registry.rollback()
        assert target == "ka_v1.0.0"
        assert registry.resolve()["manifest"]["build_id"] == "ka_v1.0.0"

    def test_rollback_sin_deprecados_rechazado(self, registry, published_build):
        registry.promote("ka_v1.0.0")
        with pytest.raises(RegistryError, match="rollback"):
            registry.rollback()


class TestIntegrity:
    def test_verify_integrity_ok(self, registry, published_build):
        assert registry.verify_integrity("ka_v1.0.0") == []

    def test_corrupcion_en_disco_detectada(self, registry, published_build):
        registry.promote("ka_v1.0.0")
        artifact_path = (
            registry.root / "builds" / "ka_v1.0.0" / "artifacts" / "alias_index.json"
        )
        artifact_path.write_bytes(b'{"aliases": {}}')

        errors = registry.verify_integrity("ka_v1.0.0")
        assert errors and "alias_index" in errors[0]

        with pytest.raises(IntegrityError, match="corrupto"):
            registry.resolve()

    def test_archivo_ausente_detectado(self, registry, published_build):
        artifact_path = (
            registry.root / "builds" / "ka_v1.0.0" / "artifacts" / "doc_roles.json"
        )
        artifact_path.unlink()
        errors = registry.verify_integrity("ka_v1.0.0")
        assert errors and "ausente" in errors[0]


class TestManifestYListado:
    def test_get_manifest_del_activo(self, registry, published_build):
        manifest, _ = published_build
        registry.promote("ka_v1.0.0")
        assert registry.get_manifest()["build_id"] == manifest["build_id"]

    def test_get_manifest_sin_activo_rechazado(self, registry):
        with pytest.raises(RegistryError, match="no hay build activo"):
            registry.get_manifest()

    def test_list_builds_estado_desconocido(self, registry):
        with pytest.raises(ValueError):
            registry.list_builds(state="purged")


class TestRetention:
    def _publish_and_promote(self, registry, build_id):
        manifest, artifacts = _make_build(build_id)
        registry.publish(manifest, artifacts)
        registry.promote(build_id)

    def test_deprecated_archivados_por_conteo(self, tmp_path):
        registry = ArtifactRegistry(
            root=tmp_path / "registry", retention={"deprecated_max_count": 1}
        )
        for i in range(4):
            self._publish_and_promote(registry, f"ka_v1.0.{i}")

        result = registry.apply_retention()
        assert registry.resolve()["manifest"]["build_id"] == "ka_v1.0.3"
        deprecated = [b.build_id for b in registry.list_builds(state="deprecated")]
        assert len(deprecated) == 1
        assert sorted(result["archived"]) == ["ka_v1.0.0", "ka_v1.0.1"]

    def test_archived_purgados_por_antiguedad(self, tmp_path):
        registry = ArtifactRegistry(
            root=tmp_path / "registry",
            retention={"deprecated_max_count": 1, "archived_max_days": 30},
        )
        for i in range(3):
            self._publish_and_promote(registry, f"ka_v1.0.{i}")
        registry.apply_retention()

        index_path = registry.root / "state" / "builds_index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        index["ka_v1.0.0"]["archived_at"] = old
        index_path.write_text(json.dumps(index), encoding="utf-8")

        result = registry.apply_retention()
        assert result["purged"] == ["ka_v1.0.0"]
        assert not (registry.root / "builds" / "ka_v1.0.0").exists()
        assert registry.resolve()["manifest"]["build_id"] == "ka_v1.0.2"
