"""
Evaluation online (ADR-0006).

Evaluadores producen EvaluationSignal; no deciden.
"""

from src.evaluation.assess_evidence import AssessEvidenceEvaluator

__all__ = ["AssessEvidenceEvaluator"]
