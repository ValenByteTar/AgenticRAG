---
id: DEC-004
category: decision
status: accepted
created: 2026-07-23
updated: 2026-07-23
author: cascade
components: [policies, retrieval, kernel, two-stage]
tags: [phase3, retry, two-stage, multi-retry, budget, entity-search]
related: [ADR-0006, ADR-0013, ADR-0017, EXP-001, EXP-002, EXP-003, DEC-003]
supersedes: null
superseded_by: null
---

# DEC-004 - Fase 3: Multi-retry con two-stage entity retrieval

## Context

Fase 2 introdujo RetrySignalPolicy con max_retries=1 y solo retrieval basico. Casos donde el primer retry no mejora entity coverage quedaban sin recuperacion. El monolito tiene two-stage entity search que busca docs especificos por entidad, pero no estaba portado al kernel.

## Decision

1. `RetrySignalPolicy` expandida a `max_retries=2` con budget check:
   - Retry 1: `capability_ref=retrieval` con `relax_entity_filter`, `boost_diversity`
   - Retry 2: `capability_ref=two_stage_retrieval` con `entity_focused=True`
   - Si no hay entidades en retry 2: fallback a `retrieval` con `widen_top_k`

2. `TwoStageRetrievalCapability` nueva capability:
   - Recibe `EntitySearchFn(query, entities, top_k, sw) -> list[dict]`
   - Limpia context/assessed stale como RetrievalCapability
   - Marca `metadata.two_stage_executed = True`

3. `RetrievalCapability` maneja nuevos params F3:
   - `widen_top_k`: top_k *= 1.5
   - `boost_diversity`: semantic_weight = max(0.3, sw - 0.15)

4. Adapter `_two_stage_retrieve` en `build_kernel_bundle_from_rag`:
   - Delega a `rag._two_stage_entity_search` si existe
   - Fallback: per-entity hybrid_search con sw=0.3, dedup, rerank, stage_boost=1.20

5. Budget: `RetrySignalPolicy` verifica `state.budget_exhausted()` antes de decidir retry.

## Consequences

- Hasta 2 retries por query, acotados por budget.
- Two-stage entity search portada al kernel sin reimplementar logica del monolito.
- No rompe paridad F1/F2: si no hay senales blandas, no hay retry.
- Observabilidad: traces registran retry_count, widen_top_k, boost_diversity, two_stage_executed.

## Alternatives

- Retry con LLM reasoning para generar nuevos terminos (rechazado: gasta budget de LLM; diferido a F4+)
- Two-stage como policy en lugar de capability (rechazado: policy decide, no ejecuta; two-stage es retrieval)
