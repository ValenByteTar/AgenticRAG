---
id: PM-001
category: postmortem
status: resolved
created: 2026-08-03
updated: 2026-08-03
author: human
components: [retrieval, doc-cards, vector-store, planner, canonical-id]
tags: [key-mismatch, retrieval-boost, silent-failure, canonical-doc-id]
related: [ADR-0022, RES-010, DEC-013, BM-006]
supersedes: null
superseded_by: null
---

# PM-001 - Key mismatch entre Chroma y DocCards: retrieval boost silenciosamente no-op

## Incident

El soft boost de `RetrievalCapability` (F6) y el `filter_to_candidates` de
`RetrievalEngine` nunca funcionaron. Desde su implementacion, el boost comparaba
`candidate_docs` (que contenia slugs del formato `doc:iso-27001-guide` producidos
por el Builder) contra `metadata.source` en Chroma (que contenia nombres de PDF
como `"ISO 27001 Guide.pdf"`).

Las keys eran semanticamente distintas. Ningun resultado recibia boost. Ningun
filtro de candidatos reducia el pool. El comportamiento era equivalente a no tener
planner ni doc_roles en absoluto.

**Impacto**: el planner producia planes con `candidate_docs` que el retrieval
ignoraba silenciosamente. La inversion en DocCards, roles, entidades y attributes
no tenia efecto en retrieval. El sistema funcionaba como un RAG plano sin
scoping por documento.

## Root Cause

No hubo un error de logica ni un bug de runtime. El problema fue arquitectural:
tres componentes (Chroma, DocCards, Builder) evolucionaron independientemente, cada
uno inventando su propia key de identidad para el mismo documento:

- Chroma: `source` = nombre del PDF (seteado por el chunker)
- DocCards: `source_path` = nombre del PDF, keyed por `source`
- Builder: `doc_id` = `f"doc:{slugify(name)}"` (producido por `CanonicalizePass`)

El retrieval boost fue escrito asumiendo que `candidate_docs` (del Builder) y
`metadata.source` (de Chroma) usarian la misma key. Nunca la usaron.

La causa raiz es la **ausencia de un contrato canonico de identidad** — no un
error de codigo.

## Resolution

1. **Definir `canonical_doc_id`** (DEC-013): una unica utility en `src/utils/canonical_id.py`
   que genera `f"doc:{slugify(Path(filename).stem)}"` desde cualquier nombre de archivo.

2. **Propagar al chunker**: cada chunk en Chroma ahora incluye `canonical_doc_id` en
   metadata (ademas de `source` para compatibilidad).

3. **Propagar a DocCards**: las keys de `doc_roles.json` son ahora `canonical_doc_id`.

4. **Actualizar retrieval boost**: `RetrievalCapability` y `filter_to_candidates`
   comparan `canonical_doc_id` de `candidate_docs` contra `canonical_doc_id` de
   Chroma metadata.

5. **Formalizar el contrato**: ADR-0022 establece el contrato canonico con 8
   invariantes. El invariante #1 ("existe exactamente un `canonical_doc_id` por
   documento") previene recurrencia.

## Prevention

1. **Invariante arquitectural**: ADR-0022 invariante #1 — cualquier PR que introduzca
   una key de identidad distinta a `canonical_doc_id` viola el contrato.

2. **Health Check futuro**: validara que todas las representaciones usen el mismo
   `canonical_doc_id` para el mismo documento. Si Chroma metadata no incluye
   `canonical_doc_id`, o si DocCards usa una key distinta, el Health Check falla.

3. **PAT-002 (Canonical Identity Propagation)**: documenta el patron para que
   cualquier componente nuevo sepa como identificar documentos.

4. **Test de boost**: `test_e4_warm_artifacts_consumer.py` ahora incluye
   `canonical_doc_id` en mock metadata y verifica que el boost se aplique.

5. **BM-006**: medira `boost_hit_rate` y `candidate_match_rate` como metricas
   explicitas. Si estas metricas caen a 0%, el test falla.
