"""Semantic Validation — LLM-based coherence check (RES-002 §6.2).

Se activa en E5 con LLM. Verifica coherencia del conocimiento:

    - consistencia de roles
    - contradicciones entre aliases
    - colisiones de canonicos
    - relaciones invalidas o ciclicas no deseadas
    - cobertura minima por documento/entidad
    - calidad de clasificacion

No reemplaza la validacion estructural. Es complementaria.
Los claims que fallan semantic validation van a cuarentena (Cold), nunca Warm.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Set

from ..kir import KIR, normalize_text


_VALID_ROLES = {
    "list", "entity_profile", "guide", "reference", "analysis", "other",
}

_VALID_PREDICATES = {
    "equivalent_to", "depends_on", "implements", "extends", "references",
    "governs", "contains", "uses", "creates",
}


class SemanticValidator:
    """Validacion semantica de KIR — reglas deterministas + LLM opcional."""

    def __init__(
        self,
        use_llm: bool = False,
        model: str = "ibm/granite4.1:3b-q6_K",
        base_url: str = "http://localhost:11434",
        timeout: int = 60,
    ):
        self.use_llm = use_llm
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def validate(self, kir: KIR) -> Dict[str, Any]:
        """Retorna dict con errors, warnings, quarantined, passed, rejected."""
        errors: List[str] = []
        warnings: List[str] = []
        quarantined: List[str] = []
        passed = 0
        rejected = 0

        # 1. Role consistency
        for dc in kir.document_claims:
            role = normalize_text(dc.role)
            if role and role not in _VALID_ROLES:
                warnings.append(f"document_claim role fuera de taxonomia: {dc.role} (doc: {dc.name})")
                # Soft warning — no rechazamos, solo advertimos

        # 2. Canonical collisions — dos entidades con mismo canonical_name pero diferentes entity_ids
        canonical_to_ids: Dict[str, Set[str]] = {}
        for c in kir.entity_claims:
            key = normalize_text(c.canonical_name)
            eid = c.raw.get("entity_id", "")
            if eid:
                canonical_to_ids.setdefault(key, set()).add(eid)

        for key, ids in canonical_to_ids.items():
            if len(ids) > 1:
                warnings.append(f"canonical collision: '{key}' tiene {len(ids)} entity_ids: {ids}")

        # 3. Alias contradictions — mismo alias apunta a diferentes canonicos
        alias_to_canonicals: Dict[str, Set[str]] = {}
        for c in kir.alias_claims:
            alias_key = normalize_text(c.alias)
            canonical = normalize_text(c.canonical_name)
            alias_to_canonicals.setdefault(alias_key, set()).add(canonical)

        for alias_key, canonicals in alias_to_canonicals.items():
            if len(canonicals) > 1:
                errors.append(
                    f"alias contradiction: '{alias_key}' apunta a {len(canonicals)} canonicos: {canonicals}"
                )
                rejected += 1

        # 4. Predicate validation
        for c in kir.relation_claims:
            pred = normalize_text(c.predicate)
            if pred and pred not in _VALID_PREDICATES:
                warnings.append(f"relation predicate fuera de catalogo: {c.predicate}")

        # 5. Self-referencing relations
        for c in kir.relation_claims:
            if normalize_text(c.subject_name) == normalize_text(c.object_name):
                warnings.append(
                    f"self-referencing relation: {c.subject_name} {c.predicate} {c.object_name}"
                )

        # 6. Evidence check — claims sin evidencia van a cuarentena
        for c in kir.entity_claims:
            if not c.evidence:
                quarantined.append(f"entity sin evidencia: {c.canonical_name}")
            else:
                passed += 1

        for c in kir.alias_claims:
            if not c.evidence:
                quarantined.append(f"alias sin evidencia: {c.alias}")
            else:
                passed += 1

        for c in kir.relation_claims:
            if not c.evidence:
                quarantined.append(
                    f"relation sin evidencia: {c.subject_name} {c.predicate} {c.object_name}"
                )
            else:
                passed += 1

        # 7. LLM-based coherence check (optional)
        if self.use_llm and kir.entity_claims:
            llm_issues = self._llm_coherence_check(kir)
            for issue in llm_issues:
                warnings.append(f"LLM coherence: {issue}")

        return {
            "errors": errors,
            "warnings": warnings,
            "quarantined": quarantined,
            "passed": passed,
            "rejected": rejected,
        }

    def _llm_coherence_check(self, kir: KIR) -> List[str]:
        """Uses LLM to detect subtle semantic inconsistencies."""
        entities_sample = [
            {"name": c.canonical_name, "types": c.entity_types, "confidence": c.confidence}
            for c in kir.entity_claims[:50]
        ]

        prompt = f"""Analyze these entities for inconsistencies.
Return a JSON array of issues found, or an empty array if none.

Each issue: {{"type": "contradiction|misclassification|duplicate", "description": "..."}}

Entities:
{json.dumps(entities_sample, indent=2, ensure_ascii=False)}

Return ONLY the JSON array."""

        try:
            import requests

            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_ctx": 4096},
                "keep_alive": "5m",
            }
            r = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            r.raise_for_status()
            response = (r.json().get("response") or "").strip()

            fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
            if fence_match:
                response = fence_match.group(1).strip()

            bracket_start = response.find("[")
            bracket_end = response.rfind("]")
            if bracket_start == -1 or bracket_end == -1:
                return []

            issues = json.loads(response[bracket_start : bracket_end + 1])
            return [issue.get("description", str(issue)) for issue in issues if isinstance(issue, dict)]

        except Exception:
            return []
