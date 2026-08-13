"""
Capabilities concretas (fuera del Kernel).

Se registran en el CapabilityRegistry via CompositionRoot (ADR-0012, P15).
"""

from src.capabilities.retrieval import RetrievalCapability
from src.capabilities.build_context import BuildContextCapability
from src.capabilities.generation import GenerationCapability
from src.capabilities.classify import ClassifyCapability
from src.capabilities.assess import AssessCapability
from src.capabilities.memory_read import MemoryReadCapability
from src.capabilities.finalize_turn import FinalizeTurnCapability
from src.capabilities.two_stage_retrieval import TwoStageRetrievalCapability
from src.capabilities.verify import VerifyCapability
from src.capabilities.entity_expansion import EntityExpansionCapability
from src.capabilities.planner import PlannerCapability

__all__ = [
    "RetrievalCapability",
    "BuildContextCapability",
    "GenerationCapability",
    "ClassifyCapability",
    "AssessCapability",
    "MemoryReadCapability",
    "FinalizeTurnCapability",
    "TwoStageRetrievalCapability",
    "VerifyCapability",
    "EntityExpansionCapability",
    "PlannerCapability",
]
