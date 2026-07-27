---
id: RES-003
category: research
status: draft
created: 2026-07-27
updated: 2026-07-27
author: human
components: [kernel, capabilities, rag_hybrid, planner, retrieval, generation, verify, assess, llm_support, model_provider]
tags: [architecture, query-time, knowledge-consumer, runtime-evolution, llm-support, observer, hypotheses, reactive, incremental, migration, warm-artifacts-consumption, small-model, cpu-parallel]
related: [RES-001, RES-002, ADR-0005, ADR-0006, ADR-0009, ADR-0012, ADR-0013, ADR-0015, ADR-0016, ADR-0019, ADR-0020, DEC-008, BM-002, BM-003, BM-004]
supersedes: null
superseded_by: null
---

# RES-003 - Knowledge Consumer / evolucion del Agentic RAG runtime

> Extracto de RES-001 (original). RES-001 fue seccionado en tres:
> - **RES-001** — El contrato Warm como centro arquitectonico
> - **RES-002** — Knowledge Builder / Knowledge Compiler
> - **RES-003** — Knowledge Consumer / evolucion del Agentic RAG runtime (este documento)

## Topic

Evolucion del Consumer (Agentic RAG kernel) en query-time: como consume Warm Artifacts publicados por el Builder (RES-002) via el contrato (RES-001), como evolucionan sus capabilities, y como un observador paralelo (LLMSupport) produce hipotesis sin bloquear ni decidir.

## Sources

- RES-001: El contrato Warm como centro arquitectonico (Warm Artifacts, Artifact Registry, fronteras)
- RES-002: Knowledge Builder / Knowledge Compiler (compilacion de conocimiento en index-time)
- BM-002: A/B Kernel+VERIFY vs Monolito — brecha de 36.3pp causada enteramente por retrieval
- BM-003: A/B Kernel Fase 6 vs Monolito — sin regresion pero brecha persistente
- BM-004: A/B Kernel Fase 6 + bug fixes — brecha reducida a 27.3pp
- DEC-008: Planner + EntityExpansion tunings — wiring completado, impacto medido en BM-004
- ADR-0005: Observability como substrato transversal
- ADR-0006: Evaluation transversal (offline + online)
- ADR-0009: Memory Port (read-only en kernel)
- ADR-0012: Capability Registry
- ADR-0013: Policy Engine (policies de primera clase)
- ADR-0015: Knowledge System (retrieval + get_entity)
- ADR-0016: Definicion del Kernel
- ADR-0019: Contrato epistemico y VERIFY a nivel de claims
- ADR-0020: Ownership de decisiones y contrato de ejecucion observable
- Monolito: `rag_hybrid.py`, `doc_cards.py`, `equivalences_manager.py`, `conceptual_map.py`, `src/rag/entity_extractor.py`, `retrieval_engine.py`

---

## 1. Motivacion

### 1.1 Sintomas observados en A/B

**BM-002** (Fase 4): 45.5% pass rate vs 81.8% monolito. Brecha de 36.3pp.

**BM-003** (Fase 6): 45.5% pass rate (sin regresion). Planner y entity expansion no mejoraron pass rate porque el conocimiento no llegaba a la query de busqueda como artefacto consumible.

**BM-004** (Fase 6 + bug fixes): 54.5% pass rate. Brecha reducida a 27.3pp. Se cerraron dos gaps de data flow en el Consumer:

1. ~~`EntityExpansionCapability` producia entidades expandidas que no llegaban a la query~~ — **FIXED en BM-004**: `RetrievalCapability` y `TwoStageRetrievalCapability` inyectan `expanded_entities`.
2. `PlannerCapability` produce `candidate_docs`, pero el soft boost (+0.05) sigue siendo debil frente a scores de reranker.
3. ~~Two-stage estaba registrado pero no se activaba automaticamente~~ — **FIXED en BM-004**: `LinearRagPolicy` activa `two_stage_retrieval` en el primer pass cuando hay entidades.
4. Las queries restantes (21, 24, 45, 51, 55) siguen fallando porque el Consumer no dispone de conocimiento de dominio compilado (gazetteer completo, equivalencias, relaciones tipadas, roles ricos).

**Mejora observada en BM-004**: +1 pregunta PASS (Q41), +11.1pp doc hit@K, +0.111 MRR.

**Lectura arquitectonica**: los bug fixes mejoraron el consumo de conocimiento ya disponible. No resolvieron la ausencia de un Knowledge Model compilado de alta calidad. Eso es trabajo de compilacion (RES-002), no de parches en runtime.

### 1.2 El Consumer hoy

El Consumer es el Agentic RAG kernel en query-time.

Responsabilidades:

- planificar la consulta
- resolver Warm Artifacts via Resolution Protocol (ver RES-001)
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

Cualquier conocimiento de dominio se compila antes del runtime (RES-002).
El Consumer solamente conoce contratos (RES-001).

---

## 2. Como consume el kernel los Warm Artifacts

| Capability actual | Hoy | Con contrato Warm |
|---|---|---|
| `PlannerCapability` | Detecta tipo de query; roles limitados | Lee `doc_roles` + taxonomy + confidence |
| `EntityExpansionCapability` | `_DEFAULT_ALIASES` + memory | Lee `alias_index` + canonical entities |
| `RetrievalCapability` | Inyecta expanded entities (BM-004) | Ademas usa `entity_index` / retrieval metadata |
| `TwoStageRetrievalCapability` | Activado en primer pass (BM-004), fallback a retrieve | Usa `entity_index` compilado para busqueda dirigida |
| `MemoryReadCapability` | Memoria runtime | Igual — memoria no es conocimiento de corpus |
| `VerifyCapability` | Groundedness de respuesta | Igual — opera sobre evidencia de la query (Hot) |

El Consumer puede seguir produciendo Hot Artifacts (`expanded_entities`, `candidate_docs`, etc.). Eso no viola la frontera: son estado de query, no conocimiento estable.

El Consumer no necesita conocer al Builder.
Solo necesita conocer el contrato.
El Consumer no habla con el Builder. Habla con el Registry (RES-001).

### 2.1 Confidence policies del Consumer

Ejemplos (no prescriptivos de implementacion actual):

- expandir solo aliases con `confidence >= 0.85`
- usar relations en comparison solo si `confidence >= 0.9`
- degradar soft-boost si doc role tiene baja confidence
- preferir entity_index entries high-confidence en two-stage
- loggear/telemetry de claims borderline

Confidence es una senal de decision del Consumer, no solo provenance. Ver RES-001 seccion de Confidence contractual.

---

## 3. LLMSupport: observador paralelo de hipotesis

### 3.1 Idea central

Un componente LLM que corre **paralelo al pipeline**, tomando la temperatura del sistema. Mientras el pipeline ejecuta su cadena secuencial:

```
Query
   |
Retrieval
   |
Reranker
   |
VERIFY
   |
LLM (generation)
```

El LLMSupport observa simultaneamente:

```
                LLMSupport
                    |
                    v
Query -------------->|
                    |
Retrieval events --->|
                    |
Reranker events ---->|
                    |
VERIFY events ------>|
                    |
LLM generation ----->|
```

### 3.2 Principios invariantes

El LLMSupport:

- **Nunca bloquea** — corre en paralelo (async/thread). El pipeline nunca espera al LLMSupport.
- **Nunca decide** — no invoca capabilities, no modifica `ExecutionState`, no sobrescribe decisiones.
- **Nunca reemplaza** — no sustituye ASSESS, VERIFY, ni al Policy Engine.
- **Simplemente observa** el estado del sistema y produce hipotesis.

Estos principios alinean directamente con:

| Principio | Como aplica |
|---|---|
| **P17** (ADR-0020) | La observabilidad no cambia el comportamiento — LLMSupport empieza 100% pasivo |
| **P16** (ADR-0020) | Ownership de decisiones — LLMSupport produce opiniones, el Policy Engine decide |
| **P14** | Una responsabilidad por eslabon — LLMSupport observa, no ejecuta |
| **P9** | Determinismo en el control, razonamiento en el lenguaje — LLMSupport razona, no controla |
| **P3** | Observabilidad antes que magia — toda hipotesis es trazable |
| **P4** | Medible antes que inteligente — pasivo primero, medir, luego habilitar influencia |

### 3.3 Que produce

No produce decisiones. Produce **hipotesis**.

Ejemplo:

```
Pipeline:
  BM25: Documento A
  Embedding: Documento B
  Reranker: Confianza 0.42

Mientras tanto LLMSupport razona:

  "La evidencia es muy pobre."
  "No encontre consenso entre BM25 y embeddings."
  "La consulta parece referirse a un documento especifico."
  "La respuesta probablemente necesite otro retrieval."
```

Esas son hipotesis. No ordenes.

### 3.4 Contrato de hipotesis

El LLMSupport produce un nuevo tipo de output: `Hypothesis`.

```json
{
  "suggestion": "RETRY_RETRIEVAL",
  "confidence": 0.71,
  "reasoning": "BM25 y embeddings no coinciden; reranker confidence 0.42 indica evidencia debil",
  "stage": "post_reranker",
  "run_id": "abc123"
}
```

- No es `EvaluationSignal` (no gatea, no produce pass/fail).
- No es `ActionDecision` (no ejecuta, no tiene `capability_ref`).
- Es una **opinion estructurada** con confidence y razonamiento.

### 3.5 Modelo reactivo incremental

El LLMSupport funciona incrementalmente, reactivo a eventos:

```
Evento 1: Query recibida
  -> piensa: analiza la pregunta
  -> hipotesis inicial

Evento 2: Llegaron candidatos (retrieval)
  -> actualiza hipotesis

Evento 3: Llego reranker
  -> actualiza hipotesis

Evento 4: LLM empezo a generar
  -> actualiza hipotesis
```

Es un sistema reactivo basado en eventos. Cada evento del pipeline dispara una actualizacion de la hipotesis. No necesita ver todo el estado para producir una opinion util.

### 3.6 No agrega latencia

Como corre en paralelo, mientras el reranker esta trabajando, el LLMSupport ya puede haber terminado.

```
t=0 ms    Query llega
          -> LLMSupport empieza a analizar la pregunta
          -> Retrieval
          -> Reranker
          -> LLMSupport ya termino
          -> VERIFY
          -> LLM
```

Cuando el pipeline llega a VERIFY, el LLMSupport ya dejo preparada una sugerencia.

No agrega practicamente latencia al camino critico.

### 3.7 Posicion en los planos arquitectonicos

LLMSupport es **transversal como Observability** (ADR-0005), pero con razonamiento LLM.

```
CONTROL          | CAPABILITIES       | KNOWLEDGE
Controller,      | Retrieval, Gen,    | Knowledge System
Policy Engine,   | Assess, Verify,    | (Warm Artifacts)
Registry         | Planner, Tools
                 |
-----------------+--------------------+------------------------
transversal: OBSERVABILITY
transversal: EVALUATION
transversal: CONFIGURATION
transversal: LLMSUPPORT (observador paralelo)
```

- No es capability (no se invoca via Registry).
- No es policy (no decide).
- No es evaluation (no produce senales duras).
- Es un **observador** que consume eventos del `TraceSink` y produce hipotesis.

### 3.8 Integracion con arquitectura existente

| Componente | Relacion con LLMSupport |
|---|---|
| `TraceSink` (ADR-0005) | Fuente de eventos. LLMSupport se suscribe a `TraceEvent` del pipeline. |
| `ExecutionState` (ADR-0004) | LLMSupport lee estado (read-only). Nunca escribe. |
| `PolicyEngine` (ADR-0013) | Consumidor opcional de hipotesis. Policy decide si las usa. |
| `CompositionRoot` (ADR-0014) | Cablea el LLMSupport (P13 — inyeccion de dependencias). |
| `ModelProvider` (ADR-0007) | LLMSupport usa un **ModelProvider dedicado** con un modelo pequeno (ver 3.8.1). |

### 3.8.1 Modelo dedicado pequeno en CPU

El LLMSupport **no usa el mismo modelo** que la capability de generation del pipeline. Usa un **modelo dedicado mas pequeno** (ej. 3B) que corre **paralelamente en CPU**.

```
Pipeline (GPU si disponible):
  LLM principal (ej. 8B)
  -> generation, verify, etc.

LLMSupport (CPU):
  Modelo pequeno (ej. 3B)
  -> observacion paralela, hipotesis
```

Razones arquitectonicas:

- **No compite por recursos GPU** — el modelo principal del pipeline tiene la GPU dedicada. El LLMSupport corre en CPU sin interferir.
- **Modelo mas liviano es suficiente** — el LLMSupport no genera respuestas; solo razona sobre el estado del pipeline y produce hipotesis. Un modelo 3B es adecuado para esta tarea.
- **Latencia marginal** — un modelo 3B en CPU puede producir una hipotesis en tiempos compatibles con la duracion de las etapas del pipeline (retrieval, reranker, verify).
- **ModelProvider inyectado** (P13) — el LLMSupport recibe su propio `ModelProvider` configurado para el modelo pequeno. El contrato (ADR-0007) se preserva; solo cambia la implementacion cableada en Composition Root.

Configuracion en Composition Root:

```python
# Ejemplo conceptual (no es codigo de implementacion)
llm_support_provider = OllamaProvider(model="qwen2.5:3b", device="cpu")
llm_support = LLMSupport(
    model_provider=llm_support_provider,
    trace_sink=bundle.trace_sink,
    mode="passive",
)
```

- `llm_support.model` = modelo pequeno dedicado (ej. 3B)
- `llm_support.device` = CPU (no compite con GPU del pipeline)
- `llm_support.mode` = `"passive"` | `"advisory"` | `"off"`
- El modelo es reemplazable (P2 — contratos estables, implementaciones desechables)

### 3.9 Fase 1: Observabilidad pura (pasivo)

```
Pipeline normal
  +
LLMSupport
  |
  v
Log: "Yo hubiera hecho retry."
```

Nada cambia. El pipeline ejecuta exactamente igual.

Se mide:
- Precision de hipotesis: cuando LLMSupport sugiere retry, era necesario?
- Recall de hipotesis: cuando el pipeline fallo, LLMSupport lo detecto?
- Comparacion con decisiones reales del Policy Engine

Despues se descubre:

> "El LLMSupport detecto correctamente el 82% de los retrieval malos."

Recien ahi se habilita influencia.

Esto sigue perfectamente el principio **P17**: la observabilidad no cambia el comportamiento.

### 3.10 Fase 2: Influencia opt-in via Policy Engine

Cuando los benchmarks validan la utilidad del LLMSupport:

```
LLMSupport
  |
  produce: Hypothesis { suggestion: RETRY_RETRIEVAL, confidence: 0.71 }
  |
  v
Policy Engine
  |
  v  Decide:
     - Ignorar?
     - Aceptar?
     - Pedir retry?
     - Cambiar estrategia?
```

El LLM nunca toma la decision. Produce una opinion. El Policy Engine conserva ownership (P16).

Habilitacion gradual por config (Composition Root):
- `llm_support.mode = "passive"` (Fase 1 — solo log)
- `llm_support.mode = "advisory"` (Fase 2 — hipotesis disponibles para Policy Engine)
- `llm_support.mode = "off"` (default seguro)

### 3.11 Ownership y fronteras

| Puede LLMSupport | Puede LLMSupport |
|---|---|
| Leer `ExecutionState` (read-only) | Invocar capabilities |
| Suscribirse a `TraceEvent` | Modificar `ExecutionState` |
| Producir `Hypothesis` | Sobrescribir decisiones del Policy Engine |
| Loggear hipotesis | Bloquear el pipeline |
| Correr en paralelo sin bloquear | Reemplazar ASSESS o VERIFY |
| Terminar antes que el pipeline | Escribir en `signals` o `last_decision` |

### 3.12 Comparativa: ASSESS/VERIFY vs LLMSupport

| Aspecto | ASSESS / VERIFY | LLMSupport |
|---|---|---|
| Momento | Discreto, post-hoc | Continuo, proactivo |
| Tipo de output | `EvaluationSignal` (pass/fail) | `Hypothesis` (sugerencia + confidence) |
| Gatea? | Si (hard gate o soft signal) | No |
| Bloquea? | Si (el pipeline espera el resultado) | No (corre en paralelo) |
| Decide? | No (produce senales) | No (produce opiniones) |
| Usa LLM? | No (determinista, local-first) | Si (razonamiento LLM) |
| Consume eventos? | No (evalua estado en un punto) | Si (reactivo, incremental) |
| Owner de la decision | Policy Engine interpreta la senal | Policy Engine interpreta la hipotesis |

ASSESS y VERIFY son evaluadores discretos que gatean en momentos especificos. LLMSupport es un observador continuo que razona sobre el estado global del run. Son complementarios, no redundantes.

---

## 4. Comparativa

| Aspecto | Monolito | Kernel actual (F6 + BM-004) | Consumer con contrato Warm + LLMSupport |
|---|---|---|---|
| **Centro del sistema** | Codigo monolitico | Kernel + wiring | Contrato Warm (RES-001) |
| **Momento del conocimiento** | Mezcla index/query | Consume poco conocimiento compilado | Compila en index-time (RES-002), consume en query-time |
| **Entity expansion** | Dict + memory + runtime | Alias limitados, ya inyectados en query | `alias_index` compilado + confidence |
| **Doc roles** | Heuristica + LLM opcional | Soft boost debil | `doc_roles` compilados |
| **Equivalences** | 92 grupos manuales | No integradas como artifact | `alias_index` + relations |
| **Two-stage** | Automatico | Activado en primer pass | Guiado por `entity_index` compilado |
| **Relations** | Hechos/ad-hoc | No tipadas | Triples + catalogo controlado |
| **Confidence** | Implicita / ausente | Ausente como contrato | Primordial en claims Warm + Policy |
| **Observacion continua** | No | No | LLMSupport paralelo |
| **Hipotesis proactivas** | No | No | LLMSupport produce hipotesis sin bloquear |
| **Evolucion a GraphRAG** | Dificil | Dificil | Natural via Relation Layer |
| **Acoplamiento** | Alto | Medio | Bajo (contrato Warm + Registry) |

---

## 5. Migracion incremental

No es big-bang.

### Fase 7a — Compiler minimo + KIR + Warm Artifacts

- Implementar `knowledge_builder/` con front-end -> KIR -> passes -> validation -> back-end (ver RES-002)
- Knowledge Pass API: NormalizePass, CanonicalizePass
- Layers iniciales: Document + Entity
- Publicar: canonical entities, alias index, doc roles, manifest, confidence minima
- Artifact Registry: publication + resolution protocol, staging -> promote (ver RES-001)
- Consumer resuelve Warm Artifacts en `bootstrap.py` via Resolution Protocol
- `EntityExpansionCapability` lee `alias_index`
- `PlannerCapability` lee `doc_roles`
- Compatibilidad con monolito se mantiene

### Fase 7b — Retrieval Layer

- Ya hecho en BM-004 a nivel Consumer:
  - inyeccion de `expanded_entities` en query
  - activacion de two-stage cuando hay entidades
- Pendiente de compiler (RES-002):
  - `entity_index` rico
  - retrieval metadata
  - two-stage guiado por artifact y no solo fallback

### Fase 7c — Relation Layer + catalogo + evidence validation

- Publicar `entity_relations` como triples del catalogo controlado
- Exigir evidence validation + confidence
- Confidence Policy configurable
- Habilitar comparison/balancing en Consumer leyendo relations (sin redescubrir dominio)
- Planner puede filtrar por thresholds de confidence

### Fase 7d — A/B contrato Warm vs monolito

- Eval con `--kernel` + manifest activo
- Medir pass rate, doc hit, recall, MRR
- Objetivo: paridad o mejora vs monolito (81.8% en muestra actual)
- Registry rollback disponible si regresion

### Fase 7e — LLMSupport pasivo

- Implementar LLMSupport como observador paralelo
- `llm_support.mode = "passive"` (solo log)
- Medir precision/recall de hipotesis vs decisiones reales
- Benchmark: detecta correctamente retrieval malos, verify innecesarios, etc.
- Sin impacto en pipeline

### Fase 7f — LLMSupport advisory

- Si Fase 7e valida utilidad (ej. >80% precision en deteccion de retrieval malos)
- `llm_support.mode = "advisory"` — hipotesis disponibles para Policy Engine
- Policy Engine decide si las consume (nueva policy o policy existente ampliada)
- Habilitacion gradual, medible, reversible

### Fase 8 — Deprecar conocimiento embebido en runtime

- Si A/B es positivo, retirar conocimiento de dominio hardcodeado del Consumer/monolito
- El monolito queda como facade
- `kernel.enabled=true` por defecto
- El contrato Warm queda como unica fuente de conocimiento estable de dominio

---

## 6. Riesgos

| Riesgo | Probabilidad | Impacto | Mitigacion |
|---|---|---|---|
| Calidad inferior al monolito al inicio | Media | Alto | A/B obligatorio antes de deprecar + rollback en Registry |
| Consumer accede directo a archivos | Media | Alto | Resolution Protocol obligatorio; Registry como unico punto de acceso (RES-001) |
| LLMSupport introduce latencia no esperada | Baja | Medio | Corre en paralelo; si no termino, la hipotesis simplemente no esta |
| LLMSupport produce hipotesis ruidosas | Media | Medio | Fase 1 pasiva para medir precision/recall antes de habilitar influencia |
| LLMSupport acopla al Consumer a un modelo | Media | Alto | ModelProvider inyectado (P13); modelo configurable |
| Policy Engine se vuelve dependiente de LLMSupport | Media | Alto | Policy Engine funciona sin LLMSupport; hipotesis son input opcional |
| Consumer vuelve a recompilar dominio | Media | Alto | Frontera explicita + reviews de arquitectura |
| Confundir Hot Artifacts con Warm | Baja | Medio | Hot es estado de query; Warm es contrato (RES-001) |

---

## 7. Open questions

1. **Bootstrap del Consumer**: carga total vs lazy por layer/artifact
2. **Thresholds de confidence por capability**: globales vs especificos
3. **Modelo del LLMSupport**: modelo pequeno dedicado (ej. 3B) corriendo en CPU, inyectado via ModelProvider (P13). No compite por GPU con el pipeline.
4. **Presupuesto del LLMSupport**: como acotar llamadas LLM del observador (max_hypothesis_updates?)
5. **Serializacion de hipotesis**: van en `ExecutionState.metadata`? En trazas? En un campo dedicado?
6. **Relacion LLMSupport con Planner**: el Planner planea antes; LLMSupport observa durante. Como coordinan?
7. **LLMSupport y streaming**: si el LLM esta streamando tokens, puede LLMSupport observar el stream?
8. **Multiple hipotesis**: puede LLMSupport mantener multiples hipotesis simultaneas?
9. **Aprendizaje del LLMSupport**: puede la precision de hipotesis mejorar con el tiempo?
10. **Separacion de repos**: cuando justificar Opcion B? (ver RES-002)

---

## 8. Takeaways

1. **El Consumer solo consume contratos.** No reconstruye conocimiento de dominio en runtime.
2. **BM-004 mejoro el consumo; falta mejorar el conocimiento compilado.** Eso es trabajo del Builder (RES-002).
3. **LLMSupport es un observador paralelo, no un decisor.** Produce hipotesis; el Policy Engine decide.
4. **LLMSupport empieza 100% pasivo.** Observabilidad pura, medir, luego habilitar influencia (P17).
5. **LLMSupport no bloquea ni agrega latencia.** Corre en paralelo, reactivo a eventos.
6. **LLMSupport es complementario a ASSESS/VERIFY.** ASSESS/VERIFY evaluan discreto; LLMSupport observa continuo.
7. **El Policy Engine conserva ownership.** LLMSupport alimenta; Policy Engine decide (P16).
8. **La migracion es incremental.** Fases 7a-7f + Fase 8, con A/B obligatorio en cada paso.
9. **No se implementa ahora.** Este research prepara la promocion futura a ADR.

---

## 9. Criterio de promocion a ADR

Este research puede promoverse a ADR cuando se acuerde al menos:

- evolucion del Consumer para consumir Warm Artifacts via Resolution Protocol
- capabilities existentes migran a leer Warm Artifacts (Planner, EntityExpansion, Retrieval, TwoStage)
- LLMSupport como componente transversal (observador paralelo)
- contrato de `Hypothesis` (suggestion, confidence, reasoning)
- modelo reactivo incremental basado en eventos (TraceSink)
- principio de no-bloqueo (paralelo, sin latencia en camino critico)
- Fase 1 pasiva obligatoria antes de Fase 2 advisory
- ownership: Policy Engine decide, LLMSupport opina (P16)
- habilitacion gradual por config (passive -> advisory -> off)
- presupuesto del LLMSupport acotado

Hasta entonces permanece como research de arquitectura de largo plazo.
