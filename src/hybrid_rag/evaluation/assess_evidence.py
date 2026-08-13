"""
ASSESS determinista de suficiencia de evidencia (ADR-0006).

Fase 1: gates base (reranker-confidence, factual_gate, vacio).
Fase 2: senales enriquecidas (entity coverage, source diversity, context density).
Produce senal; no decide (Policy decide).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from src.kernel.state import EvaluationSignal, ExecutionState


def _quality_score(r: Dict[str, Any]) -> float:
    try:
        if r.get("final_score") is not None:
            return float(r.get("final_score") or 0.0)
    except Exception:
        pass
    try:
        if r.get("rerank_score") is not None:
            return float(r.get("rerank_score") or 0.0)
    except Exception:
        pass
    try:
        return float(r.get("hybrid_score") or 0.0) * 0.5
    except Exception:
        return 0.0


_STOPWORDS: Set[str] = {
    "de", "la", "el", "en", "y", "a", "que", "es", "se", "del", "las", "los",
    "un", "una", "con", "por", "para", "su", "al", "lo", "como", "mas", "pero",
    "sus", "le", "ya", "o", "este", "si", "porque", "esta", "entre", "cuando",
    "the", "a", "an", "of", "in", "on", "for", "to", "and", "is", "are", "was",
    "were", "be", "been", "with", "by", "at", "from", "it", "this", "that",
}


def _tokenize(text: str) -> List[str]:
    return [t for t in re.findall(r"\b\w{3,}\b", text.lower()) if t not in _STOPWORDS]


def _entity_coverage(entities: List[str], context: str) -> Tuple[float, int, int]:
    if not entities or not context:
        return 1.0, 0, 0
    ctx_lower = context.lower()
    matched = 0
    total = len(entities)
    for ent in entities:
        ent_lower = str(ent).lower().strip()
        if not ent_lower:
            total -= 1
            continue
        tokens = [t for t in ent_lower.split() if len(t) > 2]
        if not tokens:
            total -= 1
            continue
        hits = sum(1 for t in tokens if t in ctx_lower)
        if hits >= max(1, len(tokens) // 2):
            matched += 1
    if total == 0:
        return 1.0, 0, 0
    return matched / total, matched, total


def _source_diversity(results: List[Dict[str, Any]]) -> int:
    sources: Set[str] = set()
    for r in results:
        md = r.get("metadata") or {}
        s = md.get("source") or r.get("source") or ""
        if s:
            sources.add(str(s).lower())
    return len(sources)


def _context_density(context: str) -> float:
    tokens = _tokenize(context)
    if not tokens:
        return 0.0
    return len(set(tokens)) / len(tokens)


class AssessEvidenceEvaluator:
    """
    Evaluation online: pass/fail sobre evidencia pre-generacion.

    Fase 2: senales blandas (entity_coverage, source_diversity,
    context_density, assess_precision_proxy) en metadata para
    consumo de policies de retry (F3) y observabilidad.
    """

    name = "assess"

    def __init__(
        self,
        *,
        min_context_chars: int = 30,
        rerank_floor: float = 0.1,
        hybrid_rescue: float = 0.5,
        factual_gate_fn=None,
        entity_coverage_floor: float = 0.0,
    ) -> None:
        self._min_context_chars = int(min_context_chars)
        self._rerank_floor = float(rerank_floor)
        self._hybrid_rescue = float(hybrid_rescue)
        self._factual_gate_fn = factual_gate_fn
        self._entity_coverage_floor = float(entity_coverage_floor)

    def evaluate(self, state: ExecutionState) -> EvaluationSignal:
        results: List[Dict[str, Any]] = list(state.results or [])
        context = state.context or ""
        meta: Dict[str, Any] = {}

        # --- Hard gate 1: sin results ---
        if not results:
            return EvaluationSignal(
                name=self.name,
                score=0.0,
                passed=False,
                reason="assess: sin results",
                metadata=meta,
                source="online",
            )

        # --- Hard gate 2: contexto vacio ---
        if len(context.strip()) < self._min_context_chars:
            return EvaluationSignal(
                name=self.name,
                score=0.0,
                passed=False,
                reason="assess: contexto vacio o insuficiente",
                metadata={"context_chars": len(context.strip())},
                source="online",
            )

        # --- Hard gate 3: rerank floor con rescate hybrid ---
        rerank_scores = []
        for r in results:
            if r.get("rerank_score") is not None:
                try:
                    rerank_scores.append(float(r.get("rerank_score")))
                except Exception:
                    pass
        if rerank_scores:
            best_rr = max(rerank_scores)
            meta["best_rerank"] = best_rr
            if best_rr < self._rerank_floor:
                hybrid_scores = []
                final_scores = []
                for r in results:
                    try:
                        if r.get("hybrid_score") is not None:
                            hybrid_scores.append(float(r.get("hybrid_score")))
                    except Exception:
                        pass
                    try:
                        if r.get("final_score") is not None:
                            final_scores.append(float(r.get("final_score")))
                    except Exception:
                        pass
                best_hybrid = max(hybrid_scores) if hybrid_scores else 0.0
                best_final = max(final_scores) if final_scores else 0.0
                meta["best_hybrid"] = best_hybrid
                meta["best_final"] = best_final
                if best_hybrid <= self._hybrid_rescue and best_final <= self._hybrid_rescue:
                    return EvaluationSignal(
                        name=self.name,
                        score=best_rr,
                        passed=False,
                        reason=(
                            f"assess: rerank max {best_rr:.3f} < {self._rerank_floor} "
                            f"sin rescate hybrid/final"
                        ),
                        metadata=meta,
                        source="online",
                    )

        quality_n = sum(1 for r in results if _quality_score(r) > 0.15)
        meta["quality_results"] = quality_n

        # --- Hard gate 4: factual gate ---
        fg = self._factual_gate_fn
        if fg is None:
            try:
                from src.rag.factual_gate import check_factual_gate

                fg = check_factual_gate
            except Exception:
                fg = None
        if fg is not None:
            try:
                allow, reason = fg(state.question, context)
                meta["factual_gate"] = reason or ""
                if not allow:
                    return EvaluationSignal(
                        name=self.name,
                        score=0.0,
                        passed=False,
                        reason=reason or "assess: factual_gate bloqueo",
                        metadata=meta,
                        source="online",
                    )
            except Exception as exc:
                meta["factual_gate_error"] = str(exc)

        # --- Fase 2: senales blandas ---

        # Entity coverage
        entities = list(state.entities or [])
        if not entities:
            cls_meta = state.metadata.get("classification") or {}
            entities = list(cls_meta.get("entities") or [])
        cov_ratio, cov_matched, cov_total = _entity_coverage(entities, context)
        meta["entity_coverage_ratio"] = round(cov_ratio, 3)
        meta["entity_coverage_matched"] = cov_matched
        meta["entity_coverage_total"] = cov_total

        # Hard gate 5 (F2): entity coverage = 0 con entidades presentes
        if cov_total > 0 and cov_matched == 0 and self._entity_coverage_floor > 0.0:
            return EvaluationSignal(
                name=self.name,
                score=0.0,
                passed=False,
                reason=(
                    f"assess: entity coverage 0/{cov_total} "
                    f"— ninguna entidad en contexto"
                ),
                metadata=meta,
                source="online",
            )

        # Source diversity
        diversity = _source_diversity(results)
        meta["source_diversity"] = diversity

        # Context density
        density = _context_density(context)
        meta["context_density"] = round(density, 3)

        # Assess precision proxy
        total_results = len(results)
        meta["assess_precision_proxy"] = round(quality_n / total_results, 3) if total_results else 0.0

        # --- Score heuristico enriquecido ---
        base = 0.2 + 0.1 * quality_n + min(0.4, len(context) / 8000.0)
        cov_bonus = min(0.15, cov_ratio * 0.15) if cov_total > 0 else 0.0
        div_bonus = min(0.1, diversity * 0.03)
        den_bonus = min(0.05, density * 0.05)
        score = min(1.0, base + cov_bonus + div_bonus + den_bonus)

        # Flags blandos para F3 retry
        meta["entity_coverage_low"] = cov_total > 0 and cov_ratio < 0.5
        meta["source_diversity_low"] = diversity <= 1 and total_results > 3

        return EvaluationSignal(
            name=self.name,
            score=score,
            passed=True,
            reason="assess: evidencia suficiente",
            metadata=meta,
            source="online",
        )
