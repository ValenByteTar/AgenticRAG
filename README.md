# Sistema RAG Hibrido de Ciberseguridad

Sistema local de Recuperacion Aumentada por Generacion (RAG) para consultar documentacion tecnica de ciberseguridad. Combina recuperacion semantica, busqueda lexical, reranking y un LLM local mediante Ollama.

El proyecto esta pensado para ejecutarse en Windows desde un entorno virtual Python. No requiere claves de APIs externas para el flujo principal.

## Contenido

- [Que hace el sistema](#que-hace-el-sistema)
- [Arquitectura](#arquitectura)
- [Requisitos](#requisitos)
- [Instalacion](#instalacion)
- [Configuracion](#configuracion)
- [Ingesta de documentos](#ingesta-de-documentos)
- [Uso](#uso)
- [Evaluacion](#evaluacion)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Troubleshooting](#troubleshooting)
- [Estado y limitaciones](#estado-y-limitaciones)

## Que hace el sistema

El flujo de consulta es:

1. Recibe una pregunta en la interfaz web o en la consola.
2. Clasifica la consulta, detecta entidades y aplica normalizaciones.
3. Genera un embedding de la pregunta.
4. Ejecuta busqueda semantica en ChromaDB y busqueda lexical BM25.
5. Fusiona ambas fuentes de resultados.
6. Reordena candidatos con un CrossEncoder.
7. Construye un contexto con los fragmentos seleccionados.
8. Aplica gates de evidencia y factualidad.
9. Genera la respuesta con un LLM local gestionado por Ollama.
10. Limpia y postprocesa la respuesta, incluyendo fuentes y paginas.

La ingesta sigue este flujo:

```text
PDF -> PyMuPDF -> texto por pagina -> chunks por tokens -> embeddings -> ChromaDB
                                                    |
                                                    +-> metadata de fuente y pagina
```

## Arquitectura

```text
                 +-------------------+
                 |    Web / CLI      |
                 +---------+---------+
                           |
                           v
                 +-------------------+
                 |    HybridRAG      |
                 |   rag_hybrid.py   |
                 +---------+---------+
                           |
          +----------------+----------------+
          |                                 |
          v                                 v
+---------------------+           +---------------------+
| RetrievalEngine     |           | ContextBuilder      |
| - BGE semantic      |           | - contexto          |
| - BM25              |           | - prompt            |
| - fusion            |           +----------+----------+
| - CrossEncoder      |                      |
+----------+----------+                      v
           |                         +---------------------+
           v                         | Ollama / LLM local |
+---------------------+               +----------+----------+
| ChromaDB            |                          |
| BGE-M3 embeddings   |                          v
+---------------------+               +---------------------+
                                     | Postprocesamiento  |
                                     | gates y fuentes    |
                                     +---------------------+
```

### Componentes principales

| Componente | Responsabilidad |
|------------|-----------------|
| `rag_hybrid.py` | Orquestacion completa del flujo de consulta |
| `retrieval_engine.py` | Busqueda semantica, BM25, fusion, filtros y reranking |
| `context_builder.py` | Seleccion y organizacion del contexto para el LLM |
| `src/pdf_extractor.py` | Extraccion de texto pagina por pagina con PyMuPDF |
| `src/chunker.py` | Segmentacion semantica o por tokens y metadata |
| `src/embedder.py` | Generacion y normalizacion de embeddings |
| `src/vector_store.py` | Persistencia y consulta de ChromaDB |
| `src/rag/factual_gate.py` | Bloqueo de respuestas factuales sin evidencia suficiente |
| `answer_postprocessor.py` | Limpieza y validacion de respuestas |
| `ollama_manager.py` | Inicio, disponibilidad y comunicacion con Ollama |
| `memory_system.py` | Memoria de conocimiento y contexto conversacional |
| `doc_cards.py` | Roles y tarjetas de documentos |

## Requisitos

### Software

- Windows 10 o posterior
- Python 3.10 o posterior
- Python 3.12 recomendado por `requirements.txt`
- Ollama instalado y disponible en `http://localhost:11434`
- Git, opcional para clonar el repositorio

### Hardware

- GPU CUDA recomendada para generar embeddings rapidamente
- CPU soportada, pero la ingesta y las consultas seran mas lentas
- Espacio suficiente para los modelos locales, ChromaDB y los PDFs
- Para el LLM local, la memoria disponible depende del modelo elegido

### Modelos locales

La configuracion actual espera, como minimo:

- Embeddings: `models/BAAI-bge-m3`
- Reranker: `models/BAAI-bge-reranker-v2-m3`
- LLM: modelo disponible en Ollama, configurado en el codigo o en la configuracion correspondiente

Los modelos locales no se descargan automaticamente por `pip`. Deben estar presentes en las rutas indicadas o ser configurados explicitamente.

## Instalacion

Desde PowerShell, ubicado en la raiz del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Si PowerShell bloquea la activacion del entorno, se puede ejecutar directamente el interprete:

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Comprobar Ollama:

```powershell
ollama list
```

Si el modelo de generacion no esta instalado, descargarlo con el nombre utilizado por la configuracion del proyecto:

```powershell
ollama pull <modelo-llm>
```

No se debe agregar una API key al codigo. El flujo principal usa modelos locales.

## Configuracion

La configuracion central esta en `config.yaml`.

### Rutas principales

```yaml
paths:
  pdf_dir: protocolosPDF
  extracted_dir: data/extracted_texts
  vectordb_dir_bge: chroma_bge_m3
```

- `protocolosPDF`: directorio de entrada de documentos.
- `data/extracted_texts`: copias de texto extraido por PDF.
- `chroma_bge_m3`: base vectorial persistente.

### Chunking

```yaml
chunking:
  token_chunking: true
  token_chunk_size: 350
  token_overlap: 50
```

El chunking actual se realiza por tokens y conserva la pagina de origen en la metadata.

### Embeddings

```yaml
embeddings_bge:
  model_name: models/BAAI-bge-m3
  provider: sentence-transformers
  device: cuda
```

Si no hay CUDA disponible, el sistema puede utilizar CPU, aunque con mayor latencia.

### Retrieval y ChromaDB

```yaml
retrieval:
  top_k: 10
  semantic_weight: 0.6

vectordb:
  collection_name_bge: cybersec_docs_bge_m3
  similarity_metric: cosine
  search_ef: 64
```

### Reranker

```yaml
reranker:
  model_name: models/BAAI-bge-reranker-v2-m3
  candidate_pool: 35
  mix:
    hybrid_weight: 0.50
    rerank_weight: 0.50
```

### Flags de RAG

`config.yaml` tambien controla planner, DocCards, postprocesamiento, deduplicacion, fuentes, expansion de sinonimos y otras heuristicas. Los cambios de configuracion deben validarse con la suite de evaluacion antes de considerarse baseline.

## Ingesta de documentos

### Ingesta completa o rebuild

1. Copiar los PDFs a `protocolosPDF/`.
2. Verificar que los modelos de embeddings y reranking existan.
3. Ejecutar el build:

```powershell
.\.venv\Scripts\python.exe build_rag_system.py
```

El build procesa los PDFs por lotes:

```text
PDF -> extraccion por pagina -> chunking -> embeddings -> ChromaDB
```

El build puede limpiar la coleccion si `vectordb.rebuild_on_build` esta en `true`. Esta operacion elimina el indice anterior y requiere reconstruir todos los embeddings.

Para elegir variante BGE explicitamente:

```powershell
.\.venv\Scripts\python.exe build_rag_system.py --variant bge
```

Antes de ejecutar un rebuild, comprobar el valor de `rebuild_on_build` y respaldar la base si es necesario.

### Ingesta incremental

La ingesta incremental evita recalcular documentos sin cambios mediante un hash SHA256 del texto extraido completo:

```powershell
.\.venv\Scripts\python.exe ingest_incremental.py
```

El registro se guarda en `data/ingest_registry.json`. Si el hash ya existe, el documento se salta. Si se agregan o modifican PDFs, solo se procesan los hashes nuevos.

Reintentar documentos cuyo numero de chunks indexados fue menor al esperado:

```powershell
.\.venv\Scripts\python.exe ingest_incremental.py --retry-incomplete
```

Actualizar DocCards despues de incorporar documentos:

```powershell
.\.venv\Scripts\python.exe ingest_incremental.py --update-doccards
```

### Que se almacena

Cada chunk queda en ChromaDB con:

- ID unico
- Texto del chunk
- Embedding normalizado
- Nombre y ruta del PDF
- Numero de pagina
- Indice del chunk
- Fecha del documento cuando esta disponible
- Categoria o seccion cuando esta disponible

Los PDFs escaneados o basados exclusivamente en imagen pueden no producir texto. Deben pasar por OCR antes de la ingesta.

## Uso

### Interfaz web

Iniciar desde la raiz del proyecto:

```powershell
.\.venv\Scripts\python.exe web_app.py
```

La aplicacion Flask queda normalmente disponible en `http://localhost:5000`. La interfaz soporta respuestas en streaming y consulta el mismo `HybridRAG` que la CLI.

### Interfaz de consola

```powershell
.\.venv\Scripts\python.exe chat.py
```

Tambien existe el entry point:

```powershell
.\.venv\Scripts\python.exe chat_console_entry.py
```

Comandos habituales de la CLI:

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

Para ejecutar una consulta sin el flujo completo del LLM:

```powershell
.\.venv\Scripts\python.exe query_rag.py
```

Este modo consulta ChromaDB, aplica el threshold configurado y muestra los fragmentos recuperados con fuente, pagina y score.

## Evaluacion

La suite esta en `tests/eval/` y usa un dataset de 75 preguntas con ground truth de fuentes, paginas, keywords y casos no respondibles.

Ejecutar la suite completa:

```powershell
.\.venv\Scripts\python.exe tests/eval/run_cybersec_eval.py
```

Ejecutar un subconjunto:

```powershell
.\.venv\Scripts\python.exe tests/eval/run_cybersec_eval.py --ids 1,5,21
.\.venv\Scripts\python.exe tests/eval/run_cybersec_eval.py --category no_answer
.\.venv\Scripts\python.exe tests/eval/run_cybersec_eval.py --limit 15
.\.venv\Scripts\python.exe tests/eval/run_cybersec_eval.py --kw-threshold 0.3
```

La suite genera reportes JSON y Markdown en `tests/eval/reports/`.

Metricas principales:

- `doc_hit`: documento esperado recuperado.
- `page_hit`: pagina esperada recuperada dentro de la tolerancia.
- `MRR` y `recall`: posicion y cobertura de documentos esperados.
- `keyword_score`: presencia de conceptos esperados en la respuesta.
- `groundedness`: ausencia de contenido prohibido o no sustentado segun el caso.
- `anti-hallucination`: capacidad de declinar preguntas sin evidencia.
- Latencia total y breakdown por etapas.

Para construir o revisar ground truth:

```powershell
.\.venv\Scripts\python.exe tests/eval/build_ground_truth.py --search "never trust always verify"
.\.venv\Scripts\python.exe tests/eval/build_ground_truth.py --list-sources --limit 30
```

## Pruebas y diagnostico

Ejecutar tests disponibles:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

Para diagnostico, revisar especialmente:

- Logs de `web_app.py` y de la consola.
- Conteo de la coleccion `cybersec_docs_bge_m3`.
- `data/ingest_registry.json`.
- `data/extracted_texts/`.
- Reportes en `tests/eval/reports/`.

## Estructura del proyecto

```text
SistemaRAGHybrid/
|-- rag_hybrid.py
|-- retrieval_engine.py
|-- context_builder.py
|-- answer_postprocessor.py
|-- ollama_manager.py
|-- query_classifier.py
|-- doc_cards.py
|-- memory_system.py
|-- conceptual_map.py
|-- learning_queue.py
|-- equivalences_manager.py
|-- web_app.py
|-- chat.py
|-- chat_console_entry.py
|-- query_rag.py
|-- build_rag_system.py
|-- ingest_incremental.py
|-- config.yaml
|-- requirements.txt
|-- protocolosPDF/
|-- data/
|   |-- extracted_texts/
|   |-- ingest_registry.json
|   `-- doc_roles.json
|-- chroma_bge_m3/
|-- models/
|   |-- BAAI-bge-m3/
|   `-- BAAI-bge-reranker-v2-m3/
|-- src/
|   |-- pdf_extractor.py
|   |-- chunker.py
|   |-- embedder.py
|   |-- vector_store.py
|   |-- hash_registry.py
|   |-- factual_gate.py
|   |-- rag/
|   `-- utils/
|-- tests/eval/
|-- docs/
|-- templates/
`-- static/
```

## Troubleshooting

### No se puede cargar el embedding

Verificar que exista `models/BAAI-bge-m3`, que el `device` sea valido y que las dependencias de `sentence-transformers` esten instaladas dentro de `.venv`.

### Ollama no responde

Comprobar que el servicio esta iniciado y que el modelo requerido aparece en `ollama list`. El sistema no puede generar respuestas si Ollama esta detenido o el modelo no existe.

### ChromaDB vacio

Ejecutar un build completo o la ingesta incremental. Verificar que haya PDFs con texto extraible en `protocolosPDF/`.

### No se recuperan paginas esperadas

Revisar que la ingesta haya sido ejecutada despues de cambiar chunking o metadata. El ground truth y el indice deben corresponder al mismo corpus.

### La ingesta se detiene por memoria

Reducir el batch de PDFs de `build_rag_system.py`, usar CPU si la GPU no tiene suficiente VRAM y revisar que el modelo de embeddings limite la longitud de secuencia.

### Windows muestra errores de encoding

Ejecutar con el entorno virtual del proyecto y mantener la salida en UTF-8. El core intenta reconfigurar stdout y stderr a UTF-8, pero la terminal tambien debe soportar esa codificacion.

## Estado y limitaciones

El pipeline actual esta orientado a un corpus tecnico de ciberseguridad y a modelos locales. Las principales limitaciones son:

- La calidad depende de que los documentos tengan texto extraible.
- Las preguntas que no estan sustentadas en el corpus deben ser rechazadas.
- El reranker y los embeddings locales pueden tener menor rendimiento en consultas cross-lingual.
- El tiempo de respuesta esta dominado por la generacion del LLM local.
- Cambiar el modelo, el chunking o el ground truth requiere revalidar la suite.
- Las carpetas de modelos, ChromaDB, PDFs y datos generados no deben versionarse sin una decision explicita.

El baseline validado del proyecto se documenta en `tests/eval/reports/` y en el plan de mejora de `C:\Users\Valen\.windsurf\plans\pipeline-improvement-v7-ac133e.md`.

## Licencia

Uso interno.
