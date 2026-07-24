---
id: DEC-008
title: "Fase 6: Planner determinista + Entity Expansion + Tunings de retrieval"
date: 2026-07-24
status: accepted
category: decisions
tags: [planner, entity-expansion, retrieval, tuning, fase-6, adr-0012]
related: [ADR-0012, ADR-0013, DEC-006, DEC-007, BM-002]
---

# DEC-008 — Fase 6: Planner determinista + Entity Expansion + Tunings

## Contexto

BM-002 identifico un gap de -44.5pp en doc hit rate vs monolito, causado por:
1. Falta de entity expansion (iso 27001 -> iso27001, iso 27k, isms)
2. Ausencia de planner (roles, comparison detection, semantic_weight adaptativo)
3. Reranker pool fijo (35) que diluye scores vs pool adaptativo (10-13) del monolito
4. Repair_hint poco directivo
5. Groundedness floor muy alto (0.3) para dominio tecnico

## Decision

### PlannerCapability (`src/capabilities/planner.py`)

- Planner determinista basado en keywords, sin LLM.
- Detecta: conceptual, procedural, comparison, simple_numeric, multi_doc.
- Asigna doc_roles_preferred segun tipo de query.
- Ajusta semantic_weight: 0.7 conceptual, 0.5 comparison/procedural, 0.4 numeric.
- NO overridea top_k (lo maneja el retrieval adapter via adaptive pool).

### EntityExpansionCapability (`src/capabilities/entity_expansion.py`)

- Gazetteer hardcoded de aliases de ciberseguridad (iso 27001, nist csf, cissp, etc.).
- Dedup case-insensitive preservando orden.
- Acepta expand_fn custom para delegar al entity_extractor del monolito.

### LinearRagPolicy actualizada

- Cadena: classify -> memory_read -> planner -> entity_expansion -> retrieval -> ...
- 2 pasos nuevos antes de retrieval, max_iterations default bump 10 -> 12.

### Tuning: Adaptive reranker pool

- Pool adaptativo segun query: 10 (simple), 15 (default), 20 (multi-doc/comparison).
- Basado en keywords y longitud de query.
- min(default_pool, adaptive) para no exceder config del usuario.

### Tuning: Repair_hint mejorado

- Instrucciones enumeradas y explicitas.
- Incluye citacion de fuentes [N].
- Mensaje mas directo: "REPARACION REQUERIDA".

### Tuning: Groundedness floor 0.3 -> 0.25

- Reduce falsos negativos en respuestas tecnicas con terminologia de dominio.
- Compensado por repair_hint mas estricto.

## Consecuencias

- Planner + entity_expansion mejoran recall pre-retrieval.
- Adaptive pool reduce dilucion de scores en reranker.
- Repair_hint mas directivo deberia producir respuestas mas grounded tras repair.
- Groundedness floor 0.25 permite respuestas tecnicas con overlap moderado.
- max_iterations default 12 acomoda cadena extendida.

## Alternativas

- Planner con LLM (rechazado: Fase 6 es determinista, LLM planner es Fase 8+).
- Entity expansion via entity_extractor del monolito (diferido: requiere wiring mas complejo).
- Pool fijo en 10 (rechazado: queries complejas necesitan mas candidatos).

## Integracion con monolito (completado)

### Entity extractor wiring

- `build_kernel_bundle_from_rag` crea `_expand_entities` closure que:
  1. Consulta `rag.entity_aliases` (gazetteer del monolito)
  2. Consulta `_DEFAULT_ALIASES` (gazetteer hardcoded Fase 6)
  3. Consulta `rag.memory.get_synonyms()` (sinonimos aprendidos)
  4. Consulta `rag.entity_extractor.domain_entities` (gazetteer de dominio)
- Se pasa como `entity_expand_fn` al `build_kernel_bundle`.

### Doc roles wiring

- `build_kernel_bundle_from_rag` crea `_planner_fn` closure que:
  1. Obtiene plan default del `PlannerCapability` determinista
  2. Si `use_doc_roles=True` y `rag.doc_roles` tiene docs, llama `select_docs_by_roles()` de `doc_cards.py`
  3. Almacena `candidate_docs` en el plan
- `PlannerCapability` guarda `candidate_docs` en `state.metadata`
- `RetrievalCapability` lee `candidate_docs` de metadata y aplica **soft boost** (+0.05 al score) post-retrieval, no hard filtering
- **Decision**: soft boost sobre hard scoping — hard scoping causó regresión severa (18.2% vs 45.5% en BM-003)
