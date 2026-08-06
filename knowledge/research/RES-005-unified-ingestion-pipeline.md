---
id: RES-005
category: research
status: proposed
created: 2026-07-29
updated: 2026-07-29
author: human
components: [ingest_incremental, knowledge_builder, vector_store, artifact_registry, hash_registry, kir_cache]
tags: [architecture, ingestion, incremental, unified-pipeline, vector-db, knowledge-builder, idempotent]
related: [RES-002, RES-006, ADR-0021, ADR-0018, BM-005, BM-006]
supersedes: null
superseded_by: null
---

# RES-005 - Unified Ingestion Pipeline

## Topic

Un unico script orquesta la ingesta completa de documentos nuevos al sistema, cubriendo tanto la indexacion en la Vector DB (ChromaDB) como la extraccion de conocimiento estructurado (Knowledge Builder KIR cache), en un solo paso incremental e idempotente.

## Sources

- `ingest_incremental.py`: ingesta incremental de PDFs a ChromaDB con hash registry
- `scripts/build_knowledge.py`: builder CLI con subcomandos extract/compile/validate/publish (ADR-0021)
- `knowledge_builder/frontend/llm_entity_extractor.py`: cache KIR por chunk con hash SHA-256
- `src/hash_registry.py`: registro persistente de hashes para Vector DB
- ADR-0021: split del builder CLI y cache KIR
- ADR-0018: arquitectura del Knowledge Builder

---

## 1. Problema

Hoy la ingesta de documentos nuevos requiere dos procesos manuales independientes:

1. **Vector DB**: `python ingest_incremental.py` — extrae PDF, chunking, embedding, inserta en ChromaDB, registra hash
2. **Knowledge Builder**: `python scripts/build_knowledge.py extract --use-llm ...` seguido de compile/validate/publish

Ambos son incrementales e idempotentes, pero:
- Son procesos separados que el operador debe coordinar manualmente
- No hay garantia de que un documento indexado en Vector DB tambien haya sido extraido por el Knowledge Builder (o viceversa)
- No hay un punto unico de observabilidad para el estado de la ingesta
- El operador debe recordar el orden correcto y los parametros de cada comando

## 2. Idea central

Un unico script `ingest_unified.py` que:

1. Detecte documentos nuevos (o modificados) via hash
2. Los indexe en ChromaDB (Vector DB)
3. Los extraiga con LLM (Knowledge Builder KIR cache)
4. Opcionalmente ejecute compile + validate + publish al final

```
PDF nuevo
   |
   v
[Hash Check] -- ya procesado en ambos? --> skip
   |
   v
[Vector DB Ingest] -- ChromaDB + HashRegistry
   |
   v
[KIR Extract] -- LLM cache por chunk
   |
   v
[Checkpoint] -- persiste estado de ambos sistemas
   |
   (repeat per doc)
   |
   v
[Compile + Validate + Publish] -- opcional, al final
```

## 3. Diseño propuesto

### 3.1 Script unificado

```python
# ingest_unified.py
# Uso:
#   python ingest_unified.py                          # ingesta todos los nuevos
#   python ingest_unified.py --max-docs 50            # limita a 50 docs nuevos
#   python ingest_unified.py --publish                # compile+validate+publish al final
#   python ingest_unified.py --use-llm                # activa extractor LLM
#   python ingest_unified.py --llm-model ibm/granite4.1:8b-q4_K_M
```

### 3.2 Estado unificado

Un registro unificado `data/ingest_unified_state.json` que trackea por documento:

```json
{
  "doc_hash": "sha256...",
  "filename": "example.pdf",
  "vector_db": {
    "status": "indexed",
    "chunks_indexed": 42,
    "timestamp": "2026-07-30T..."
  },
  "knowledge_builder": {
    "status": "extracted",
    "chunks_cached": 15,
    "kir_claims": 120,
    "timestamp": "2026-07-30T..."
  }
}
```

Estados posibles por subsistema:
- `pending`: no procesado
- `indexed` / `extracted`: completado
- `failed`: error (con mensaje)
- `partial`: interrumpido a mitad (para reintentar)

### 3.3 Flujo por documento

```python
for doc in new_docs:
    # 1. Vector DB
    if not vector_db_state[doc].is_indexed():
        chunks = chunker.create_chunks_with_metadata(pdf_data)
        embeddings = embedder.process_chunks(chunks)
        vectordb.add_chunks(chunks)
        update_state(doc, vector_db="indexed")

    # 2. Knowledge Builder (KIR cache)
    if not kb_state[doc].is_extracted():
        kir = llm_extractor.extract_doc(doc)  # cache por chunk
        update_state(doc, knowledge_builder="extracted")

    # 3. Checkpoint (persistir estado)
    save_state()
```

### 3.4 Publicacion opcional

Con `--publish`, despues de procesar todos los docs:

```python
if args.publish:
    subprocess.run(["python", "scripts/build_knowledge.py", "compile", ...])
    subprocess.run(["python", "scripts/build_knowledge.py", "validate", ...])
    subprocess.run(["python", "scripts/build_knowledge.py", "publish", ...])
```

### 3.5 Idempotencia

- **Vector DB**: `HashRegistry` con SHA-256 del contenido del PDF
- **Knowledge Builder**: cache KIR por chunk con hash SHA-256 del texto del chunk
- **Estado unificado**: el registro `ingest_unified_state.json` permite reanudar desde el ultimo doc completado

Re-ejecutar el script no re-procesa nada ya completado. Si se corta a mitad de un doc, ese doc se reintentara completo en la siguiente ejecucion (el chunk a medias se re-procesa, los chunks completos son cache hit).

## 4. Separacion de responsabilidades

El script unificado **no fusiona** la logica de Vector DB y Knowledge Builder. Solo **orquesta**:

- **Vector DB**: delega a `PDFExtractor`, `TextChunker`, `EmbeddingGenerator`, `VectorStore`, `HashRegistry`
- **Knowledge Builder**: delega a `LLMEntityExtractor` (cache KIR) y `build_knowledge.py` subcomandos

Cada subsistema mantiene su propia persistencia y idempotencia. El script unificado solo coordina y trackea estado.

## 5. Ventajas

- **Un solo comando** para ingesta completa
- **Consistencia garantizada**: un documento siempre esta en ambos sistemas o en ninguno
- **Observabilidad unificada**: un solo JSON con el estado de toda la ingesta
- **Interrumpible y reanudable**: el estado persiste entre ejecuciones
- **No acoplamiento**: orquesta, no fusiona. Cada subsistema es independiente

## 6. Riesgos y mitigaciones

| Riesgo | Mitigacion |
|---|---|
| Fallo en Vector DB pero KB exitoso | Estado unificado detecta la inconsistencia y reintenta solo el subsistema fallido |
| Fallo en LLM (Ollama caido) | KIR cache persiste lo completado; Vector DB ya indexo. Reanudar despues |
| Documento muy grande (>100 chunks) | Procesar por chunk, checkpoint por chunk, no por doc |
| Regresion en ingest_incremental.py | El script unificado delega, no reemplaza. ingest_incremental.py sigue funcionando independiente |
| Cache KIR con 0 claims por timeout LLM | Fix aplicado: resultados con error de extraccion no se cachean (metadata `extraction_error`) |

## 7. Compatibility

- `ingest_incremental.py` sigue funcionando para Vector DB solo
- `scripts/build_knowledge.py` sigue funcionando para KB solo
- El script unificado es una capa de orquestacion encima, no un reemplazo

## 8. Roadmap

- **Fase 1**: Script basico que orquesta ambos procesos secuencialmente con estado unificado
- **Fase 2**: Paralelizacion opcional (Vector DB y KB en paralelo por doc, ya que son independientes)
- **Fase 3**: Integracion con observabilidad (logs estructurados, metricas de throughput)

## 9. Limitaciones conocidas

- **Solo texto**: el pipeline actual extrae unicamente texto de PDFs via `PDFExtractor`. Imagenes, diagramas, figuras y contenido visual se ignoran completamente. Un documento cuyo valor explicativo reside en un diagrama (ej: arquitectura de red, flujo de ataque) pierde ese conocimiento. Ver RES-006 para la propuesta de ingesta multimodal.

## 10. Open questions

1. **Chunks paralelos**: ¿vale la pena paralelizar Vector DB y KB por documento, o procesar secuencial es suficiente?
2. **Granularidad de checkpoint**: ¿por chunk o por documento? Por chunk es mas fino pero mas I/O.
3. **Re-embedding**: si el modelo de embeddings cambia, ¿como detectar que hay que re-indexar Vector DB aunque el hash del PDF no cambio?
4. **Re-extraccion KIR**: si el prompt del LLM cambia, ¿como invalidar cache KIR selectivamente?
