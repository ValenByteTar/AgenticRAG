"""Front-end: Knowledge Acquisition (RES-002 §3).

Extractores deterministas + LLM convergen al mismo KIR:

1. EquivalencesExtractor  — parsea EQUIVALENCES_EMBEDDED_TEXT (92 grupos)
2. EntityAliasesExtractor — lee el dict entity_aliases hardcoded
3. DocCardsExtractor       — lee doc_roles.json (roles, atributos, centralidad)
4. LLMEntityExtractor     — extrae entidades/aliases/relaciones via LLM (E5)

Todos producen exactamente el mismo formato KIR. El compiler no sabe ni
necesita saber que extractor produjo que. (RES-002 §4.1)
"""

from __future__ import annotations

from .equivalences_extractor import EquivalencesExtractor
from .entity_aliases_extractor import EntityAliasesExtractor
from .doc_cards_extractor import DocCardsExtractor
from .llm_entity_extractor import LLMEntityExtractor

__all__ = [
    "EquivalencesExtractor",
    "EntityAliasesExtractor",
    "DocCardsExtractor",
    "LLMEntityExtractor",
]
