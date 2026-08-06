---
id: BM-002
title: "A/B Kernel+VERIFY vs Monolito — muestra estratificada 11q"
date: 2026-07-23
status: completed
category: benchmarks
tags: [ab, kernel, verify, repair, monolito, fase-4]
related: [DEC-006, EXP-005, BM-001, ADR-0006, ADR-0013]
---

# BM-002 — A/B Kernel+VERIFY vs Monolito — muestra estratificada 11q

## Setup

- **IDs**: 1, 3, 7, 21, 24, 31, 35, 41, 45, 51, 55 (5 categorías: 3 simple, 2 multi_doc, 2 no_answer, 2 ambiguous, 2 complex)
- **Modelo**: mistral:7b via Ollama
- **Índice**: 100,480 documentos, dominio ciberseguridad
- **Reranker**: BGE reranker, pool=35 (kernel) / 10-13 (monolito)
- **Kernel**: Fase 4 con VERIFY + VerifyRepairPolicy(max_repairs=1)
- **Monolito**: rag_hybrid.py sin kernel (heurísticas completas)
- **Fecha**: 2026-07-23

## Resultados globales

| Métrica | Kernel+VERIFY | Monolito | Delta |
|---|---|---|---|
| **Pass rate** | 45.5% (5/11) | 81.8% (9/11) | **-36.3pp** |
| **Answerable pass** | 33.3% | 77.8% | -44.5pp |
| **No-answer pass** | 100.0% | 100.0% | = |
| **Doc hit@K** | 33.3% | 77.8% | -44.5pp |
| **Recall prom** | 0.269 | 0.519 | -0.250 |
| **MRR prom** | 0.157 | 0.620 | -0.463 |
| **Precision@K** | 0.125 | 0.434 | -0.309 |
| **KW score prom** | 0.710 | 0.738 | -0.028 |
| **Groundedness** | 100.0% | 100.0% | = |
| **Anti-alucinación** | 100.0% | 100.0% | = |
| **Alucinaciones** | 0 | 0 | = |
| **Latencia avg** | 69,535ms | 54,782ms | +27.0% |
| **Latencia p50** | 58,524ms | 49,499ms | +18.2% |

## Por categoría

| Categoría | Kernel pass | Monolito pass | Kernel recall | Monolito recall |
|---|---|---|---|---|
| simple (3) | 3/3 (100%) | 3/3 (100%) | 0.806 | 0.917 |
| multi_doc (2) | 0/2 (0%) | 1/2 (50%) | 0.000 | 0.375 |
| no_answer (2) | 2/2 (100%) | 2/2 (100%) | N/A | N/A |
| ambiguous (2) | 0/2 (0%) | 0/2 (0%) | 0.000 | 0.000 |
| complex (2) | 0/2 (0%) | 2/2 (100%) | 0.000 | 0.750 |

## Análisis por pregunta

| ID | Cat | Kernel | Monolito | Causa delta |
|---|---|---|---|---|
| 1 | simple | PASS R4 | PASS R1 | Kernel: rerank pool=35 diluye; monolito: heurísticas entity+two-stage |
| 3 | simple | PASS R6 | PASS R1 | Mismo patrón |
| 7 | simple | PASS R1 | PASS R1 | = |
| 21 | multi_doc | FAIL doc_miss | PASS R4 | Monolito: entity expansion (iso 27001 → iso27001, iso 27k, isms) + comparison detection |
| 24 | multi_doc | FAIL doc_miss | PASS R1 | Monolito: planner roles + procedural detection + multi-doc mode |
| 31 | no_answer | PASS | PASS | = (ambos declinan correctamente) |
| 35 | no_answer | PASS | PASS | = (ambos declinan correctamente) |
| 41 | ambiguous | FAIL doc_miss | FAIL doc_miss | = (ambos fallan retrieval) |
| 45 | ambiguous | FAIL doc_miss | FAIL doc_miss | = (ambos fallan retrieval) |
| 51 | complex | FAIL doc_miss | PASS R1 | Monolito: entity expansion (cism) + planner roles + multi-doc mode |
| 55 | complex | FAIL doc_miss | PASS R1 | Monolito: entity detection (microsoft) + planner scoping |

## Observaciones de VERIFY + REPAIR

### Repair activado
En todas las preguntas donde se generó respuesta (9/11), se observaron **2 calls a Ollama** — la primera generate y la segunda repair. Esto indica que VERIFY detectó groundedness insuficiente en la primera respuesta y VerifyRepairPolicy activó repair.

**Sin embargo**, las respuestas reparadas fueron casi idénticas a las originales (mismo contenido, leve reformulación). El repair_hint actual (instrucciones de texto) no cambia significativamente el comportamiento del LLM.

### Groundedness 100%
Ambos caminos logran 100% groundedness y 0 alucinaciones. VERIFY no introduce falsos negativos en este sample.

### No-answer detection
El kernel detecta correctamente no-answer vía reranker score bajo (sin LLM), igual que el monolito vía factual_gate.

## Brecha principal: retrieval

El gap de 36.3pp entre kernel y monolito se debe **enteramente a retrieval**, no a generation ni groundedness:

- **Entity expansion**: el monolito expande entidades (`iso 27001` → `iso27001, iso 27k, isms`; `cism` → `certified information security manager`). El kernel no tiene esto.
- **Planner roles**: el monolito usa un planner que preselecciona documentos por rol (procedure, manual, analysis_report). El kernel no tiene planner.
- **Comparison detection**: el monolito detecta queries comparativas y balancea búsqueda entre entidades. El kernel no tiene esto.
- **Two-stage retrieval**: el monolito usa two-stage con entity matching para encontrar documentos específicos. El kernel lo tiene registrado pero no lo activa automáticamente.
- **Reranker pool**: kernel usa pool=35 fijo; monolito usa 10-13 adaptativo. Pool más grande diluye scores.

## Conclusión

**VERIFY + REPAIR funciona correctamente** como mecanismo anti-alucinación:
- 100% groundedness, 0 alucinaciones
- Repair se activa cuando groundedness es baja
- No introduce falsos negativos

**La brecha con el monolito es de retrieval, no de generation**. Las heurísticas del monolito (entity expansion, planner roles, comparison detection, adaptive pool) son responsables del gap. Esto era esperado y consistente con BM-001.

**Próximos pasos** para cerrar la brecha (Fase 5+):
1. Entity expansion en kernel (capability pre-retrieval)
2. Planner determinista (Fase 6)
3. Adaptive reranker pool
4. Comparison detection policy
5. Mejorar repair_hint para que sea más efectivo (no solo texto, sino parámetros de generación)