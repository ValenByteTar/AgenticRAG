"""
Policy: verify repair (ADR-0013, ADR-0006).

Fase 4: observa la senal VERIFY. Si fallo y hay presupuesto de repair,
decide re-generar con hint de reparacion. Si el presupuesto de repair
se agoto, decide decline.

Orden de prioridad: despues de AssessGatePolicy y RetrySignalPolicy,
antes de LinearRagPolicy.
"""

from __future__ import annotations

from typing import Optional

from src.kernel.state import ActionDecision, ExecutionState

_DEFAULT_DECLINE = (
    "No se pudo generar una respuesta soportada por la evidencia disponible."
)

_DEFAULT_REPAIR_HINT = (
    "REPARACION REQUERIDA: Tu respuesta anterior no esta suficientemente "
    "soportada por el contexto proporcionado.\n"
    "Instrucciones estrictas:\n"
    "1. Responde UNICAMENTE con informacion presente en el contexto.\n"
    "2. No uses conocimiento externo ni generalidades.\n"
    "3. Si el contexto no contiene la respuesta, di 'no hay informacion suficiente'.\n"
    "4. Cita la fuente usando [N] donde N es el numero de documento en el contexto."
)


class VerifyRepairPolicy:
    """
    Policy de reparacion basada en senal VERIFY.

    Decide re-generar si:
    - verify fallo (passed=False)
    - repair_count < max_repairs
    - presupuesto no agotado

    Decide decline si:
    - verify fallo y repair_count >= max_repairs
    """

    name = "verify_repair"

    def __init__(
        self,
        max_repairs: int = 1,
        decline_message: str = _DEFAULT_DECLINE,
        repair_hint: str = _DEFAULT_REPAIR_HINT,
    ) -> None:
        self._max_repairs = int(max_repairs)
        self._decline_message = decline_message
        self._repair_hint = repair_hint

    def decide(self, state: ExecutionState) -> Optional[ActionDecision]:
        if state.done:
            return None

        # Solo actua si ya se corrio verify
        if not state.metadata.get("verified"):
            return None

        sig = state.latest_signal("verify")
        if sig is None:
            return None

        # Si verify paso, no hay nada que hacer
        if sig.passed is not False:
            return None

        repair_count = int(state.metadata.get("repair_count", 0) or 0)

        # Presupuesto de repair agotado -> decline
        if repair_count >= self._max_repairs:
            return ActionDecision(
                action="decline",
                terminate=True,
                reason=f"verify_repair: budget agotado ({repair_count}/{self._max_repairs}) — {sig.reason}",
                params={"message": self._decline_message},
            )

        # Presupuesto general agotado -> decline
        if state.budget_exhausted():
            return ActionDecision(
                action="decline",
                terminate=True,
                reason="verify_repair: presupuesto general agotado",
                params={"message": self._decline_message},
            )

        # Decidir repair: limpiar answer y re-generar
        next_repair = repair_count + 1
        return ActionDecision(
            action="retry",
            capability_ref="generation",
            reason=f"verify_repair[{next_repair}]: {sig.reason}",
            params={
                "repair_count": next_repair,
                "repair_hint": self._repair_hint,
                "verify_reason": sig.reason or "",
            },
        )
