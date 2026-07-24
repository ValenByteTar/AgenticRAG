---
id: EXP-004
category: experiment
status: accepted
created: 2026-07-23
updated: 2026-07-23
author: cascade
components: [facade, generation, kernel, knowledge]
tags: [cleanup, streaming, eks-index, phase3, no-regression]
related: [ADR-0017, DEC-005, DEC-001, DEC-004, EXP-003]
supersedes: null
superseded_by: null
---

# EXP-004 - Limpieza dominio electrico, streaming kernel y EKS index

## Hypothesis

Los tres items pendientes (limpieza dominio electrico, streaming kernel, EKS index) pueden implementarse sin regresion funcional ni cambios arquitectonicos.

## Config

- **Limpieza**: regex/sed sobre `rag_hybrid.py` para reemplazar terminos electricos por genericos.
- **Streaming**: campos transient en `ExecutionState` + passthrough en `GenerationCapability` + adapter en `bootstrap.py` + propagacion en `query_via_kernel`.
- **EKS index**: script Python que parsea frontmatter YAML y genera `INDEX.md` + `_eks_index.json`.

## Results

### Limpieza dominio electrico

- `centrales_map` -> `domain_map` (consistente con DEC-001).
- `_is_centrales_list_request` -> `_is_listing_request`.
- Keywords: WTG/aerogenerador/turbina/fotovoltaica/eolico -> endpoint/server/router/module/component.
- Entidades especificas (Kosten, Loma Blanca, Grenergy, Goldwind, Pampetrol, CROM, CAMMESA) eliminadas de heuristicas, prompts, ban_tokens, evidence_words y anforas.
- `test_hybrid_rag()` reemplazado con pregunta NIST CSF.
- `rag_hybrid.py` compila sin errores (`py_compile`).
- **0 referencias residuales** a terminos electricos (verificado con grep).

### Streaming kernel

- `ExecutionState.token_callback` y `.cancel_checker` son transient (no en `to_dict()`).
- `GenerationCapability` pasa `stream=True` + callbacks al `generate_fn` cuando estan presentes.
- Fallback `TypeError` si el fn no acepta kwargs (compatibilidad backward).
- `query_via_kernel` acepta y propaga `token_callback`/`cancel_checker`.
- `query()` pasa streaming params al camino kernel.

### EKS index

- 6 documentos indexados (DEC-001, DEC-003, DEC-004, EXP-002, EXP-003, BM-001).
- `INDEX.md`: tabla por categoria + cross-references.
- `_eks_index.json`: formato maquina con todos los campos de frontmatter.

### Tests

- **23 tests nuevos** en `test_phase3_cleanup_streaming_eks.py`:
  - 7 tests limpieza dominio (parametrizados sobre terminos prohibidos).
  - 8 tests streaming unit (callbacks, serializacion, fallback, cancel_checker).
  - 1 test streaming E2E (controller.run con token_callback).
  - 7 tests EKS index (existencia, validez JSON, campos requeridos).
- **90 tests totales** pasan sin regresion (excluyendo `test_embedder_cache.py` por dependencia `rich` no instalada).

## Conclusiones

- Los tres items se implementaron sin cambios arquitectonicos ni regresion.
- La limpieza de dominio electrico fue mas extensa de lo esperado (~15 referencias en heuristicas profundas del monolito), pero mecanica.
- El streaming es opt-in y backward compatible.
- El EKS index es regenerable y se actualiza con un solo comando.

## Diferido

- Knowledge Curator (dev-time) sigue diferido.
- A/B evaluation para habilitar `kernel.enabled=true` por defecto.
