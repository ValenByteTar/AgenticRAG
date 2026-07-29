"""Contrato Warm Artifacts (ADR-0018.1).

Schemas versionados en ``contract/<version>/`` y validador compartido
consumido por Builder, Registry y tests de contrato.
"""

from src.contract.validator import (
    CONTRACT_ROOT,
    DEFAULT_VERSION,
    declared_artifacts,
    validate_artifact,
    validate_build,
    validate_manifest,
)

__all__ = [
    "CONTRACT_ROOT",
    "DEFAULT_VERSION",
    "declared_artifacts",
    "validate_artifact",
    "validate_build",
    "validate_manifest",
]
