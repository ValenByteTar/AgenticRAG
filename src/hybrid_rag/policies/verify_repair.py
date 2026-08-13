"""
Policy: verify repair (ADR-0013, ADR-0006, ADR-0019).

Fase 4: observa la senal VERIFY y decide reparacion dirigida.
Repara solo cuando hay riesgo factual real (claims contradichos o
factualmente no soportados, citas invalidas). No repara por bajo
overlap lexico puro ni por respuestas conceptuales correctas con
soporte debil.

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
    "REPARACION REQUERIDA: Tu respuesta anterior contiene afirmaciones no "
    "soportadas por el contexto proporcionado.\n"
    "Instrucciones dirigidas:\n"
    "1. Conserva las partes de tu respuesta anteriores que SI estan respaldadas.\n"
    "2. Elimina o reformula UNICAMENTE los claims marcados como no soportados.\n"
    "3. NO inventes numeros, versiones, nombres de controles/frameworks ni citas documentales.\n"
    "4. Si un claim no tiene soporte en el contexto, omítelo o declara 'no hay informacion suficiente'.\n"
    "5. Las definiciones conceptuales generales son aceptables si se marcan como [Conocimiento general].\n"
    "6. Cita fuentes usando [Doc N - nombre p.X] cuando uses datos especificos del contexto."
)


def _should_repair(sig: EvaluationSignal) -> bool:
    """
    Determina si la senal verify amerita reparacion segun ADR-0019.

    Reparar solo ante:
    - claim contradicho (hedge injustificado, cita invalida, etc.)
    - claim factual no soportado
    - 0 citas validas cuando se usaron citas
    """
    if sig.passed is not False:
        return False
    if not sig.metadata:
        return False
    claim_status = sig.metadata.get("claim_support_status")
    if claim_status in ("contradicted", "unsupported"):
        return True
    # Back-compat: repair si hay 0 citas validas (cita inventada) o sin claim metadata
    if claim_status is None:
        # Senal legacy sin claim metadata: reparar solo si hay razon de cita o hedge injustificado
        reason = (sig.reason or "").lower()
        return (
            "0 citas validas" in reason
            or "hedge injustificado" in reason
            or "invalid" in reason
        )
    return False


def _build_directed_repair_hint(
    sig: EvaluationSignal, default_hint: str
) -> str:
    """Construye repair hint dirigido a los claims problematicos."""
    problematic = sig.metadata.get("claim_support_problematic") or []
    status = sig.metadata.get("claim_support_status")
    if not problematic:
        return default_hint
    lines = [default_hint]
    lines.append("\nClaims problematicos a corregir:")
    for i, claim in enumerate(problematic[:5], 1):
        lines.append(f"{i}. {claim[:250]}")
    if status:
        lines.append(f"\nRazon: {status}")
    return "\n".join(lines)


class VerifyRepairPolicy:
    """
    Policy de reparacion dirigida basada en senal VERIFY (ADR-0019).

    Decide re-generar si:
    - verify fallo por claim contradicho/factual no soportado o 0 citas validas
    - repair_count < max_repairs
    - presupuesto no agotado

    Decide decline si:
    - verify fallo y repair_count >= max_repairs
    - o verify fallo por un riesgo no reparable (retrieval insuficiente)
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
        # Usar claim metadata si esta disponible (ADR-0019)
        self._use_claim_metadata = True

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

        # ADR-0019: solo reparar riesgos factuales reales.
        if not _should_repair(sig):
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

        # Decidir repair dirigido: conservar claims correctos, reescribir problematicos
        next_repair = repair_count + 1
        directed_hint = _build_directed_repair_hint(sig, self._repair_hint)
        return ActionDecision(
            action="retry",
            capability_ref="generation",
            reason=f"verify_repair[{next_repair}]: {sig.reason}",
            params={
                "repair_count": next_repair,
                "repair_hint": directed_hint,
                "verify_reason": sig.reason or "",
                "claim_support_status": sig.metadata.get("claim_support_status") if sig.metadata else None,
            },
        )
