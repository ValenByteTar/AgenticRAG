---
id: PAT-002
category: pattern
status: accepted
created: 2026-08-03
updated: 2026-08-03
author: human
components: [chunker, vector-store, doc-cards, retrieval, knowledge-builder, canonical-id]
tags: [canonical-identity, propagation, key-alignment, slug]
related: [ADR-0022, RES-010, PAT-001, DEC-013]
supersedes: null
superseded_by: null
---

# PAT-002 - Canonical Identity Propagation

## Problem

Cuando un documento pasa por multiples etapas de procesamiento (extraccion →
chunking → embedding → retrieval → knowledge building), cada etapa tiende a
inventar su propia key de identidad (nombre de archivo, path, slug, hash, etc.).
Esto produce key mismatches silenciosos: dos componentes que deberian referirse
al mismo documento usan keys distintas y nunca matchean.

## Solution

Definir una **funcion unica** que genera el `canonical_doc_id` desde cualquier
representacion del nombre del documento, y propagarla a todos los componentes:

1. **Definir**: `canonical_doc_id(filename) = f"doc:{slugify(Path(filename).stem)}"`
   en una unica utility (`src/utils/canonical_id.py`).
2. **Propagar en produccion**: el chunker incluye `canonical_doc_id` en cada chunk
   que envia a Chroma.
3. **Propagar en consumo**: todos los componentes que comparan o filtran por
   documento usan `canonical_doc_id` como key:
   - `select_docs_by_roles` retorna `canonical_doc_id`s.
   - `RetrievalCapability` boost compara `canonical_doc_id` de `candidate_docs`
     contra `canonical_doc_id` de Chroma metadata.
   - `filter_to_candidates` filtra por `canonical_doc_id`.
   - `DocCardsExtractor` usa `canonical_doc_id` como `source_doc_id` en KIR.
4. **No dependencia circular**: la utility se coloca en `src/utils/` (no en
   `knowledge_builder/kir/`) para que ambos paquetes puedan importarla sin
   crear dependencias circulares.

```
                    canonical_doc_id(filename)
                            │
         ┌────────┬─────────┼──────────┬──────────┐
         │        │         │          │          │
    Chunker    Chroma   DocCards   Retrieval   Builder/KIR
    (produce)  (store)  (key)      (match)     (source_doc_id)
```

## Tradeoffs

- **Gana**: una sola key. Cualquier componente puede comparar sin normalizacion.
- **Gana**: la funcion es deterministica y sin estado — no requiere lookup.
- **Pierde**: dos archivos con el mismo stem (distinta extension) colisionan.
  Mitigacion: el corpus ya tiene nombres unicos post-limpieza (Fase 1).
- **Pierde**: si se renombra un archivo, el `canonical_doc_id` cambia. Mitigacion:
  el `source_path` se preserva en DocCards para trazabilidad.

## Examples

- `src/utils/canonical_id.py` — la utility unica.
- `src/chunker.py:169` — `canonical_doc_id(pdf_data['filename'])` en metadata del chunk.
- `doc_cards.py:177` — `canonical_doc_id(fname)` como key de `sources_seen`.
- `src/capabilities/retrieval.py:62` — `md.get("canonical_doc_id")` para boost match.
- `retrieval_engine.py:302` — `canonical_doc_id` en `filter_to_candidates`.
- `knowledge_builder/frontend/doc_cards_extractor.py:49` — `cid` como `source_doc_id`.
