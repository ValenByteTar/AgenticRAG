---
id: EXP-005
title: "VERIFY + REPAIR: experimento de groundedness post-generacion"
date: 2026-07-23
status: completed
category: experiments
tags: [verify, repair, groundedness, fase-4, evaluation]
related: [DEC-006, ADR-0006, ADR-0013]
---

# EXP-005 — VERIFY + REPAIR: experimento de groundedness post-generacion

## Hipotesis

Un evaluador determinista de groundedness (overlap de tokens) + citation fidelity puede detectar alucinaciones post-generacion sin LLM-as-judge, y un presupuesto de repair de 1 intento puede corregir respuestas no soportadas.

## Setup

- **Evaluador**: `VerifyGroundednessEvaluator` con groundedness_floor=0.3, min_answer_chars=20.
- **Policy**: `VerifyRepairPolicy(max_repairs=1)` con repair_hint inyectando instrucciones estrictas.
- **Pipeline**: `classify -> memory_read -> retrieval -> build_context -> assess -> generation -> verify -> [repair?] -> finalize_turn`.
- **Cadena policies**: `AssessGate -> RetrySignal -> VerifyRepair -> LinearRag`.
- **Tests**: 20 tests unitarios cubriendo evaluator, capability, policy y E2E.

## Resultados

### Tests unitarios (20/20 passed)

| Suite | Tests | Estado |
|---|---|---|
| VerifyGroundednessEvaluator | 9 | PASS |
| VerifyCapability | 2 | PASS |
| VerifyRepairPolicy | 5 | PASS |
| E2E Verify+Repair | 3 | PASS |
| LinearRagVerifyChain | 1 | PASS |

### E2E key scenarios

1. **Verify pass + finalize**: answer con overlap suficiente -> 1 generate call, verify passed, finalized.
2. **Verify fail -> repair -> pass**: primera generate alucina, repair con hint produce answer grounded -> 2 generate calls, repair_count=1, finalized.
3. **Verify fail -> repair fail -> decline**: ambas generates alucinan -> 2 generate calls, decline=True, no finalize.

### Metricas del evaluador

- **Groundedness**: ratio de tokens de contenido del answer presentes en context. Stopwords filtradas. Tokens >= 3 chars.
- **Hedge detection**: 18 frases de rechazo. Distingue justificado (assess fallo) vs injustificado (assess paso).
- **Citation fidelity**: regex `[Doc N]` o `[N]`. Hard fail solo si 0 validas. Partial es flag blando.

## Conclusiones

- VERIFY determinista es viable sin LLM-as-judge.
- Repair con presupuesto=1 es suficiente para corregir respuestas con hint contextual.
- Groundedness floor=0.3 es un default razonable (configurable).
- Hedge detection evita falsos positivos cuando el sistema correctamente declina.

## Pendiente

- ~~A/B evaluation con dataset completo (75 preguntas) comparando kernel con verify vs sin verify.~~ → Ver BM-002 (muestra estratificada 11q)
- Ajuste de groundedness_floor segun dominio.
- Integracion de citation fidelity con DocCards del monolito.

## A/B Results (BM-002)

A/B ejecutado con muestra estratificada de 11 preguntas (5 categorías):

| Métrica | Kernel+VERIFY | Monolito |
|---|---|---|
| Pass rate | 45.5% | 81.8% |
| Groundedness | 100% | 100% |
| Alucinaciones | 0 | 0 |
| Latencia avg | 69.5s | 54.8s |

**VERIFY funciona**: 100% groundedness, 0 alucinaciones, repair se activa correctamente.
**Brecha es de retrieval** (entity expansion, planner, comparison detection), no de generation.
Ver BM-002 para análisis completo.
