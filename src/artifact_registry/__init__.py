"""Artifact Registry (ADR-0018, RES-001 §5).

Single publication authority para Warm Artifacts. El Builder publica via
Publication Protocol; el Consumer resuelve via Resolution Protocol. Ninguno
accede a archivos directamente.
"""

from src.artifact_registry.registry import (
    ArtifactRegistry,
    BuildInfo,
    BuildNotFoundError,
    IntegrityError,
    RegistryError,
    ValidationError,
    compute_checksums,
)

__all__ = [
    "ArtifactRegistry",
    "BuildInfo",
    "BuildNotFoundError",
    "IntegrityError",
    "RegistryError",
    "ValidationError",
    "compute_checksums",
]
