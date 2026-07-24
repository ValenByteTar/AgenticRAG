---
id: DEC-003
category: decision
status: accepted
created: 2026-07-23
updated: 2026-07-23
author: cascade
components: [evaluation, assess, policies, kernel]
tags: [phase2, assess, enriched, entity-coverage, retry, signals]
related: [ADR-0006, ADR-0013, ADR-0017, EXP-001, EXP-002, DEC-002]
supersedes: null
superseded_by: null
---

# DEC-003 - Fase 2: ASSESS enriquecido con senales blandas

## Context

Fase 1 ASSESS tenia gates binarios (rerank floor, factual gate, vacio). Casos donde retrieval devuelve docs con buen score pero irrelevantes a la entidad preguntada pasaban el gate y generaban respuestas degradadas.

## Decision

1. ASSESS produce 4 senales blandas ademas de pass/fail:
   - `entity_coverage_ratio`: fraccion de entidades del query presentes en contexto
   - `source_diversity`: nº de sources distintos en results
   - `context_density`: tokens unicos / tokens totales
   - `assess_precision_proxy`: quality_results / total_results

2. Hard gate 5 nuevo: entity_coverage = 0 con entidades presentes y floor configurable (default 0.0 para no romper paridad F1).

3. Flags blandos `entity_coverage_low` y `source_diversity_low` alimentan RetrySignalPolicy.

4. `RetrySignalPolicy` (max_retries=1) se registra entre AssessGatePolicy y LinearRagPolicy. Si assess paso pero con flags bajos, decide retry con `capability_ref=retrieval`.

5. `RetrievalCapability` limpia `context` y `assessed` stale al recibir params de retry, para que build_context y assess re-executen.

6. Score enriquecido: bonuses por coverage (+0.15), diversity (+0.10), density (+0.05).

## Consequences

- ASSESS ahora detecta evidencia topicalmente irrelevante que gates duros no capturan.
- RetrySignalPolicy prepara el terreno para F3 (multi-retry, two-stage entity).
- No rompe paridad F1: entity_coverage_floor default 0.0.
- Observabilidad rica: metadata del signal disponible para trazas y metricas offline.

## Alternatives

- ASSESS con LLM judge (rechazado: latencia + no determinista; diferido a F4 VERIFY)
- Retry sin senales blandas (rechazado: retry incondicional desperdicia budget)
