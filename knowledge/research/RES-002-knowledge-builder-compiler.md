---
id: RES-002
category: research
status: accepted
created: 2026-07-27
updated: 2026-07-28
author: human
components: [knowledge_builder, kir, entity_extractor, doc_cards, equivalences_manager, conceptual_map]
tags: [architecture, index-time, knowledge-compiler, knowledge-ir, knowledge-pass, validation, knowledge-model, layers, codegen, confidence-policy, incremental-compilation]
related: [RES-001, RES-003, RES-004, ADR-0015, ADR-0017, ADR-0018, DEC-008, BM-002, BM-003, BM-004]
supersedes: null
superseded_by: null
---

# RES-002 - Knowledge Builder (Knowledge Compiler)

> Extracto de RES-001 (original). RES-001 fue seccionado en tres:
> - **RES-001** — El contrato Warm como centro arquitectonico
> - **RES-002** — Knowledge Builder / Knowledge Compiler (este documento)
> - **RES-003** — Knowledge Consumer / evolucion del Agentic RAG runtime
>
> **Nota de seccionamiento (2026-07-28):** RES-003 fue a su vez seccionado; el observador
> paralelo LLMSupport quedo en **RES-004**.

## Topic

El Knowledge Builder como compiler de conocimiento: transforma documentos crudos en Knowledge IR, ejecuta passes, valida, y serializa Warm Artifacts publicables via el Artifact Registry.

## Sources

- RES-001: El contrato Warm como centro arquitectonico (frontera Builder/Consumer, Artifact Registry, contrato)
- RES-003: Knowledge Consumer / evolucion del Agentic RAG runtime (como el Consumer consume los artifacts)
- BM-002: A/B Kernel+VERIFY vs Monolito — brecha de 36.3pp causada enteramente por retrieval
- BM-003: A/B Kernel Fase 6 vs Monolito — sin regresion pero brecha persistente
- BM-004: A/B Kernel Fase 6 + bug fixes — brecha reducida a 27.3pp
- DEC-008: Planner + EntityExpansion tunings
- ADR-0015: Knowledge System (retrieval + get_entity)
- ADR-0017: EKS (Engineering Knowledge System dev-time)
- ADR-0018: Knowledge Builder / Consumer split
- Monolito: `rag_hybrid.py`, `doc_cards.py`, `equivalences_manager.py`, `conceptual_map.py`, `src/rag/entity_extractor.py`, `retrieval_engine.py`

---

## 1. Motivacion

### 1.1 El problema de fondo es arquitectonico

El monolito (`rag_hybrid.py`) mezcla responsabilidades de index-time y query-time en un solo flujo. Cada query reconstruye o reinterpreta conocimiento que deberia haberse compilado una vez durante la indexacion.

| Trabajo | Donde se hace hoy | Cuando se ejecuta | Deberia ser |
|---|---|---|---|
| Extraer entidades de documentos | `entity_extractor.update_domain_from_collection()` | Init + cada query | Index-time (compilacion) |
| Clasificar roles de documentos | `doc_cards.build_doc_cards()` / `build_doc_cards_llm()` | Init (con fallback en query) | Index-time (compilacion) |
| Descubrir sinonimos/aliases | `entity_aliases` dict hardcoded + `memory.get_synonyms()` | Cada query | Index-time + Warm Artifact |
| Expandir equivalencias | `equivalences_manager.expand()` (92 grupos hardcoded) | Cada query | Index-time + Warm Artifact |
| Inferir atributos de documentos | `doc_cards._infer_attributes_presence()` | Init | Index-time (compilacion) |
| Estimar centralidad | `doc_cards._estimate_centrality()` | Init | Index-time (compilacion) |
| Construir gazetteer de dominio | `entity_extractor` + `doc_roles` + `domain_map` | Init + cada query | Index-time (compilacion) |
| Expansion ligera de query | `extra_terms` (control, incidente, troubleshooting) | Cada query | Query-time sobre Warm Artifacts |
| Mapa conceptual (hechos aprendidos) | `conceptual_map.py` | Cada query (read) + aprendizaje diferido | Warm Artifact + aprendizaje controlado |
| Filtrado por tecnologia | `_filter_results_by_technology()` | Cada query | Query-time sobre `doc_roles` compilado |

El sintoma visible son las heuristicas. La causa raiz es la ausencia de una frontera clara entre:

- **compilar conocimiento** (index-time)
- **consumir conocimiento** (query-time)

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

## 2. El Builder es un Knowledge Compiler

El Builder no se define alrededor de un LLM.

Se define como un **Knowledge Compiler** con fases explicitas: front-end (adquisicion), middle-end (transformacion), y back-end (generacion de artifacts).

Esto no es un ETL lineal. Es un compiler con representacion intermedia, passes componibles, y back-end intercambiable.

```
              FRONT-END
             (Knowledge Acquisition)
                   |
      +------------+------------+
      |            |            |
  Document     Structural    Knowledge
  Parsing      Analysis      Extraction
      |            |            |
      +------------+------------+
                   |
                   v
          KNOWLEDGE IR (KIR)
          (lossless)
                   |
          +--------+--------+
          |                 |
      IR Pass 1         IR Pass 2
      (Normalize)      (Canonicalize)
          |                 |
          +--------+--------+
                   |
                   v
           IR Validation
          (Structural +
           Semantic +
           Evidence)
                   |
                   v
          Knowledge Model
         (validated KIR)
                   |
            MIDDLE-END
          (optimization)
                   |
                   v
             BACK-END
        (artifact generation)
                   |
          +--------+--------+
          |                 |
      Warm Codegen      Cold Codegen
          |                 |
          +--------+--------+
                   |
                   v
          Artifact Registry
           (publish)
```

### 2.1 Cadena real de produccion de conocimiento

El Builder **no produce artifacts directamente**.

Produce conocimiento.

Ese conocimiento se materializa despues.

```
Knowledge Compiler
  (front-end: acquisition)
        |
        v
  Knowledge IR (KIR)
  (lossless intermediate representation)
        |
        v
  IR Passes (middle-end)
  (normalize, canonicalize, deduplicate, merge)
        |
        v
  IR Validation
  (structural + semantic + evidence)
        |
        v
  Knowledge Model
  (validated KIR, layered)
        |
        v
  Back-End (artifact generation)
        |
        v
  Artifact Registry
  (publish via publication protocol)
        |
        v
  Knowledge Consumer
  (resolve via resolution protocol)
```

- **Knowledge Compiler**: transforma documentos en conocimiento estructurado en fases
- **Knowledge IR (KIR)**: representacion intermedia lossless, no persistida como contrato
- **IR Passes**: transformaciones componibles sobre KIR
- **Knowledge Model**: subconjunto validado de KIR, estructurado en layers
- **Artifact Generation (back-end)**: serializa el Knowledge Model a representaciones persistentes
- **Artifact Registry**: autoridad unica de publicacion de Warm Artifacts (ver RES-001)
- **Knowledge Consumer**: resuelve Warm Artifacts y opera en query-time (ver RES-003)

El Artifact no es el modelo interno.
El Artifact es una **representacion persistente** del Knowledge Model.

### 2.2 Vista end-to-end del Builder

```
Document Corpus
      |
      v
+-------------------------------------------------------------+
|                 KNOWLEDGE BUILDER                            |
|              (index-time Knowledge Compiler)                 |
|                                                              |
|  FRONT-END (Knowledge Acquisition)                           |
|    Document Parsing -> Structural Analysis                   |
|    -> Knowledge Extraction                                   |
|    (multiple extractors -> same KIR)                         |
|                                                              |
|  Knowledge IR (KIR)                                          |
|    (lossless intermediate representation)                    |
|                                                              |
|  MIDDLE-END (IR Passes)                                      |
|    NormalizePass -> CanonicalizePass                         |
|    -> DeduplicationPass -> MergePass                         |
|    (Knowledge Pass API: run(kir) -> kir)                     |
|                                                              |
|  IR Validation                                               |
|    Structural + Semantic + Evidence                          |
|                                                              |
|  Knowledge Model (validated KIR, in-memory, layered)         |
|    L1 Document / L2 Entity / L3 Concept                      |
|    L4 Relation / L5 Retrieval                                |
|                                                              |
|  BACK-END (Artifact Generation)                              |
|    Warm Codegen -> serializa layers validadas                |
|    Cold Codegen -> dump internals + quarantine               |
|                                                              |
|  Cold Artifacts: solo internos al build                      |
+----------------------------+--------------------------------+
                             | publish (Publication Protocol)
                             v
                    +------------------+
                    | ARTIFACT REGISTRY |
                    |  (ver RES-001)    |
                    +--------+---------+
                             |
                             | resolve (Resolution Protocol)
                             v
+-------------------------------------------------------------+
|                 KNOWLEDGE CONSUMER                           |
|              (ver RES-003)                                   |
+-------------------------------------------------------------+
```

---

## 3. Front-End (Knowledge Acquisition)

Transforma documentos crudos en Knowledge IR.

### 3.1 Document Parsing

Parse de estructura, metadata, filenames, headers, formatos.

- PDF parser, Markdown parser, HTML parser
- Metadata extraction (filename, path, frontmatter, headers)
- Deteccion de encoding, idioma, estructura basica

### 3.2 Structural Analysis

Deteccion de estructura documental:

- secciones, subsecciones, jerarquia
- tablas, listas, bloques de codigo
- deteccion de boundaries de chunks
- mapeo de estructura a unidades semanticas

### 3.3 Knowledge Extraction

Deteccion de entidades, relaciones, claims, senales de dominio.

Mecanismos posibles (intercambiables y componibles):

- Regex / reglas deterministas
- NER clasico
- LLM extractor
- futuros extractores (vision, tables, OCR, graph extractors)

El LLM es **un extractor mas**, no el eje de la arquitectura.

---

## 4. Knowledge IR (KIR)

La representacion intermedia no es un artifact. Es el formato interno del compiler.

Analogica al AST en un compiler de codigo:

- no se persiste como contrato
- puede cambiar entre versiones del Builder
- es lo que los passes transforman y validan
- es lo que el back-end serializa a artifacts

KIR es estructurado pero no normalizado todavia. Es el punto donde multiples extractores convergen.

### 4.1 Multiple Extractors, Single IR

**Esta es una decision arquitectonica de primer nivel.**

Cualquier extractor que implemente la interfaz de extraccion produce KIR:

- PDF Parser
- Markdown Parser
- OCR
- Vision
- Tables
- LLM
- NER
- Regex

Todos producen **exactamente el mismo formato**.

El compiler no sabe ni necesita saber que extractor produjo que. Todos convergen al mismo KIR.

Esto significa que anadir un nuevo extractor no cambia nada aguas abajo. El middle-end y el back-end son agnosticos al extractor.

### 4.2 KIR es lossless

Propiedad fundamental: **KIR es lossless**.

Toda transformacion posterior (normalize, canonicalize, validate, codegen) debe poder justificarse remontandose al KIR original. Nada se descarta sin dejar rastro.

Esto facilita:

- **Debugging**: si un Warm Artifact tiene un claim incorrecto, se puede trazar de vuelta al KIR -> al extractor -> al documento fuente
- **Auditoria**: reconstruir que transformaciones se aplicaron a que claims
- **Reproducibilidad**: mismo documento + mismo KIR = mismo artifact

---

## 5. IR Passes (Middle-End)

Transformaciones sobre KIR. Todos los passes implementan la misma interfaz:

```python
class KnowledgePass:
    def run(self, kir: KIR) -> KIR:
        ...
```

**Knowledge Pass API**: todo lo que transforma KIR es un pass. Los passes son plugins.

El compiler decide el orden de los passes. Los passes son componibles, reordenables y extensibles. Un nuevo pass se agrega sin tocar el resto del compiler.

Passes iniciales:

- **NormalizePass**: casing, whitespace, puntuacion, idioma basico, tipos de entidad, schemas intermedios
- **CanonicalizePass**: alias -> entidad canonica, variantes ortograficas -> forma estable, ids de documento estables, predicados de relacion del catalogo controlado, taxonomia de roles
- **DeduplicationPass**: eliminar claims duplicados de multiples extractores
- **MergePass**: mergear KIR nuevo con KIR existente (incremental compilation)
- **ValidationPass**: structural, semantic, evidence (puede rechazar claims)

### 5.1 Confidence Policy

La combinacion de confidence cuando multiples extractores producen el mismo claim **no es un pass**. Es una **politica configurable**.

Confidence Policy:

- **Max**: tomar la confidence mas alta
- **Mean**: promediar
- **Weighted**: ponderar por confianza del extractor (ej. LLM pesa mas que regex)
- **Bayesian**: combinacion probabilistica
- **LLM arbitration**: un LLM decide la confidence final
- **Rule-based**: reglas explicitas por tipo de claim

La politica es configurable por build. No es un paso fijo del pipeline. Es una estrategia intercambiable.

---

## 6. IR Validation

No se publica directamente la salida cruda de Extract.

Toda candidatura a formar parte del Knowledge Model publicable pasa por validacion formal.

### 6.1 Structural Validation

Verifica forma y referencias:

- schema valido
- tipos correctos
- ids presentes y unicos
- referencias resolubles (`doc_id`, `entity_id`, `chunk_id`)
- predicados pertenecientes al catalogo controlado
- ausencia de campos prohibidos en proyecciones Warm

Fallo estructural => el claim no entra al Knowledge Model publicable.

### 6.2 Semantic Validation

Verifica coherencia del conocimiento:

- consistencia de roles
- contradicciones entre aliases
- colisiones de canonicos
- relaciones invalidas o ciclicas no deseadas
- cobertura minima por documento/entidad
- calidad de clasificacion

### 6.3 Evidence Validation

Toda entidad, alias o relacion debe poder justificar su existencia con evidencia del corpus.

Cada claim publicable debe incluir, como minimo:

- `evidence_text` o puntero a evidencia
- `source_doc_id`
- `source_chunk_ids` (si aplica)
- `confidence`
- `validated`
- `builder_version`
- `generated_by` / `extractor_id`

Objetivo: evitar conocimiento imposible de explicar.

Si no hay evidencia suficiente, el claim:

- se descarta, o
- queda en cuarentena (Cold / review queue), nunca como Warm Artifact activo

---

## 7. Knowledge Model (validated KIR)

El subconjunto de KIR que sobrevive validation.

No es un archivo.
No es un JSON.
No es el contrato.

Es la estructura interna sobre la cual se razona, valida y proyecta.

### 7.1 Knowledge Layers

El Builder no genera "un artifact monolitico de conocimiento".

Construye **capas de conocimiento**.

Los artifacts son la forma de persistir cada capa.

Las layers son la estructura del KIR / Knowledge Model, no del artifact.

```
Layer 1  Document Layer
   |
   v
Layer 2  Entity Layer
   |
   v
Layer 3  Concept Layer
   |
   v
Layer 4  Relation Layer
   |
   v
Layer 5  Retrieval Layer
   |
   v
 Artifacts (proyecciones persistentes)
```

#### Layer 1 — Document Layer

Conocimiento sobre documentos:

- identidad documental
- estructura
- roles
- summaries
- atributos presentes
- centralidad

#### Layer 2 — Entity Layer

Conocimiento sobre entidades mencionadas o definidas:

- entidades canonicas
- tipos
- aliases
- menciones por documento/chunk

#### Layer 3 — Concept Layer

Conocimiento abstracto del dominio:

- taxonomias
- categorias
- conceptos no necesariamente anclados a un unico documento
- agrupaciones semanticas estables

#### Layer 4 — Relation Layer

Conocimiento relacional tipado:

- triples subject/predicate/object
- evidencia
- confidence
- versionado

#### Layer 5 — Retrieval Layer

Conocimiento orientado a consumo de retrieval:

- entity index
- retrieval metadata
- preferencias de scoping
- senales utiles para planner/two-stage/comparison

### 7.2 Relacion layers -> artifacts

| Layer | Ejemplos de proyeccion Warm |
|---|---|
| Document | `doc_roles`, doc summaries |
| Entity | `canonical_entities`, `alias_index`, `entity_index` |
| Concept | `taxonomy` |
| Relation | `entity_relations` |
| Retrieval | `retrieval_metadata`, indices derivados |

Esto evita confundir:

- el conocimiento (layers / Knowledge Model)
- con su serializacion (artifacts)

---

## 8. Back-End (Artifact Generation)

Analogico a codegen en un compiler real:

- **Warm codegen**: serializa proyecciones del Knowledge Model a Warm Artifacts (JSON, SQLite, lo que sea)
- **Cold codegen**: dumpea internals (extractor outputs, validation reports, KIR snapshots) a Cold Artifacts para auditoria

El back-end es intercambiable: mismo Knowledge Model -> distintos formatos de artifact (JSON, SQLite, binario).

### 8.1 Publish

El back-end entrega Warm Artifacts al Artifact Registry via Publication Protocol.

El Builder no escribe archivos directamente. Publica a traves del Registry.

Ver RES-001 para el contrato del Artifact Registry.

### 8.2 Modelo utilizado (implementacion inicial)

- Modelo por defecto del Builder: **Granite 4.1 8B**
- El modelo es reemplazable
- El contrato **no depende** del modelo
- En el futuro pueden convivir distintos modelos para distintas etapas (extract, validate, summarize)
- Granite representa la implementacion inicial, no la arquitectura

---

## 9. Que conocimiento del monolito se compila

Esta tabla no dice "reemplazar heuristicas por LLM".

Dice: **ese conocimiento deja de reconstruirse en runtime y pasa a compilarse en el Knowledge Model, luego serializarse como Warm Artifact**.

| Componente actual del monolito | Conocimiento que aporta | Layer | Warm Artifact destino |
|---|---|---|---|
| `entity_aliases` dict | aliases de dominio | Entity | `alias_index` + canonical entities |
| `EQUIVALENCES_EMBEDDED_TEXT` | equivalencias | Entity/Relation | `alias_index` + `entity_relations` |
| `entity_extractor.update_domain_from_collection()` | gazetteer desde corpus | Entity | `entity_index` + canonical entities |
| `doc_cards.*` | roles, atributos, centralidad | Document | `doc_roles` + retrieval metadata |
| `conceptual_map.entity_aliases` | aliases aprendidos | Entity | `alias_index` |
| `conceptual_map.entity_facts` | hechos verificados | Relation | `entity_relations` tipadas |
| `_filter_results_by_technology()` | senales de tipo/tecnologia | Retrieval | `doc_roles` / retrieval metadata |
| `extra_terms` | expansion ad-hoc | Retrieval | expansion query-time sobre Warm Artifacts |
| `_plan_retrieval()` roles preferred | preferencias de retrieval | Retrieval | taxonomy + `doc_roles` |

Los mecanismos de extraccion (regex, NER, LLM, etc.) son internos del Builder. Todos producen KIR. El compiler los procesa de forma agnostica.

---

## 10. Modelos de ejecucion del Builder

### 10.1 Opcion A: Batch standalone (recomendado inicial)

```bash
python build_knowledge.py \
  --docs /path/to/docs \
  --model granite-4.1-8b \
  --output knowledge_artifacts/ka_v1.0.0
```

- Corre fuera del kernel
- Ejecuta full recompile: front-end -> KIR -> passes -> validation -> Knowledge Model -> back-end -> publish
- Publica Warm Artifacts + manifest al Artifact Registry via Publication Protocol
- El Consumer resuelve el manifest en bootstrap via Resolution Protocol

**Ventajas**: simple, desacoplado, auditable.
**Desventajas**: update completo puede ser costoso sin incrementalidad.

### 10.2 Opcion B: Incremental

- Detecta docs nuevos/modificados
- Recompila solo el delta: front-end -> KIR parcial -> MergePass con KIR existente -> revalidacion del grafo afectado
- Regenera y publica nuevo build versionado
- El Registry maneja el swap atomico

### 10.3 Opcion C: Compiler agentic (fase posterior)

El Builder orquesta tools de compilacion:

- `read_document`
- `extract`
- `run_pass` (cualquier pass via Knowledge Pass API)
- `validate`
- `update_knowledge_model`
- `generate_artifacts`
- `publish_to_registry`

Sigue siendo un compiler. La agenticidad es orquestacion, no una excusa para publicar conocimiento no validado.

---

## 11. Donde vive el Builder

### Opcion A: Mismo repo, paquete separado (inicial)

```text
AgenticRAG/
  src/                     # Consumer (kernel)
  knowledge_builder/       # Compiler
    frontend/              # acquisition: parsing, structural, extraction
    kir/                   # Knowledge IR definition
    passes/                # IR passes (Knowledge Pass API)
    validate/              # IR validation
    model/                 # Knowledge Model + layers
    backend/               # artifact generation (codegen)
    publish/               # publication protocol client
  knowledge_artifacts/     # Artifact Registry (builds versionados)
  contract/                # schemas del contrato Warm (shared)
  tests/
```

### Opcion B: Repo separado, shared contract

```text
AgenticRAG/                # Consumer
  src/
  knowledge_artifacts/     # Registry
  contract/                # contrato Warm (shared)

KnowledgeBuilder/          # Compiler
  src/
  contract/                # mismo contrato Warm
```

**Recomendacion**: A inicial, migrar a B si el compiler crece o se despliega independiente.

En ambos casos, el artefacto conceptual central compartido es el **contrato** (ver RES-001), no el codigo del Builder.

---

## 12. Riesgos

| Riesgo | Probabilidad | Impacto | Mitigacion |
|---|---|---|---|
| Extractores generan claims incorrectos | Media | Alto | Evidence validation + cuarentena + confidence |
| Predicados inventados por LLM | Media | Alto | Catalogo controlado + structural validation |
| Confundir Knowledge Model con Artifacts | Media | Alto | Separar KIR / Model / Artifact Generation / Registry |
| Confundir KIR con contrato | Baja | Medio | KIR es interno; contrato es Warm Artifacts (RES-001) |
| Costo de recompilar corpus grande | Alta | Alto | Incremental builds + MergePass + cache por documento |
| Warm Artifacts demasiado grandes | Baja | Medio | Particionado por layer + lazy load |
| Acoplar arquitectura a Granite | Media | Alto | Modelo detras de interfaz; contrato independiente del modelo |
| Centrar el sistema en el Builder | Media | Alto | Repetir: el centro es el contrato (RES-001) |
| Consumer vuelve a recompilar dominio | Media | Alto | Frontera explicita + reviews de arquitectura |
| Extractor divergence (formatos incompatibles) | Baja | Medio | Multiple Extractors -> Same KIR; KIR es el punto de convergencia |

---

## 13. Open questions

1. **Granularidad de compilacion**: documento vs chunk vs seccion
2. **Evolucion del catalogo de predicados**: proceso de extension y versionado
3. **Politica de cuarentena**: automatica vs human-in-the-loop
4. **Aprendizaje runtime**: puede la memoria proponer claims al Builder, o solo el Builder publica Warm?
5. **Multi-idioma**: normalizacion y canonicalizacion cross-lingual
6. **A/B de builds**: metricas de calidad del Knowledge Model ademas del pass rate end-to-end
7. **Compatibilidad GraphRAG**: export nativo desde Relation Layer
8. **Knowledge Pass ordering**: quien decide el orden de passes? El compiler? Config? CI?
9. **Multiple extractores en paralelo**: orquestacion concurrente y merge de KIR
10. **Storage del Artifact Registry**: ver RES-001 open questions

---

## 14. Takeaways

1. **El Builder es un Knowledge Compiler** con front-end, KIR, passes, y back-end — no un ETL lineal.
2. **KIR es lossless**: toda transformacion se puede trazar al origen.
3. **Multiple Extractors -> Same KIR** es una decision arquitectonica de primer nivel.
4. **Knowledge Pass API** hace que toda transformacion sea un plugin extensible.
5. **Confidence es una Policy**, no un pass fijo — estrategia configurable por build.
6. **Knowledge Model se organiza en layers**: Document, Entity, Concept, Relation, Retrieval.
7. **El LLM es un extractor opcional e intercambiable** dentro del front-end.
8. **Validation es obligatoria** antes de publicar Warm.
9. **El conocimiento del monolito se compila, no se reemplaza por LLM.**
10. **El Builder no es el centro del sistema.** El centro es el contrato (RES-001).
11. **No se implementa ahora.** Este research prepara la promocion futura a ADR.

---

## 15. Criterio de promocion a ADR

Este research puede promoverse a ADR cuando se acuerde al menos:

- Knowledge Compiler con front-end / KIR / passes / back-end
- KIR lossless como representacion intermedia
- Multiple Extractors -> Same KIR
- Knowledge Pass API como mecanismo de extension
- Confidence Policy como estrategia configurable
- separacion Knowledge Model vs Artifacts
- knowledge layers
- pipeline de compilacion y validation
- modelo inicial y su reemplazabilidad
- estrategia de compilacion incremental

Hasta entonces permanece como research de arquitectura de largo plazo.
