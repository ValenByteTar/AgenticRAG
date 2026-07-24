---
id: DEC-007
title: "MemoryPortAdapter + KnowledgeSystemAdapter: contratos concretos Fase 5"
date: 2026-07-24
status: accepted
category: decisions
tags: [memory, knowledge, adapters, fase-5, adr-0009, adr-0015]
related: [ADR-0009, ADR-0015, ADR-0014, DEC-006]
---

# DEC-007 — MemoryPortAdapter + KnowledgeSystemAdapter: contratos concretos Fase 5

## Contexto

ADR-0009 declara contratos minimos para Memory (read con provenance; write controlado y verifiable) y Tool.
ADR-0015 declara KnowledgeSystem como un subsistema (no un store), con esquema interno diferido (P11).

En Fase 5 necesitamos implementaciones concretas que satisfagan estos contratos para que el kernel pueda usarlos via bootstrap, sin congelar el esquema interno.

## Decision

### MemoryPortAdapter (`src/adapters/memory_port.py`)

- Envuelve `MemorySystem` (SQLite) bajo contrato `MemoryPort`.
- `read()`: delega a `search_memory()`, agrega `provenance` a cada record (source, origin, record_id, timestamp).
- `write()`: passthrough a `add_knowledge()`, retorna bool. Write es parte del contrato pero su uso controlado/verificado se difiere a Fase 7.
- Vive en el composition boundary (`src/adapters/`), no en el Kernel.

### KnowledgeSystemAdapter (`src/adapters/knowledge_system.py`)

- Envuelve `hybrid_search` + `_rerank_results` bajo contrato `KnowledgeSystem`.
- `retrieve()`: delega a hybrid_search + rerank con kwargs (top_k, semantic_weight).
- `get_entity()`: stub que retorna None (esquema interno diferido, P11).
- Reserva la frontera: el Knowledge Architect futuro puede extender get_entity sin cambiar el contrato.

### MemoryReadCapability

- Actualizado para aceptar `MemoryPort` (con `.read()`) ademas de callable plano.
- Deteccion via `hasattr(self._read, "read")`.
- Backward compatible: callable plano sigue funcionando.

### Bootstrap wiring

- `build_kernel_bundle` acepta `memory_port` y `knowledge_system` opcionales.
- `build_kernel_bundle_from_rag` crea automaticamente `MemoryPortAdapter` (si `rag.memory` existe) y `KnowledgeSystemAdapter`.
- Si `memory_port` se provee, toma precedencia sobre `memory_read_fn`.

## Consecuencias

- Memory read ahora incluye provenance metadata en cada hit.
- KnowledgeSystem es una frontera reservada: el indice vectorial es una via de acceso, no la totalidad.
- Adapters viven en `src/adapters/` (composition boundary), no en Kernel ni en capabilities.
- Backward compatible: tests existentes no se rompen.

## Alternativas

- MemoryPort directo sobre SQLite sin adapter (rechazado: viola ADR-0014, composition boundary).
- KnowledgeSystem con esquema congelado ahora (rechazado: ADR-0015 dice diferido P11).
- MemoryReadCapability solo con callable (rechazado: no aprovecha provenance del contrato).
