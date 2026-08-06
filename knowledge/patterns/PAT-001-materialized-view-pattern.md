---
id: PAT-001
category: pattern
status: accepted
created: 2026-08-03
updated: 2026-08-03
author: human
components: [knowledge-builder, warm-artifacts, doc-cards, entity-index, retrieval, planner]
tags: [materialized-view, single-producer, downward-flow, regeneration]
related: [ADR-0022, RES-010, PAT-002]
supersedes: null
superseded_by: null
---

# PAT-001 - Materialized View Pattern

## Problem

Un sistema de conocimiento tiene multiples representaciones derivadas del mismo
documento (DocCards, Entity Index, Retrieval Metadata, Planner Cache, UI Cards).
Sin un patron que defina su lifecycle, cada representacion tiende a:

- Editarse manualmente, generando drift.
- Acumular enriquecimiento local no trazable al productor.
- Divergir de las demas representaciones.

## Solution

Toda representacion derivada es una **Materialized View** con estas reglas:

1. **Single Producer**: existe exactamente un productor autorizado (el Knowledge Builder).
   La view no produce conocimiento — solo lo proyecta.
2. **Stateless regeneration**: la view se regenera cuando cambia el Builder. No tiene
   lifecycle propio. No se edita manualmente.
3. **Downward-only flow**: la view puede consumir conocimiento del Builder pero nunca
   enriquecerlo localmente. Si necesita un dato nuevo, se agrega al Builder.
4. **Reconstructible**: la view debe poder reconstruirse desde el Builder en cualquier
   momento. No hay estado que no se pueda derivar.
5. **Contract-bound**: la view consume via el contrato (Warm Artifacts), no via acceso
   directo al modelo interno del Builder.

```
Knowledge Builder → Warm Artifacts (contract)
                         ↓
          ┌──────────────┼──────────────┐
          │              │              │
     DocCards      Entity Index    Retrieval Meta
     (view)        (view)          (view)
          │              │              │
          └──────────────┼──────────────┘
                         ↓
                   Planner / Retrieval / UI
```

## Tradeoffs

- **Gana**: consistencia automatica. No hay drift. Cualquier view se puede regenerar.
- **Gana**: el Health Check puede validar el ecosistema completo comparando views
  contra el Builder.
- **Pierde**: latencia de propagacion. Un cambio en el Builder no se refleja
  instantaneamente en todas las views — requiere re-publicar.
- **Pierde**: durante transicion (Fase 2A), las heuristicas temporales coexisten
  con el contrato. Esto se resuelve cuando el Builder sobreescribe en Fase 5.

## Examples

- `doc_cards.py` — DocCards lee del corpus y produce `doc_roles.json` como view
  temporal. Post-Fase 5, el Builder sobreescribe via Warm Artifacts.
- `warm_codegen._gen_doc_roles` — serializa `DocumentRole` del Knowledge Model al
  artifact `doc_roles.json`. El artifact es la view publicada.
- `warm_codegen._gen_retrieval_metadata` — serializa metadata de retrieval por
  documento. Es una view del mismo modelo.
- `warm_codegen._gen_entity_index` — serializa el indice de entidades. Es una view
  del mismo modelo.
