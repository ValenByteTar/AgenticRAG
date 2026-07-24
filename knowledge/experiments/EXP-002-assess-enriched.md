---
id: EXP-002
category: experiment
status: accepted
created: 2026-07-23
updated: 2026-07-23
author: cascade
components: [evaluation, assess, policies, kernel]
tags: [phase2, assess, enriched, entity-coverage, retry, signals]
related: [ADR-0006, ADR-0013, ADR-0017, EXP-001, DEC-002, DEC-003]
supersedes: null
superseded_by: null
---

# EXP-002 - ASSESS enriquecido: senales blandas + retry signal

## Hypothesis

Senales blandas (entity_coverage, source_diversity, context_density) en ASSESS permiten detectar evidencia insuficiente que los gates duros (rerank floor, factual gate) no capturan, y RetrySignalPolicy puede corregir via re-retrieval sin degradar latencia p50.

## Motivation

Fase 1 ASSESS solo tenia gates binarios (pass/fail). Casos donde el retrieval devuelve docs con buen score pero irrelevantes a la entidad preguntada pasaban el gate y generaban respuestas degradadas.

## Configuration

- Evaluator: `AssessEvidenceEvaluator` con 5 hard gates + 4 senales blandas
- Policy: `RetrySignalPolicy(max_retries=1)` entre AssessGate y LinearRag
- Senales blandas: entity_coverage_ratio, source_diversity, context_density, assess_precision_proxy
- Flags blandos: entity_coverage_low (<0.5), source_diversity_low (<=1 con >3 results)
- Hard gate 5: entity_coverage=0 con floor configurable (default off para no romper paridad F1)
- Tests: `tests/unit/test_phase2_assess_enriched.py` — 44 passed total suite

## Metrics

- entity_coverage_ratio: matched/total entidades en contexto
- source_diversity: nº sources distintos en top-k
- context_density: tokens unicos / tokens totales
- assess_precision_proxy: quality_results / total_results
- retry_yield: % queries donde retry mejoro entity_coverage de 0 a >0
- latencia overhead: p50 con retry vs sin retry (informativo)

## Results

### A. Scaffold / cierre de codigo (2026-07-23)

| Check | Resultado |
|-------|-----------|
| Entity coverage full/partial/zero | PASS |
| Source diversity multi/single | PASS |
| Context density normal/repetitive | PASS |
| Metadata enriquecida en signal pass | PASS |
| Entity coverage = 0 hard fail (floor>0) | PASS |
| Entity coverage = 0 sin floor → pass + flag low | PASS |
| Source diversity low flag | PASS |
| RetrySignalPolicy fire on low coverage | PASS |
| RetrySignalPolicy fire on low diversity | PASS |
| RetrySignalPolicy no fire on good signals | PASS |
| RetrySignalPolicy no fire on max_retries | PASS |
| RetrySignalPolicy no fire on assess fail | PASS |
| E2E retry flow (retrieve→assess→retry→re-retrieve→assess→generate) | PASS |
| AssessGate still declines on hard fail | PASS |
| Suite total | **44 passed** |

### B. Offline vs BM-001 (pendiente de entorno)

No ejecutado. Requiere rank_bm25 + Chroma + Ollama.

## Conclusion

**Codigo Fase 2 cerrado.** ASSESS ahora produce senales ricas para policies de retry (F3) y observabilidad. RetrySignalPolicy funcional con max_retries=1.

**Validacion de calidad offline** queda pendiente (seccion B).

## Recommendation

- [x] Experiment (cerrado en scaffold; seccion B abierta)
- [ ] Benchmark (si seccion B pasa: BM-003 assess_enriched)
- [x] Decision (DEC-003)
- [ ] Nothing
