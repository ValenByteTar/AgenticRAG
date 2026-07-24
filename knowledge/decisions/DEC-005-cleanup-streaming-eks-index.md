---
id: DEC-005
category: decision
status: accepted
created: 2026-07-23
updated: 2026-07-23
author: cascade
components: [facade, generation, kernel, knowledge]
tags: [cleanup, electric-domain, streaming, eks-index, phase3]
related: [ADR-0017, DEC-001, DEC-004, EXP-003]
supersedes: null
superseded_by: null
---

# DEC-005 - Limpieza dominio electrico, streaming kernel y EKS index

## Context

Tras cerrar Fases 0-3 del roadmap, quedaban tres items pendientes sin bloqueo de entorno:

1. **Dominio electrico residual**: `rag_hybrid.py` arrastraba terminos del dominio electrico (centrales, parques, WTG, CAMMESA, Pampetrol, etc.) en prompts, heuristicas, patrones de entity extraction y nombres de variables.
2. **Streaming en camino kernel**: `GenerationCapability` no soportaba `token_callback`/`cancel_checker`; el camino kernel ignoraba los params de streaming que el monolito ya manejaba.
3. **EKS index**: el README de `knowledge/` listaba "Index generado" como diferido. Con 6 documentos con frontmatter, era viable generarlo.

## Decision

### 1. Limpieza de dominio electrico

- Renombrar `centrales_map`/`centrales_loaded` -> `domain_map`/`domain_loaded` (consistente con DEC-001).
- Renombrar `_is_centrales_list_request` -> `_is_listing_request`.
- Reemplazar keywords de dominio electrico (WTG, aerogenerador, turbina, fotovoltaica, eolico) por terminos genericos de ciberseguridad (endpoint, server, router, module, component).
- Limpiar comentarios, ejemplos de `/ayuda`, patrones de anforas, ban_tokens, evidence_words y heuristicas de comparacion que referenciaban entidades electricas especificas (Kosten, Loma Blanca, Grenergy, Goldwind, Pampetrol, CROM, CAMMESA).
- Reemplazar `test_hybrid_rag()` con pregunta de ciberseguridad (NIST CSF).

### 2. Streaming en camino kernel

- `ExecutionState`: anadir campos transient `token_callback` y `cancel_checker` (no serializados en `to_dict()`).
- `GenerationCapability`: pasar `stream=True`, `token_callback` y `cancel_checker` al `generate_fn` cuando esten presentes. Fallback con `TypeError` si el fn no acepta kwargs.
- `_generate` adapter en `bootstrap.py`: pasar streaming kwargs a `rag.generate_with_ollama`.
- `query_via_kernel`: aceptar `token_callback` y `cancel_checker`, propagarlos a `ExecutionState`.
- `query()`: pasar streaming params a `query_via_kernel` cuando `kernel.enabled=true`.

### 3. EKS index

- Script `scripts/generate_eks_index.py`: parsea frontmatter YAML de todos `.md` bajo `knowledge/` (excluyendo `_schema/`, `_templates/`, `README.md`).
- Genera `knowledge/INDEX.md` (tabla legible) y `knowledge/_eks_index.json` (maquina).
- 6 documentos indexados: DEC-001, DEC-003, DEC-004, EXP-002, EXP-003, BM-001.

## Status

accepted

## Notes

- La limpieza de dominio electrico fue mecanica (regex/sed sobre `rag_hybrid.py`); se preservaron estructura y logica, solo se reemplazaron terminos.
- El streaming es opt-in: si `token_callback` es None, el comportamiento es identico al anterior.
- El EKS index es regenerable: `python scripts/generate_eks_index.py`.
- `kernel.enabled` sigue `false` por defecto (no cambiar hasta A/B evaluation).
