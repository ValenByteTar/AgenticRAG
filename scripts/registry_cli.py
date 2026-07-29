"""CLI de operador del Artifact Registry (RES-001 §5, DEC-012).

Uso:

    python scripts/registry_cli.py publish <build_dir> [--root <path>]
    python scripts/registry_cli.py promote <build_id> [--expect warm-v1]
    python scripts/registry_cli.py resolve
    python scripts/registry_cli.py rollback
    python scripts/registry_cli.py list [--state staging]
    python scripts/registry_cli.py verify [build_id]
    python scripts/registry_cli.py retention

`<build_dir>` debe contener `manifest.json` y un subdirectorio `artifacts/`
con un `<artifact>.json` por entrada del manifest.

El root por defecto se lee de `config.yaml` -> `knowledge_registry.root`
(fallback: `./artifacts_registry`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.artifact_registry import ArtifactRegistry, RegistryError


def _default_root() -> Path:
    config_path = Path("config.yaml")
    if config_path.exists():
        try:
            import yaml

            config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            root = (config.get("knowledge_registry") or {}).get("root")
            if root:
                return Path(root)
        except Exception:
            pass
    return Path("artifacts_registry")


def _load_build_dir(build_dir: Path):
    manifest_path = build_dir / "manifest.json"
    if not manifest_path.exists():
        raise RegistryError(f"manifest.json no encontrado en {build_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = {}
    for name in (manifest.get("artifacts") or {}).keys():
        artifact_path = build_dir / "artifacts" / f"{name}.json"
        if not artifact_path.exists():
            raise RegistryError(f"artifact faltante en {build_dir}: {name}.json")
        artifacts[name] = json.loads(artifact_path.read_text(encoding="utf-8"))
    return manifest, artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description="Artifact Registry CLI")
    parser.add_argument("--root", type=Path, default=None, help="registry root")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("publish", help="entrega un build a staging")
    p.add_argument("build_dir", type=Path)

    p = sub.add_parser("promote", help="activa un build en staging")
    p.add_argument("build_id")
    p.add_argument("--expect", dest="expected", default=None, help="contract_version esperada")

    sub.add_parser("resolve", help="muestra el build activo")
    sub.add_parser("rollback", help="vuelve al build deprecado mas reciente")

    p = sub.add_parser("list", help="lista builds")
    p.add_argument("--state", default=None)

    p = sub.add_parser("verify", help="verifica checksums de un build")
    p.add_argument("build_id", nargs="?", default=None)

    sub.add_parser("retention", help="aplica politica de retencion")

    args = parser.parse_args()
    root = args.root or _default_root()
    registry = ArtifactRegistry(root=root)

    try:
        if args.command == "publish":
            manifest, artifacts = _load_build_dir(args.build_dir)
            build_id = registry.publish(manifest, artifacts)
            print(f"published: {build_id} (staging)")

        elif args.command == "promote":
            registry.promote(args.build_id, expected_contract_version=args.expected)
            print(f"promoted: {args.build_id}")

        elif args.command == "resolve":
            resolved = registry.resolve()
            manifest = resolved["manifest"]
            print(f"active: {manifest['build_id']} ({manifest['contract_version']})")
            for name in resolved["artifacts"]:
                print(f"  - {name}")

        elif args.command == "rollback":
            target = registry.rollback()
            print(f"rollback -> {target}")

        elif args.command == "list":
            for info in registry.list_builds(state=args.state):
                print(f"{info.build_id}\t{info.state}\t{info.contract_version}")

        elif args.command == "verify":
            errors = registry.verify_integrity(args.build_id)
            if errors:
                for error in errors:
                    print(f"ERROR: {error}")
                return 1
            print("integrity OK")

        elif args.command == "retention":
            result = registry.apply_retention()
            print(f"archived: {result['archived']}")
            print(f"purged: {result['purged']}")

    except RegistryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
