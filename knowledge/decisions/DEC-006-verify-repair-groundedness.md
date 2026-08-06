---
id: DEC-006
title: "VERIFY + REPAIR: groundedness post-generacion con presupuesto de reparacion"
date: 2026-07-23
status: accepted
category: decisions
tags: [verify, repair, groundedness, fase-4, evaluation]
related: [ADR-0006, ADR-0013, DEC-005]
---

# DEC-006 — VERIFY + REPAIR: groundedness post-generacion con presupuesto de reparacion

## Contexto

El camino Kernel (Fases 1-3) implementa ASSESS (suficiencia de evidencia pre-generacion) pero no valida la respuesta generada. Sin VERIFY, el sistema puede producir respuestas no soportadas por el contexto (alucinaciones) sin mecanismo de deteccion ni reparacion.

El monolito HybridRAG tiene heuristicas dispersas (post-procesamiento, factual_gate) pero no estructuradas como evaluacion online.

## Decision

Implementar VERIFY como evaluador online (ADR-0006) post-generacion con tres chequeos deterministas:

1. **Groundedness**: overlap de tokens de contenido entre answer y context. Floor configurable (default 0.3).
2. **Hedge detection**: si el answer contiene frases de rechazo pero ASSESS paso, es un hedge injustificado (fail). Si ASSESS fallo, el hedge es justificado (pass).
3. **Citation fidelity**: marcadores `[Doc N]` o `[N]` en el answer deben corresponder a results reales. Falla solo si 0 citas validas.

### Repair

`VerifyRepairPolicy` (ADR-0013) observa la senal VERIFY:
- Si fallo y `repair_count < max_repairs` (default 1): decide `retry` con `repair_hint` que prependa instrucciones estrictas al contexto.
- Si fallo y presupuesto agotado: decide `decline`.
- Si paso: no actua.

### Cadena de policies

```
AssessGatePolicy -> RetrySignalPolicy -> VerifyRepairPolicy -> LinearRagPolicy
```

### Pipeline

```
classify -> memory_read -> retrieval -> build_context -> assess -> generation -> verify -> finalize_turn
```

## Consecuencias

- Deteccion determinista de alucinaciones sin LLM-as-judge (zero-cost).
- Repair con presupuesto acotado (1 intento por defecto) evita loops infinitos.
- Groundedness floor configurable permite ajustar sensibilidad.
- Hedge detection distingue declives correctos (assess fallo) de evasivas injustificadas (assess paso).
- Citation fidelity como flag blando (no hard gate) salvo 0 validas.

## Alternativas

- LLM-as-judge para verificar (rechazado: costo + latencia + no determinista).
- VERIFY como capability normal, no evaluator (rechazado: ADR-0006 separa evaluation de execution).
- Sin repair, solo decline (rechazado: desperdicia oportunidad de correccion).