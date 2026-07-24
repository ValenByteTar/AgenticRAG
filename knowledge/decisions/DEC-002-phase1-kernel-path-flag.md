---
id: DEC-002
category: decision
status: accepted
created: 2026-07-23
updated: 2026-07-23
author: cascade
components: [kernel, control, capabilities, policies, facade, evaluation]
tags: [phase1, close, kernel-enabled, parity, facade]
related: [ADR-0002, ADR-0003, ADR-0006, ADR-0009, ADR-0010, ADR-0013, ADR-0017, BM-001, EXP-001]
supersedes: null
superseded_by: null
---

# DEC-002 - Cierre Fase 1: camino kernel lineal detras de flag

## Context

Fase 1 debia migrar el control de `query()` al Controller FSM con paridad 1:1 y sin romper la fachada (ADR-0010). El monolito sigue existiendo como `_query_linear_impl`.

## Decision

1. `query()` despacha por `kernel.enabled` (default **false**).
2. Camino kernel F1.c fijo via `LinearRagPolicy` + `AssessGatePolicy`:
   classify -> memory_read -> retrieve(+sticky+rerank) -> build_context(+mem) -> assess -> generate -> finalize_turn.
3. ASSESS es Evaluation online (ADR-0006): produce `EvaluationSignal`; Policy decide decline.
4. Memory en kernel es **solo lectura** (ADR-0009); write/aprendizaje no migrado.
5. Harness soporta `python tests/eval/run_cybersec_eval.py --kernel` para A/B sin cambiar default.
6. Entity two-stage y streaming del monolito quedan **fuera** del camino kernel en F1 (diferidos).
7. Default `kernel.enabled=true` **no** se activa hasta A/B medible vs BM-001 (EXP-001 results).

## Consequences

- Flag off: comportamiento historico del monolito.
- Flag on: Controller + capabilities; contrato de retorno estable.
- Cierre de codigo Fase 1 aceptado con gates unitarios; paridad de calidad offline queda como EXP-001 en ejecucion cuando haya LLM+indice.

## Alternatives

- Reescribir monolito completo en un solo PR (rechazado: riesgo alto, P incremental).
- Activar kernel por default sin A/B (rechazado: viola gates BM-001).
