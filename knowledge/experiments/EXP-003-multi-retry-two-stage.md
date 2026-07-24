---
id: EXP-003
category: experiment
status: accepted
created: 2026-07-23
updated: 2026-07-23
author: cascade
components: [policies, retrieval, kernel, two-stage]
tags: [phase3, retry, two-stage, multi-retry, budget, entity-search]
related: [ADR-0006, ADR-0013, ADR-0017, EXP-001, EXP-002, DEC-003, DEC-004]
supersedes: null
superseded_by: null
---

# EXP-003 - Multi-retry con two-stage entity retrieval

## Hypothesis

Multi-retry con budget acotado (max 2) y two-stage entity search en el segundo intento mejora entity_coverage y doc_hit sin degradar latencia p50 ni exceder presupuesto de LLM.

## Motivation

Fase 2 introdujo RetrySignalPolicy con max_retries=1 y solo retrieval basico. Casos donde el primer retry no mejora entity coverage quedaban sin recuperacion. El monolito tiene two-stage entity search que busca docs especificos por entidad, pero no estaba portado al kernel.

## Configuration

- Policy: `RetrySignalPolicy(max_retries=2)` entre AssessGate y LinearRag
- Retry 1: `capability_ref=retrieval` con `relax_entity_filter=True`, `boost_diversity=True`
  - `boost_diversity`: semantic_weight -= 0.15 (min 0.3)
  - `widen_top_k`: top_k *= 1.5 (solo si no hay entidades para retry 2)
- Retry 2: `capability_ref=two_stage_retrieval` con `entity_focused=True`
  - Per-entity search (top 3 entidades) con sw=0.3
  - Dedup por source+page
  - Rerank si disponible
  - stage_boost=1.20 en hybrid_score
- Budget: respeta `state.budget_exhausted()` antes de decidir retry
- `TwoStageRetrievalCapability`: nueva capability con `EntitySearchFn` inyectado
- Adapter `_two_stage_retrieve` en `build_kernel_bundle_from_rag`: fallback a per-entity hybrid_search si RAG no tiene `_two_stage_entity_search`
- Tests: `tests/unit/test_phase3_retry_two_stage.py` — 54 passed total suite

## Metrics

- retry_yield: % queries donde retry mejoro entity_coverage de <0.5 a >0.5
- retry_count: nº de retries ejecutados por query (0, 1, o 2)
- two_stage_activation: % queries donde retry 2 uso two_stage_retrieval
- latency_overhead: p50/p90 con retry vs sin retry (informativo)
- budget_exhaustion_rate: % queries donde budget detuvo retry

## Results

### A. Scaffold / cierre de codigo (2026-07-23)

| Check | Resultado |
|-------|-----------|
| TwoStageRetrievalCapability with entities | PASS |
| TwoStageRetrievalCapability skipped no entities | PASS |
| TwoStageRetrievalCapability falls back to classification entities | PASS |
| Retry 1 uses retrieval with boost_diversity | PASS |
| Retry 2 uses two_stage_retrieval with entities | PASS |
| Retry 2 no entities falls back to retrieval widen_top_k | PASS |
| Retry respects budget_exhausted | PASS |
| Retry max_retries=2 no third retry | PASS |
| E2E multi-retry: retrieve -> retry1 -> retry2(two_stage) -> generate | PASS |
| E2E budget stops retry | PASS |
| Suite total | **54 passed** |

### B. Offline vs BM-001 (pendiente de entorno)

No ejecutado. Requiere rank_bm25 + Chroma + Ollama.

## Conclusion

**Codigo Fase 3 cerrado.** Multi-retry con two-stage entity search funcional. Budget respeta max_iterations y max_llm_calls. TwoStageRetrievalCapability portada del monolito al kernel con adapter.

**Validacion de calidad offline** queda pendiente (seccion B).

## Recommendation

- [x] Experiment (cerrado en scaffold; seccion B abierta)
- [ ] Benchmark (si seccion B pasa: BM-004 retry_yield)
- [x] Decision (DEC-004)
- [ ] Nothing
