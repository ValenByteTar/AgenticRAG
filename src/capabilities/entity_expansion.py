"""
Capability: entity_expansion (ADR-0012, Fase 6).

Expansion de entidades pre-retrieval usando un gazetteer de aliases.
Mejora recall al buscar variantes de entidades (iso 27001 -> iso27001, iso 27k, isms).

Determinista: no usa LLM. El gazetteer es inyectado via callable o dict.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Union

from src.kernel.state import ExecutionState

EntityExpandFn = Callable[[str, List[str]], List[str]]

_DEFAULT_ALIASES: Dict[str, List[str]] = {
    "iso 27001": ["iso 27001", "iso27001", "iso 27k", "isms"],
    "nist csf": ["nist csf", "nist cybersecurity framework", "cybersecurity framework", "nist framework"],
    "cissp": ["cissp", "certified information systems security professional", "(isc)2"],
    "ceh": ["ceh", "certified ethical hacker", "ethical hacker"],
    "cism": ["cism", "certified information security manager"],
    "mitre att&ck": ["mitre att&ck", "mitre attack", "mitre attck", "attack framework"],
    "owasp": ["owasp", "open web application security project"],
    "splunk": ["splunk", "splunk siem", "splunk enterprise security"],
    "nist rmf": ["nist rmf", "nist risk management framework", "risk management framework"],
    "cobit": ["cobit", "control objectives for information and related technologies"],
    "pci dss": ["pci dss", "payment card industry data security standard"],
    "soc 2": ["soc 2", "soc2", "service organization control 2"],
}


class EntityExpansionCapability:
    name = "entity_expansion"

    def __init__(
        self,
        expand_fn: Optional[EntityExpandFn] = None,
        *,
        aliases: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        self._expand_fn = expand_fn
        self._aliases = aliases or _DEFAULT_ALIASES

    def execute(
        self, state: ExecutionState, params: Optional[Dict[str, Any]] = None
    ) -> ExecutionState:
        entities = list(state.entities or [])
        if not entities:
            state.metadata["entity_expansion"] = True
            state.metadata["expanded_entities"] = []
            state.add_trace("capability.entity_expansion", "n=0 (no entities)")
            return state

        if self._expand_fn is not None:
            try:
                expanded = list(self._expand_fn(state.question, entities) or [])
            except Exception as exc:
                state.add_trace("capability.entity_expansion", f"error:{exc}")
                expanded = entities
        else:
            expanded = self._expand_with_aliases(entities)

        # Deduplicate preserving order
        seen = set()
        unique = []
        for e in expanded:
            el = e.lower().strip()
            if el and el not in seen:
                seen.add(el)
                unique.append(e)

        state.entities = unique
        state.metadata["entity_expansion"] = True
        state.metadata["expanded_entities"] = unique
        state.metadata["entity_expansion_count"] = len(unique) - len(entities)
        state.add_trace(
            "capability.entity_expansion",
            f"n={len(unique)} (was {len(entities)})",
            {"added": len(unique) - len(entities)},
        )
        return state

    def _expand_with_aliases(self, entities: List[str]) -> List[str]:
        expanded = set()
        for e in entities:
            el = e.lower().strip()
            expanded.add(el)
            if el in self._aliases:
                expanded.update(self._aliases[el])
        return list(expanded)
