---
id: BM-004
category: benchmark
status: completed
created: 2026-07-24
updated: 2026-07-28
author: human
components: [kernel, retrieval, two-stage-retrieval, entity-expansion, planner]
tags: [ab, kernel, fase-6, bug-fixes, data-flow, monolito, retrieval]
related: [BM-003, DEC-008, DEC-010, EXP-006b, ADR-0006, ADR-0018, RES-001, RES-002, RES-003]
supersedes: null
superseded_by: null
---

# BM-004 - A/B Kernel Fase 6 + bug fixes de data flow vs Monolito

## Goal

Medir el impacto de cerrar dos gaps de data flow en el Consumer identificados en BM-003, sobre la misma muestra 11q y el mismo comparador monolito (81.8% pass).

Bug fixes medidos:

1. **`expanded_entities` inyectadas en la query de busqueda**: `RetrievalCapability` y `TwoStageRetrievalCapability` dejan de expandir solo en metadata y modifican la query.
2. **Two-stage activado automaticamente**: `LinearRagPolicy` activa `two_stage_retrieval` en el primer pass cuando hay entidades (deja de ser solo retry).

## Environment

- Commit / tag: posterior a BM-003 (reporte `20260724_194640`, mismo dia)
- `kernel.enabled`: true
- Modelo LLM: mistral:7b via Ollama
- Coleccion / indice: 100,480 documentos, dominio ciberseguridad
- Hardware: local

## Dataset

Muestra estratificada 11q, identica a BM-002/BM-003:

- IDs: 1, 3, 7, 21, 24, 31, 35, 41, 45, 51, 55
- Categorias: 3 simple, 2 multi_doc, 2 no_answer, 2 ambiguous, 2 complex

## Metrics

Pass rate end-to-end, answerable pass, no-answer pass, doc hit@K, recall promedio (multi-doc), MRR, precision@K, keyword score, groundedness, anti-alucinacion, latencia.

## Results

| Metrica | Kernel F6 + fixes (BM-004) | Kernel F6 (BM-003) | Monolito (BM-002/003) |
|---|---|---|---|
| **Pass rate** | **54.5% (6/11)** | 45.5% (5/11) | 81.8% (9/11) |
| Answerable pass | 44.4% | 33.3% | 77.8% |
| No-answer pass | 100.0% | 100.0% | 100.0% |
| **Doc hit@K** | **44.4%** | 33.3% | 77.8% |
| Recall prom (multi-doc) | 0.259 | 0.204 | 0.519 |
| **MRR prom** | **0.246** | 0.135 | 0.620 |
| Precision@K | 0.136 | 0.103 | 0.434 |
| KW score prom | 0.706 | 0.710 | 0.738 |
| Groundedness | 100.0% | 100.0% | 100.0% |
| Anti-alucinacion | 100.0% | 100.0% | 100.0% |
| Alucinaciones | 0 | 0 | 0 |
| Latencia avg | 46,194 ms | 54,042 ms | 54,782 ms |

### Por categoria

| Categoria | BM-004 | BM-003 | Monolito |
|---|---|---|---|
| simple (3) | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) |
| multi_doc (2) | 0/2 (0%) | 0/2 (0%) | 1/2 (50%) |
| no_answer (2) | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) |
| ambiguous (2) | **1/2 (50%)** | 0/2 (0%) | 0/2 (0%) |
| complex (2) | 0/2 (0%) | 0/2 (0%) | 2/2 (100%) |

### Deltas vs BM-003

- **+1 pregunta PASS**: Q41 (ambiguous) pasa a PASS
- **+11.1pp doc hit@K** (33.3% -> 44.4%)
- **+0.111 MRR** (0.135 -> 0.246)
- Brecha con monolito reducida de 36.3pp a **27.3pp**

## Lectura arquitectonica

Los bug fixes mejoraron el **consumo** de conocimiento ya disponible en el Consumer. No resolvieron la ausencia de un Knowledge Model compilado de alta calidad:

- Las queries restantes que fallan (21, 24, 45, 51, 55) lo hacen porque el Consumer no dispone de conocimiento de dominio compilado (gazetteer completo, equivalencias, relaciones tipadas, roles ricos).
- El soft boost del Planner (+0.05) sigue siendo debil frente a scores del reranker.

Esto fundamenta ADR-0018 y los RES-001/002/003: la brecha restante es trabajo de **compilacion** (index-time), no de parches en runtime (query-time).

Artefactos:

- `tests/eval/reports/report_20260724_194640.json`
- `tests/eval/reports/report_20260724_194640.md`
- Contexto de la iteracion: `tests/eval/reports/report_20260724_174814.*` (hard scoping, 18.2%), `tests/eval/reports/report_20260724_180126.*` (soft boost, 45.5%)
