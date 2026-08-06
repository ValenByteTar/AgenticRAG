---
id: RES-010
title: "Contrato canonico de documento: Single Producer, Downward-Only Flow y Materialized Views"
date: 2026-08-03
status: proposed
category: research
tags: [architecture, canonical-document-contract, single-producer-principle, downward-only-flow, materialized-views, doccards, chroma, knowledge-builder, warm-artifacts, ownership, invariants, corpus-cleanup, extraction-overhaul]
related: [RES-001, RES-002, RES-003, RES-007, ADR-0018, ADR-0021, DEC-011]
supersedes: null
superseded_by: null
---

# RES-010 — Contrato canonico de documento

## Topic

Establecer un contrato canonico para la representacion de documentos que unifica las tres representaciones existentes del corpus (Vector Store, DocCards, Knowledge Builder) bajo dos axiomas arquitectonicos, un modelo de ownership explicito, ocho invariantes y el concepto unificador de Materialized View.

## Sources

- RES-001: El contrato Warm como centro arquitectonico (frontera Builder/Consumer)
- RES-002: Knowledge Builder / Knowledge Compiler (pipeline extract → compile → validate → publish)
- RES-003: Knowledge Consumer / evolucion del Agentic RAG runtime
- RES-007: Estrategia de modelos LLM locales (Granite 3B Q6)
- ADR-0018: Knowledge Builder / Consumer split
- ADR-0021: Builder CLI split, KIR, cache por chunk, catalogo de 9 predicados, roles v2
- DEC-011: Poblado escalonado, predicados fuera de catalogo rechazados
- Plan: `corpus-cleanup-and-extraction-overhaul-1cdb2a.md`

---

## 1. Motivacion

### 1.1 El problema de fondo

El sistema evoluciono de un monolito RAG hacia una arquitectura formal con Knowledge Builder, Warm Artifacts y Artifact Registry (RES-001, ADR-0018). Sin embargo, tres representaciones del mismo documento coexisten sin contrato:

- **Vector Store (Chroma)**: chunks + embeddings + metadata local
- **DocCards** (`data/doc_roles.json`): roles, entities, attributes, centrality, summary
- **Knowledge Builder** (KIR → Warm Artifacts): entidades, aliases, relaciones, document roles

Cada representacion evoluciono independientemente con su propia key de identidad, su propia taxonomia de roles, sus propios resumenes, sus propias entidades y sus propios atributos.

### 1.2 Incompatibilidades sistemicas detectadas

Los problemas observados no son errores independientes — son sintomas de la ausencia de una representacion canonica del documento:

1. **Key mismatch**: Chroma usa `source` = nombre PDF. DocCards usa `source_path` = nombre PDF. Builder publica `doc_id` = `slugify(name)`. El boost en `RetrievalCapability` compara `candidate_docs` (slugs) contra `metadata.source` (PDF names) — nunca matchea.
2. **Roles divergentes**: `retrieval_engine.py` pide roles viejos (`grid_ops`, `manual_scada`, `analysis_report`). `doc_cards._guess_role_by_name` produce roles viejos. `llm_entity_extractor` prompt pide roles v2. `warm_codegen` evalua roles v2.
3. **Attributes se pierden**: DocCards produce `attributes_index`. `DocCardsExtractor` los pasa al KIR. Pero `warm_codegen._gen_doc_roles` no los serializa al artifact — se pierden entre KIR y artifacts.
4. **Entities no se cruzan**: DocCards usa regex hardcoded de ~30 patrones. Builder extrae free-form via LLM. `entity_index` se construye solo desde KIR del LLM.
5. **Exclusions no se propagan a Chroma**: `corpus_exclusions.json` se respeta en Builder pero `ingest_incremental.py` no tiene filtro — indexa todo.
6. **Summary duplicado**: Builder produce `doc_summary` via LLM. DocCards produce `summary` via heuristica (primer parrafo). `retrieval_metadata` y `entity_index` pueden generar sus propios summaries.

### 1.3 Por que no alcanza con parches individuales

Cada incompatibilidad podria arreglarse aisladamente (alinear keys, migrar roles, preservar attributes). Pero sin un contrato que defina ownership, esas correcciones serian parches puntuales. El siguiente componente que se agregue volvera a generar su propia representacion local, recreando el problema.

La solucion es definir la arquitectura antes de implementar la migracion.

---

## 2. Axiomas

### Axioma 1: Single Producer Principle

Para cada hecho del sistema existe exactamente un productor autorizado.

Todos los demas componentes unicamente consumen, proyectan o transforman ese hecho sin reinterpretarlo.

Este principio aparece una y otra vez en sistemas distribuidos, compiladores, bases de datos, ECS, arquitecturas event-driven y sistemas de conocimiento. Tenerlo explicito evita que, con el tiempo, vuelvan a aparecer fuentes paralelas de verdad.

### Axioma 2: Downward-Only Information Flow

La informacion solamente fluye hacia abajo en la cadena de representaciones.

Nunca al reves.

Nunca.

```
Corpus
    ↓
Knowledge Builder
    ↓
Canonical Knowledge Model
    ↓
 ┌──────────────┬───────────────┬──────────────┐
 │ WarmArtifacts│ DocCards      │ Entity Index │
 │              │               │              │
 └──────────────┴───────────────┴──────────────┘
    ↓
Planner / Retrieval / UI
```

Si una materialized view agrega un atributo, ese atributo no vuelve jamas al Builder. Y ya hay dos verdades.

Las representaciones derivadas nunca pueden enriquecerse localmente. Toda modificacion al conocimiento debe ocurrir en el productor oficial y propagarse hacia abajo.

Las materialized views se regeneran cuando cambia el Builder. Nunca se editan manualmente.

---

## 3. Ownership

| Informacion | Productor oficial | Consumidores | Estado |
|---|---|---|---|
| Identidad del documento | Corpus | Todos | `canonical_doc_id` unico, independiente del nombre usado por cada componente |
| Roles | Knowledge Builder | Retrieval, DocCards (Materialized View), Planner | Ningun otro componente puede inferir roles propios |
| Summary | Knowledge Builder | Retrieval, DocCards (Materialized View), Planner, UI | Ningun componente puede generar un summary propio — siempre reutiliza el del Builder |
| Entidades | Knowledge Builder | Retrieval, DocCards (Materialized View), Entity Index | Las regex de DocCards dejan de ser representacion independiente |
| Attributes | Knowledge Builder | Retrieval, DocCards (Materialized View), Planner | Deben preservarse durante compilacion KIR → Warm Artifacts |
| Centralidad | CONGELADA | Retrieval, Planner | Heuristica temporal hasta definir metodo basado en evidencia |

---

## 4. Rol de cada representacion

- **Corpus**: fuente primaria de contenido. No contiene interpretacion.
- **Knowledge Builder**: unico productor de conocimiento estructurado (roles, summaries, entities, aliases, relationships, attributes, retrieval metadata). Representacion canonica del conocimiento del documento.
- **Canonical Knowledge Model**: el modelo de conocimiento producido por el Builder. Es la unica fuente de verdad. Todas las demas representaciones se derivan de aca.
- **Warm Artifacts**: publicacion estable del Canonical Knowledge Model. Contrato consumido por componentes runtime. Es una materialized view del Builder.
- **DocCards (Materialized View)**: deja de existir como concepto arquitectonico independiente. No tiene lifecycle propio. Es una materialized view del Builder via Warm Artifacts. Se regenera cuando cambia el Builder. Nunca se edita manualmente.
- **Entity Index (Materialized View)**: otra materialized view del mismo conocimiento. Mismo principio que DocCards.
- **Vector Store (Chroma)**: deja de ser propietario de metadata. Su unica responsabilidad es almacenar embeddings, chunks e indexar texto. La metadata debe derivar del contrato canonico, nunca ser generada localmente.

El concepto unificador es **Materialized View**: DocCards, Entity Index, Planner Cache, Retrieval Index, Search Catalog, UI Cards — todos son distintas materializaciones del mismo conocimiento. Se regeneran cuando cambia el Builder. Nunca se enriquecen localmente. Nunca se editan manualmente.

---

## 5. Invariantes arquitectonicos

1. Existe exactamente un `canonical_doc_id` por documento.
2. Existe exactamente un productor para cada pieza de conocimiento.
3. Ningun consumidor modifica conocimiento.
4. La informacion solo fluye hacia abajo. Las representaciones derivadas nunca pueden enriquecerse localmente.
5. Toda representacion debe poder reconstruirse desde el Builder.
6. Chroma jamas contiene conocimiento derivado.
7. Warm Artifacts son deterministicos respecto del mismo KIR.
8. Todas las materialized views se regeneran cuando cambia el Builder. Nunca se editan manualmente.

Cualquier PR futuro puede preguntarse: ¿rompo alguno de estos invariantes? Si la respuesta es si, el PR viola el contrato.

Los dos axiomas (Single Producer Principle + Downward-Only Information Flow) son los principios centrales del proyecto. Los 8 invariantes son su formalizacion.

---

## 6. Contrato de compatibilidad

Toda representacion debera poder responder afirmativamente:

- ¿Corresponde al mismo `canonical_doc_id`?
- ¿Representa el mismo documento?
- ¿Consume el mismo rol?
- ¿Consume el mismo resumen?
- ¿Consume los mismos atributos?
- ¿Consume la misma identidad?

Si alguna respuesta es negativa, existe violacion del contrato.

---

## 7. Fases de implementacion

### Fase 0A — Definicion arquitectonica (sin codigo)

Define ownership, identidad, productores, consumidores e invariantes. Es este documento.

### Fase 0B — Migracion al contrato canonico

Implementa los cambios de codigo necesarios:

1. **Definir `canonical_doc_id`**: formato unico derivado del corpus. Todos los componentes usan este ID como key.
2. **Propagar exclusions a Chroma**: `ingest_incremental.py` carga `corpus_exclusions.json` y saltea archivos excluidos.
3. **Migrar DocCards a materialized view**: eliminar `_guess_role_by_name`, `_extract_basic_entities`, `_infer_attributes_presence`. Simplificar `build_doc_cards` / `build_doc_cards_llm` a vista del Builder.
4. **Preservar attributes en compilacion**: `warm_codegen._gen_doc_roles` debe incluir `attributes` del `DocumentClaim` en el artifact.
5. **Eliminar summaries duplicados**: ningun componente genera summaries propios.
6. **Alinear roles en retrieval**: `retrieval_engine.plan_retrieval` debe usar roles v2.
7. **Alinear keys en retrieval boost**: `RetrievalCapability` debe comparar `canonical_doc_id` de `candidate_docs` contra `canonical_doc_id` de Chroma metadata.

### Fase 1 — Limpieza del corpus ✅ COMPLETADO

928 → 725 docs (203 excluidos via `corpus_exclusions.json`).

### Fase 2A — Regenerar DocCards (transicion a materialized view)

Las heuristicas de DocCards se usan temporalmente para generar el `doc_roles.json` inicial. El Builder las sobreescribe en Fase 5. Post-Fase 5, DocCards son una materialized view sin estado del Builder.

### Fase 2B — Mejorar centralidad (CONGELADA)

No se ejecuta hasta que el Builder estabilice. La centralidad podria calcularse con Warm Artifacts, PageRank o corroboracion — decisiones que requieren experimentacion.

### Fase 3 — Ampliar fallback de predicados + atributos de arista

Script de auditoria genera tabla de mappings. Usuario revisa antes de aplicar. Metrica: aumentar capacidad descriptiva (no solo bajar `references`).

### Fase 4 — Mejoras de velocidad del extractor

Paralelismo 4x, `format: "json"`, `num_predict` cap, `num_ctx` reduction, `_EXTRACTOR_ID` dinamico.

### Fase 5 — Flush cache + run limpio

Extraccion completa con corpus depurado + mejoras.

### Fase 6 — Muestreo de singletons

Clasificar 300 singletons para decidir si endurecer el prompt.

### Fase 7 — Revisar prompt (condicional)

Solo si Fase 6 demuestra >40% ruido.

---

## 8. Orden de ejecucion

```
Fase 0A (contrato) → Fase 0B (migracion) → Fase 1 ✅ → Fase 2A (doccards transicion)
→ Fase 3 (fallback) → Fase 4 (velocidad) → Fase 5 (run limpio)
→ Fase 6 (muestreo) → [Fase 7 condicional]
→ [Fase 2B descongelada post-experimentacion]
→ [Knowledge Health Check post-estabilizacion del contrato]
```

---

## 9. Roadmap posterior

Una vez estabilizado el contrato, un Knowledge Health Check verificara automaticamente la consistencia entre Corpus, Builder, Warm Artifacts, DocCards View y Chroma.

El Health Check no valida el Builder — valida el ecosistema. Valida que todos respeten el contrato.

No se implementa antes de estabilizar el contrato canonico. Primero se define la verdad. Luego se valida que todos la respeten.

---

## 10. Riesgos

- **Fase 0A**: el contrato puede revelar dependencias no detectadas. Mitigacion: el contrato es declarativo — si se detecta un nuevo productor duplicado, se agrega a la tabla de ownership sin cambiar codigo.
- **Fase 0B**: migrar a `canonical_doc_id` requiere tocar todos los componentes. Mitigacion: cambio incremental — primero definir el ID, luego propagar componente por componente.
- **Fase 0B**: eliminar heuristicas de DocCards puede romper el pipeline si el Builder no ha corrido aun. Mitigacion: las heuristicas se mantienen temporalmente durante Fase 2A; el Builder las sobreescribe en Fase 5.
- **Fase 3**: el script `predicate_audit.py` puede sugerir mappings incorrectos. Mitigacion: el usuario revisa cada sugerencia antes de aplicar.
- **Fase 4**: `format: "json"` puede romper si Ollama no soporta structured output para el modelo. Mitigacion: fallback a sin format si falla.
- **Fase 4**: paralelismo puede saturar VRAM. Mitigacion: `OLLAMA_NUM_PARALLEL` configurable, empezar con 2x.
- **Fase 5**: run completo ~20h. No hay shortcut si el cache se flushea.
