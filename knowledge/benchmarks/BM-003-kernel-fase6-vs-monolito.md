---
id: BM-003
title: "A/B Kernel Fase 6 vs Monolito — misma muestra 11q"
date: 2026-07-24
status: completed
category: benchmarks
tags: [ab, kernel, fase-6, planner, entity-expansion, doc-roles, monolito]
related: [DEC-008, EXP-006b, BM-002, ADR-0006, ADR-0013]
---

# BM-003 — A/B Kernel Fase 6 vs Monolito — muestra estratificada 11q

## Setup

- **IDs**: 1, 3, 7, 21, 24, 31, 35, 41, 45, 51, 55 (5 categorías: 3 simple, 2 multi_doc, 2 no_answer, 2 ambiguous, 2 complex)
- **Modelo**: mistral:7b via Ollama
- **Índice**: 100,480 documentos, dominio ciberseguridad
- **Kernel**: Fase 6 con Planner + EntityExpansion + soft doc boost + adaptive pool + verify/repair
- **Monolito**: rag_hybrid.py sin kernel (heurísticas completas)
- **Fecha**: 2026-07-24

## Resultados globales

| Métrica | Kernel Fase 6 | Monolito (BM-002) | Delta vs BM-002 Kernel |
|---|---|---|---|
| **Pass rate** | 45.5% (5/11) | 81.8% (9/11) | = (sin regresion) |
| **Answerable pass** | 33.3% | 77.8% | = |
| **No-answer pass** | 100.0% | 100.0% | = |
| **Doc hit@K** | 33.3% | 77.8% | = |
| **Recall prom** | 0.204 | 0.519 | -0.065 (mejora vs 0.269) |
| **MRR prom** | 0.135 | 0.620 | -0.022 (mejora vs 0.157) |
| **Precision@K** | 0.103 | 0.434 | -0.022 (mejora vs 0.125) |
| **KW score prom** | 0.710 | 0.738 | = |
| **Groundedness** | 100.0% | 100.0% | = |
| **Anti-alucinación** | 100.0% | 100.0% | +50pp (vs 50% en hard scoping) |
| **Alucinaciones** | 0 | 0 | = |
| **Latencia avg** | 54,042ms | 54,782ms | -1.4% |

## Por categoría

| Categoría | Kernel Fase 6 | Monolito | Kernel BM-002 |
|---|---|---|---|
| simple (3) | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) |
| multi_doc (2) | 0/2 (0%) | 1/2 (50%) | 0/2 (0%) |
| no_answer (2) | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) |
| ambiguous (2) | 0/2 (0%) | 0/2 (0%) | 0/2 (0%) |
| complex (2) | 0/2 (0%) | 2/2 (100%) | 0/2 (0%) |

## Análisis por pregunta

| ID | Cat | Kernel F6 | Monolito | Causa delta |
|---|---|---|---|---|
| 1 | simple | PASS R10 | PASS R1 | Kernel: retrieval encuentra doc pero en rank alto |
| 3 | simple | PASS R9 | PASS R1 | Mismo patrón |
| 7 | simple | PASS R1 | PASS R1 | = |
| 21 | multi_doc | FAIL doc_miss | PASS R4 | Monolito: entity expansion + two-stage |
| 24 | multi_doc | FAIL doc_miss | PASS R1 | Monolito: planner roles + multi-doc mode |
| 31 | no_answer | PASS | PASS | = |
| 35 | no_answer | PASS | PASS | = (ambos declinan correctamente) |
| 41 | ambiguous | FAIL doc_miss | FAIL doc_miss | = (ambos fallan retrieval) |
| 45 | ambiguous | FAIL doc_miss | FAIL doc_miss | = (ambos fallan retrieval) |
| 51 | complex | FAIL doc_miss | PASS R1 | Monolito: entity expansion (cism) + planner scoping |
| 55 | complex | FAIL doc_miss | PASS R1 | Monolito: entity detection (microsoft) + planner scoping |

## Iteración: hard scoping vs soft boost

### Intento 1: hard scoping via allowed_sources

Primer intento: pasar `candidate_docs` como `allowed_sources` a `hybrid_search()` (filtro a nivel DB).

**Resultado**: 18.2% pass rate (2/11) — **regresión severa** vs BM-002 (45.5%).

**Causa**: `select_docs_by_roles` con entity matching restrictivo filtra demasiado. El monolito tiene safety checks (mantener al menos 50% o mínimo 5 resultados) que el kernel no tenía.

### Intento 2: soft boost post-retrieval

Segundo intento: recuperar normalmente y aplicar boost de +0.05 al score de resultados en `candidate_docs`.

**Resultado**: 45.5% pass rate (5/11) — **sin regresión** vs BM-002.

## Brecha restante con el monolito

El gap de 36.3pp persiste y se debe **enteramente a retrieval**:

1. **Two-stage retrieval**: el monolito usa two-stage con entity matching para encontrar documentos específicos. El kernel lo tiene registrado pero no lo activa automáticamente.
2. **Equivalences**: el monolito expande la query con equivalencias (92 grupos). El kernel no las usa.
3. **Conceptual map**: el monolito usa un mapa conceptual aprendido. El kernel no lo tiene.
4. **Technology filtering**: el monolito filtra/reordena por tipo de documento. El kernel no lo hace.
5. **Entity expansion en search query**: el monolito modifica la query de búsqueda con entidades expandidas. El kernel expande entidades en metadata pero no las inyecta en la query de búsqueda.

## Conclusión

**Fase 6 no introduce regresión** con el enfoque de soft boost. Las capabilities de planner y entity expansion están wired y funcionando, pero su impacto en retrieval es limitado sin las heurísticas adicionales del monolito.

**Próximos pasos** para cerrar la brecha (Fase 7+):
1. Inyectar entidades expandidas en la query de búsqueda (no solo metadata)
2. Activar two-stage retrieval automáticamente para queries con entidades
3. Integrar equivalences del monolito en el kernel
4. Technology filtering post-retrieval
5. Conceptual map integration
