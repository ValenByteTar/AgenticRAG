"""Publication Protocol client (RES-002 §8.1, RES-001 §5.2).

El Builder no escribe archivos directamente. Publica a traves del Registry.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from src.artifact_registry.registry import ArtifactRegistry


class Publisher:
    """Cliente del Publication Protocol: publish + promote al Artifact Registry."""

    def __init__(self, registry: ArtifactRegistry):
        self.registry = registry

    def publish(self, manifest: Mapping[str, Any], artifacts: Mapping[str, Any]) -> str:
        """Publica un build al Registry (staging). Retorna build_id."""
        return self.registry.publish(manifest, artifacts)

    def promote(self, build_id: str, expected_contract_version: Optional[str] = None) -> None:
        """Promueve un build de staging a activo (swap atomico)."""
        self.registry.promote(build_id, expected_contract_version=expected_contract_version)

    def publish_and_promote(
        self,
        manifest: Mapping[str, Any],
        artifacts: Mapping[str, Any],
        expected_contract_version: Optional[str] = None,
    ) -> str:
        """Publica y promueve en un solo paso. Retorna build_id."""
        build_id = self.publish(manifest, artifacts)
        self.promote(build_id, expected_contract_version=expected_contract_version)
        return build_id
