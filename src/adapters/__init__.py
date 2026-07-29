"""
Adapters concretos para contratos del Kernel (ADR-0014, composition boundary).

MemoryPortAdapter (ADR-0009) y KnowledgeSystemAdapter (ADR-0015).
Viven en el composition boundary, no en el Kernel.
"""

from src.adapters.memory_port import MemoryPortAdapter
from src.adapters.knowledge_system import KnowledgeSystemAdapter
from src.adapters.warm_artifact_resolver import WarmArtifactResolver

__all__ = [
    "MemoryPortAdapter",
    "KnowledgeSystemAdapter",
    "WarmArtifactResolver",
]
