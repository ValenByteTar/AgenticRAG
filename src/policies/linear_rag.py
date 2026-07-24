"""
Policy lineal (Fase 1 + Fase 6): classify -> memory_read -> planner
-> entity_expansion -> retrieve -> build_context
-> assess -> generate -> verify -> finalize_turn -> done.

Una policy = una decision (ADR-0013). No ejecuta capabilities.
AssessGatePolicy (registrada antes) intercepta assess fallido.
VerifyRepairPolicy (registrada antes) intercepta verify fallido.
"""

from __future__ import annotations

from typing import Optional

from src.kernel.state import ActionDecision, ExecutionState


class LinearRagPolicy:
    """
    Secuencia fija para paridad con HybridRAG lineal + ASSESS + memory read
    + planner + entity expansion (Fase 6).
    No conoce implementaciones; solo emite capability_ref por nombre.
    """

    name = "linear_rag"

    def decide(self, state: ExecutionState) -> Optional[ActionDecision]:
        if state.done:
            return ActionDecision(action="terminate", terminate=True, reason="already_done")

        if state.answer and state.metadata.get("finalized"):
            return ActionDecision(action="done", terminate=True, reason="answer_ready")

        # OOD detectado en classify: decline sin retrieval
        if state.metadata.get("out_of_domain") and state.metadata.get("classified"):
            return ActionDecision(
                action="decline",
                terminate=True,
                reason="out_of_domain",
                params={
                    "message": state.metadata.get(
                        "ood_message",
                        "Lo siento, esta consulta esta fuera del alcance de mi especialidad.",
                    )
                },
            )

        if not state.metadata.get("classified"):
            return ActionDecision(
                action="invoke",
                capability_ref="classify",
                reason="need_classify",
            )

        if not state.metadata.get("memory_read"):
            return ActionDecision(
                action="invoke",
                capability_ref="memory_read",
                reason="need_memory_read",
            )

        # Fase 6: planner antes de retrieval
        if not state.metadata.get("planned"):
            return ActionDecision(
                action="invoke",
                capability_ref="planner",
                reason="need_planner",
            )

        # Fase 6: entity expansion antes de retrieval
        if not state.metadata.get("entity_expansion"):
            return ActionDecision(
                action="invoke",
                capability_ref="entity_expansion",
                reason="need_entity_expansion",
            )

        if not state.results:
            # F6: if entities detected (post entity_expansion), use two-stage on first pass
            entities = list(state.entities or state.metadata.get("expanded_entities") or [])
            if entities and not state.metadata.get("two_stage_executed"):
                return ActionDecision(
                    action="invoke",
                    capability_ref="two_stage_retrieval",
                    reason="need_two_stage_retrieval (entities detected)",
                    params={"entities": entities},
                )
            # F6: if two-stage produced no results, fall back to plain retrieval
            if state.metadata.get("two_stage_executed") and not state.metadata.get("retrieval_executed"):
                return ActionDecision(
                    action="invoke",
                    capability_ref="retrieval",
                    reason="need_retrieval (two-stage fallback)",
                )
            # F6: both two-stage and retrieval tried with no results — proceed to generation with empty
            if state.metadata.get("retrieval_executed") and not state.results:
                state.metadata["retrieval_empty"] = True
                return ActionDecision(
                    action="invoke",
                    capability_ref="build_context",
                    reason="need_context (empty results)",
                )
            return ActionDecision(
                action="invoke",
                capability_ref="retrieval",
                reason="need_retrieval",
            )

        if not state.context and state.results:
            return ActionDecision(
                action="invoke",
                capability_ref="build_context",
                reason="need_context",
            )

        if state.context and not state.metadata.get("assessed"):
            return ActionDecision(
                action="invoke",
                capability_ref="assess",
                reason="need_assess",
            )

        if not state.answer:
            if state.use_llm or state.results:
                return ActionDecision(
                    action="invoke",
                    capability_ref="generation",
                    reason="need_generation" if state.use_llm else "fallback_generation",
                )

        # Fase 4: verify despues de generation, antes de finalize
        if state.answer and not state.metadata.get("verified"):
            return ActionDecision(
                action="invoke",
                capability_ref="verify",
                reason="need_verify",
            )

        # Si verify paso, continuar a finalize
        if state.answer and state.metadata.get("verified"):
            verify_sig = state.latest_signal("verify")
            if verify_sig is not None and verify_sig.passed is False:
                # VerifyRepairPolicy deberia haber interceptado antes
                # Si llegamos aqui, es un fallback de seguridad
                return ActionDecision(
                    action="decline",
                    terminate=True,
                    reason="linear_rag: verify fallo sin repair",
                    params={"message": "No se pudo verificar la respuesta."},
                )

        if state.answer and not state.metadata.get("finalized"):
            return ActionDecision(
                action="invoke",
                capability_ref="finalize_turn",
                reason="need_finalize",
            )

        return ActionDecision(action="terminate", terminate=True, reason="linear_complete")
