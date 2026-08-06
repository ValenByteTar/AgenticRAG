# ADR-0022 - Contrato canonico de documento: Single Producer, Downward-Only Flow, Materialized Views

- **Estado:** Aceptado
- **Fecha:** 2026-08-03
- **Relaciona con:** ADR-0018, ADR-0021, RES-010, DEC-011, DEC-013, DEC-014

## Contexto

El sistema evoluciono de un monolito RAG hacia una arquitectura formal con Knowledge Builder, Warm Artifacts y Artifact Registry (ADR-0018, ADR-0021). Sin embargo, tres representaciones del mismo documento coexisten sin contrato:

1. **Vector Store (Chroma)**: chunks + embeddings + metadata local (`source` = nombre PDF)
2. **DocCards** (`data/doc_roles.json`): roles, entities, attributes, centrality, summary (`source_path` = nombre PDF)
3. **Knowledge Builder** (KIR → Warm Artifacts): entidades, aliases, relaciones, document roles (`doc_id` = `slugify(name)`)

Cada representacion evoluciono independientemente con su propia key de identidad, taxonomia de roles, resumenes, entidades y atributos. Esto produjo seis incompatibilidades sistemicas detectadas (RES-010 §1.2): key mismatch, roles divergentes, attributes perdidos, entities no cruzadas, exclusions no propagadas, summaries duplicados.

## Decision

Establecer un **contrato canonico de documento** con dos axiomas, un modelo de ownership explicito, ocho invariantes y el concepto unificador de Materialized View.

### Axioma 1: Single Producer Principle

Para cada hecho del sistema existe exactamente un productor autorizado. Todos los demas componentes unicamente consumen, proyectan o transforman ese hecho.

### Axioma 2: Downward-Only Information Flow

La informacion fluye exclusivamente hacia abajo en la cadena de representaciones. Las representaciones derivadas nunca pueden enriquecerse localmente.

```
Corpus → Knowledge Builder → Canonical Knowledge Model
    ↓                              ↓
    ↓                    ┌─────────┼─────────┐
    ↓                    │         │         │
    Vector Store    Warm Artifacts  DocCards  Entity Index
    (embeddings)    (contract)      (view)    (view)
                         ↓
                    Planner / Retrieval / UI
```

### Ownership

| Informacion | Productor | Consumidores |
|---|---|---|
| Identidad | Corpus | Todos (`canonical_doc_id`) |
| Roles | Knowledge Builder | Retrieval, DocCards, Planner |
| Summary | Knowledge Builder | Retrieval, DocCards, Planner, UI |
| Entidades | Knowledge Builder | Retrieval, DocCards, Entity Index |
| Attributes | Knowledge Builder | Retrieval, DocCards, Planner |
| Centralidad | CONGELADA | Retrieval, Planner |

### 8 Invariantes

1. Existe exactamente un `canonical_doc_id` por documento.
2. Existe exactamente un productor para cada pieza de conocimiento.
3. Ningun consumidor modifica conocimiento.
4. La informacion solo fluye hacia abajo.
5. Toda representacion debe poder reconstruirse desde el Builder.
6. Chroma jamas contiene conocimiento derivado.
7. Warm Artifacts son deterministicos respecto del mismo KIR.
8. Todas las materialized views se regeneran cuando cambia el Builder. Nunca se editan manualmente.

### DocCards como Materialized View

DocCards deja de ser un concepto arquitectonico independiente. No tiene lifecycle propio. Es una materialized view del Builder via Warm Artifacts. Se regenera cuando cambia el Builder. Nunca se edita manualmente.

### Vector Store como almacen plano

Chroma deja de ser propietario de metadata. Su unica responsabilidad es almacenar embeddings, chunks e indexar texto. La metadata debe derivar del contrato canonico (`canonical_doc_id`), nunca ser generada localmente.

## Alternativas consideradas

1. **Parches individuales sin contrato**: alinear keys, migrar roles, preservar attributes aisladamente. Rechazado porque el siguiente componente que se agregue volvera a generar su propia representacion local, recreando el problema.

2. **Migrar todo al Builder inmediatamente**: eliminar heuristicas de DocCards hoy. Rechazado porque el Builder no ha corrido sobre el corpus completo. Las heuristicas se mantienen temporalmente (Fase 2A) hasta que el Builder las sobreescriba (Fase 5).

3. **Contrato sin axiomas explicitos**: solo listar invariantes. Rechazado porque los axiomas capturan la intuicion arquitectonica de forma verificable: cualquier PR futuro puede preguntarse "¿rompo Single Producer?" o "¿introduzco flujo ascendente?".

## Consecuencias

- **Positivas**: una sola fuente de verdad. Cualquier componente nuevo consume del Builder. No puede crear su propia representacion. El Health Check futuro valida el ecosistema, no componentes individuales.
- **Negativas**: migracion toca todos los componentes (chunker, ingest, doc_cards, retrieval, planner, warm_codegen, tests). Requiere Fase 2A transitoria donde las heuristicas coexisten con el contrato.
- **Neutras**: la centralidad queda congelada hasta que se defina un metodo basado en evidencia (Fase 2B post-experimentacion).

## Implementacion

La implementacion se detalla en RES-010 §7 (Fases 0B-7) y se ejecuta incrementalmente:

- **Fase 0B** (completada): `canonical_doc_id` utility, exclusions a Chroma, DocCards desacoplado, attributes preservados, roles v2 alineados, keys alineadas en retrieval boost.
- **Fase 2A** (completada): DocCards regenerado desde corpus con roles v2 y `canonical_doc_id`.
- **Fase 3** (completada): fallback de predicados ampliado, edge attributes, script de auditoria.
- **Fase 5** (pendiente): flush cache + run limpio del Builder.
