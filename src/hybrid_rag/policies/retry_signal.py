"""
Policy: retry signal observador (ADR-0013, ADR-0006).

Fase 2: observa senales blandas de ASSESS (entity_coverage_low,
source_diversity_low) y emite decision de retry con params alternativos.
No ejecuta retry directamente; el Controller invoca la capability indicada.

Fase 3: multi-retry con budget.
- Retry 1: retrieval con relax_entity_filter + boost_diversity
- Retry 2: two_stage_retrieval con entity-focused search
Respeta max_iterations y max_llm_calls del state.

Si el assess fallo, AssessGatePolicy ya declino antes.
"""

from __future__ import annotations

from typing import Optional

from src.kernel.state import ActionDecision, ExecutionState


class RetrySignalPolicy:
    """
    Policy de retry basada en senales blandas de ASSESS.

    Decide re-retrieve con params alternativos si:
    - assess paso (passed=True)
    - entity_coverage_low o source_diversity_low
    - no ha habido retry previo (metadata.retry_count < max_retries)
    - presupuesto no agotado
    """

    name = "retry_signal"

    def __init__(self, max_retries: int = 2) -> None:
        self._max_retries = int(max_retries)

    def decide(self, state: ExecutionState) -> Optional[ActionDecision]:
        if state.done or state.answer:
            return None

        sig = state.latest_signal("assess")
        if sig is None or sig.passed is not True:
            return None

        retry_count = int(state.metadata.get("retry_count", 0) or 0)
        if retry_count >= self._max_retries:
            return None

        if state.budget_exhausted():
            return None

        meta = sig.metadata or {}
        needs_retry = False
        reason_parts = []

        if meta.get("entity_coverage_low"):
            needs_retry = True
            ratio = meta.get("entity_coverage_ratio", 0.0)
            reason_parts.append(f"entity_coverage={ratio:.2f}")

        if meta.get("source_diversity_low"):
            needs_retry = True
            diversity = meta.get("source_diversity", 0)
            reason_parts.append(f"source_diversity={diversity}")

        if not needs_retry:
            return None

        next_retry = retry_count + 1

        if next_retry == 1:
            return ActionDecision(
                action="retry",
                capability_ref="retrieval",
                reason=f"retry_signal[1]: {'; '.join(reason_parts)}",
                params={
                    "retry_count": next_retry,
                    "relax_entity_filter": True,
                    "boost_diversity": True,
                },
            )

        # Retry 2+: two-stage entity search
        entities = list(state.entities or [])
        if not entities:
            cls_meta = state.metadata.get("classification") or {}
            entities = list(cls_meta.get("entities") or [])

        if not entities:
            return ActionDecision(
                action="retry",
                capability_ref="retrieval",
                reason=f"retry_signal[{next_retry}]: {'; '.join(reason_parts)} (no entities, fallback retrieval)",
                params={
                    "retry_count": next_retry,
                    "relax_entity_filter": True,
                    "boost_diversity": True,
                    "widen_top_k": True,
                },
            )

        return ActionDecision(
            action="retry",
            capability_ref="two_stage_retrieval",
            reason=f"retry_signal[{next_retry}]: {'; '.join(reason_parts)} (two-stage entity)",
            params={
                "retry_count": next_retry,
                "entities": entities,
                "entity_focused": True,
            },
        )
