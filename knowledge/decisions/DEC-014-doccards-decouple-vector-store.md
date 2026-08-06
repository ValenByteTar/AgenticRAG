---
id: DEC-014
title: "Desacoplamiento de DocCards del Vector Store"
date: 2026-08-03
status: accepted
category: decision
tags: [doccards, vector-store, decoupling, materialized-view, corpus]
related: [ADR-0022, RES-010, DEC-013]
supersedes: null
superseded_by: null
---

# DEC-014 - Desacoplamiento de DocCards del Vector Store

## Context

`build_doc_cards`, `build_doc_cards_llm` y `build_doc_cards_llm_incremental` leian
directamente de `vector_store.collection.get()` para obtener metadatas y documentos.
Esto creaba tres problemas:

1. **Acoplamiento innecesario**: DocCards requeria que Chroma estuviera inicializado
   y poblado para funcionar. No se podian generar DocCards sin un vector store.
2. **Carga de memoria**: `collection.get()` sin limites podia cargar 100K+ chunks en
   memoria para identificar documentos unicos por `source`.
3. **Violacion del contrato**: Chroma dejaria de ser propietario de metadata segun
   ADR-0022. DocCards no puede depender de Chroma para obtener conocimiento del documento.

## Decision

Las tres funciones de DocCards ahora leen directamente del corpus
(`data/extracted_texts/*.txt`) en lugar de Chroma:

- `build_doc_cards(vector_store=None)` — lee `.txt` del corpus, ignora `vector_store`.
- `build_doc_cards_llm(vector_store=None, ...)` — lee `.txt` del corpus para heuristicas
  y refinamiento LLM.
- `build_doc_cards_llm_incremental(vector_store=None, ...)` — lee `.txt` del corpus para
  identificar documentos nuevos.

El parametro `vector_store` se mantiene en la firma por compatibilidad pero se ignora.

Adicionalmente, todas las funciones respetan `corpus_exclusions.json` via `_load_exclusions()`.

## Status

accepted

## Notes

No es un ADR porque no cambia una frontera arquitectonica — es la implementacion
de ADR-0022 §4 (DocCards como Materialized View). El parametro `vector_store` se
mantiene para no romper scripts existentes que lo pasan posicionalmente.
