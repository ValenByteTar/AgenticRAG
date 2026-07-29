---
id: RES-001
category: research
status: accepted
created: 2026-07-24
updated: 2026-07-28
author: human
components: [contract, artifact-registry, warm-artifacts, cold-artifacts, hot-artifacts]
tags: [architecture, contract, warm-artifacts, artifact-registry, publication-protocol, resolution-protocol, cold-warm-hot, confidence, predicate-catalog, builder-consumer-boundary]
related: [RES-002, RES-003, RES-004, ADR-0009, ADR-0012, ADR-0013, ADR-0015, ADR-0017, ADR-0018, DEC-008, BM-002, BM-003, BM-004, EXP-006b]
supersedes: null
superseded_by: null
---

# RES-001 - El contrato Warm como centro arquitectonico

> **Nota de revision (2026-07-27):** Este research fue seccionado en tres documentos:
> - **RES-001** (este documento) — El contrato Warm como centro arquitectonico
> - **RES-002** — Knowledge Builder / Knowledge Compiler (index-time)
> - **RES-003** — Knowledge Consumer / evolucion del Agentic RAG runtime (query-time)
>
> El contenido original fue redistribuido respetando las tres preocupaciones arquitectonicas
> que tenian lifecycles y stakeholders distintos: el contrato, el Builder, y el Consumer.
>
> **Nota de seccionamiento (2026-07-28):** RES-003 fue a su vez seccionado; el observador
> paralelo LLMSupport quedo en **RES-004**.

## Topic

El contrato Warm Artifacts como centro del sistema: la frontera inviolable entre Knowledge Builder (index-time) y Knowledge Consumer (query-time), mediada por el Artifact Registry.

## Sources

- BM-002: A/B Kernel+VERIFY vs Monolito — brecha de 36.3pp causada enteramente por retrieval
- BM-003: A/B Kernel Fase 6 vs Monolito — sin regresion pero brecha persistente
- BM-004: A/B Kernel Fase 6 + bug fixes — brecha reducida a 27.3pp
- DEC-008: Planner + EntityExpansion tunings — wiring completado, impacto medido en BM-004
- ADR-0009: Memory Port (read-only en kernel)
- ADR-0015: Knowledge System (retrieval + get_entity)
- ADR-0017: EKS (Engineering Knowledge System dev-time)
- ADR-0018: Knowledge Builder / Consumer split
- Monolito: `rag_hybrid.py`, `doc_cards.py`, `equivalences_manager.py`, `conceptual_map.py`, `src/rag/entity_extractor.py`, `retrieval_engine.py`
- RES-002: Knowledge Builder / Knowledge Compiler (implementacion del Builder)
- RES-003: Knowledge Consumer / evolucion del Agentic RAG runtime (implementacion del Consumer)

---

## 1. Motivacion

### 1.1 El problema de fondo es arquitectonico

El monolito (`rag_hybrid.py`) mezcla responsabilidades de index-time y query-time en un solo flujo. Cada query reconstruye o reinterpreta conocimiento que deberia haberse compilado una vez durante la indexacion.

El sintoma visible son las heuristicas. La causa raiz es la ausencia de una frontera clara entre:

- **compilar conocimiento** (index-time — ver RES-002)
- **consumir conocimiento** (query-time — ver RES-003)

Y la ausencia de un **contrato** que medie esa frontera.

### 1.2 Por que no alcanza con parches en el Consumer

Cuando el conocimiento de dominio se embebe en el runtime:

1. El kernel se acopla a un dominio especifico
2. Se duplica logica entre monolito y kernel
3. No escala a otros dominios
4. Viola clean boundaries
5. Viola architecture-first

El problema no es "tener heuristicas". El problema es **reconstruir o hardcodear conocimiento de dominio en query-time**.

Aunque una heuristica sea correcta, si pertenece al dominio y es estable, debe vivir como conocimiento compilado y serializado en Warm Artifacts, no como codigo del Consumer.

---

## 2. El centro es el contrato, no el Builder

Builder y Consumer son implementaciones reemplazables.

Lo estable es el contrato de Warm Artifacts.

```
                 +----------------------+
                 |   WARM ARTIFACTS     |
                 |   (shared contract)  |
                 +----------+-----------+
                            ^
            publish         |         resolve
                            |
     +----------------+     |     +------------------+
     | Knowledge      |-----+-----| Knowledge        |
     | Builder        |           | Consumer         |
     | (replaceable)  |           | (replaceable)    |
     | (ver RES-002)  |           | (ver RES-003)    |
     +----------------+           +------------------+
```

Repetir esta idea:

- el Builder puede reescribirse por completo
- el Consumer puede reescribirse por completo
- el storage puede cambiar
- el modelo LLM puede cambiar
- **solo el contrato debe permanecer estable**

### 2.1 Tres protocolos, dos responsabilidades

Entre Builder y Consumer no hay un unico protocolo. Hay dos responsabilidades distintas mediadas por un componente con identidad propia: el **Artifact Registry**.

```
  Builder (RES-002)
    |
    |  Publication Protocol
    |  ("aca hay un build nuevo")
    v
  Artifact Registry
    |  (single publication authority)
    |
    |  Resolution Protocol
    |  ("dame el build activo")
    v
  Consumer (RES-003)
```

**Publication Protocol**: el Builder entrega un build (artifacts + manifest) al Registry. El Registry lo pone en staging, valida integrity y compatibility, y espera un `promote` explicito. El Builder no publica directamente archivos. Publica a traves del Registry.

**Resolution Protocol**: el Consumer le pide al Registry el build activo. El Registry devuelve el manifest + artifacts. El Consumer nunca sabe ni necesita saber donde estan los archivos fisicamente.

Dos responsabilidades distintas. **Publicar no es Resolver.** El Builder nunca resuelve. El Consumer nunca publica.

---

## 3. Frontera Builder / Consumer

### 3.1 Builder

El Builder es un **Knowledge Compiler**.

Responsabilidades (ver RES-002 para detalle):

- adquirir conocimiento de documentos (front-end)
- producir KIR lossless
- ejecutar IR passes (middle-end)
- validar KIR
- construir el Knowledge Model
- serializar Warm Artifacts (back-end)
- publicar en el Artifact Registry via Publication Protocol

El Builder puede usar parsers, regex, NER, metadata extractors, LLMs u otros mecanismos. Esos mecanismos son implementacion interna.

El Builder no es el centro del sistema. Es un productor del contrato.

### 3.2 Consumer

El Consumer es el Agentic RAG kernel en query-time.

Responsabilidades (ver RES-003 para detalle):

- planificar la consulta
- resolver Warm Artifacts via Resolution Protocol
- ejecutar retrieval / generation / verification
- producir Hot Artifacts temporales
- responder

El Consumer:

- nunca interpreta documentos crudos para descubrir dominio
- nunca genera conocimiento estable de dominio
- nunca ejecuta extraccion semantica de corpus
- nunca reconstruye entidades, aliases o roles desde cero
- nunca publica artifacts
- unicamente consume contratos

### 3.3 Frontera inviolable

| Puede | Builder | Consumer |
|---|---|---|
| Leer documentos del corpus | Si | No (salvo via retrieval ya indexado) |
| Construir Knowledge Model | Si | No |
| Descubrir entidades/aliases/roles | Si | No |
| Validar y compilar conocimiento | Si | No |
| Generar Warm Artifacts | Si | No |
| Publicar al Artifact Registry | Si (via Publication Protocol) | **Nunca** |
| Resolver Warm Artifacts | Si (durante publish/verify) | Si (via Resolution Protocol) |
| Crear Hot Artifacts de query | No | Si |
| Acceder a Cold Artifacts | Si | **Nunca** |
| Mutar el contrato unilateralmente | No | No |

---

## 4. Artifacts

Los artifacts no son el modelo interno.

Son representaciones persistentes, versionadas y publicables del Knowledge Model.

### 4.1 Cold Artifacts

Caracteristicas:

- existen solo durante index-time / build
- el Consumer **nunca** puede usarlos
- desaparecen o se archivan fuera del contrato al finalizar el build
- son internos al Builder

Ejemplos:

- salidas crudas de extractores
- prompts y reasoning temporal
- caches internas de build
- estadisticas intermedias
- reportes temporales de validacion
- cuarentena de claims no publicados
- snapshots intermedios del KIR no publicados

Frontera: Cold Artifacts no forman parte del contrato.

### 4.2 Warm Artifacts

Caracteristicas:

- persisten luego del build
- se resuelven via Resolution Protocol en bootstrap
- son read-only para el Consumer
- representan proyecciones estables del Knowledge Model
- **constituyen el unico contrato compartido**

Ejemplos:

- Entity Index
- Alias Index
- Canonical Entities
- Doc Roles
- Taxonomy
- Entity Relations (tipadas)
- Retrieval Metadata
- Doc Summaries (si se publican)
- Build Manifest

El Consumer puede leerlos. No puede modificarlos.

### 4.3 Hot Artifacts

Caracteristicas:

- se generan solo durante una consulta
- representan estado temporal de runtime
- se destruyen al finalizar la query
- no se persisten como conocimiento de dominio

Ejemplos:

- Planner State
- Expanded Entities (de la query actual)
- Candidate Docs
- Retrieval Graph
- Evidence Graph de la respuesta
- Verification State
- Repair State

Hot Artifacts pertenecen al Consumer. No son output del Builder.

### 4.4 Mapa de ownership

| Artifact class | Owner | Lifetime | Consumer access |
|---|---|---|---|
| Cold | Builder | build | none |
| Warm | Contract / Registry | durable / versioned | read-only (via Resolution Protocol) |
| Hot | Consumer | per-query | read/write local |

Nota: Warm Artifacts no "pertenecen" conceptualmente al Builder como secreto interno.
El Builder los publica.
El contrato los posee.
El Registry los administra.

---

## 5. Artifact Registry

El Artifact Registry no es un directorio. Es un **componente con identidad propia**.

Analogico a:

- Docker Registry
- Maven Repository
- PyPI
- OCI Registry

> **The Artifact Registry is the single publication authority for Warm Artifacts.**

El Builder no publica directamente. Publica a traves del Registry.
El Consumer no lee archivos. Resuelve a traves del Registry.

### 5.1 Identidad

El Registry es un componente con interfaz definida:

| Operacion | Quien llama | Descripcion |
|---|---|---|
| `publish` | Builder | Entrega un build (artifacts + manifest) al Registry |
| `promote` | Builder / CI | Activa un build en staging como build activo (swap atomico) |
| `resolve` | Consumer | Devuelve el manifest + artifacts del build activo |
| `rollback` | Operator / CI | Apunta el manifest a un build previo |
| `verify_integrity` | Registry / Consumer | Valida checksums de artifacts |
| `list_builds` | Operator / CI | Lista builds disponibles (staging, active, deprecated) |
| `get_manifest` | Consumer / CI | Devuelve el manifest de un build especifico o del activo |

### 5.2 Publication Protocol

Como el Builder publica:

1. El Builder entrega un build (artifacts + manifest) al Registry
2. El Registry lo pone en **staging**
3. El Registry valida **integrity** (checksums) y **compatibility** (`contract_version`)
4. Si validacion pasa, el build queda en staging esperando `promote`
5. `promote` = swap atomico del manifest pointer al nuevo build
6. Un build puede existir en staging sin ser activo

El Builder no escribe archivos por su cuenta. Todo pasa por el Registry.

### 5.3 Resolution Protocol

Como el Consumer resuelve:

1. El Consumer le pide al Registry el build activo
2. El Registry devuelve el manifest + artifacts
3. El Consumer valida integrity al cargar (checksums)
4. El Consumer nunca sabe ni necesita saber donde estan los archivos fisicamente

El Consumer nunca habla con el Builder. Habla con el Registry.

### 5.4 Compatibility Contracts

Cada build declara `contract_version` (ej. `warm-v1`).

El Registry valida que un build sea compatible con el Consumer antes de promoverlo.

Si el Consumer espera `warm-v2` y el build es `warm-v1`, se rechaza la promocion.

Esto permite evolucionar el contrato sin romper consumers antiguos.

### 5.5 Rollback

El Registry mantiene N builds anteriores.

Rollback = apuntar el manifest a un build previo. Operacion instantanea, sin recompilar.

Casos de uso:

- build defectuoso
- regresion detectada en A/B
- modelo degradado
- corrupcion de artifacts

### 5.6 Integrity

Checksums (SHA-256) por artifact.

El Consumer valida integridad al cargar.

Si un Warm Artifact fue corrompido en disco:

- el Registry puede servirlo desde un build alternativo
- o rechazar la carga con error explicito

No hay silencio ante corrupcion.

### 5.7 Migrations

Cuando el contrato evoluciona (`warm-v1` -> `warm-v2`), el Registry puede albergar migraciones que transformen builds antiguos al nuevo schema sin recompilar desde documentos.

Ejemplo: anadir un campo `confidence` con default `1.0` a todos los claims existentes.

Las migraciones son:

- declarativas (definen la transformacion de schema)
- validadas (el resultado debe pasar integrity checks)
- versionadas (cada migracion tiene su propia version)
- opcionales (un build puede recompilarse desde documentos en lugar de migrarse)

### 5.8 Build Lifecycle dentro del Registry

```
staging -> promoted (active) -> deprecated -> archived -> purged
```

| Estado | Significado |
|---|---|
| `staging` | Build entregado, validado, pero no activo |
| `promoted` | Build activo, el Consumer lo resuelve |
| `deprecated` | Build reemplazado por uno mas nuevo, retenido para rollback |
| `archived` | Build viejo, retenido solo para auditoria |
| `purged` | Build eliminado del Registry |

Solo un build activo por manifest.

---

## 6. Artifact Lifecycle

Cold / Warm / Hot no son solo categorias estaticas.
Tienen un ciclo de vida.

```
Documento
   |
   v
Front-End (Knowledge Acquisition)
   |
   v
KIR (lossless)
   |
   v
IR Passes (middle-end)
   |
   v
Cold
   |
   v
IR Validation
   |
   v
Knowledge Model (publishable subset)
   |
   v
Back-End (Artifact Generation)
   |
   v
Warm
   |
   v
Artifact Registry (publish)
   |
   v
Registry (staging -> promote)
   |
   v
Bootstrap (Consumer resolve)
   |
   v
RAM (Consumer)
   |
   v
Hot (por query)
   |
   v
Destroy
```

### 6.1 Por que Cold jamas cruza la frontera

Cold existe antes y durante la validacion.

Puede contener:

- ruido
- alucinaciones de extractores
- reasoning no confiable
- claims sin evidencia

Solo el subconjunto que sobrevive Validation entra al Knowledge Model publicable y luego se serializa como Warm.

Por eso Cold jamas es legible por el Consumer.

### 6.2 Momentos de nacimiento y muerte

| Estado | Nace en | Muere / se archiva en |
|---|---|---|
| Cold | Front-End / IR Passes | fin de build o archive interno |
| Warm | Back-End (codegen) + publish | deprecacion de build / nuevo manifest |
| Hot | query runtime | fin de query |

### 6.3 Implicacion para el Consumer

El Consumer solo ve Warm ya validado y publicado.

Nunca participa de Compilation.
Nunca ve Cold.
Nunca convierte Hot en Warm por su cuenta.

---

## 7. Contrato Builder -> Consumer

### 7.1 Principio central

El verdadero centro del sistema es el contrato.

El Consumer solo puede acceder a **Warm Artifacts** publicados por el manifest activo en el Artifact Registry.

El Builder puede cambiar internamente (ver RES-002):

- extractores
- modelos
- prompts
- caches
- estrategias de validacion
- representacion interna del KIR
- passes del middle-end
- formato del back-end
- storage interno

...siempre que preserve el contrato de Warm Artifacts.

El Consumer tambien puede cambiar internamente (ver RES-003):

- policies
- capabilities
- planner
- retry logic
- generation stack

...siempre que consuma el mismo contrato.

Ese desacoplamiento es la propiedad arquitectonica central.

### 7.2 El Consumer no puede acceder a

- prompts
- reasoning
- caches de build
- extractores
- validaciones internas
- KIR del Builder
- Knowledge Model in-memory del Builder
- Cold Artifacts
- archivos del Registry directamente (solo via Resolution Protocol)

### 7.3 Provenance y Confidence en todo claim publicable

Todo claim serializado en Warm Artifacts debe cargar metadata de confianza.

No por auditoria cosmética.
Sino porque el Consumer puede decidir en runtime:

> "No confio lo suficiente en esta relacion / alias / rol."

Campos minimos:

```json
{
  "confidence": 0.94,
  "validated": true,
  "builder_version": "2.1.0",
  "generated_by": {
    "extractor_id": "llm:granite-4.1-8b",
    "pipeline_stage": "canonicalize+validate"
  }
}
```

Usos posibles en el Consumer (ver RES-003):

- Planner ignora relations bajo umbral
- Entity expansion solo usa aliases high-confidence
- Two-stage prioriza entidades con mejor soporte evidencial
- Comparison balancing descarta aristas debiles
- Verify/repair puede preferir evidencia de claims fuertes

### 7.4 Warm Artifacts minimos del contrato inicial

#### Canonical Entities

```json
{
  "entity_id": "ent:iso-27001",
  "canonical_name": "ISO 27001",
  "types": ["framework", "standard"],
  "confidence": 0.93,
  "validated": true,
  "builder_version": "1.0.0",
  "generated_by": {
    "extractor_id": "llm:granite-4.1-8b"
  }
}
```

#### Alias Index

```json
{
  "iso27001": {
    "entity_id": "ent:iso-27001",
    "confidence": 0.98,
    "validated": true,
    "builder_version": "1.0.0"
  },
  "iso 27k": {
    "entity_id": "ent:iso-27001",
    "confidence": 0.91,
    "validated": true,
    "builder_version": "1.0.0"
  }
}
```

#### Entity Index

```json
{
  "ent:iso-27001": {
    "doc_ids": ["doc:iso27001", "doc:isms-guide"],
    "chunk_ids": ["doc:iso27001#c12", "doc:isms-guide#c3"],
    "confidence": 0.95,
    "validated": true,
    "builder_version": "1.0.0"
  }
}
```

#### Doc Roles

```json
{
  "doc:iso27001": {
    "role": "entity_profile",
    "name": "ISO 27001 Standard",
    "centrality": 0.92,
    "entity_ids": ["ent:iso-27001"],
    "attributes": ["controls", "risk assessment", "annex a"],
    "summary": "International standard for information security management systems.",
    "confidence": 0.9,
    "validated": true,
    "builder_version": "1.0.0"
  }
}
```

#### Entity Relations (tipadas, catalogo controlado, graph-ready)

No usar un campo generico `related`.

Usar triples inspirados en RDF:

```
Subject -> Predicate -> Object
```

No hace falta implementar RDF.
Si hace falta un vocabulario controlado.

```json
{
  "relation_id": "rel:iso27001-defines-isms",
  "subject": "ent:iso-27001",
  "predicate": "defines",
  "object": "ent:isms",
  "confidence": 0.91,
  "validated": true,
  "evidence": [
    {
      "source_doc_id": "doc:iso27001",
      "source_chunk_ids": ["doc:iso27001#c4"],
      "quote": "ISO 27001 defines requirements for an ISMS..."
    }
  ],
  "builder_version": "1.0.0",
  "generated_by": {
    "extractor_id": "llm:granite-4.1-8b"
  }
}
```

### 7.5 Catalogo controlado de predicados

El conjunto de relaciones permitidas es cerrado y versionado.

Objetivo: evitar que un extractor (incluido Granite) invente predicados libres.

Catalogo inicial propuesto:

| Predicate | Significado |
|---|---|
| `defines` | A define B |
| `implements` | A implementa B |
| `belongs_to` | A pertenece a B |
| `extends` | A extiende B |
| `references` | A referencia B |
| `depends_on` | A depende de B |
| `supersedes` | A reemplaza/supera a B |
| `equivalent_to` | A es equivalente a B |
| `part_of` | A es parte de B |
| `located_in` | A se ubica en B |
| `governs` | A gobierna/regula B |
| `certifies` | A certifica B |
| `compares_with` | A se compara con B |

Reglas:

1. Todo `predicate` publicado **debe** existir en el catalogo activo
2. Structural Validation rechaza predicados fuera de catalogo
3. El catalogo es versionado junto al build
4. Ampliar el catalogo es decision de arquitectura, no de un extractor
5. `related_to` se evita como default; solo se agrega si se demuestra necesario

Esta forma habilita evolucion futura hacia GraphRAG sin reventar el contrato.

#### Manifest

```json
{
  "active_build": "ka_v1.0.0",
  "contract_version": "warm-v1",
  "builder_version": "1.0.0",
  "default_model": "granite-4.1-8b",
  "predicate_catalog_version": "1.0.0",
  "created_at": "2026-07-24T18:00:00Z",
  "artifacts": {
    "canonical_entities": "warm/canonical_entities.json",
    "alias_index": "warm/alias_index.json",
    "entity_index": "warm/entity_index.json",
    "doc_roles": "warm/doc_roles.json",
    "entity_relations": "warm/entity_relations.json",
    "retrieval_metadata": "warm/retrieval_metadata.json",
    "predicate_catalog": "warm/predicate_catalog.json"
  },
  "checksums": {
    "canonical_entities": "sha256:abc123...",
    "alias_index": "sha256:def456...",
    "entity_index": "sha256:ghi789...",
    "doc_roles": "sha256:jkl012...",
    "entity_relations": "sha256:mno345...",
    "retrieval_metadata": "sha256:pqr678...",
    "predicate_catalog": "sha256:stu901..."
  }
}
```

### 7.6 Ejemplo de paquete publicado (no monolitico)

```text
knowledge_artifacts/
  ka_v1.0.0/
    manifest.json
    warm/
      canonical_entities.json
      alias_index.json
      entity_index.json
      doc_roles.json
      entity_relations.json
      retrieval_metadata.json
      predicate_catalog.json
    cold/                     # opcional, nunca leido por Consumer
      extractor_dumps/
      validation_reports/
      kir_snapshots/
  ka_v0.9.0/                  # deprecated, retenido para rollback
    manifest.json
    warm/
      ...
  ka_manifest.json            # pointer al build activo
```

El Consumer resuelve solo `manifest` + Warm Artifacts referenciados via Resolution Protocol.

---

## 8. Confidence

### 8.1 Por que existe

Confidence no es metadata decorativa.

Es una senal de decision para el Consumer.

Sin confidence, el runtime trata todo claim como verdad equivalente.
Con confidence, el runtime puede modular comportamiento.

### 8.2 Campos minimos por claim

| Campo | Tipo | Rol |
|---|---|---|
| `confidence` | float 0..1 | fortaleza estimada del claim |
| `validated` | bool | paso validation formal |
| `builder_version` | string | provenance de compilacion |
| `generated_by` | object | extractor/pipeline responsables |
| `evidence` | list | soporte en corpus |

### 8.3 Confidence no autoriza saltarse Validation

Un claim puede tener confidence alta y aun asi fallar Structural/Semantic/Evidence validation.

Solo claims `validated=true` pueden publicarse como Warm.

---

## 9. Riesgos

| Riesgo | Probabilidad | Impacto | Mitigacion |
|---|---|---|---|
| Structural drift del contrato | Media | Alto | Schemas versionados + contract_version + validacion en carga |
| Contract drift entre builds activos | Baja | Alto | Registry valida compatibility antes de promote |
| Confundir Knowledge Model con Artifacts | Media | Alto | Separar KIR / Model / Artifact Generation / Registry (RES-002) |
| Confundir KIR con contrato | Baja | Medio | KIR es interno; contrato es Warm Artifacts |
| Warm Artifacts demasiado grandes | Baja | Medio | Particionado por layer + lazy load |
| Acoplar arquitectura a Granite | Media | Alto | Modelo detras de interfaz; contrato independiente del modelo |
| Centrar el sistema en el Builder | Media | Alto | Repetir: el centro es el contrato |
| Consumer accede directo a archivos | Media | Alto | Resolution Protocol obligatorio; Registry como unico punto de acceso |
| Calidad inferior al monolito al inicio | Media | Alto | A/B obligatorio antes de deprecar + rollback en Registry (RES-003) |

---

## 10. Open questions

1. **Storage del Artifact Registry**: archivos versionados, SQLite, o metadata store
2. **Evolucion del catalogo de predicados**: proceso de extension y versionado
3. **Politica de cuarentena**: automatica vs human-in-the-loop
4. **Aprendizaje runtime**: puede la memoria proponer claims al Builder, o solo el Builder publica Warm?
5. **Multi-idioma**: normalizacion y canonicalizacion cross-lingual
6. **A/B de builds**: metricas de calidad del Knowledge Model ademas del pass rate end-to-end
7. **Compatibilidad GraphRAG**: export nativo desde Relation Layer
8. **Bootstrap del Consumer**: carga total vs lazy por layer/artifact (ver RES-003)
9. **Thresholds de confidence por capability**: globales vs especificos (ver RES-003)
10. **Separacion de repos**: cuando justificar Opcion B? (ver RES-002)
11. **Registry migrations**: cuando migrar vs recompilar desde documentos?

---

## 11. Takeaways

1. **El problema no son las heuristicas; es recompilar conocimiento en query-time.**
2. **El centro del sistema es el contrato Warm, no el Builder.**
3. **Builder y Consumer son implementaciones reemplazables; el contrato es lo estable.**
4. **Los Artifacts son serializaciones**, no el modelo interno.
5. **El Artifact Registry es la autoridad unica de publicacion** — un componente con identidad propia, no un directorio.
6. **Tres protocolos**: Publication Protocol (Builder -> Registry), Resolution Protocol (Consumer -> Registry), y el contrato Warm (Registry -> Consumer).
7. **Artifact Lifecycle explica por que Cold nunca cruza la frontera.**
8. **Confidence es una senal de decision del Consumer**, no solo provenance.
9. **Entity Relations usan catalogo controlado** inspirado en RDF, no predicados libres.
10. **El contrato es lo unico que Builder y Consumer comparten.** Todo lo demas es reemplazable.
11. **No se implementa ahora.** Este research prepara la promocion futura a ADR.

---

## 12. Criterio de promocion a ADR

Este research puede promoverse a ADR cuando se acuerde al menos:

- el contrato como centro del sistema
- frontera Builder/Consumer mediada por Artifact Registry
- tres protocolos: Publication, Resolution, contrato Warm
- Artifact Registry como componente de primera clase (publication, compatibility, rollback, integrity, migrations)
- taxonomy Cold/Warm/Hot y su lifecycle
- confidence minima por claim
- catalogo controlado de predicados
- Warm Artifacts minimos del contrato inicial
- manifest schema y checksums

Hasta entonces permanece como research de arquitectura de largo plazo.

Ver tambien:
- **RES-002** para el detalle del Knowledge Builder (compiler, KIR, passes, validation, layers, codegen)
- **RES-003** para el detalle del Knowledge Consumer (consumo de Warm Artifacts, LLMSupport, migracion incremental)
