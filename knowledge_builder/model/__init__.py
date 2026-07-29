"""Knowledge Model + Confidence Policy (RES-002 §5.1, §7)."""

from .confidence import (
    BayesianPolicy,
    ConfidencePolicy,
    MaxPolicy,
    MeanPolicy,
    WeightedPolicy,
    get_policy,
)
from .knowledge_model import (
    AliasEntry,
    CanonicalEntity,
    DocumentRole,
    EntityIndexEntry,
    KnowledgeModel,
    RelationEntry,
)

__all__ = [
    "ConfidencePolicy",
    "MaxPolicy",
    "MeanPolicy",
    "WeightedPolicy",
    "BayesianPolicy",
    "get_policy",
    "KnowledgeModel",
    "CanonicalEntity",
    "AliasEntry",
    "EntityIndexEntry",
    "DocumentRole",
    "RelationEntry",
]
