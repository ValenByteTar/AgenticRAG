---
id: DEC-001
category: decision
status: accepted
created: 2026-07-22
updated: 2026-07-22
author: cascade
components: [facade, capabilities]
tags: [domain, rename, cleanup, phase0]
related: [ADR-0017]
supersedes: null
superseded_by: null
---

# DEC-001 - Renombrar centrales_map a domain_map

## Context

El HybridRAG arrastraba el nombre `centrales_map` del dominio electrico residual. El gazetteer de entidades es generico (ciberseguridad); el nombre inducia confusion y violaba el espiritu de P7 (dominio como dato, no arquitectura embebida en nombres).

## Decision

Renombrar a `domain_map` / `domain_map_loaded` en `rag_hybrid.py`, manteniendo aliases `centrales_map` / `centrales_loaded` por compatibilidad con codigo legacy que aun lee el atributo antiguo.

## Status

accepted

## Notes

No es un ADR: no cambia contratos del Kernel ni fronteras de planos; es un rename local con alias de compatibilidad. Limpieza profunda de prompts/heuristicas electricas queda diferida.
