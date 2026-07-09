# Documentacion

## Arquitectura

El sistema RAG hibrido combina:

1. **Busqueda semantica** (BGE-m3 via sentence-transformers) + **BM25** (rank-bm25)
2. **Reranking** con CrossEncoder
3. **Construccion de contexto** con prompts especializados por tipo de query
4. **Generacion LLM** via Ollama (modelo local)
5. **Postprocesado** con validacion y limpieza de respuestas

## Modulos principales

| Modulo | Responsabilidad |
|--------|----------------|
| `rag_hybrid.py` | Orquestador principal (HybridRAG) |
| `retrieval_engine.py` | Busqueda hibrida + reranking + filtrado |
| `context_builder.py` | Construccion de contexto y prompts LLM |
| `answer_postprocessor.py` | Postprocesado y auto-review |
| `conceptual_map.py` | Mapa conceptual (shortcuts) |
| `learning_queue.py` | Autoaprendizaje diferido |
| `memory_system.py` | Memoria SQLite + conversacion |
| `ollama_manager.py` | Gestion de modelo Ollama |
| `query_classifier.py` | Clasificacion de intencion |
| `doc_cards.py` | Tarjetas de documentos |
| `equivalences_manager.py` | Sinonimos y equivalencias |

## Configuracion

Ver `config.yaml` para parametros de embeddings, retrieval, reranking y RAG.

## Tests

```bash
python -m pytest tests/ -q
```
