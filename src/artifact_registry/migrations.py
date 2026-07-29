"""Migrations del contrato Warm (RES-001 §5.7, DEC-012.5).

Cuando el contrato evoluciona (``warm-v1`` -> ``warm-v2``), una migration
transforma un build antiguo al nuevo schema sin recompilar desde documentos.

Las migrations son:

- **declarativas**: una funcion registrada por par ``(from_version, to_version)``
  que transforma ``(manifest, artifacts)``.
- **validadas**: el resultado se revalida con ``validate_build`` de la version
  destino antes de aceptarse.
- **versionadas**: cada migration declara explicitamente su origen y destino.
- **opcionales**: un build siempre puede recompilarse desde documentos en
  lugar de migrarse.

En ``warm-v1`` el registro esta vacio: no existe version destino todavia.
El framework se implementa ahora para que E8 (o quien introduzca warm-v2)
solo tenga que registrar la transformacion.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Tuple

from src.contract.validator import validate_build

Migration = Callable[[Dict[str, Any], Dict[str, Any]], Tuple[Dict[str, Any], Dict[str, Any]]]

_MIGRATIONS: Dict[Tuple[str, str], Migration] = {}


def register(from_version: str, to_version: str) -> Callable[[Migration], Migration]:
    """Registra una migration para el par (from_version, to_version)."""

    def decorator(fn: Migration) -> Migration:
        _MIGRATIONS[(from_version, to_version)] = fn
        return fn

    return decorator


def _find_path(from_version: str, to_version: str) -> List[Tuple[str, str]]:
    """BFS sobre el grafo de migrations. Lista de pasos (from, to)."""
    if from_version == to_version:
        return []
    queue: List[Tuple[str, List[Tuple[str, str]]]] = [(from_version, [])]
    visited = {from_version}
    while queue:
        current, path = queue.pop(0)
        for (src, dst) in _MIGRATIONS:
            if src != current or dst in visited:
                continue
                # pragma: no cover
            next_path = path + [(src, dst)]
            if dst == to_version:
                return next_path
            visited.add(dst)
            queue.append((dst, next_path))
    raise ValueError(f"no hay migration path {from_version} -> {to_version}")


def migrate(
    manifest: Mapping[str, Any],
    artifacts: Mapping[str, Any],
    to_version: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Aplica la cadena de migrations y revalida contra la version destino.

    Retorna ``(manifest, artifacts)`` migrados. Lanza ``ValueError`` si no hay
    path o si el resultado no valida contra el contrato destino.
    """
    new_manifest = dict(manifest)
    new_artifacts = dict(artifacts)
    for src, dst in _find_path(new_manifest["contract_version"], to_version):
        new_manifest, new_artifacts = _MIGRATIONS[(src, dst)](new_manifest, new_artifacts)
        new_manifest["contract_version"] = dst

    errors = validate_build(new_manifest, new_artifacts, version=to_version)
    if errors:
        raise ValueError(
            f"build migrado a {to_version} no valida: " + "; ".join(errors)
        )
    return new_manifest, new_artifacts
