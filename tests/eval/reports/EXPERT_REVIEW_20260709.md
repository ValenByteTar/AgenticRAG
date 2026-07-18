# Informe de Evaluacion del Pipeline RAG - Ciberseguridad
**Fecha:** 09 de Julio 2026  
**Evaluador:** Sistema automatizado (harness `run_cybersec_eval.py`)  
**Destinatario:** Experto en arquitectura de sistemas RAG  
**Objetivo:** Identificar deficiencias del pipeline para priorizar mejoras y refactorizaciones

---

## 1. Resumen Ejecutivo

El pipeline RAG de ciberseguridad fue evaluado sobre un dataset de **75 preguntas** curadas, distribuidas en cinco categorias: simple, multi-documento, sin-respuesta esperada, ambigua y compleja. El tiempo total de ejecucion fue de **4048 segundos (~67 minutos)**.

| Metrica Global | Valor |
|---|---|
| Preguntas evaluadas | 75 |
| Tasa de aprobacion general | **36.0%** (27/75) |
| Tasa aprobacion - respondibles | **39.7%** (respuestas con fuente en corpus) |
| Tasa aprobacion - no-respondibles | **16.7%** (rechazo correcto de preguntas fuera de alcance) |
| Tiempo promedio por query | **52.3 segundos** |

El resultado es **insatisfactorio para produccion**. La causa principal es un fallo masivo en la capa de retrieval (36/75 casos con `retrieval_doc_miss`) combinado con una tasa de alucinacion critica en preguntas fuera de dominio (83.3% de tasa de fallo).

---

## 2. Metricas por Capa del Pipeline

### 2.1 Capa de Retrieval

| Metrica | Valor | Interpretacion |
|---|---|---|
| Doc hit rate | **42.9%** | El documento correcto aparece en top-10 solo 4 de 10 veces |
| Page hit rate | **11.1%** | La pagina exacta casi nunca es recuperada |
| Recall@1 | **22.2%** | El doc correcto en posicion 1 solo 1 de 5 veces |
| Recall@3 | **34.9%** | En top-3 solo 1 de 3 veces |
| Recall@5 | **41.3%** | En top-5 menos de la mitad de las veces |
| MRR promedio | **0.292** | Rango promedio de primer hit: posicion ~3.4 |
| Precision@K | **0.146** | Solo 1.5 documentos relevantes de cada 10 recuperados |
| Doc miss count | **36 casos** | 48% de todas las preguntas respondibles fallan en retrieval |
| Page miss count | **20 casos** | De los que recuperan el doc, 74% no llegan a la pagina correcta |

**Diagnostico:** El retrieval es el cuello de botella dominante. Un Recall@5 de 41.3% sobre un corpus de 100.480 chunks indica que la busqueda semantica y BM25 no estan priorizando correctamente los fragmentos relevantes para este dominio.

### 2.2 Veredictos Independientes por Capa

| Capa | Tasa de Aprobacion | Casos que fallan |
|---|---|---|
| Retrieval | **52.0%** | 36/75 |
| Groundedness (forbidden) | **92.0%** | 6/75 |
| Generation (keywords) | **86.7%** | 10/75 |
| Anti-alucinacion | **16.7%** | 10/12 preguntas no-respondibles |

La capa de groundedness y generation funcionan razonablemente. **El retrieval y el control de alucinacion son las dos fallas criticas.**

### 2.3 Top Problemas por Frecuencia

| Problema | Frecuencia | % del total |
|---|---|---|
| `retrieval_doc_miss` | **36** | 48% |
| `retrieval_page_miss` (warning) | **20** | 27% |
| `hallucination_no_decline` | **10** | 13% |
| `low_kw_score` | **10** | 13% |
| `found_forbidden` | **6** | 8% |

---

## 3. Rendimiento por Categoria

| Categoria | Total | Aprobadas | Tasa | Doc Hit | Recall | MRR | KW Score |
|---|---|---|---|---|---|---|---|
| **simple** | 30 | 11 | **36.7%** | 11 | 0.367 | 0.199 | 0.597 |
| **multi_document** | 11 | 6 | **54.5%** | 6 | 0.258 | 0.424 | 0.614 |
| **no_answer** | 12 | 2 | **16.7%** | 0 | N/A | N/A | 1.0 |
| **ambiguous** | 10 | 2 | **20.0%** | 3 | 0.250 | 0.200 | 0.275 |
| **complex** | 12 | 6 | **50.0%** | 7 | 0.417 | 0.479 | 0.439 |

**Observaciones criticas:**
- Las preguntas **complejas** superan a las **simples** (50% vs 36.7%) — esto sugiere que el pipeline favorece consultas elaboradas con multiples entidades, y falla en consultas cortas y directas donde la query es ambigua para el retriever.
- Las preguntas **ambiguas** tienen la tasa mas baja entre las respondibles (20%) — el pipeline carece de un mecanismo de aclaracion o desambiguacion.
- Las preguntas **no-respondibles** fallan el 83.3% — el sistema no declina adecuadamente consultas fuera de dominio.

---

## 4. Analisis de Latencia

### 4.1 Estadisticas Generales

| Metrica | Valor |
|---|---|
| Promedio | **52.3 s** |
| P50 (mediana) | **49.3 s** |
| P95 | **103.6 s** |
| Maximo | **149.6 s** |

### 4.2 Breakdown por Etapa (promedio)

| Etapa | Avg (ms) | % del total | Evaluacion |
|---|---|---|---|
| Embed query (BGE-M3) | **750 ms** | ~1.4% | Aceptable; cacheable |
| Busqueda semantica (ChromaDB) | **65 ms** | ~0.1% | Excelente |
| BM25 keyword search | **1,310 ms** | ~2.5% | Alto para 100k docs; ver nota |
| Fusion + ranking | **59 ms** | ~0.1% | Excelente |
| Re-ranker (BGE-reranker-v2-m3) | **3,211 ms** | ~6.1% | Mejorable; ver nota |
| LLM Ollama (mistral:7b) - estimado | **54,189 ms** | **~103%** | Dominante absoluto |

**Notas:**
- El **LLM domina el 90%+ de la latencia**. Cualquier optimizacion en retrieval tiene impacto marginal mientras el LLM no mejore.
- El **re-ranker oscila entre 50ms (aislado) y 3.5s (con LLM activo)** — la causa es contension de VRAM entre `mistral:7b` (~4.4 GB) y el re-ranker (~400 MB) en una GPU de 6 GB. El re-ranker se descarga/recarga entre inferencias.
- El **BM25 sobre 100k documentos** tarda 1.3s — para produccion con alta concurrencia esto puede ser un cuello de botella.
- El **embedding de query (750ms)** es alto para una sola query; con cache LRU activo deberia bajar en conversaciones multi-turno.

---

## 5. Analisis de Fallas Especificas

### 5.1 Retrieval Miss en Preguntas Simples (Alta Prioridad)

Las siguientes preguntas basicas fallan en retrieval pese a que el corpus contiene los documentos relevantes:

| Query | Razon probable |
|---|---|
| "Que es el NIST Cybersecurity Framework?" | El retriever devuelve `NIST SP 1800-28` pero el ground-truth es `NIST CSF 2.0` — problema de precision de fuente esperada |
| "Que significa CIA en ciberseguridad?" | Acronimo ambiguo; el retriever trae chunks generales, no el documento anchor especifico |
| "Que es phishing?" | Termino generico; el retriever no prioriza el documento con la definicion canonicaи |
| "Que es SQL injection?" / "Que es XSS?" | El corpus tiene OWASP WSTGuide pero el retriever no lo rankea en top-10 para queries cortas |
| "Que es SOAR en el contexto de un SOC?" | El acronimo SOAR no es expandido ni reconocido por el entity extractor |

**Patron identificado:** Queries cortas con acronimos o terminos genericos producen resultados dispersos. El retriever no tiene un mecanismo de "query expansion" ni un lookup de acronimos previo a la busqueda.

### 5.2 Fallo Critico en Anti-Alucinacion (16.7% tasa de aprobacion)

De 12 preguntas no-respondibles, el sistema **solo rechazo correctamente 2**. Los 10 fallos incluyen:

| Query | Problema |
|---|---|
| "Cual es el precio de la certificacion CISSP en Argentina?" | Respondio con precio inventado |
| "Cuantos empleados tiene ISC2 a nivel global?" | Respondio con numero inventado |
| "Cual es la temperatura ideal de un datacenter segun ASHRAE?" | Respondio con "18 grados" (informacion fuera del corpus) |
| "Que CVE especifico fue usado en SolarWinds SUNBURST?" | No declino, respondio con informacion parcial |
| "Cual es el salario promedio de un CISO en Latinoamerica?" | Respondio con salario inventado |
| "Que dice el RFC 9293 sobre TCP?" | El RFC no esta en el corpus; respondio igual |
| "Cuantos requisitos tiene PCI DSS 4.0.1?" | Respondio con numero especifico no verificable |
| "Cuales son los endpoints de la API de ChatGPT para vision?" | Completamente fuera de dominio; respondio igual |
| "Cual fue el impacto financiero exacto de NotPetya en Maersk?" | Respondio con cifra especifica pese a no estar en corpus |
| "Cual es la contrasena por defecto del Cisco ASA 5505?" | No declino ante pregunta de seguridad operacional |

**El sistema no tiene un gate de rechazo efectivo para preguntas fuera de corpus o fuera de dominio.**

### 5.3 Page Miss (27% de las preguntas)

De los 27 casos que pasan retrieval, 20 no llegan a la pagina correcta (74%). Esto indica que el sistema recupera el documento correcto pero fragmentos irrelevantes del mismo. El chunking actual no preserva suficiente contexto semantico localizado.

---

## 6. Distribucion de Rank del Primer Hit Relevante

| Rank | Frecuencia | Acumulado |
|---|---|---|
| 1 | 14 (51.9% de hits) | 51.9% |
| 2 | 4 | 66.7% |
| 3 | 4 | 81.5% |
| 4 | 3 | 92.6% |
| 5 | 1 | 96.3% |
| 9 | 1 | 100% |

**Positivo:** Cuando el retriever encuentra el documento, lo pone en posicion 1 el 52% de las veces. El problema no es el ranking una vez que hay match, sino que no encuentra el documento el 48% de las veces.

---

## 7. Problemas Identificados y Recomendaciones

### PRIORIDAD CRITICA

#### P1: Gate de Rechazo (Anti-Alucinacion)
**Problema:** El sistema responde preguntas completamente fuera del corpus con informacion inventada. La tasa de alucinacion es 83.3% en preguntas no-respondibles.  
**Recomendacion:** Implementar un gate pre-LLM basado en score del re-ranker. Si el max rerank score < umbral (ej. 0.3), el sistema debe declinar antes de invocar el LLM. Actualmente el sistema llama al LLM incluso cuando todos los scores del re-ranker son < 0.01.  
**Impacto estimado:** Eliminar 8-10 alucinaciones directas; mejorar tasa no-respondibles de 16.7% a >80%.

#### P2: Query Expansion para Acronimos y Terminos Cortos
**Problema:** Queries de 2-5 palabras con acronimos (CIA, SIEM, SOAR, XSS, OT/ICS) no recuperan los documentos correctos porque el retriever no expande el vocabulario antes de buscar.  
**Recomendacion:** Expandir el gazetteer de acronimos en `entity_extractor.py` para cubrir los terminos que fallan. Agregar una etapa de "query rewriting" que convierta "Que es CIA?" en "CIA Confidentiality Integrity Availability triad cybersecurity" antes de llamar a `hybrid_search`.  
**Impacto estimado:** Reducir `retrieval_doc_miss` de 36 a ~20, mejorando pass rate general de 36% a ~50%.

### PRIORIDAD ALTA

#### P3: Contension de VRAM entre LLM y Re-ranker
**Problema:** El re-ranker BGE-reranker-v2-m3 en CUDA tarda 50ms en aislamiento pero 3.5s cuando comparte GPU con `mistral:7b`, porque la GPU descarga el modelo entre inferencias.  
**Recomendacion:** Configurar `keep_alive` en Ollama para mantener `mistral:7b` residente en VRAM durante la sesion. Adicionalmente, evaluar mover el re-ranker a CPU con multithreading (4-8 threads) como alternativa dado que 10 pares en CPU con todos los hilos tarda ~200ms — comparable a CUDA con contension.  
**Impacto estimado:** Reducir latencia del re-ranker de 3.5s a <200ms, ahorrando ~3s por query (~6% del total).

#### P4: Latencia del LLM (Dominante al 90%)
**Problema:** `mistral:7b` promedia 54 segundos por respuesta. Para preguntas complejas con contextos de 17.000-25.000 caracteres, supera los 100-150 segundos.  
**Recomendaciones:**
- Evaluar `mistral:7b-instruct-q4_K_M` (cuantizacion 4-bit) que reduce tokens/s a ~40% menos de VRAM y tipicamente 2x mas rapido.
- Reducir el tamano maximo del contexto enviado al LLM. Actualmente se envian hasta 25.000 chars (~6.000 tokens); limitar a 8.000-10.000 chars para preguntas simples.
- Evaluar modelos alternativos: `phi-3-mini` (3.8B) o `gemma2:2b` para preguntas simples, reservando `mistral:7b` para preguntas complejas (routing por complejidad).

#### P5: Page-Level Retrieval Deficiente (11.1% page hit)
**Problema:** Solo el 11% de queries recupera la pagina exacta (+/-2). Esto indica que los chunks no estan suficientemente contextualizados con metadatos de seccion o que el chunk size es inadecuado.  
**Recomendacion:** Revisar el chunking strategy. Actualmente parece usar chunks de ~500-2000 chars por pagina. Considerar:
- Chunks con overlap del 20-30% para preservar continuidad semantica entre paginas.
- Metadatos enriquecidos: titulo de seccion, capitulo, numero de pagina en el chunk text (no solo en metadata).
- Chunking jerarquico: chunks pequeños para retrieval, chunks grandes para contexto LLM.

### PRIORIDAD MEDIA

#### P6: BM25 sobre 100k Documentos (1.3s promedio)
**Problema:** El indice BM25 se recalcula sobre 100.480 documentos en cada query, tardando 1.3s. En produccion con concurrencia esto escala mal.  
**Recomendacion:** Pre-computar y cachear el indice BM25 en disco (serializar con `pickle`). El indice BM25 es estatico mientras no cambia el corpus. Tiempo de carga desde disco: ~200ms vs recalculo 1.3s/query.

#### P7: Preguntas Ambiguas (20% tasa de aprobacion)
**Problema:** El pipeline no tiene mecanismo de desambiguacion. Queries como "Como audito el sistema?", "Que es un agente?", "Como me preparo para la certificacion?" fallan porque son demasiado vagas para el retriever.  
**Recomendacion:** Implementar un clasificador de ambiguedad. Si la query es detectada como ambigua (longitud < 5 palabras, sin entidades reconocidas, sin contexto previo), responder con una pregunta aclaratoria en lugar de intentar recuperar documentos.

#### P8: Ausencia de Fidelidad de Citas (citation_fidelity = null)
**Problema:** El campo `citation_fidelity` es null en el 100% de los casos. El sistema no genera citas en formato `[Doc N - nombre p.X]` que permitirian verificar la fuente de cada afirmacion.  
**Recomendacion:** Revisar el prompt template para instruir explicitamente al LLM a incluir referencias. Agregar post-procesamiento que verifique que cada afirmacion factual tenga una cita verificable contra `sources_returned`.

#### P9: Keyword Score en Preguntas Complejas (avg 0.439)
**Problema:** Las preguntas complejas tienen el keyword score mas bajo (0.439). El LLM genera respuestas que no usan el vocabulario exacto esperado.  
**Recomendacion:** Los keywords de evaluacion para preguntas complejas deben ser mas flexibles (sinonimos, variantes). Alternativamente, en produccion usar semantic similarity contra keywords en lugar de exact match.

---

## 8. Inventario de Deficiencias por Componente

| Componente | Archivo | Deficiencia | Severidad |
|---|---|---|---|
| Gate pre-LLM | `rag_hybrid.py` | No existe umbral de score para declinar | **CRITICA** |
| Query expansion | `src/rag/entity_extractor.py` | Gazetteer incompleto (SOAR, OT/ICS, CIA triad, etc.) | **ALTA** |
| Chunking strategy | `build_rag_system.py` | Sin overlap, sin metadatos de seccion en texto | **ALTA** |
| Re-ranker device | `rag_hybrid.py` | Contension VRAM con LLM; configurar keep_alive | **ALTA** |
| LLM model | `config.yaml` | `mistral:7b` demasiado lento para produccion | **ALTA** |
| BM25 index | `rag_hybrid.py` | Se recalcula en memoria cada sesion | **MEDIA** |
| Desambiguacion | `rag_hybrid.py` | Sin deteccion ni manejo de queries ambiguas | **MEDIA** |
| Prompt template | `src/rag/prompt_builder.py` | Sin instruccion explicita de citar fuentes | **MEDIA** |
| Contexto al LLM | `rag_hybrid.py` | Hasta 25k chars enviados; sin limite por tipo de pregunta | **MEDIA** |
| Evaluation keywords | `cybersec_eval_questions.json` | Keywords para preguntas complejas muy especificas | **BAJA** |

---

## 9. Metricas Adicionales de Calidad de Respuesta

| Metrica | Valor | Contexto |
|---|---|---|
| KW score promedio | **0.596** | Aceptable; el LLM cubre ~60% de los terminos esperados |
| KW score - simple | 0.597 | Estable entre categorias |
| KW score - no_answer | **1.0** | Las respuestas de "no encontre" satisfacen KW check |
| KW score - ambiguous | **0.275** | Muy bajo; respuestas vagas a preguntas vagas |
| KW score - complex | 0.439 | Las respuestas complejas usan vocabulario diferente al esperado |
| Casos con todos KW presentes | ~47% (estimado de pass_generation) | |
| Casos con KW parcial (warning) | ~20 warnings en total | |

---

## 10. Conclusion y Roadmap Sugerido

### Estado Actual
El pipeline es **funcional pero no apto para produccion** en su estado actual. Genera respuestas coherentes y bien redactadas en la mayoria de los casos, pero no puede garantizar que la informacion provenga del corpus correcto ni que decline apropiadamente cuando no tiene la respuesta.

### Roadmap de Mejoras (orden de impacto/costo)

| Sprint | Accion | Impacto esperado en pass rate |
|---|---|---|
| 1 (1-2 dias) | Implementar gate de rechazo basado en rerank score | +8-10% (anti-alucinacion) |
| 1 (1 dia) | Expandir gazetteer de acronimos + query rewriting basico | +8-12% (retrieval simple) |
| 2 (2-3 dias) | Cachear BM25 en disco + configurar keep_alive en Ollama | Latencia -20%; sin impacto en calidad |
| 2 (3-5 dias) | Re-chunking con overlap 20% y metadatos de seccion | +5-10% (page hit rate) |
| 3 (1 semana) | Evaluar modelo LLM mas rapido (phi-3, gemma2, mistral-q4) | Latencia -40-60% |
| 3 (3 dias) | Implementar clasificador de ambiguedad y flujo de aclaracion | +5-8% (categoria ambiguous) |
| 4 (1 semana) | Implementar citation generation en prompts y verificacion | Nuevo: fidelidad de citas medible |

**Meta realista post-Sprint 1-2:** Tasa de aprobacion general de ~55-60%, anti-alucinacion >80%, latencia <35s promedio.

---

*Reporte generado automaticamente por `run_cybersec_eval.py` v2.0*  
*Dataset: `cybersec_eval_questions.json` (75 preguntas, 5 categorias)*  
*Modelo LLM: `mistral:7b` via Ollama*  
*Embeddings: `BAAI/bge-m3` (sentence-transformers, CUDA)*  
*Re-ranker: `BAAI/bge-reranker-v2-m3` (CUDA, max_length=128)*  
*Corpus: `cybersec_docs_bge_m3` - 100.480 chunks*  
*JSON completo: `report_20260709_022419.json`*
