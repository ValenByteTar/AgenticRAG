"""Validador compartido del contrato Warm (ADR-0018.1, RES-001 §5/§7, DEC-011).

Responsabilidades:

- Validar artifacts individuales contra su schema JSON (draft-07).
- Validar el manifest de build.
- Validar un build completo: schemas + integridad referencial entre artifacts
  (catalogo de predicados, entity_ids colgantes, doc_ids colgantes).

Quien lo consume:

- Builder: antes de publicar (ningun claim sale sin pasar validacion).
- Registry: en ``publish`` y ``promote``.
- Tests de contrato: ``tests/unit/test_contract_warm_v1.py``.

No valida checksums SHA-256 contra disco: eso es responsabilidad del Registry
(Integrity, RES-001 §5.6).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import jsonschema

CONTRACT_ROOT = Path(__file__).resolve().parents[2] / "contract"
DEFAULT_VERSION = "warm-v1"

_COMMON_SCHEMA = "common"
_MANIFEST_SCHEMA = "manifest"

_COMMON_REF_PREFIX = f"{_COMMON_SCHEMA}.schema.json#/definitions/"

# Artifacts declarados por version (DEC-011). El orden es solo documental.
_DECLARED_ARTIFACTS: Dict[str, List[str]] = {
    "warm-v1": [
        "canonical_entities",
        "alias_index",
        "entity_index",
        "doc_roles",
        "entity_relations",
        "retrieval_metadata",
        "predicate_catalog",
    ],
}


def declared_artifacts(version: str = DEFAULT_VERSION) -> List[str]:
    """Lista de artifacts declarados por una version del contrato."""
    try:
        return list(_DECLARED_ARTIFACTS[version])
    except KeyError:
        raise ValueError(f"contract version desconocida: {version}")


@lru_cache(maxsize=None)
def _load_schema(name: str, version: str) -> Dict[str, Any]:
    """Carga un schema y compone las referencias a ``common.schema.json``.

    Las referencias externas ``common.schema.json#/definitions/x`` se inlinan
    como ``#/definitions/x`` contra las definiciones del schema comun. Esto
    evita resolver URIs y mantiene el validador autocontenido.
    """
    path = CONTRACT_ROOT / version / f"{name}.schema.json"
    if not path.exists():
        raise ValueError(f"schema no encontrado: {path}")
    schema = json.loads(path.read_text(encoding="utf-8"))
    if name in (_COMMON_SCHEMA,):
        return schema
    common = _load_schema(_COMMON_SCHEMA, version)
    return _compose(schema, common.get("definitions", {}))


def _compose(node: Any, common_definitions: Mapping[str, Any]) -> Any:
    if isinstance(node, dict):
        out: Dict[str, Any] = {}
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str) and value.startswith(_COMMON_REF_PREFIX):
                out[key] = "#/definitions/" + value[len(_COMMON_REF_PREFIX):]
            elif key == "definitions":
                out[key] = value
            else:
                out[key] = _compose(value, common_definitions)
        out.setdefault("definitions", dict(common_definitions))
        return out
    if isinstance(node, list):
        return [_compose(item, common_definitions) for item in node]
    return node


def _schema_errors(schema: Mapping[str, Any], data: Any) -> List[str]:
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    result = []
    for error in errors:
        location = "/".join(str(p) for p in error.absolute_path) or "<root>"
        result.append(f"{location}: {error.message}")
    return result


def validate_artifact(
    name: str, data: Any, version: str = DEFAULT_VERSION
) -> List[str]:
    """Valida un artifact individual contra su schema. Retorna lista de errores."""
    if name not in declared_artifacts(version):
        return [f"artifact desconocido en {version}: {name}"]
    schema = _load_schema(name, version)
    return _schema_errors(schema, data)


def validate_manifest(manifest: Any, version: str = DEFAULT_VERSION) -> List[str]:
    """Valida un manifest de build contra su schema. Retorna lista de errores."""
    schema = _load_schema(_MANIFEST_SCHEMA, version)
    return _schema_errors(schema, manifest)


def validate_build(
    manifest: Mapping[str, Any],
    artifacts: Mapping[str, Any],
    version: str = DEFAULT_VERSION,
) -> List[str]:
    """Valida un build completo.

    1. Manifest contra schema.
    2. Todo artifact del manifest debe estar declarado en la version (DEC-011).
    3. Cada artifact contra su schema.
    4. Integridad referencial entre artifacts presentes y no vacios:
       - predicados de relations pertenecen al catalogo del build
       - ``entity_id`` de aliases existen en ``canonical_entities``
       - claves de ``entity_index`` existen en ``canonical_entities``
       - ``entity_ids`` de ``doc_roles`` existen en ``canonical_entities``
       - subject/object de relations existen en ``canonical_entities``
       - claves de ``retrieval_metadata`` existen en ``doc_roles``
    """
    errors: List[str] = []
    errors.extend(validate_manifest(manifest, version))

    declared = set(declared_artifacts(version))
    listed = set((manifest.get("artifacts") or {}).keys())
    for name in sorted(listed - declared):
        errors.append(f"manifest: artifact no declarado en {version}: {name}")

    for name in sorted(listed & declared):
        data = artifacts.get(name)
        if data is None:
            errors.append(f"build: artifact listado en manifest sin datos: {name}")
            continue
        for err in validate_artifact(name, data, version):
            errors.append(f"{name}: {err}")

    errors.extend(_cross_artifact_errors(artifacts))
    return errors


def _canonical_ids(artifacts: Mapping[str, Any]) -> Optional[set]:
    canonical = artifacts.get("canonical_entities")
    if not canonical:
        return None
    return {e.get("entity_id") for e in canonical.get("entities", []) if isinstance(e, dict)}


def _doc_role_ids(artifacts: Mapping[str, Any]) -> Optional[set]:
    doc_roles = artifacts.get("doc_roles")
    if not doc_roles:
        return None
    return set((doc_roles.get("docs") or {}).keys())


def _catalog_predicates(artifacts: Mapping[str, Any]) -> Optional[set]:
    catalog = artifacts.get("predicate_catalog")
    if not catalog:
        return None
    return {
        p.get("id") for p in catalog.get("predicates", []) if isinstance(p, dict)
    }


def _cross_artifact_errors(artifacts: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []

    canonical_ids = _canonical_ids(artifacts)
    doc_role_ids = _doc_role_ids(artifacts)
    predicates = _catalog_predicates(artifacts)

    relations = (artifacts.get("entity_relations") or {}).get("relations") or []
    if predicates is not None:
        for rel in relations:
            pred = rel.get("predicate")
            if pred and pred not in predicates:
                errors.append(
                    f"entity_relations: predicado fuera de catalogo: {pred} ({rel.get('relation_id')})"
                )

    if canonical_ids is not None:
        aliases = (artifacts.get("alias_index") or {}).get("aliases") or {}
        for alias, claim in aliases.items():
            entity_id = (claim or {}).get("entity_id")
            if entity_id and entity_id not in canonical_ids:
                errors.append(
                    f"alias_index: entity_id sin canonical entity: {entity_id} (alias '{alias}')"
                )

        entity_index = (artifacts.get("entity_index") or {}).get("entities") or {}
        for entity_id in entity_index.keys():
            if entity_id not in canonical_ids:
                errors.append(
                    f"entity_index: clave sin canonical entity: {entity_id}"
                )

        doc_roles = (artifacts.get("doc_roles") or {}).get("docs") or {}
        for doc_id, claim in doc_roles.items():
            for entity_id in (claim or {}).get("entity_ids") or []:
                if entity_id not in canonical_ids:
                    errors.append(
                        f"doc_roles: entity_id sin canonical entity: {entity_id} (doc '{doc_id}')"
                    )

        for rel in relations:
            for end in ("subject", "object"):
                entity_id = rel.get(end)
                if entity_id and entity_id not in canonical_ids:
                    errors.append(
                        f"entity_relations: {end} sin canonical entity: {entity_id} "
                        f"({rel.get('relation_id')})"
                    )

    if doc_role_ids is not None:
        retrieval = (artifacts.get("retrieval_metadata") or {}).get("docs") or {}
        for doc_id in retrieval.keys():
            if doc_id not in doc_role_ids:
                errors.append(
                    f"retrieval_metadata: doc sin doc_role: {doc_id}"
                )

    return errors
