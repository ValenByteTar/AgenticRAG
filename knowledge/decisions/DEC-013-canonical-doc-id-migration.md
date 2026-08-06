---
id: DEC-013
title: "Migracion a canonical_doc_id como key unica de documento"
date: 2026-08-03
status: accepted
category: decision
tags: [canonical-doc-id, identity, migration, chunker, retrieval, doccards]
related: [ADR-0022, RES-010, DEC-014]
supersedes: null
superseded_by: null
---

# DEC-013 - Migracion a canonical_doc_id como key unica de documento

## Context

Antes del contrato canonico, cada componente usaba una key distinta para identificar
el mismo documento:

- Chroma metadata: `source` = nombre del PDF (ej. `"ISO 27001 Guide.pdf"`)
- DocCards: `source_path` = nombre del PDF, keyed por `source`
- Builder/KIR: `doc_id` = `f"doc:{slugify(name)}"` (ej. `"doc:iso-27001-guide"`)
- Retrieval boost: comparaba `candidate_docs` (slugs del Builder) contra `metadata.source`
  (nombres PDF) — nunca matcheaba.

Esto causaba que el soft boost de `RetrievalCapability` y el `filter_to_candidates` de
`RetrievalEngine` fueran no-ops: las keys eran semanticamente distintas.

## Decision

Definir `canonical_doc_id` como `f"doc:{slugify(Path(filename).stem)}"` en una unica
utility (`src/utils/canonical_id.py`) y propagarla a todos los componentes:

1. **Chunker**: cada chunk incluye `canonical_doc_id` en metadata.
2. **Chroma**: la metadata del chunk incluye `canonical_doc_id` (via chunker).
3. **DocCards**: las keys de `doc_roles.json` son `canonical_doc_id`.
4. **RetrievalCapability**: boost compara `canonical_doc_id` de `candidate_docs`
   contra `canonical_doc_id` de Chroma metadata.
5. **RetrievalEngine.filter_to_candidates**: filtra por `canonical_doc_id`.
6. **DocCardsExtractor**: usa `canonical_doc_id` del doc_roles data como `source_doc_id`
   en KIR EvidenceItems.

La utility se coloca en `src/utils/` (no en `knowledge_builder/kir/`) para evitar
dependencias circulares entre `src/` y `knowledge_builder/`.

## Status

accepted

## Notes

No es un ADR porque no cambia una frontera arquitectonica — es la implementacion
de ADR-0022. Es reversible (se puede cambiar el formato de slugify sin cambiar la
arquitectura), pero no sin costo alto (requiere re-ingestar Chroma y regenerar
DocCards).
