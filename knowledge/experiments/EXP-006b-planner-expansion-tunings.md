---
id: EXP-006b
title: "Fase 6: Planner + Entity Expansion + Tunings — experimento"
date: 2026-07-24
status: completed
category: experiments
tags: [planner, entity-expansion, retrieval, tuning, fase-6]
related: [DEC-008, BM-002]
---

# EXP-006b — Fase 6: Planner + Entity Expansion + Tunings

## Hipotesis

Portar entity expansion y planner del monolito al kernel, junto con tunings de reranker pool, repair_hint y groundedness floor, cerrara el gap de -44.5pp en doc hit rate identificado en BM-002.

## Setup

- **PlannerCapability**: determinista, detecta tipo de query, ajusta semantic_weight, asigna roles.
- **EntityExpansionCapability**: gazetteer de aliases (iso 27001 -> iso27001, iso 27k, isms).
- **Adaptive reranker pool**: 10/15/20 segun complejidad de query (vs 35 fijo).
- **Repair_hint mejorado**: instrucciones enumeradas, citacion [N], mas directivo.
- **Groundedness floor**: 0.3 -> 0.25 para dominio tecnico.
- **LinearRagPolicy**: cadena extendida con planner + entity_expansion antes de retrieval.
- **max_iterations**: default 10 -> 12 para acomodar cadena extendida.

## Resultados

### Tests unitarios (23/23 passed)

| Suite | Tests | Estado |
|---|---|---|
| PlannerCapability | 7 | PASS |
| EntityExpansionCapability | 6 | PASS |
| E2EPlannerEntityExpansion | 2 | PASS |
| AdaptiveRerankerPool | 1 | PASS |
| RepairHintImproved | 1 | PASS |
| GroundednessFloorAdjusted | 2 | PASS |
| EntityExtractorWiring | 2 | PASS |
| DocRolesWiring | 2 | PASS |

### Suite global: 150 passed (127 existentes + 23 nuevos, 0 regresion)

### Validaciones clave

1. **Planner**: detecta correctamente conceptual/comparison/procedural/numeric, ajusta semantic_weight, no overridea top_k.
2. **Entity expansion**: iso 27001 -> [iso 27001, iso27001, iso 27k, isms], dedup case-insensitive.
3. **Adaptive pool**: query corta "que es nist?" -> pool=10 (vs 35 fijo anterior).
4. **Repair_hint**: contiene "REPARACION REQUERIDA", instrucciones enumeradas, citacion [N].
5. **Groundedness floor**: 0.25 por defecto, permite borderline technical answers.
6. **E2E comparison**: "compara ISO 27001 con NIST CSF" -> is_comparison=True, semantic_weight=0.5.

## Conclusiones

- Las capabilities son deterministas y no requieren LLM.
- El planner no overridea top_k, respetando el contrato del retrieval adapter.
- Entity expansion usa gazetteer hardcoded (12 entidades de ciberseguridad).
- Los tunings son backward compatible (127 tests existentes pasan sin cambios de logica).
- A/B pendiente para validar mejora en doc hit rate.

## A/B completado (BM-003)

### Resultados kernel Fase 6 vs monolito (11q estratificadas)

| Métrica | Kernel F6 | Monolito | Delta |
|---|---|---|---|
| Pass rate | 45.5% (5/11) | 81.8% (9/11) | -36.3pp |
| Doc hit@K | 33.3% | 77.8% | -44.5pp |
| Anti-alucinacion | 100% | 100% | = |
| Groundedness | 100% | 100% | = |

### Iteracion: hard scoping vs soft boost

- **Hard scoping** (allowed_sources en hybrid_search): 18.2% pass rate — **regresion severa**
- **Soft boost** (+0.05 score post-retrieval): 45.5% pass rate — **sin regresion**

### Conclusion

Fase 6 no introduce regresion con soft boost. La brecha restante es de retrieval (two-stage, equivalences, conceptual map, technology filtering).

## Pendiente

- Cerrar brecha con monolito via Fase 7+ (two-stage auto, equivalences, conceptual map).
