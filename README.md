# Sistema RAG Hibrido de Ciberseguridad

Sistema de Recuperacion Aumentada por Generacion (RAG) especializado en documentacion tecnica de ciberseguridad.

## Caracteristicas

### RAG Hibrido
- Busqueda semantica (BGE-m3) + BM25 (keywords)
- Reranking con CrossEncoder
- Filtrado por entidad con fuzzy matching
- Busqueda en dos etapas: documento especifico + contexto amplio

### Gestion de Conocimiento
- Memoria incremental (SQLite) para sinonimos y equivalencias
- Mapa conceptual (JSON) para hechos verificados
- Cola de autoaprendizaje con validacion LLM

### Interfaz
- Web: Flask + streaming de respuestas
- CLI: chat.py
- Comandos especiales: /ayuda, /reset, /documentos, /memoria

## Arquitectura

```
Usuario (Web/CLI)
    |
HybridRAG.query()  (rag_hybrid.py)
    |
    +-- RetrievalEngine     (retrieval_engine.py)
    |     +-- Vector Store  (ChromaDB, BGE-m3)
    |     +-- BM25          (rank-bm25)
    |     +-- Reranker      (CrossEncoder)
    |
    +-- ContextBuilder      (context_builder.py)
    |     +-- Prompt generation
    |     +-- LLM scoring de snippets
    |
    +-- AnswerPostprocessor (answer_postprocessor.py)
    |     +-- Validacion y limpieza
    |     +-- Auto-review opcional
    |
    +-- Ollama              (ollama_manager.py)
          +-- LLM local (Qwen3, etc.)
```

## Instalacion

### Requisitos
- Python 3.10+
- Ollama con modelo local
- GPU recomendada (CUDA) para embeddings

### Pasos

1. Clonar repositorio:
```bash
git clone https://github.com/ValenByteTar/SistemaRAGHybrid.git
cd SistemaRAGHybrid
```

2. Crear entorno virtual e instalar dependencias:
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m spacy download es_core_news_sm
```

3. Configurar Ollama:
```bash
ollama pull <modelo>
```

4. Indexar documentos PDF:
```bash
python build_rag_system.py
```

5. Iniciar:
```bash
# Web
python web_app.py
# CLI
python chat.py
```

## Configuracion

Archivo principal: `config.yaml`

```yaml
embeddings:
  model_name: models/BAAI-bge-m3
  device: cuda
  provider: sentence-transformers

vectordb:
  collection_name: cybersec_docs_bge_m3

rag:
  top_k: 10
  use_reranker: true
```

## Estructura del Proyecto

```
SistemaRAGHybrid/
├── rag_hybrid.py            # Core RAG (HybridRAG)
├── retrieval_engine.py      # Busqueda hibrida + reranking
├── context_builder.py       # Construccion de contexto y prompts
├── answer_postprocessor.py  # Postprocesado de respuestas
├── conceptual_map.py        # Mapa conceptual (shortcuts)
├── learning_queue.py        # Autoaprendizaje
├── memory_system.py         # Memoria + conversacion
├── ollama_manager.py        # Gestion de Ollama
├── query_classifier.py      # Clasificacion de queries
├── doc_cards.py             # Tarjetas de documentos
├── equivalences_manager.py  # Sinonimos y equivalencias
├── web_app.py               # Flask web server
├── chat.py                  # CLI interface
├── build_rag_system.py      # Indexado de documentos
├── ingest_incremental.py    # Indexado incremental
├── config.yaml              # Configuracion
├── requirements.txt         # Dependencias
├── src/
│   ├── embedder.py          # Embeddings (BGE-m3 / Ollama)
│   ├── vector_store.py      # ChromaDB wrapper
│   ├── chunker.py           # Chunking de texto
│   ├── pdf_extractor.py     # Extraccion de PDFs
│   ├── hash_registry.py     # Hash de documentos
│   ├── metrics_logger.py    # Logging de metricas
│   ├── metrics_analyzer.py  # Analisis de metricas
│   ├── rag/
│   │   ├── entity_extractor.py
│   │   ├── query_classifier.py
│   │   ├── prompt_builder.py
│   │   └── system_commands.py
│   └── utils/
│       ├── config_loader.py
│       ├── console.py
│       └── device_utils.py
├── scripts/
│   ├── diagnostics/         # Scripts de diagnostico
│   ├── tests/               # Tests sueltos
│   └── utils/               # Utilitarios
├── tests/
│   ├── unit/                # Tests unitarios
│   └── eval/                # Scripts de evaluacion
├── templates/               # Templates Flask
└── static/                  # Assets web
```

## Tests

```bash
.venv\Scripts\activate
python -m pytest tests/ -q
```

## Licencia

Uso interno.
