"""
VERIFY determinista de groundedness y fidelidad de citas (ADR-0006).

Fase 4: evaluacion online post-generacion.
Produce senal; no decide (Policy decide).

Chequeos:
  1. Groundedness: overlap de tokens de contenido entre answer y context.
     Overlap bajo = posible alucinacion.
  2. Hedge detection: si el answer contiene frases de rechazo pero el
     contexto tenia evidencia suficiente (assess paso), es una respuesta
     evasiva injustificada.
  3. Citation fidelity: marcadores [Doc N - ...] o [N] en el answer deben
     corresponder a resultados reales en state.results.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from src.kernel.state import EvaluationSignal, ExecutionState


_STOPWORDS: Set[str] = {
    "de", "la", "el", "en", "y", "a", "que", "es", "se", "del", "las", "los",
    "un", "una", "con", "por", "para", "su", "al", "lo", "como", "mas", "pero",
    "sus", "le", "ya", "o", "este", "si", "porque", "esta", "entre", "cuando",
    "the", "a", "an", "of", "in", "on", "for", "to", "and", "is", "are", "was",
    "were", "be", "been", "with", "by", "at", "from", "it", "this", "that",
    "no", "se", "menciona", "encuentra", "hay", "informacion", "contexto",
    "proporcionado", "datos", "documento", "documentos",
}

_HEDGE_PHRASES = [
    "no se menciona",
    "no se encuentra",
    "no hay informacion",
    "no hay evidencia",
    "no se proporciona",
    "no se contiene",
    "no existe",
    "no se documenta",
    "no esta disponible",
    "no tengo informacion",
    "no encontre",
    "no hay datos",
    "no hay documentos",
    "no hay suficiente",
    "insuficiente",
    "fuera de mi alcance",
    "fuera del alcance",
    "no puedo responder",
    "no dispongo",
]

_CITATION_RE = re.compile(
    r"\[(?:Doc\s+)?(\d+)[^\]]*\]",
    re.IGNORECASE,
)


def _tokenize(text: str) -> List[str]:
    return [t for t in re.findall(r"\b\w{3,}\b", text.lower()) if t not in _STOPWORDS]


def _groundedness_ratio(answer: str, context: str) -> Tuple[float, int, int]:
    """
    Fraccion de tokens de contenido del answer que aparecen en el context.
    Retorna (ratio, matched, total).
    """
    answer_tokens = _tokenize(answer)
    if not answer_tokens:
        return 0.0, 0, 0
    context_lower = context.lower()
    context_tokens = set(_tokenize(context))
    if not context_tokens:
        return 0.0, 0, len(answer_tokens)
    matched = sum(1 for t in answer_tokens if t in context_tokens)
    return matched / len(answer_tokens), matched, len(answer_tokens)


def _detect_hedge(answer: str) -> Optional[str]:
    """Retorna la frase de hedge encontrada, o None."""
    answer_lower = answer.lower()
    for phrase in _HEDGE_PHRASES:
        if phrase in answer_lower:
            return phrase
    return None


def _check_citations(answer: str, results: List[Dict[str, Any]]) -> Tuple[int, int, List[int]]:
    """
    Extrae marcadores de cita del answer y verifica contra results.
    Retorna (valid_citations, total_citations, invalid_indices).
    """
    matches = _CITATION_RE.findall(answer)
    if not matches:
        return 0, 0, []
    total = len(matches)
    n_results = len(results)
    invalid = []
    valid = 0
    for m in matches:
        idx = int(m)
        if 1 <= idx <= n_results:
            valid += 1
        else:
            invalid.append(idx)
    return valid, total, invalid


class VerifyGroundednessEvaluator:
    """
    Evaluation online: verifica que el answer este soportado por el context.

    Fase 4: groundedness + citation fidelity post-generacion.
    Produce EvaluationSignal(name="verify"); no decide.
    """

    name = "verify"

    def __init__(
        self,
        *,
        groundedness_floor: float = 0.25,
        min_answer_chars: int = 20,
        max_answer_chars: int = 8000,
    ) -> None:
        self._groundedness_floor = float(groundedness_floor)
        self._min_answer_chars = int(min_answer_chars)
        self._max_answer_chars = int(max_answer_chars)

    def evaluate(self, state: ExecutionState) -> EvaluationSignal:
        answer = (state.answer or "").strip()
        context = state.context or ""
        results = list(state.results or [])
        meta: Dict[str, Any] = {}

        # --- Hard gate 1: sin answer ---
        if not answer:
            return EvaluationSignal(
                name=self.name,
                score=0.0,
                passed=False,
                reason="verify: answer vacio",
                metadata=meta,
                source="online",
            )

        # --- Hard gate 2: answer demasiado corto ---
        if len(answer) < self._min_answer_chars:
            meta["answer_chars"] = len(answer)
            return EvaluationSignal(
                name=self.name,
                score=0.0,
                passed=False,
                reason=f"verify: answer demasiado corto ({len(answer)} chars)",
                metadata=meta,
                source="online",
            )

        # --- Groundedness ---
        ratio, matched, total = _groundedness_ratio(answer, context)
        meta["groundedness_ratio"] = round(ratio, 3)
        meta["groundedness_matched"] = matched
        meta["groundedness_total"] = total

        # --- Hedge detection ---
        hedge = _detect_hedge(answer)
        if hedge:
            meta["hedge_phrase"] = hedge
            # Si assess paso pero el answer hedgea, es una respuesta evasiva
            assess_sig = state.latest_signal("assess")
            if assess_sig is not None and assess_sig.passed:
                meta["unjustified_hedge"] = True
                return EvaluationSignal(
                    name=self.name,
                    score=0.0,
                    passed=False,
                    reason=f"verify: hedge injustificado '{hedge}' con assess pasado",
                    metadata=meta,
                    source="online",
                )
            # Hedge justificado (assess fallo o no hay) -> verify pasa (decline correcto)
            return EvaluationSignal(
                name=self.name,
                score=0.5,
                passed=True,
                reason=f"verify: hedge justificado '{hedge}'",
                metadata=meta,
                source="online",
            )

        # --- Groundedness floor ---
        if ratio < self._groundedness_floor:
            return EvaluationSignal(
                name=self.name,
                score=ratio,
                passed=False,
                reason=(
                    f"verify: groundedness {ratio:.3f} < {self._groundedness_floor} "
                    f"({matched}/{total} tokens en contexto)"
                ),
                metadata=meta,
                source="online",
            )

        # --- Citation fidelity ---
        valid_cites, total_cites, invalid_indices = _check_citations(answer, results)
        if total_cites > 0:
            meta["citation_valid"] = valid_cites
            meta["citation_total"] = total_cites
            meta["citation_invalid_indices"] = invalid_indices
            if invalid_indices:
                meta["citation_fidelity"] = round(valid_cites / total_cites, 3)
                # Citas invalidas son un flag blando, no hard gate
                if valid_cites == 0:
                    return EvaluationSignal(
                        name=self.name,
                        score=ratio * 0.5,
                        passed=False,
                        reason=f"verify: 0 citas validas de {total_cites}",
                        metadata=meta,
                        source="online",
                    )

        # --- Score final ---
        cite_bonus = 0.0
        if total_cites > 0 and not invalid_indices:
            cite_bonus = 0.1
        score = min(1.0, ratio + cite_bonus)

        return EvaluationSignal(
            name=self.name,
            score=score,
            passed=True,
            reason="verify: answer soportado por contexto",
            metadata=meta,
            source="online",
        )
