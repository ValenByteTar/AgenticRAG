"""
VERIFY determinista de groundedness y fidelidad de citas (ADR-0006, ADR-0019).

Fase 4: evaluacion online post-generacion.
Produce senal; no decide (Policy decide).

Chequeos:
  1. Claim-level support: segmenta la respuesta en claims y clasifica cada uno
     como supported / weakly_supported / unsupported / contradicted.
     Los claims conceptuales de fondo (parafrazis, expansion de acronimos)
     pueden estar weakly_supported sin fallo. Los claims con tokens factuales
     especificos (numeros, versiones, acronimos) deben tener soporte lexico
     alto; si no, se marcan unsupported.
  2. Hedge detection: si el answer contiene frases de rechazo pero el
     contexto tenia evidencia suficiente (assess paso), es una respuesta
     evasiva injustificada (contradicted).
  3. Citation fidelity: marcadores [Doc N - ...] o [N] en el answer deben
     corresponder a resultados reales en state.results.

El overlap lexico global sigue computandose como diagnostico, pero ya no es
un gate duro por si solo.
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

# Segmentacion de claims por oraciones.
_CLAIM_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

# Tokens de riesgo factual: numeros y versiones. Los acronimos no se tratan
# como riesgo factual por si solos; el control de citas cubre referencias inventadas.
_RISK_TOKEN_PATTERNS = [
    re.compile(r"v?\d+\.\d+(?:\.\d+)*"),  # versiones
    re.compile(r"\b\d+\b"),  # numeros generales (ignorados si son citas)
]


def _clean_claim_for_risk_tokens(claim: str) -> str:
    """Elimina marcadores de cita para que los numeros de referencia no sean riesgo."""
    return _CITATION_RE.sub(" ", claim)


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


def _extract_claims(answer: str) -> List[str]:
    """Segmenta la respuesta en claims/oraciones."""
    parts = [p.strip() for p in _CLAIM_SPLIT_RE.split(answer) if p.strip()]
    if not parts:
        parts = [answer.strip()]
    return parts


def _claim_has_risk_tokens(claim: str) -> bool:
    """Indica si el claim contiene tokens que requieren soporte documental alto."""
    for pat in _RISK_TOKEN_PATTERNS:
        if pat.search(claim):
            return True
    return False


def _extract_risk_token_matches(claim: str) -> List[str]:
    """Extrae los strings que coinciden con patrones de riesgo factual."""
    claim = _clean_claim_for_risk_tokens(claim)
    matches: Set[str] = set()
    for pat in _RISK_TOKEN_PATTERNS:
        for m in pat.finditer(claim):
            matches.add(m.group(0).strip())
    return [m for m in matches if m]


def _risk_tokens_supported(claim: str, context: str) -> Tuple[bool, List[str], List[str]]:
    """
    Verifica si los tokens de riesgo del claim aparecen en el contexto.
    Retorna (soporte_total, tokens_soportados, tokens_faltantes).
    """
    risk_tokens = _extract_risk_token_matches(claim)
    if not risk_tokens:
        return True, [], []
    context_lower = context.lower()
    supported = []
    missing = []
    for tok in risk_tokens:
        if tok.lower() in context_lower:
            supported.append(tok)
        else:
            missing.append(tok)
    return not missing, supported, missing


def _assess_claim_support(
    answer: str, context: str, results: List[Dict[str, Any]], assess_passed: bool
) -> Tuple[str, List[Dict[str, Any]], Optional[str], List[str]]:
    """
    Clasifica cada claim de la respuesta.

    Retorna:
        status: 'supported' | 'weakly_supported' | 'unsupported' | 'contradicted'
        claim_details: lista de dicts con texto y estado de cada claim
        reason: razon de fallo (si aplica)
        problematic_claims: textos de claims que motivan repair
    """
    claims = _extract_claims(answer)
    details: List[Dict[str, Any]] = []
    problematic_claims: List[str] = []

    for i, claim in enumerate(claims):
        claim_lower = claim.lower()
        detail: Dict[str, Any] = {"claim_index": i, "claim_text": claim[:160]}

        # 1. Hedge injustificado = contradicted
        hedge = _detect_hedge(claim)
        if hedge and assess_passed:
            detail["status"] = "contradicted"
            detail["reason"] = f"hedge injustificado: '{hedge}'"
            problematic_claims.append(claim)
            details.append(detail)
            continue

        # 2. Citas invalidas en el claim = contradicted
        valid_cites, total_cites, invalid_indices = _check_citations(claim, results)
        detail["citation_valid"] = valid_cites
        detail["citation_total"] = total_cites
        if total_cites > 0 and valid_cites == 0:
            detail["status"] = "contradicted"
            detail["reason"] = f"citas invalidas: {invalid_indices}"
            problematic_claims.append(claim)
            details.append(detail)
            continue

        # 3. Soporte lexico del claim
        ratio, matched, total = _groundedness_ratio(claim, context)
        detail["groundedness_ratio"] = round(ratio, 3)
        detail["groundedness_matched"] = matched
        detail["groundedness_total"] = total

        # 4. Verificar tokens factuales especificos presentes en el contexto
        risk_supported, risk_found, risk_missing = _risk_tokens_supported(claim, context)
        detail["risk_tokens"] = _extract_risk_token_matches(claim)
        detail["risk_tokens_supported"] = risk_found
        detail["risk_tokens_missing"] = risk_missing

        # 5. Clasificacion del claim
        if not risk_supported:
            # Introduce tokens factuales (numeros, versiones) no presentes en contexto
            detail["status"] = "unsupported"
            detail["reason"] = (
                f"claim factual no soportado: tokens ausentes {risk_missing} "
                f"(groundedness={ratio:.3f})"
            )
            problematic_claims.append(claim)
        elif risk_found:
            # Claim con tokens factuales que SI estan en contexto: puede ser parafrazis
            if ratio >= 0.5:
                detail["status"] = "supported"
            elif ratio > 0.0:
                detail["status"] = "weakly_supported"
            else:
                # risk_found implica que al menos el token de riesgo aparece -> weakly supported
                detail["status"] = "weakly_supported"
        else:
            # Claim conceptual sin tokens factuales de riesgo
            if ratio >= 0.15:
                detail["status"] = "supported"
            else:
                # Conocimiento de fondo consistente con el dominio (sin riesgo factual)
                detail["status"] = "weakly_supported"
                if ratio == 0.0:
                    detail["reason"] = "conocimiento de fondo sin soporte lexico directo"

        details.append(detail)

    # Determinar estado agregado
    statuses = [d.get("status", "weakly_supported") for d in details]
    if any(s == "contradicted" for s in statuses):
        return "contradicted", details, "verify: claim(s) contradicted", problematic_claims
    if any(s == "unsupported" for s in statuses):
        return (
            "unsupported",
            details,
            "verify: claim(s) factual no soportado(s) por el contexto (groundedness insuficiente)",
            problematic_claims,
        )
    if all(s == "supported" for s in statuses):
        return "supported", details, None, []
    if any(s == "weakly_supported" for s in statuses):
        return "weakly_supported", details, None, []
    return "supported", details, None, []


class VerifyGroundednessEvaluator:
    """
    Evaluation online: verifica que el answer este soportado por el context.

    Fase 4: claim-level groundedness + citation fidelity post-generacion.
    Produce EvaluationSignal(name="verify"); no decide.
    """

    name = "verify"

    def __init__(
        self,
        *,
        groundedness_floor: float = 0.25,
        min_answer_chars: int = 20,
        max_answer_chars: int = 8000,
        factual_risk_floor: float = 0.5,
        conceptual_floor: float = 0.15,
    ) -> None:
        self._groundedness_floor = float(groundedness_floor)
        self._min_answer_chars = int(min_answer_chars)
        self._max_answer_chars = int(max_answer_chars)
        self._factual_risk_floor = float(factual_risk_floor)
        self._conceptual_floor = float(conceptual_floor)

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

        # --- Claim-level support (Fase B: local-first claim check) ---
        assess_sig = state.latest_signal("assess")
        assess_passed = assess_sig is not None and assess_sig.passed
        claim_status, claim_details, claim_fail_reason, problematic_claims = _assess_claim_support(
            answer, context, results, assess_passed
        )
        meta["claim_support_status"] = claim_status
        meta["claim_support_details"] = claim_details
        meta["claim_support_problematic"] = [
            c[:200] for c in problematic_claims
        ]
        meta["factual_risk_floor"] = self._factual_risk_floor
        meta["conceptual_floor"] = self._conceptual_floor

        # Preservar metadata de citas a nivel top-level (backward-compat tests)
        all_invalid: List[int] = []
        total_cites_sum = 0
        valid_cites_sum = 0
        for d in claim_details:
            total_cites_sum += int(d.get("citation_total", 0) or 0)
            valid_cites_sum += int(d.get("citation_valid", 0) or 0)
            if d.get("citation_total", 0) and d.get("citation_valid", 0) < d["citation_total"]:
                # Re-computar indices invalidos del claim para metadata top-level
                claim_text = d.get("claim_text", "")
                _, _, invalid = _check_citations(claim_text, results)
                all_invalid.extend(invalid)
        if total_cites_sum > 0:
            meta["citation_total"] = total_cites_sum
            meta["citation_valid"] = valid_cites_sum
            if all_invalid:
                meta["citation_invalid_indices"] = all_invalid
                meta["citation_fidelity"] = round(
                    valid_cites_sum / total_cites_sum, 3
                ) if total_cites_sum else 0.0

        # --- Gate duro: contradicho o factual no soportado ---
        if claim_status in ("contradicted", "unsupported"):
            return EvaluationSignal(
                name=self.name,
                score=ratio,
                passed=False,
                reason=claim_fail_reason or f"verify: {claim_status}",
                metadata=meta,
                source="online",
            )

        # --- Groundedness floor legacy: diagnostico, no gate duro ---
        if ratio < self._groundedness_floor:
            meta["low_groundedness_warning"] = (
                f"groundedness {ratio:.3f} < {self._groundedness_floor} "
                f"({matched}/{total} tokens en contexto)"
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
