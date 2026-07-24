---
id: EXP-006
title: "Fase 5: MemoryPortAdapter + KnowledgeSystemAdapter — experimento"
date: 2026-07-24
status: completed
category: experiments
tags: [memory, knowledge, adapters, fase-5, provenance]
related: [DEC-007, ADR-0009, ADR-0015]
---

# EXP-006 — Fase 5: MemoryPortAdapter + KnowledgeSystemAdapter

## Hipotesis

Se pueden implementar contratos concretos para MemoryPort (ADR-0009) y KnowledgeSystem (ADR-0015) que:
1. Envuelvan infraestructura existente sin congelar esquema interno.
2. Agreguen provenance a memory reads.
3. Sean backward compatible con callables existentes.
4. Pasen isinstance contra Protocol runtime_checkable.

## Setup

- **MemoryPortAdapter**: envuelve `MemorySystem` (SQLite), agrega provenance dict a cada record.
- **KnowledgeSystemAdapter**: envuelve `hybrid_search` + `_rerank_results`, `get_entity` retorna None.
- **MemoryReadCapability**: detecta `hasattr(read_fn, "read")` para usar MemoryPort o callable.
- **Bootstrap**: `build_kernel_bundle_from_rag` crea adapters automaticamente.

## Resultados

### Tests unitarios (17/17 passed)

| Suite | Tests | Estado |
|---|---|---|
| MemoryPortAdapter | 6 | PASS |
| KnowledgeSystemAdapter | 5 | PASS |
| MemoryReadWithPort | 3 | PASS |
| E2EBootstrapWithAdapters | 3 | PASS |

### Suite global: 127 passed (110 existentes + 17 nuevos, 0 regresion)

### Validaciones clave

1. **Protocol compliance**: `isinstance(MemoryPortAdapter(...), MemoryPort)` = True. `isinstance(KnowledgeSystemAdapter(...), KnowledgeSystem)` = True.
2. **Provenance**: cada memory hit incluye `provenance.source`, `provenance.origin`, `provenance.record_id`, `provenance.timestamp`.
3. **Backward compatible**: callable plano sigue funcionando en MemoryReadCapability.
4. **Error resilience**: read retorna [] on exception, write retorna False on exception.
5. **E2E con memory**: `build_kernel_bundle_from_rag` con `rag.memory` crea MemoryPortAdapter automaticamente, provenance visible en `out.metadata["memory_hits"]`.

## Conclusiones

- Los contratos ADR-0009 y ADR-0015 son implementables sin congelar esquema interno.
- Provenance se agrega en el adapter, no en MemorySystem, preservando separacion de concerns.
- KnowledgeSystemAdapter reserva la frontera para el Knowledge Architect futuro.
- No hay regresion en la suite existente (127 passed).

## Pendiente

- Write controlado y verificado (Fase 7).
- Knowledge Architect con entidades/relaciones (P11, diferido).
- Integracion de get_entity con entity_extractor existente.
