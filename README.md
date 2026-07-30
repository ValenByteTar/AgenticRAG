# InfraPolus — Sistema RAG Hibrido de Ciberseguridad

Sistema local de Recuperacion Aumentada por Generacion (RAG) para consultar documentacion tecnica de ciberseguridad. Combina recuperacion semantica, busqueda lexical, reranking, un LLM local mediante Ollama, y un Knowledge Builder que extrae conocimiento estructurado del corpus y lo publica como Warm Artifacts consumidos por el runtime.

El proyecto es **local-first** (ADR-0011): no requiere claves de APIs externas para el flujo principal. Todos los modelos corren en la maquina del operador via Ollama y sentence-transformers.

Pensado para ejecutarse en Windows desde un entorno virtual Python.

---

## Contenido

- [Vision general](#vision-general)
- [Arquitectura](#arquitectura)
- [Knowledge Builder y Artifact Registry](#knowledge-builder-y-artifact-registry)
- [Requisitos](#requisitos)
- [Instalacion](#instalacion)
- [Configuracion](#configuracion)
- [Ingesta de documentos](#ingesta-de-documentos)
- [Knowledge Builder: extraccion, compilacion y publicacion](#knowledge-builder-extraccion-compilacion-y-publicacion)
- [Uso](#uso)
- [Evaluacion y benchmarks](#evaluacion-y-benchmarks)
- [Sistema de conocimiento de ingenieria (EKS)](#sistema-de-conocimiento-de-ingenieria-eks)
- [Pruebas](#pruebas)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Roadmap y estado](#roadmap-y-estado)
- [Troubleshooting](#troubleshooting)
- [Limitaciones conocidas](#limitaciones-conocidas)
- [Trabajo futuro](#trabajo-futuro)
- [Licencia](#licencia)

---

## Vision general

### Que hace el sistema

El flujo de consulta es:

1. Recibe una pregunta en la interfaz web o en la consola.
2. Clasifica la consulta, detecta entidades y aplica normalizaciones (aliases, sinonimos).
3. Genera un embedding de la pregunta con BGE-M3.
4. Ejecuta busqueda semantica en ChromaDB y busqueda lexical BM25.
5. Fusiona ambas fuentes de resultados.
6. Reordena candidatos con un CrossEncoder (BGE-reranker-v2-m3).
7. Construye un contexto con los fragmentos seleccionados.
8. Aplica gates de evidencia (ASSESS) y factualidad (VERIFY).
9. Genera la respuesta con un LLM local gestionado por Ollama.
10. Limpia y postprocesa la respuesta, incluyendo fuentes y paginas.

### Dos modos de ejecucion

| Modo | Config | Descripcion |
|------|--------|-------------|
| **Monolito** | `kernel.enabled: false` (default) | `rag_hybrid.py` ejecuta el flujo lineal completo. Fachada estable (ADR-0010). |
| **Kernel** | `kernel.enabled: true` | Controller FSM (ADR-0003) ejecuta capabilities registradas con observabilidad, policies y evaluation online. |

Ambos modos comparten el mismo corpus, modelos y Artifact Registry. El modo Kernel es el camino arquitectonico futuro; el monolito se mantiene como fachada estable hasta E8.

### Dos pipelines de ingesta

| Pipeline | Funcion | Salida |
|----------|---------|--------|
| **Vector DB** | Indexar documentos para retrieval semantico | ChromaDB con embeddings BGE-M3 |
| **Knowledge Builder** | Extraer conocimiento estructurado del corpus | Warm Artifacts en el Artifact Registry |

Ambos son incrementales, cacheables y resumibles. Ver [Ingesta de documentos](#ingesta-de-documentos) y [Knowledge Builder](#knowledge-builder-extraccion-compilacion-y-publicacion).

---

## Arquitectura

### Diagrama del runtime

```text
                 +-------------------+
                 |    Web / CLI      |
                 +---------+---------+
                           |
                           v
                 +-------------------+
                 |    HybridRAG      |        ADR-0010: fachada estable
                 |   rag_hybrid.py   |
                 +---------+---------+
                           |
              +------------+------------+
              | kernel.enabled=false    | kernel.enabled=true
              v                         v
    +-------------------+     +-------------------+
    |  Flujo lineal     |     |  Controller FSM   |  ADR-0003
    |  (monolito)       |     |  + Capabilities   |  ADR-0012
    +-------------------+     |  + Policy Engine  |  ADR-0013
              |               |  + Observability  |  ADR-0005
              |               +---------+---------+
              |                         |
          +---+---+                     |
          |       |                     v
          v       v              +-------------------+
    +---------+ +----------+     | Capability Chain  |
    |Retrieval| | Context  |     | classify ->       |
    |Engine   | | Builder  |     |   memory_read ->  |
    |BGE+BM25 | |          |     |   planner ->      |
    |+Rerank  | +----+-----+     |   entity_expand ->|
    +----+----+      |           |   retrieval ->    |
         |           v           |   build_context ->|
         v    +-----------+      |   assess ->       |
    +--------+ | Ollama    |     |   generate ->     |
    |ChromaDB| | LLM local |     |   verify ->       |
    |BGE-M3  | +-----+-----+     |   finalize_turn   |
    +--------+       |           +-------------------+
                    v
              +-----------+
              | Postproc  |
              | gates     |
              | fuentes   |
              +-----------+
```

### Componentes del runtime

| Componente | Responsabilidad | ADR |
|------------|-----------------|-----|
| `rag_hybrid.py` | Fachada estable; despacha monolito vs kernel | ADR-0010 |
| `retrieval_engine.py` | Busqueda semantica, BM25, fusion, filtros y reranking | — |
| `context_builder.py` | Seleccion y organizacion del contexto para el LLM | — |
| `src/kernel/controller.py` | FSM que ejecuta capabilities | ADR-0003 |
| `src/kernel/registry.py` | Capability Registry (descubrimiento y registro) | ADR-0012 |
| `src/kernel/policy_engine.py` | Policy Engine (senal -> policy -> accion) | ADR-0013 |
| `src/kernel/state.py` | ExecutionState (estado mutable del turno) | ADR-0004 |
| `src/kernel/observability.py` | TraceSink (trazas transversales) | ADR-0005 |
| `src/capabilities/` | Capabilities: classify, memory_read, planner, entity_expansion, retrieval, two_stage_retrieval, build_context, assess, generation, verify, finalize_turn | ADR-0012 |
| `src/policies/` | Policies: LinearRagPolicy, RetrySignalPolicy, AssessGatePolicy, VerifyRepairPolicy | ADR-0013 |
| `src/evaluation/` | Evaluators: AssessEvidenceEvaluator, VerifyGroundednessEvaluator | ADR-0006 |
| `src/adapters/knowledge_system.py` | KnowledgeSystemAdapter (puente entre Knowledge System y capabilities) | ADR-0015 |
| `src/adapters/warm_artifact_resolver.py` | WarmArtifactResolver (Resolution Protocol del Registry) | ADR-0018 |
| `src/adapters/memory_port.py` | MemoryPortAdapter (memoria bajo contrato) | ADR-0009 |
| `src/pdf_extractor.py` | Extraccion de texto pagina por pagina con PyMuPDF | — |
| `src/chunker.py` | Segmentacion semantica o por tokens y metadata | — |
| `src/embedder.py` | Generacion y normalizacion de embeddings (con cache LRU) | — |
| `src/vector_store.py` | Persistencia y consulta de ChromaDB | — |
| `src/hash_registry.py` | Registro de hashes para ingesta incremental idempotente | — |
| `answer_postprocessor.py` | Limpieza y validacion de respuestas | — |
| `ollama_manager.py` | Inicio, disponibilidad y comunicacion con Ollama | ADR-0007 |
| `memory_system.py` | Memoria de conocimiento y contexto conversacional | ADR-0009 |
| `doc_cards.py` | Roles y tarjetas de documentos | — |

---

## Knowledge Builder y Artifact Registry

### Concepto

El Knowledge Builder extrae conocimiento estructurado del corpus en tiempo de indexacion (no en query-time) y lo publica como **Warm Artifacts** en el **Artifact Registry**. El runtime (Consumer) resuelve estos artifacts via Resolution Protocol en lugar de reconstruir conocimiento en cada consulta.

Esto resuelve la brecha de calidad entre el monolito (que tiene conocimiento hardcodeado) y el kernel agentic (que no lo tenia). Ver ADR-0018, RES-001, RES-002, RES-003.

### Arquitectura del Knowledge Builder

```text
                    Corpus (data/extracted_texts/)
                              |
                              v
                    +-------------------+
                    |    Frontend       |
                    |  (Extractors)     |
                    |  - DocCards       |
                    |  - Equivalences   |
                    |  - EntityAliases  |
                    |  - LLM (Granite)  |
                    +---------+---------+
                              |
                              v
                    +-------------------+
                    |    KIR            |     Knowledge Intermediate Representation
                    |  (lossless)       |     cache por chunk: cache/<doc>/chunk_N.kir.json
                    +---------+---------+
                              |
                              v
                    +-------------------+
                    |    Passes         |
                    |  - Normalize      |
                    |  - Canonicalize   |
                    |  - Dedup          |
                    +---------+---------+
                              |
                              v
                    +-------------------+
                    |  Knowledge Model  |     5 layers: Document, Entity, Relation, Concept, Retrieval
                    +---------+---------+
                              |
                              v
                    +-------------------+
                    |    Validate       |     Structural + Semantic + Contract
                    +---------+---------+
                              |
                              v
                    +-------------------+
                    |    Codegen        |
                    |  - Warm Artifacts |     7 proyecciones del contrato warm-v1
                    |  - Cold Artifacts |
                    +---------+---------+
                              |
                              v
                    +-------------------+
                    |  Artifact Registry|     publish -> promote -> resolve
                    |  knowledge_artifacts/ |
                    +-------------------+
```

### Cuatro subcomandos (ADR-0021)

El Builder se divide en cuatro fases unidireccionales (I11):

| Comando | Que hace | LLM? | Cache? |
|---------|----------|------|--------|
| `extract` | Extrae KIR del corpus (determinista + LLM) | Si | Si, por chunk |
| `compile` | Mergea cache, corre passes, produce KnowledgeModel | No | Lee cache |
| `validate` | Valida modelo (structural + semantic + contract) | Opcional | No |
| `publish` | Codegen + publica al Registry | No | No |

**Invariante I9**: validation ocurre antes de codegen. Jamas existen Warm Artifacts invalidos.

### Contrato Warm v1

7 proyecciones (JSON Schemas versionados en `contract/`):

| Artifact | Contenido |
|----------|-----------|
| `canonical_entities` | Entidades canonicas con tipos, confidence, evidence |
| `alias_index` | Mapeo alias -> entity_id |
| `entity_index` | Mapeo entity_id -> documentos relevantes |
| `doc_roles` | Roles de documentos (reference, standard, guide, etc.) |
| `entity_relations` | Relaciones tipadas (9 predicados v2) |
| `retrieval_metadata` | Metadata de retrieval (scoping, preferencias) |
| `predicate_catalog` | Catalogo de predicados versionado |

### Catalogo de predicados v2 (9 predicados)

`equivalent_to`, `depends_on`, `implements`, `extends`, `references`, `governs`, `contains`, `uses`, `creates`

El extractor LLM produce predicados en lenguaje natural; el compilador normaliza al catalogo v2 via `_PREDICATE_FALLBACK` (I10).

### Artifact Registry

| Operacion | Descripcion |
|-----------|-------------|
| `publish` | Entrega artifacts al staging area del Registry |
| `promote` | Valida integridad + compatibility; swap atomico del build activo |
| `resolve` | Punto unico de acceso del Consumer (nunca expone paths) |
| `rollback` | Swap atomico al build anterior |
| `verify_integrity` | SHA-256 por artifact sobre bytes canonicos |
| `list_builds` | Lista builds con estado (staging, promoted, deprecated, archived) |
| `get_manifest` | Manifest del build (build id, contract_version, checksums) |

Ciclo de vida: `staging -> promoted -> deprecated -> archived -> purged`. Un solo build activo.

CLI de operador: `scripts/registry_cli.py`

### Builds registrados

| Build ID | Estado | Descripcion |
|----------|--------|-------------|
| `ka_v1.0.0` | deprecated | Build con extractores deterministas (E3) |
| `ka_v2.0.0` | deprecated | Build con LLM Granite, 10 docs (E5.2 inicial) |
| `ka_v2.0.0_e5` | promoted | Build con LLM Granite, 10 docs + fix de aliases (E5.2) |
| `ka_v2.0.0_full` | (en curso) | Build con LLM Granite, corpus completo (E5.2 extendido) |

### Benchmarks registrados

| BM | Comparacion | Resultado |
|----|-------------|-----------|
| BM-001 | Baseline pre-agentic Fase 0 | 52% pass (25q) |
| BM-002 | Kernel verify vs monolito | 45.5% pass (11q) |
| BM-003 | Kernel fase 6 + bugfixes vs monolito | 45.5% pass (11q) |
| BM-004 | Kernel fase 6 + bugfixes (data flow) | 54.5% pass (11q) |
| BM-005 | Consumer con Warm Artifacts vs baseline | **63.6% pass (7/11)** — gate superado (+9.1pp) |
| BM-006 | (pendiente) ka_v2.0.0_full vs ka_v1.0.0 | — |

---

## Requisitos

### Software

- Windows 10 o posterior
- Python 3.12+ (recomendado por `requirements.txt`)
- Ollama instalado y disponible en `http://localhost:11434`
- Git (opcional)

### Hardware

- **GPU CUDA** recomendada para embeddings y LLM
- CPU soportada, pero ingesta y consultas seran mas lentas
- RAM: minimo 16 GB (32 GB recomendado para modelos 8B)
- Espacio: modelos (~5 GB), ChromaDB (~2 GB), corpus PDFs, cache KIR

### Modelos locales

| Rol | Modelo | Path / Ollama tag |
|-----|--------|-------------------|
| Embeddings | BGE-M3 | `models/BAAI-bge-m3` |
| Reranker | BGE-reranker-v2-m3 | `models/BAAI-bge-reranker-v2-m3` |
| LLM (default) | Mistral 7B | `mistral:7b` (Ollama) |
| LLM (Knowledge Builder) | IBM Granite 4.1 8B | `ibm/granite4.1:8b-q4_K_M` (Ollama) |
| LLM (DocCards) | Qwen3 4B RAG | `qwen3-4b-rag:latest` (Ollama) |
| Embeddings (Vector DB) | Nomic Embed Text | `nomic-embed-text:latest` (Ollama) |

Los modelos locales no se descargan automaticamente por `pip`. Usar `ollama pull <tag>` para modelos de Ollama y colocar los de sentence-transformers en `models/`.

---

## Instalacion

Desde PowerShell, en la raiz del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Si PowerShell bloquea la activacion del entorno:

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Descargar modelos de Ollama necesarios:

```powershell
ollama pull mistral:7b
ollama pull ibm/granite4.1:8b-q4_K_M
ollama pull nomic-embed-text:latest
ollama pull qwen3-4b-rag:latest
```

Verificar:

```powershell
ollama list
```

No se debe agregar una API key al codigo. El flujo principal usa modelos locales (ADR-0011).

---

## Configuracion

La configuracion central esta en `config.yaml`.

### Rutas principales

```yaml
paths:
  pdf_dir: protocolosPDF
  extracted_dir: data/extracted_texts
  vectordb_dir_bge: chroma_bge_m3
```

### Chunking

```yaml
chunking:
  token_chunking: true
  token_chunk_size: 350
  token_overlap: 50
```

### Embeddings

```yaml
embeddings:
  model_name: models/BAAI-bge-m3
  provider: sentence-transformers
  device: cuda
```

### Retrieval y ChromaDB

```yaml
retrieval:
  top_k: 10
  semantic_weight: 0.6
  entity_mode: boost    # filter | boost | off (ADR-0020)

vectordb:
  collection_name: cybersec_docs_bge_m3
  similarity_metric: cosine
  search_ef: 64
  rebuild_on_build: false
```

### Reranker

```yaml
reranker:
  model_name: models/BAAI-bge-reranker-v2-m3
  candidate_pool: 20
  mix:
    hybrid_weight: 0.70
    rerank_weight: 0.30
```

### LLM

```yaml
llm:
  provider: ollama
  model_name: mistral:7b
  base_url: http://localhost:11434
  num_gpu: 99
  num_ctx: 8192
```

### Kernel (modo agentic)

```yaml
kernel:
  enabled: false       # false = monolito; true = Controller FSM
  max_iterations: 12
  max_llm_calls: 6
```

### Knowledge System (Warm Artifacts)

```yaml
knowledge:
  warm_artifacts_enabled: true    # true = Consumer resuelve del Registry
  registry_root: knowledge_artifacts
  confidence_threshold: 0.0
```

### DocCards

```yaml
doccards:
  llm_enabled: true
  model_name: qwen3-4b-rag:latest
  llm_ratio: 0.2         # refina top 20% por centralidad
  llm_timeout: 8
  sample_chars: 600
```

### Flags de RAG

`config.yaml` tambien controla planner, postprocesamiento, deduplicacion, fuentes, expansion de sinonimos y heuristicas. Los cambios de configuracion deben validarse con la suite de evaluacion antes de considerarse baseline.

---

## Ingesta de documentos

### Pipeline 1: Vector DB (retrieval semantico)

#### Ingesta completa o rebuild

```powershell
.\.venv\Scripts\python.exe build_rag_system.py
```

Flujo: `PDF -> PyMuPDF -> texto por pagina -> chunks por tokens -> embeddings BGE-M3 -> ChromaDB`

Si `vectordb.rebuild_on_build` es `true`, se elimina el indice anterior. Por defecto es `false` (ADR Fase 0).

#### Ingesta incremental (idempotente)

```powershell
.\.venv\Scripts\python.exe ingest_incremental.py
```

Usa `HashRegistry` (`src/hash_registry.py`) con SHA-256 del contenido. Si el hash ya existe en `data/ingest_registry.json`, el documento se salta. Solo se procesan hashes nuevos.

Opciones:

```powershell
.\.venv\Scripts\python.exe ingest_incremental.py --retry-incomplete
.\.venv\Scripts\python.exe ingest_incremental.py --update-doccards
```

#### Que se almacena en ChromaDB

Cada chunk incluye: ID unico, texto, embedding normalizado, nombre y ruta del PDF, numero de pagina, indice del chunk, fecha y categoria cuando estan disponibles.

### Pipeline 2: Knowledge Builder (extraccion de conocimiento)

Ver [Knowledge Builder: extraccion, compilacion y publicacion](#knowledge-builder-extraccion-compilacion-y-publicacion).

### Limitacion: solo texto

El pipeline actual extrae unicamente texto de PDFs via `PDFExtractor`. Imagenes, diagramas, figuras y contenido visual se ignoran completamente. Ver [Trabajo futuro](#trabajo-futuro) para la propuesta de ingesta multimodal (RES-006).

---

## Knowledge Builder: extraccion, compilacion y publicacion

### Extraccion incremental con LLM

```powershell
.\.venv\Scripts\python.exe scripts\build_knowledge.py extract --use-llm --llm-max-docs 928 --build-id ka_v2.0.0_full --builder-version 2.0.0 --verbose --cache-dir cache
```

**Caracteristicas**:
- **Cache por chunk**: `cache/<doc_slug>/chunk_N.kir.json` + `meta.json` con hash SHA-256 por chunk
- **Resumible**: cortar con Ctrl+C; relanzar continua desde el ultimo chunk cacheado
- **Persistente**: el cache sobrevive reinicios y apagados
- **Skip cache on error**: si el LLM falla (timeout, JSON invalido), el resultado no se cachea (metadata `extraction_error`)
- **Determinista + LLM**: los extractores deterministas procesan todos los docs; el LLM procesa hasta `--llm-max-docs`

### Compilacion

```powershell
.\.venv\Scripts\python.exe scripts\build_knowledge.py compile --build-id ka_v2.0.0_full --builder-version 2.0.0 --cache-dir cache
```

Lee el cache KIR, corre los passes (Normalize, Canonicalize, Dedup) y produce un `KnowledgeModel`. No invoca al LLM (I11).

### Validacion

```powershell
.\.venv\Scripts\python.exe scripts\build_knowledge.py validate --build-id ka_v2.0.0_full --builder-version 2.0.0 --cache-dir cache
```

Validacion structural + semantica + contrato. Solo modelos validados pueden publicarse (I9).

### Publicacion

```powershell
.\.venv\Scripts\python.exe scripts\build_knowledge.py publish --build-id ka_v2.0.0_full --builder-version 2.0.0 --cache-dir cache
```

Codegen de Warm Artifacts + publicacion al Artifact Registry. Requiere `promote` manual despues.

### Flujo completo (retrocompatible)

```powershell
.\.venv\Scripts\python.exe scripts\build_knowledge.py --use-llm --llm-max-docs 100 --build-id ka_v2.0.0_full --builder-version 2.0.0
```

Sin subcomando, ejecuta los cuatro pasos en secuencia.

### CLI del Artifact Registry

```powershell
.\.venv\Scripts\python.exe scripts\registry_cli.py list
.\.venv\Scripts\python.exe scripts\registry_cli.py promote --build-id ka_v2.0.0_full
.\.venv\Scripts\python.exe scripts\registry_cli.py rollback
.\.venv\Scripts\python.exe scripts\registry_cli.py verify --build-id ka_v2.0.0_full
```

---

## Uso

### Interfaz web

```powershell
.\.venv\Scripts\python.exe web_app.py
```

Aplicacion Flask en `http://localhost:5000`. Soporta respuestas en streaming y consulta el mismo `HybridRAG` que la CLI.

### Interfaz de consola

```powershell
.\.venv\Scripts\python.exe chat.py
```

Comandos de la CLI:

| Comando | Accion |
|---------|--------|
| `/ayuda` | Muestra la ayuda |
| `/fuentes` | Activa o desactiva fuentes |
| `/detalles` | Muestra scores y fragmentos |
| `/config` | Ajusta parametros de busqueda durante la sesion |
| `/agregar` | Agrega conocimiento a la memoria |
| `/memoria` | Consulta la memoria guardada |
| `/contexto` | Limpia el historial conversacional |
| `/limpiar` | Limpia la pantalla |
| `/salir` | Cierra la aplicacion |

### Consulta semantica basica

```powershell
.\.venv\Scripts\python.exe query_rag.py
```

Consulta ChromaDB sin el flujo completo del LLM. Muestra fragmentos recuperados con fuente, pagina y score.

### Scripts de operacion

| Script | Funcion |
|--------|---------|
| `scripts/healthcheck.py` | Diagnostico del sistema (Ollama, ChromaDB, modelos, config) |
| `scripts/llm_monitor.py` | Monitor de Ollama en tiempo real |
| `scripts/backup.py` | Backup del sistema (ChromaDB, config, datos) |
| `scripts/restore.py` | Restauracion desde backup |
| `scripts/build_doccards.py` | Generacion de DocCards |
| `scripts/build_doccards_incremental.py` | DocCards incrementales |
| `scripts/generate_eks_index.py` | Genera indice del EKS |
| `scripts/registry_cli.py` | CLI del Artifact Registry |

---

## Evaluacion y benchmarks

### Suite de evaluacion

Dataset de 75 preguntas con ground truth de fuentes, paginas, keywords y casos no respondibles.

```powershell
.\.venv\Scripts\python.exe tests\eval\run_cybersec_eval.py
```

Subconjuntos:

```powershell
.\.venv\Scripts\python.exe tests\eval\run_cybersec_eval.py --ids 1,5,21
.\.venv\Scripts\python.exe tests\eval\run_cybersec_eval.py --category no_answer
.\.venv\Scripts\python.exe tests\eval\run_cybersec_eval.py --limit 15
.\.venv\Scripts\python.exe tests\eval\run_cybersec_eval.py --kernel    # forzar camino Kernel
```

Reportes en `tests/eval/reports/`.

### Metricas

- `doc_hit`: documento esperado recuperado
- `page_hit`: pagina esperada recuperada dentro de tolerancia
- `MRR` y `recall`: posicion y cobertura
- `keyword_score`: presencia de conceptos esperados
- `groundedness`: ausencia de contenido no sustentado
- `anti-hallucination`: capacidad de declinar sin evidencia
- Latencia total y breakdown por etapas

### Historial de benchmarks

| BM | Fase | Comparacion | Pass rate | Delta |
|----|------|-------------|-----------|-------|
| BM-001 | F0 | Baseline pre-agentic | 52% (25q) | — |
| BM-002 | F1 | Kernel verify vs monolito | 45.5% (11q) | baseline kernel |
| BM-003 | F6 | Kernel fase 6 + bugfixes | 45.5% (11q) | sin regresion |
| BM-004 | F6 | Kernel fase 6 (data flow fix) | 54.5% (11q) | +9pp |
| BM-005 | E4 | Warm Artifacts vs baseline | **63.6% (7/11)** | +9.1pp |
| BM-006 | E5.3 | (pendiente) ka_v2.0.0_full vs ka_v1.0.0 | — | — |

Objetivo: cerrar la brecha de 27.3pp entre el kernel (54.5%) y el monolito (81.8%).

---

## Sistema de conocimiento de ingenieria (EKS)

El proyecto mantiene un **Engineering Knowledge System** (ADR-0017) fuera de `src/`, en `knowledge/`. No es el Knowledge System runtime (ADR-0015); es documentacion viva de decisiones, experimentos, benchmarks y research.

### Estructura

```
knowledge/
├── decisions/     (DEC-001 a DEC-012)
├── experiments/   (EXP-001 a EXP-006b)
├── benchmarks/    (BM-001 a BM-005)
├── research/      (RES-001 a RES-006)
├── postmortems/
├── patterns/
├── skills/
├── INDEX.md       (auto-generado)
└── _eks_index.json
```

### ADRs

22 ADRs en `docs/adr/` (ADR-0000 a ADR-0021). Cubren: proceso, modelo de planos, contrato controller, FSM, execution state, observability, evaluation, model provider, knowledge store, memory, fachada, local-first, capability registry, policy engine, inyeccion de dependencias, knowledge system, kernel, EKS, knowledge builder/consumer split, epistemic contract, ownership, y builder CLI split + KIR cache.

### Documentos de research

| RES | Topic | Status |
|-----|-------|--------|
| RES-001 | Contrato Warm como centro arquitectonico | accepted |
| RES-002 | Knowledge Builder (Knowledge Compiler) | accepted |
| RES-003 | Knowledge Consumer / evolucion del Agentic RAG runtime | accepted |
| RES-004 | LLMSupport: observador paralelo de hipotesis | accepted |
| RES-005 | Unified Ingestion Pipeline (Vector DB + KB) | proposed |
| RES-006 | Multimodal Ingestion: Knowledge Sources, Normalizers & Connectors | proposed |

### Plan de orquestacion

El plan detallado de ejecucion del Knowledge Builder/Consumer esta en `docs/plan-orquestacion-knowledge.md`, con etapas E0-E8 (Track A) y B0-B3 (Track B - LLMSupport).

---

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

### Cobertura de tests

| Modulo | Tests | Descripcion |
|--------|-------|-------------|
| `tests/unit/test_kernel_phase0.py` | 13 | Kernel, contracts, execution state |
| `tests/unit/test_phase1_close_gates.py` | 24 | Controller FSM, capabilities |
| `tests/unit/test_phase3_cleanup_streaming_eks.py` | 23 | Streaming, EKS index |
| `tests/unit/test_phase4_verify_repair.py` | 20 | VERIFY evaluator, repair policy |
| `tests/unit/test_phase5_knowledge_memory.py` | 17 | Adapters, protocol compliance |
| `tests/unit/test_phase6_planner_expansion.py` | 23 | Planner, entity expansion |
| `tests/unit/test_contract_warm_v1.py` | 34 | Contrato Warm, JSON Schemas |
| `tests/unit/test_artifact_registry.py` | 21 | Registry, publish, rollback, integrity |
| `tests/unit/test_knowledge_builder_e3.py` | 46 | KIR, extractors, passes, codegen |
| `tests/unit/test_e5_1_adr_0021.py` | 374 | CLI split, KIR cache, predicate v2, roles v2 |
| `tests/unit/test_e4_warm_artifacts_consumer.py` | — | Consumer resolviendo Warm Artifacts |

Total: 200+ tests.

---

## Estructura del proyecto

```text
AgenticRAG/
├── rag_hybrid.py                  # Fachada estable (ADR-0010)
├── retrieval_engine.py            # Busqueda hibrida (semantica + BM25 + rerank)
├── context_builder.py             # Construccion de contexto para LLM
├── answer_postprocessor.py        # Postprocesamiento de respuestas
├── ollama_manager.py              # Gestion de Ollama
├── query_classifier.py            # Clasificacion de consultas
├── doc_cards.py                   # Roles y tarjetas de documentos
├── memory_system.py               # Memoria conversacional
├── conceptual_map.py              # Mapa conceptual / atajos
├── learning_queue.py              # Cola de aprendizaje
├── equivalences_manager.py        # Equivalencias y sinonimos
├── web_app.py                     # Interfaz web (Flask)
├── chat.py                        # Interfaz de consola
├── query_rag.py                   # Consulta semantica basica
├── build_rag_system.py            # Build completo de Vector DB
├── ingest_incremental.py          # Ingesta incremental Vector DB
├── config.yaml                    # Configuracion central
├── requirements.txt               # Dependencias
│
├── src/
│   ├── kernel/                    # Controller, Registry, PolicyEngine, State, Observability
│   ├── capabilities/              # 11 capabilities (classify, retrieval, generation, etc.)
│   ├── policies/                  # Policies (retry, assess gate, verify repair)
│   ├── evaluation/                # Evaluators (assess, verify)
│   ├── adapters/                  # KnowledgeSystemAdapter, WarmArtifactResolver, MemoryPort
│   ├── artifact_registry/         # Artifact Registry (publish, promote, resolve, rollback)
│   ├── contract/                  # Validador de contrato Warm
│   ├── providers/                 # ModelProvider (Ollama)
│   ├── pdf_extractor.py           # Extraccion de texto de PDFs
│   ├── chunker.py                 # Segmentacion de texto
│   ├── embedder.py                # Generacion de embeddings
│   ├── vector_store.py            # ChromaDB wrapper
│   ├── hash_registry.py           # Registro de hashes para ingesta incremental
│   ├── rag/                       # Factual gate
│   └── utils/                     # Utilidades
│
├── knowledge_builder/
│   ├── frontend/                  # Extractors (DocCards, Equivalences, EntityAliases, LLM)
│   ├── kir/                       # Knowledge Intermediate Representation
│   ├── passes/                    # Normalize, Canonicalize, Dedup
│   ├── model/                     # KnowledgeModel (5 layers)
│   ├── validate/                  # Structural + Semantic validators
│   ├── backend/                   # Warm codegen + Cold codegen
│   ├── publish/                   # Publicacion al Registry
│   ├── compiler.py                # Orquestador del Builder
│   └── diff_report.py             # Reporte de diferencias entre builds
│
├── contract/                      # JSON Schemas del contrato Warm v1
│
├── knowledge_artifacts/           # Artifact Registry (builds, state, cold artifacts)
│   ├── builds/                    # Builds publicados (inmutables)
│   ├── cold/                      # Cold Artifacts
│   └── state/                     # active.json + builds_index.json
│
├── cache/                         # KIR cache por chunk (extraccion LLM incremental)
│
├── scripts/
│   ├── build_knowledge.py         # CLI del Knowledge Builder (extract/compile/validate/publish)
│   ├── registry_cli.py            # CLI del Artifact Registry
│   ├── healthcheck.py             # Diagnostico del sistema
│   ├── llm_monitor.py             # Monitor de Ollama
│   ├── backup.py                  # Backup del sistema
│   ├── restore.py                 # Restauracion desde backup
│   ├── build_doccards.py          # Generacion de DocCards
│   ├── generate_eks_index.py      # Genera indice del EKS
│   └── diagnostics/               # Scripts de diagnostico
│
├── knowledge/                     # Engineering Knowledge System (EKS)
│   ├── decisions/                 # DEC-001 a DEC-012
│   ├── experiments/               # EXP-001 a EXP-006b
│   ├── benchmarks/                # BM-001 a BM-005
│   ├── research/                  # RES-001 a RES-006
│   ├── postmortems/
│   ├── patterns/
│   ├── skills/
│   ├── INDEX.md                   # Auto-generado
│   └── _eks_index.json
│
├── docs/
│   ├── adr/                       # 22 ADRs (ADR-0000 a ADR-0021)
│   ├── plan-orquestacion-knowledge.md  # Plan E0-E8 + Track B
│   ├── roadmap.md                 # Roadmap de implementacion
│   ├── philosophy.md              # Filosofia del proyecto
│   ├── vision.md                  # Vision arquitectonica
│   ├── principles.md              # Principios de diseño
│   └── phase0-exit.md             # Gate de salida Fase 0
│
├── tests/
│   ├── eval/                      # Suite de evaluacion (75q dataset)
│   ├── unit/                      # Tests unitarios (200+)
│   └── contract/                  # Tests de contrato Warm
│
├── data/
│   ├── extracted_texts/           # Texto extraido de PDFs
│   ├── ingest_registry.json       # Hash registry de Vector DB
│   └── doc_roles.json             # Roles de documentos
│
├── protocolosPDF/                 # Corpus de PDFs
├── chroma_bge_m3/                 # ChromaDB persistente
├── models/                        # Modelos locales (BGE-M3, reranker)
├── templates/                     # Templates Flask
└── static/                        # Assets web
```

---

## Roadmap y estado

### Fases completadas

| Fase | Descripcion | Estado | Gate |
|------|-------------|--------|------|
| F0 | Kernel y fundaciones | CERRADA | baseline congelado, kernel testeado |
| F1 | Controller FSM 1:1 | CERRADA | 24 tests passed |
| F2 | ASSESS enriquecido | CERRADA | 44 tests passed |
| F3 | Multi-retry + two-stage | CERRADA | 54 tests passed |
| F4 | VERIFY + repair | CERRADA | 20 tests passed |
| F5 | Knowledge System + Memory | CERRADA | 17 tests passed |
| F6 | Planner + decomposition | CERRADA | 23 tests, BM-003 |
| E0 | Saneamiento del EKS | CERRADA | docs consistentes |
| E1 | Contrato Warm v1 | CERRADA | 34 tests, schemas validan |
| E2 | Artifact Registry | CERRADA | 21 tests, CLI funcional |
| E3 | Builder minimo (determinista) | CERRADA | ka_v1.0.0, diff report |
| E4 | Consumer resuelve Warm Artifacts | CERRADA | BM-005 = 63.6% (gate superado) |
| E5.1 | Infraestructura ADR-0021 | CERRADA | CLI split, KIR cache, predicate v2 |

### En curso

| Etapa | Descripcion | Estado |
|-------|-------------|--------|
| E5.2 | Build ka_v2.0.0_full con LLM | Extraccion incremental en curso (corpus completo) |
| E5.3 | BM-006: A/B ka_v2.0.0_full vs ka_v1.0.0 | Pendiente de E5.2 |

### Pendientes

| Etapa | Descripcion |
|-------|-------------|
| E6 | Retrieval Layer (retrieval_metadata rico, two-stage guiado por artifact) |
| E7 | Relation Layer + Concept Layer (entity_relations, taxonomy) |
| E8 | Deprecacion del conocimiento embebido (monolito -> fachada pura) |
| B0-B3 | LLMSupport (observador paralelo de hipotesis) |
| F9 | Compuestas (memoria escritura, tools, multi-modelo) |

---

## Troubleshooting

### No se puede cargar el embedding

Verificar que exista `models/BAAI-bge-m3`, que `device` sea valido y que `sentence-transformers` este instalado en `.venv`.

### Ollama no responde

```powershell
ollama list
```

Si el modelo no aparece: `ollama pull <modelo>`. Si Ollama no esta corriendo: `ollama serve`.

### Ollama timeout durante extraccion LLM

El modelo 8B puede tardar 100+ segundos por chunk. Si hay timeout:
- El resultado no se cachea (fix aplicado: `extraction_error` en metadata)
- Relanzar el extract continua desde el ultimo chunk exitoso
- Verificar que no haya otros procesos usando la GPU

### ChromaDB vacio

Ejecutar `build_rag_system.py` o `ingest_incremental.py`. Verificar que haya PDFs con texto extraible en `protocolosPDF/`.

### No se recuperan paginas esperadas

Revisar que la ingesta haya sido ejecutada despues de cambiar chunking o metadata. El ground truth y el indice deben corresponder al mismo corpus.

### La ingesta se detiene por memoria

Reducir el batch de PDFs, usar CPU si la GPU no tiene suficiente VRAM, revisar que el modelo de embeddings limite la longitud de secuencia.

### Windows muestra errores de encoding

Ejecutar con el entorno virtual del proyecto y mantener la salida en UTF-8. El core reconfigura stdout y stderr a UTF-8, pero la terminal tambien debe soportarlo.

### Cache KIR con 0 claims

Si un chunk tiene 0 claims, puede ser por timeout del LLM o JSON invalido. El fix aplicado evita que se cachee. Borrar el chunk afectado de `cache/<doc_slug>/` y relanzar el extract.

---

## Limitaciones conocidas

- **Solo texto**: el pipeline actual extrae unicamente texto de PDFs. Imagenes, diagramas, figuras y contenido visual se ignoran (RES-006 propone solucion).
- **Sin ingesta unificada**: Vector DB y Knowledge Builder se ejecutan por separado. RES-005 propone un orquestador unificado.
- **Conocimiento embebido**: el monolito (`rag_hybrid.py`) aun contiene conocimiento de dominio hardcodeado (aliases, roles, equivalences). Se deprecara en E8.
- **Kernel deshabilitado por defecto**: `kernel.enabled: false`. Se activara por defecto tras EXP-001-B.
- **Modelos locales**: la calidad depende de los modelos elegidos. Cambiar modelo requiere revalidar la suite.
- **Cross-lingual**: el reranker y los embeddings pueden tener menor rendimiento en consultas cross-lingual.
- **Corpus de ciberseguridad**: el sistema esta orientado a un corpus tecnico de ciberseguridad. Dominios requieren reconfiguracion.

---

## Trabajo futuro

### RES-005: Unified Ingestion Pipeline

Propone un unico script (`ingest_unified.py`) que orquesta tanto la ingesta a Vector DB como la extraccion del Knowledge Builder en un solo paso incremental e idempotente, con estado unificado y observabilidad.

### RES-006: Multimodal Ingestion

Propone extender el pipeline para soportar multiples fuentes de conocimiento mas alla de texto de PDFs:

- **Knowledge Sources**: Documentos, Presentaciones (PPTX), Codigo, Web, Tablas, Conversaciones, Datos estructurados, Imagenes (OCR + Vision LLM), Emails, Archives
- **Normalizers**: capa separada que transforma la salida de cualquier parser en un `CanonicalDocument`
- **CanonicalDocument**: contrato explicito con identidad, metadata, contenido, secciones, attachments, fingerprinting dual (binary hash + content hash) y versioning
- **Canonical Intermediate Representation (CIR)**: representacion rica del documento (secciones, parrafos, tablas, imagenes, metadata). El texto es una vista, no el centro
- **Acquisition Connectors**: Local FS, Google Drive, GitHub, Notion, Confluence, SharePoint, Dropbox, OneDrive, S3

### Roadmap arquitectonico

- **E6**: Retrieval Layer con `retrieval_metadata` rico y two-stage guiado por artifact
- **E7**: Relation Layer + Concept Layer con `entity_relations` y taxonomy
- **E8**: Deprecacion del conocimiento embebido; monolito reducido a fachada
- **Track B**: LLMSupport como observador paralelo de hipotesis
- **F9**: Capacidades compuestas (memoria escritura verificada, tools, multi-modelo)

---

## Licencia

Uso interno.
