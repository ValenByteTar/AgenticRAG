---
id: RES-009
category: research
status: proposed
created: 2026-08-03
updated: 2026-08-03
author: human
components: [rag_hybrid, memory_system, learning_queue, conceptual_map, warm-artifacts, artifact-registry, knowledge-builder]
tags: [deprecation, eradication, legacy, memory, learning-queue, conceptual-map, warm-artifacts, architectural-debt, cleanup]
related: [ADR-0018, ADR-0019, ADR-0020, RES-001, RES-002, RES-003, RES-008]
supersedes: null
superseded_by: null
---

# RES-009 - Erradicacion de modulos legacy de memoria y aprendizaje

## Topic

Proponer la remocion completa de tres modulos legacy (`memory_system.py`, `learning_queue.py`, `conceptual_map.py`) y su artefacto de estado (`memory.db`), que implementan funcionalidades de memoria, aprendizaje y atajos que han sido superseded por la arquitectura formal de Warm Artifacts, Knowledge Builder y Artifact Registry.

## Sources

- ADR-0018: Knowledge Builder / Consumer split (frontera inviolable, Registry como autoridad)
- ADR-0019: Contrato epistemico y VERIFY a nivel de claims (senales, no decisiones)
- ADR-0020: Ownership de decisiones y contrato de ejecucion observable
- RES-001: El contrato Warm como centro arquitectonico
- RES-002: Knowledge Builder (Knowledge Compiler) — pipeline extract → compile → validate → publish
- RES-003: Knowledge Consumer / evolucion del Agentic RAG runtime
- RES-008: Capability-Oriented Execution Model

---

## 1. Motivacion

### 1.1 El problema

El proyecto evoluciono de un monolito RAG (`rag_hybrid.py`) con modulos ad-hoc de memoria y aprendizaje hacia una arquitectura formal con Knowledge Builder, Warm Artifacts y Artifact Registry. Tres modulos legacy sobreviven como codigo muerto o semi-activo, generando deuda tecnica, confusion arquitectural y superficie de mantenimiento innecesaria.

### 1.2 Los tres modulos legacy

| Modulo | Archivo | Estado | Lineas |
|--------|---------|--------|--------|
| MemorySystem | `memory_system.py` | Semi-activo (importado por `rag_hybrid.py:89`) | 459 |
| LearningQueue | `learning_queue.py` | Semi-activo (importado por `rag_hybrid.py:95`) | 469 |
| ConceptualMap | `conceptual_map.py` | Semi-activo (importado por `rag_hybrid.py:91`) | 342 |
| memory.db | `memory.db` | Artefacto de state | 65 KB |

Total: ~1,270 lineas de codigo + 1 artefacto SQLite que duplican funcionalidades ya resueltas por la arquitectura formal.

---

## 2. Analisis por modulo

### 2.1 `memory_system.py` + `memory.db`

#### Que hace

SQLite con dos tablas:
- `user_knowledge`: pares pregunta/respuesta agregados manualmente por el usuario via `/agregar` en `chat.py`
- `term_synonyms`: sinonimos definidos manualmente o detectados automaticamente

#### Como se integra

- `rag_hybrid.py:499` — `self.memory = MemorySystem()` (inicializa SQLite)
- `rag_hybrid.py:9402` — `self.memory.search_memory(question, limit=3)` (busca en memoria antes de responder)
- `rag_hybrid.py:6345` — `self.memory.add_synonyms(...)` (guarda sinonimos desde comandos "X = Y = Z")
- `rag_hybrid.py:6895` — `self.memory.get_synonyms(entity)` (expande entidades con sinonimos)
- `chat.py:190-210` — `add_to_memory(rag)` (UI para agregar conocimiento)
- `chat.py:221-233` — `view_memory(rag)` (UI para ver memoria)

#### Por que es obsoleto

1. **Sin contrato epistemico**: El conocimiento se persiste sin evidence, sin SHA256, sin confidence score, sin validacion. Contradice ADR-0019 (claim-verify).
2. **Sin owner de validacion**: Cualquier cosa que el usuario escriba se guarda sin filtro. Contradice ADR-0020 (ownership de decisiones).
3. **Duplica Warm Artifacts**: `WarmArtifactResolver` (`src/adapters/warm_artifact_resolver.py`) ya indexa entidades, aliases y relaciones con evidencia, confidence y contrato formal. `memory.db` es una version primitiva sin ninguna de esas garantias.
4. **Duplica EquivalencesManager**: Los sinonimos manuales duplican la funcionalidad de `equivalences_manager.py` que ya carga equivalencias estructuradas desde `EQUIVALENCES_EMBEDDED_TEXT`.
5. **Busqueda primitiva**: Busca por keywords en SQLite (`LIKE %keyword%`). WarmArtifactResolver indexa por nombre canonico, entity ID, aliases y roles de documento.

#### Reemplazo arquitectural

| Funcionalidad legacy | Reemplazo formal |
|----------------------|------------------|
| `user_knowledge` (conocimiento manual) | Knowledge Builder pipeline: extract → compile → validate → publish al Artifact Registry |
| `term_synonyms` (sinonimos) | `equivalences_manager.py` (equivalencias estructuradas) + Warm Artifacts aliases |
| `search_memory()` (busqueda pre-query) | `WarmArtifactResolver.resolve_by_query()` |

### 2.2 `learning_queue.py`

#### Que hace

Cola de candidatos de aprendizaje auto-generados. Cuando el RAG responde con cierta confianza, genera un `LearningCandidate` (entity, attribute, answer, source, page, confidence) que se encola para validacion en background.

#### Como se integra

- `rag_hybrid.py:95` — `from learning_queue import LearningQueue`
- `rag_hybrid.py:10464` — `_post_query_learning()` procesa la cola despues de responder
- Persiste en `data/learning_queue.json`

#### Por que es obsoleto

1. **Duplica el Knowledge Builder pipeline**: El pipeline formal (extract → compile → validate → publish) hace exactamente lo mismo: extraer conocimiento de documentos, validarlo, y persistirlo. Pero con KIR estructurado, passes de compilacion, validacion semantica y warm artifacts versionados.
2. **Sin contrato**: Los candidatos se guardan como JSON ad-hoc sin contrato, sin versionado, sin SHA256 de evidencia.
3. **Validacion en background sin owner**: La validacion se hace con un LLM call en background sin trazabilidad. Contradice ADR-0020 (ownership de decisiones).
4. **Aprendizaje en runtime**: Persistir conocimiento durante queries en runtime contradice la separacion Builder/Consumer (ADR-0018). El Consumer no debe mutar conocimiento; solo lo lee del Registry.

#### Reemplazo arquitectural

| Funcionalidad legacy | Reemplazo formal |
|----------------------|------------------|
| `LearningCandidate` (candidato de aprendizaje) | KIR claims generados por `LLMEntityExtractor` en el pipeline del Builder |
| `LearningQueue.validate()` (validacion background) | `semantic_validator.py` en el pipeline de validacion del Builder |
| `data/learning_queue.json` (persistencia) | Artifact Registry con warm artifacts versionados |

### 2.3 `conceptual_map.py`

#### Que hace

JSON en `data/conceptual_map.json` con:
- `entity_facts`: hechos verificados por entidad (ej: "VMRS tiene 12 inversores")
- `query_shortcuts`: atajos de queries frecuentes para saltar el retrieval
- `entity_aliases`: aliases de entidades

#### Como se integra

- `rag_hybrid.py:91` — `from conceptual_map import ConceptualMap`
- Activado via `config.yaml:use_conceptual_map: true`
- Salta el retrieval completo si la query coincide con un atajo conocido

#### Por que es obsoleto

1. **Duplica WarmArtifactResolver**: `WarmArtifactResolver` ya indexa entidades por nombre canonico, entity ID, aliases y roles de documento. Hace lo mismo pero con artifacts validados, no con un JSON ad-hoc.
2. **Shortcut sin validacion**: Saltarse el retrieval con atajos hardcoded contradice el modelo de retrieval hibrido + claim-verify (ADR-0019). Es un bypass del pipeline epistemico.
3. **Sin contrato**: Los hechos se guardan sin evidence, sin confidence, sin SHA256. Contradice el contrato warm-v1.
4. **Hechos stale**: Los hechos en `conceptual_map.json` pueden quedar desactualizados sin mecanismo de invalidacion. El Artifact Registry tiene versionado semver.
5. **Config flag activo**: `use_conceptual_map: true` en `config.yaml` significa que esta funcionalidad esta activa y puede estar sirviendo respuestas sin validacion.

#### Reemplazo arquitectural

| Funcionalidad legacy | Reemplazo formal |
|----------------------|------------------|
| `entity_facts` (hechos por entidad) | Warm Artifacts: `entity_canonical` con confidence y evidence |
| `query_shortcuts` (atajos de query) | WarmArtifactResolver + retrieval hibrido (no saltar retrieval) |
| `entity_aliases` (aliases) | Warm Artifacts: `entity_aliases` con contrato formal |

---

## 3. Impacto en `rag_hybrid.py`

### 3.1 Lineas a remover

| Linea | Codigo | Accion |
|-------|--------|--------|
| 89 | `from memory_system import MemorySystem, ConversationHistory, parse_memory_command` | Remover import |
| 91 | `from conceptual_map import ConceptualMap` | Remover import |
| 95 | `from learning_queue import LearningQueue` | Remover import |
| 497-499 | `self.memory = MemorySystem()` | Remover inicializacion |
| ~500 | `self.conceptual_map = ConceptualMap()` | Remover inicializacion |
| ~510 | `self.learning_queue = LearningQueue(...)` | Remover inicializacion |
| 6329-6385 | Comandos de memoria (`parse_memory_command`, `add_synonyms`) | Remover bloque |
| 6853-6895 | Expansion de entidades con sinonimos de memoria | Remover o reemplazar con WarmArtifactResolver |
| 9400-9420 | `search_memory()` pre-query | Remover o reemplazar con WarmArtifactResolver |
| 10170-10188 | `_post_query_learning()` | Remover metodo |
| 10464+ | `_post_query_learning()` call | Remover call |

### 3.2 Impacto en `chat.py`

| Linea | Codigo | Accion |
|-------|--------|--------|
| 57-58 | `/agregar`, `/memoria` en help | Remover |
| 102-103 | `/agregar`, `/memoria` en help detallado | Remover |
| 190-220 | `add_to_memory(rag)` | Remover funcion |
| 221-233 | `view_memory(rag)` | Remover funcion |
| 258-260 | Indicador de `memory_hits` | Remover |
| 343-344 | `/agregar`, `/memoria` en banner | Remover |
| 395-399 | Handlers de `/agregar` y `/memoria` | Remover |

### 3.3 Impacto en `config.yaml`

| Key | Accion |
|-----|--------|
| `use_conceptual_map: true` | Remover o setear `false` |

---

## 4. Plan de erradicacion

### Fase 1 — Marcar como deprecated (no romper nada)

1. Setear `use_conceptual_map: false` en `config.yaml`
2. Agregar `DeprecationWarning` en los imports de `rag_hybrid.py` para los 3 modulos
3. Agregar comentarios `# DEPRECATED — RES-009` en las lineas de integracion
4. Documentar en `chat.py` que `/agregar` y `/memoria` seran removidos

### Fase 2 — Remover integracion de `rag_hybrid.py`

1. Remover los 3 imports (lineas 89, 91, 95)
2. Remover inicializaciones (~497-510)
3. Remover `search_memory()` pre-query (9400-9420)
4. Remover `_post_query_learning()` (10170+)
5. Remover comandos de memoria (6329-6385)
6. Remover expansion con sinonimos de memoria (6853-6895) — reemplazar con `WarmArtifactResolver` si aplica
7. Remover handlers de `/agregar` y `/memoria` en `chat.py`

### Fase 3 — Eliminar archivos

1. Eliminar `memory_system.py`
2. Eliminar `learning_queue.py`
3. Eliminar `conceptual_map.py`
4. Eliminar `memory.db`
5. Eliminar `data/conceptual_map.json` (si existe)
6. Eliminar `data/learning_queue.json` (si existe)

### Fase 4 — Verificacion

1. Ejecutar suite de tests completa
2. Verificar que `rag_hybrid.py` funciona sin los 3 modulos
3. Verificar que `chat.py` funciona sin `/agregar` y `/memoria`
4. Verificar que `web_app.py` funciona sin memory_hits
5. Confirmar que `WarmArtifactResolver` cubre todos los casos de uso

---

## 5. Riesgos y mitigaciones

### 5.1 Perdida de conocimiento guardado en `memory.db`

**Riesgo**: Si el usuario agrego conocimiento manualmente que no esta en los documentos, se pierde.

**Mitigacion**: Antes de eliminar `memory.db`, exportar su contenido a un documento de texto e ingestarlo via el pipeline del Knowledge Builder. Asi el conocimiento pasa por el pipeline formal con validacion.

### 5.2 Perdida de atajos en `conceptual_map.json`

**Riesgo**: Si hay atajos que mejoran latencia para queries frecuentes.

**Mitigacion**: El retrieval hibrido con WarmArtifactResolver deberia ser igual de rapido para queries que matchean entidades conocidas. Si la latencia es un problema, medir con benchmark antes/despes.

### 5.3 Regresion en calidad de respuestas

**Riesgo**: Remover `search_memory()` podria afectar respuestas que dependian de conocimiento manual.

**Mitigacion**: Ejecutar BM-005 (Consumer con Warm Artifacts) como regression test. Si los warm artifacts cubren los mismos casos, no hay regresion.

### 5.4 `ConversationHistory` se importa desde `memory_system.py`

**Riesgo**: `rag_hybrid.py:89` importa `ConversationHistory` y `parse_memory_command` desde `memory_system.py`. Si se elimina el archivo, se rompe el import.

**Mitigacion**: Antes de eliminar `memory_system.py`, extraer `ConversationHistory` y `parse_memory_command` a un modulo separado o inlinearlos en `rag_hybrid.py` si son simples. Verificar si `ConversationHistory` esta en uso activo.

---

## 6. Conclusion

Los tres modulos legacy (`memory_system.py`, `learning_queue.py`, `conceptual_map.py`) y su artefacto `memory.db` son vestigios de una era pre-arquitectura que duplican funcionalidades ya resueltas formalmente por:

- **Warm Artifacts** + **Artifact Registry** (para conocimiento estructurado con contrato)
- **Knowledge Builder pipeline** (para extraccion, validacion y publicacion de conocimiento)
- **WarmArtifactResolver** (para resolucion de entidades, aliases y roles en runtime)
- **EquivalencesManager** (para sinonimos y equivalencias estructuradas)

Su remocion reduce ~1,270 lineas de codigo, elimina deuda tecnica, alinea el runtime con la arquitectura formal (ADR-0018, ADR-0019, ADR-0020) y simplifica el monolito `rag_hybrid.py`.

Se recomienda ejecutar el plan en 4 fases con verificacion en cada paso.
