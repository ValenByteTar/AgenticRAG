"""Confidence Policy — estrategia configurable (RES-002 §5.1).

La combinacion de confidence cuando multiples extractores producen el
mismo claim no es un pass. Es una politica configurable.

Politicas disponibles:
    - Max:       tomar la confidence mas alta
    - Mean:      promediar
    - Weighted:  ponderar por confianza del extractor (default)
    - Bayesian:  combinacion probabilistica

La politica es configurable por build. No es un paso fijo del pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List


_EXTRACTOR_WEIGHTS = {
    "deterministic:equivalences-text": 0.95,
    "deterministic:entity-aliases-dict": 0.90,
    "deterministic:doc-cards": 0.70,
    "llm:granite-4.1-8b": 0.85,
}


class ConfidencePolicy(ABC):
    """Interfaz base: combine(confidences, extractor_ids) -> float."""

    @abstractmethod
    def combine(self, confidences: List[float], extractor_ids: List[str]) -> float:
        ...

    @property
    def name(self) -> str:
        return self.__class__.__name__


class MaxPolicy(ConfidencePolicy):
    """Toma la confidence mas alta."""

    def combine(self, confidences: List[float], extractor_ids: List[str]) -> float:
        return max(confidences) if confidences else 0.0


class MeanPolicy(ConfidencePolicy):
    """Promedia las confidences."""

    def combine(self, confidences: List[float], extractor_ids: List[str]) -> float:
        if not confidences:
            return 0.0
        return sum(confidences) / len(confidences)


class WeightedPolicy(ConfidencePolicy):
    """Pondera por confianza del extractor (default).

    Si un extractor no tiene peso asignado, se usa 0.5.
    """

    def __init__(self, weights: dict | None = None):
        self.weights = dict(_EXTRACTOR_WEIGHTS)
        if weights:
            self.weights.update(weights)

    def combine(self, confidences: List[float], extractor_ids: List[str]) -> float:
        if not confidences:
            return 0.0
        total_weight = 0.0
        weighted_sum = 0.0
        for conf, eid in zip(confidences, extractor_ids):
            w = self.weights.get(eid, 0.5)
            weighted_sum += conf * w
            total_weight += w
        if total_weight == 0:
            return max(confidences)
        return min(1.0, weighted_sum / total_weight)


class BayesianPolicy(ConfidencePolicy):
    """Combinacion probabilistica bayesiana.

    P(claim) = 1 - product(1 - p_i)
    """

    def combine(self, confidences: List[float], extractor_ids: List[str]) -> float:
        if not confidences:
            return 0.0
        prob_false = 1.0
        for p in confidences:
            prob_false *= (1.0 - p)
        return min(1.0, 1.0 - prob_false)


def get_policy(name: str = "weighted", **kwargs) -> ConfidencePolicy:
    """Factory: obtiene una politica por nombre."""
    policies = {
        "max": MaxPolicy,
        "mean": MeanPolicy,
        "weighted": WeightedPolicy,
        "bayesian": BayesianPolicy,
    }
    cls = policies.get(name.lower())
    if cls is None:
        raise ValueError(f"politica desconocida: {name}. Disponibles: {list(policies.keys())}")
    return cls(**kwargs)
