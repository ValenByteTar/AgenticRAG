"""Artifact Registry — componente con identidad propia (RES-001 §5, DEC-012).

Interfaz de 7 operaciones:

- ``publish``: entrega un build (artifacts + manifest) -> staging.
- ``promote``: swap atomico del puntero al build activo.
- ``resolve``: devuelve manifest + artifacts del build activo.
- ``rollback``: apunta el puntero al build deprecado mas reciente.
- ``verify_integrity``: valida checksums SHA-256 de artifacts.
- ``list_builds``: lista builds por estado.
- ``get_manifest``: manifest de un build especifico o del activo.

Storage backend (DEC-012): filesystem versionado, puntero atomico via
``os.replace``, builds inmutables, estado en JSON.

Lifecycle (RES-001 §5.8):

    staging -> promoted -> deprecated -> archived -> purged

``archived`` y ``purged`` los aplica ``apply_retention`` (funcion de operador,
no parte de la interfaz de 7).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from src.contract.validator import declared_artifacts, validate_build, validate_manifest

STATE_STAGING = "staging"
STATE_PROMOTED = "promoted"
STATE_DEPRECATED = "deprecated"
STATE_ARCHIVED = "archived"

_STATES = (STATE_STAGING, STATE_PROMOTED, STATE_DEPRECATED, STATE_ARCHIVED)


class RegistryError(Exception):
    """Error base del Artifact Registry."""


class ValidationError(RegistryError):
    """El build no paso validacion de contrato o integridad."""


class IntegrityError(RegistryError):
    """Checksums no coinciden."""


class BuildNotFoundError(RegistryError):
    """Build inexistente en el Registry."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_bytes(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2).encode("utf-8")


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def compute_checksums(artifacts: Mapping[str, Any]) -> Dict[str, str]:
    """SHA-256 por artifact sobre serializacion canonica (DEC-012.3).

    Lo usa el Builder para declarar checksums en el manifest; el Registry
    verifica los bytes escritos contra esos valores.
    """
    return {name: _sha256_bytes(_canonical_bytes(data)) for name, data in artifacts.items()}


def _atomic_write(path: Path, content: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(content)
    os.replace(tmp, path)


@dataclass
class BuildInfo:
    build_id: str
    state: str
    contract_version: Optional[str] = None
    created_at: Optional[str] = None
    promoted_at: Optional[str] = None
    deprecated_at: Optional[str] = None
    archived_at: Optional[str] = None


class ArtifactRegistry:
    """Single publication authority para Warm Artifacts."""

    def __init__(
        self,
        root: Path | str,
        supported_versions: tuple = ("warm-v1",),
        retention: Optional[Mapping[str, Any]] = None,
    ):
        self.root = Path(root)
        self.supported_versions = tuple(supported_versions)
        self.retention = {
            "deprecated_max_count": 5,
            "archived_max_days": 30,
            **(retention or {}),
        }
        (self.root / "builds").mkdir(parents=True, exist_ok=True)
        (self.root / "state").mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ paths

    def _build_dir(self, build_id: str) -> Path:
        return self.root / "builds" / build_id

    @property
    def _index_path(self) -> Path:
        return self.root / "state" / "builds_index.json"

    @property
    def _active_path(self) -> Path:
        return self.root / "state" / "active.json"

    # ------------------------------------------------------------------ state

    def _load_index(self) -> Dict[str, Any]:
        if not self._index_path.exists():
            return {}
        return json.loads(self._index_path.read_text(encoding="utf-8"))

    def _save_index(self, index: Mapping[str, Any]) -> None:
        _atomic_write(self._index_path, _canonical_bytes(index))

    def _load_active(self) -> Optional[Dict[str, Any]]:
        if not self._active_path.exists():
            return None
        return json.loads(self._active_path.read_text(encoding="utf-8"))

    def _set_active(self, build_id: str) -> None:
        _atomic_write(
            self._active_path,
            _canonical_bytes({"build_id": build_id, "promoted_at": _now()}),
        )

    def _set_state(self, index: Dict[str, Any], build_id: str, state: str) -> None:
        entry = index[build_id]
        entry["state"] = state
        entry[f"{state}_at"] = _now()

    def _require_build(self, build_id: str) -> None:
        if not (self._build_dir(build_id) / "manifest.json").exists():
            raise BuildNotFoundError(f"build inexistente: {build_id}")

    # ------------------------------------------------------------- 1. publish

    def publish(
        self, manifest: Mapping[str, Any], artifacts: Mapping[str, Any]
    ) -> str:
        """Entrega un build al Registry (Publication Protocol, RES-001 §5.2).

        Valida contrato (schemas + integridad referencial), compatibilidad
        (``contract_version`` soportada) e integridad (checksums del manifest
        contra los bytes canonicos). Si pasa, el build queda en ``staging``.
        """
        errors: List[str] = []

        errors.extend(validate_manifest(manifest))
        version = manifest.get("contract_version")
        if version and version not in self.supported_versions:
            errors.append(f"contract_version no soportada: {version}")
        if not errors:
            errors.extend(validate_build(manifest, artifacts, version=version))

        if not errors:
            computed = compute_checksums(artifacts)
            for name, entry in (manifest.get("artifacts") or {}).items():
                declared = (entry or {}).get("sha256")
                if name in computed and declared and declared != computed[name]:
                    errors.append(
                        f"integrity: checksum declarado no coincide para {name}"
                    )

        if errors:
            raise ValidationError("; ".join(errors))

        build_id = manifest["build_id"]
        if (self._build_dir(build_id) / "manifest.json").exists():
            raise RegistryError(f"build ya publicado: {build_id}")

        build_dir = self._build_dir(build_id)
        artifacts_dir = build_dir / "artifacts"
        artifacts_dir.mkdir(parents=True)
        for name, data in artifacts.items():
            _atomic_write(artifacts_dir / f"{name}.json", _canonical_bytes(data))
        _atomic_write(build_dir / "manifest.json", _canonical_bytes(dict(manifest)))

        index = self._load_index()
        index[build_id] = {
            "state": STATE_STAGING,
            "contract_version": version,
            "created_at": _now(),
        }
        self._save_index(index)
        return build_id

    # ------------------------------------------------------------- 2. promote

    def promote(
        self, build_id: str, expected_contract_version: Optional[str] = None
    ) -> None:
        """Swap atomico del puntero al build activo (RES-001 §5.2 paso 5).

        Requiere build en ``staging``. Revalida integridad antes del swap.
        Si el Consumer espera otra ``contract_version``, se rechaza (RES-001 §5.4).
        El build activo anterior pasa a ``deprecated``.
        """
        self._require_build(build_id)
        index = self._load_index()
        entry = index.get(build_id)
        if entry is None:
            raise BuildNotFoundError(f"build no indexado: {build_id}")
        if entry["state"] != STATE_STAGING:
            raise RegistryError(
                f"promote requiere staging; build {build_id} esta en {entry['state']}"
            )

        manifest = self.get_manifest(build_id)
        if expected_contract_version and manifest["contract_version"] != expected_contract_version:
            raise ValidationError(
                f"compatibility: consumer espera {expected_contract_version}, "
                f"build declara {manifest['contract_version']}"
            )
        integrity_errors = self.verify_integrity(build_id)
        if integrity_errors:
            raise IntegrityError("; ".join(integrity_errors))

        active = self._load_active()
        if active and active["build_id"] in index:
            self._set_state(index, active["build_id"], STATE_DEPRECATED)

        self._set_state(index, build_id, STATE_PROMOTED)
        self._set_active(build_id)
        self._save_index(index)

    # ------------------------------------------------------------- 3. resolve

    def resolve(self) -> Dict[str, Any]:
        """Devuelve manifest + artifacts del build activo (Resolution Protocol).

        Valida integridad al cargar (RES-001 §5.3 paso 3). No hay silencio
        ante corrupcion (RES-001 §5.6).
        """
        active = self._load_active()
        if active is None:
            raise RegistryError("no hay build activo")
        build_id = active["build_id"]
        integrity_errors = self.verify_integrity(build_id)
        if integrity_errors:
            raise IntegrityError(
                f"build activo {build_id} corrupto: " + "; ".join(integrity_errors)
            )
        return {
            "manifest": self.get_manifest(build_id),
            "artifacts": self._load_artifacts(build_id),
        }

    # ------------------------------------------------------------ 4. rollback

    def rollback(self) -> str:
        """Apunta el puntero al build deprecado mas reciente (RES-001 §5.5).

        Operacion instantanea, sin recompilar. El build activo actual pasa a
        ``deprecated``.
        """
        index = self._load_index()
        active = self._load_active()
        if active is None:
            raise RegistryError("no hay build activo")

        candidates = [
            (bid, entry)
            for bid, entry in index.items()
            if entry["state"] == STATE_DEPRECATED and bid != active["build_id"]
        ]
        if not candidates:
            raise RegistryError("no hay build deprecado para rollback")

        target_id, _ = max(
            candidates, key=lambda item: item[1].get("promoted_at") or ""
        )
        self._set_state(index, active["build_id"], STATE_DEPRECATED)
        self._set_state(index, target_id, STATE_PROMOTED)
        self._set_active(target_id)
        self._save_index(index)
        return target_id

    # ----------------------------------------------------- 5. verify_integrity

    def verify_integrity(self, build_id: Optional[str] = None) -> List[str]:
        """Re-hashea los artifacts en disco contra los checksums del manifest."""
        if build_id is None:
            active = self._load_active()
            if active is None:
                raise RegistryError("no hay build activo")
            build_id = active["build_id"]
        self._require_build(build_id)

        manifest = self.get_manifest(build_id)
        artifacts_dir = self._build_dir(build_id) / "artifacts"
        errors: List[str] = []
        for name, entry in (manifest.get("artifacts") or {}).items():
            path = artifacts_dir / f"{name}.json"
            if not path.exists():
                errors.append(f"{name}: archivo ausente")
                continue
            actual = _sha256_bytes(path.read_bytes())
            declared = (entry or {}).get("sha256")
            if declared and actual != declared:
                errors.append(f"{name}: checksum no coincide")
        return errors

    # ------------------------------------------------------------ 6. list_builds

    def list_builds(self, state: Optional[str] = None) -> List[BuildInfo]:
        """Lista builds disponibles, opcionalmente filtrados por estado."""
        if state and state not in _STATES:
            raise ValueError(f"estado desconocido: {state}")
        index = self._load_index()
        infos = [
            BuildInfo(
                build_id=bid,
                state=entry["state"],
                contract_version=entry.get("contract_version"),
                created_at=entry.get("created_at"),
                promoted_at=entry.get("promoted_at"),
                deprecated_at=entry.get("deprecated_at"),
                archived_at=entry.get("archived_at"),
            )
            for bid, entry in index.items()
            if state is None or entry["state"] == state
        ]
        return sorted(infos, key=lambda info: info.created_at or "")

    # ----------------------------------------------------------- 7. get_manifest

    def get_manifest(self, build_id: Optional[str] = None) -> Dict[str, Any]:
        """Manifest de un build especifico o del activo."""
        if build_id is None:
            active = self._load_active()
            if active is None:
                raise RegistryError("no hay build activo")
            build_id = active["build_id"]
        path = self._build_dir(build_id) / "manifest.json"
        if not path.exists():
            raise BuildNotFoundError(f"build inexistente: {build_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------ internals

    def _load_artifacts(self, build_id: str) -> Dict[str, Any]:
        manifest = self.get_manifest(build_id)
        artifacts_dir = self._build_dir(build_id) / "artifacts"
        loaded: Dict[str, Any] = {}
        for name in (manifest.get("artifacts") or {}).keys():
            path = artifacts_dir / f"{name}.json"
            if path.exists():
                loaded[name] = json.loads(path.read_text(encoding="utf-8"))
        return loaded

    # ------------------------------------------------------------- retention

    def apply_retention(self) -> Dict[str, List[str]]:
        """Funcion de operador (DEC-012.4), fuera de la interfaz de 7.

        - ``deprecated`` -> ``archived``: cuando superan ``deprecated_max_count``
          (se archivan los mas antiguos primero).
        - ``archived`` -> ``purged``: cuando superan ``archived_max_days``
          (se elimina el build del disco y del indice).

        Nunca toca el build activo ni el candidato inmediato de rollback.
        """
        index = self._load_index()
        active = self._load_active()
        active_id = active["build_id"] if active else None

        archived: List[str] = []
        purged: List[str] = []

        deprecated = sorted(
            (
                (bid, e.get("promoted_at") or "")
                for bid, e in index.items()
                if e["state"] == STATE_DEPRECATED and bid != active_id
            ),
            key=lambda item: item[1],
        )
        keep = max(self.retention["deprecated_max_count"], 1)
        for bid, _ in deprecated[: max(len(deprecated) - keep, 0)]:
            self._set_state(index, bid, STATE_ARCHIVED)
            archived.append(bid)

        cutoff = datetime.now(timezone.utc) - timedelta(
            days=self.retention["archived_max_days"]
        )
        for bid, entry in list(index.items()):
            if entry["state"] != STATE_ARCHIVED or bid == active_id:
                continue
            archived_at = entry.get("archived_at")
            if archived_at and datetime.fromisoformat(archived_at) < cutoff:
                shutil.rmtree(self._build_dir(bid), ignore_errors=True)
                del index[bid]
                purged.append(bid)

        self._save_index(index)
        return {"archived": archived, "purged": purged}
