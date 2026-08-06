# Plan de Orquestacion - Knowledge Builder / Consumer

Documento de baja estabilidad (cambia por etapa cerrada). Deriva de ADR-0018, RES-001, RES-002, RES-003.

Cubre la ejecucion de las Fases 7a-7f y Fase 8 del [roadmap](roadmap.md).

Leyenda de estado: `[ ]` pendiente, `[~]` en curso, `[x]` cerrada.

---

## 1. Objetivo

Trasladar el conocimiento estable de dominio desde query-time (Consumer) hacia index-time (Builder), mediado por el contrato Warm y el Artifact Registry, **sin regresion de calidad medida** en ningun punto del camino.

Meta cuantitativa: cerrar la brecha de 27.3pp entre el kernel (54.5% pass, BM-004) y el monolito (81.8%).

## 2. Invariantes del plan

Estas reglas no se negocian durante la ejecucion. Romper una exige ADR.

| # | Invariante | Origen |
|---|---|---|
| I1 | El contrato Warm es el centro. Builder y Consumer son reemplazables. | ADR-0018.1 |
| I2 | El Consumer nunca publica. El Builder nunca resuelve. | ADR-0018.11 |
| I3 | El Consumer nunca accede a archivos del Registry directamente. Solo Resolution Protocol. | RES-001 §5.3 |
| I4 | Cold Artifacts jamas cruzan la frontera. | ADR-0018.10 |
| I5 | Ningun claim se publica sin `validated=true`. | RES-002 §6 |
| I6 | Toda etapa cierra con A/B medido y registrado como BM. | P4 |
| I7 | Toda etapa es reversible: rollback del Registry o feature flag. | RES-001 §5.5 |
| I8 | El conocimiento y la arquitectura no cambian en la misma etapa. | §4 (E3/E5) |
| I9 | Validation ocurre antes de Codegen. Jamas existen Warm Artifacts invalidos. | ADR-0021.1 |
| I10 | El extractor no conoce el catalogo de predicados. El compilador normaliza. | ADR-0021.5 |
| I11 | Las fases del Builder son unidireccionales: extract → compile → validate → publish. Compile nunca invoca extractores. | ADR-0021.1 |

**I8 es el criterio de secuenciacion mas importante del plan.** E3 migra el conocimiento *existente* a la nueva arquitectura; E5 introduce conocimiento *nuevo*. Si se hicieran juntos, ningun A/B podria atribuir la variacion.

## 3. Estructura de ejecucion

Dos tracks independientes. **No comparten dependencias.**

```
TRACK A - Contrato / Builder / Consumer
E0 -> E1 -> E2 -> E3 -> E4 -> E5 -> E6 -> E7 -> E8

TRACK B - LLMSupport (paralelizable en cualquier momento tras E0)
B0 -> B1 -> B2 -> B3
```

Track B solo depende de `TraceSink` y `ModelProvider`, ambos ya existentes. Puede adelantarse, atrasarse o correr en paralelo sin afectar Track A.

---

## 4. Track A - Etapas

### E0 - Saneamiento del EKS (bloqueante) — CERRADA

**Por que primero:** ADR-0018 esta `Aceptado` citando BM-004 (inexistente como documento) y RES-002/RES-003 (en `draft`). No se puede medir contra una baseline sin registro ni ejecutar research no aceptado.

- [x] Registrar `BM-004-kernel-fase6-bugfixes.md` (fuente: `tests/eval/reports/report_20260724_194640.*`; deltas verificados)
- [x] RES-002 `draft` -> `accepted`
- [x] Seccionar RES-003: queda **RES-003** (Knowledge Consumer / consumo de Warm Artifacts) y nace **RES-004** (LLMSupport)
- [x] RES-003 y RES-004 `draft` -> `accepted`
- [x] Actualizar `related` cruzados en RES-001/002/003/004 y ADR-0018
- [x] Regenerar `knowledge/INDEX.md` y `knowledge/_eks_index.json`

**Gate de salida — cumplido:** ningun documento citado por un ADR aceptado esta ausente o en `draft`.
**Riesgo:** bajo. **Reversible:** trivial.

---

### E1 - Contrato Warm v1 — CERRADA

**Alcance:** definir el contrato. No implementa productores ni consumidores.

- [x] `contract/` con JSON Schemas versionados `warm-v1` (+ `common.schema.json`, `README.md`)
- [x] Schemas de las 7 proyecciones: `canonical_entities`, `alias_index`, `entity_index`, `doc_roles`, `entity_relations`, `retrieval_metadata`, `predicate_catalog`
- [x] Schema del `manifest` (build id, `contract_version`, `builder_version`, artifacts, checksums)
- [x] Bloque de confianza obligatorio en todo claim: `confidence`, `validated` (const true), `builder_version`, `generated_by`; `evidence` obligatorio solo en relations (DEC-011.5)
- [x] `predicate_catalog` v1.0.0 con los 13 predicados de RES-001 §7.5 (fixture + schema)
- [x] Validador de contrato compartido: `src/contract/validator.py` (`validate_artifact`, `validate_manifest`, `validate_build` con integridad referencial)

**Decision de fasing:** resuelta en **DEC-011** — declaracion completa en v1, poblado escalonado (Document+Entity en E3, Retrieval en E6, Relation en E7, taxonomy diferida). Artifact declarado y vacio es valido; artifact no declarado rompe el build.

**Gate de salida — cumplido:** los schemas validan los ejemplos literales de RES-001 §7.4 (fixtures en `tests/contract/fixtures/`); `tests/unit/test_contract_warm_v1.py` 34 passed; suite completa 192 passed sin regresion.
**Riesgo:** medio — errores aca se propagan a todo el plan. **Reversible:** si (nada lo consume aun).

---

### E2 - Artifact Registry (componente full) — CERRADA

**Alcance confirmado: producto, no experimento.** Se implementa el componente completo aunque hoy corra en una sola maquina. La infraestructura de publicacion se construye una vez y bien.

- [x] Componente con identidad propia (`src/artifact_registry/registry.py`) e interfaz de 7 operaciones: `publish`, `promote`, `resolve`, `rollback`, `verify_integrity`, `list_builds`, `get_manifest`
- [x] **Publication Protocol**: entrega -> staging -> validacion integrity + compatibility -> espera `promote`
- [x] **Resolution Protocol**: `resolve()` unico punto de acceso del Consumer; nunca expone paths
- [x] **Build lifecycle completo**: `staging -> promoted -> deprecated -> archived -> purged`; un solo build activo
- [x] **Integrity**: SHA-256 por artifact sobre bytes canonicos, validado en publish, promote y carga. Corrupcion lanza `IntegrityError`
- [x] **Compatibility**: `contract_version` validado antes de promote; rechazo explicito si el Consumer espera otra version
- [x] **Rollback**: swap atomico del puntero via `os.replace`, sin recompilar
- [x] **Migrations**: framework declarativo en `src/artifact_registry/migrations.py` (registro `(from, to)` + revalidacion con `validate_build`; vacio hasta warm-v2)
- [x] **Retencion**: `apply_retention()` (deprecated -> archived por conteo; archived -> purged por antiguedad; nunca toca activo ni candidato de rollback)
- [x] Storage backend detras de interfaz — **DEC-012**: filesystem versionado, builds inmutables, estado en JSON
- [x] CLI de operador: `scripts/registry_cli.py` (publish/promote/resolve/rollback/list/verify/retention)

**Gate de salida — cumplido:** 21 tests en `tests/unit/test_artifact_registry.py` (publicacion, promocion, rollback, rechazo por incompatibilidad, deteccion de corrupcion, ciclo de vida y retencion) + smoke test del CLI; suite completa 213 passed. Pendiente para E4: el test de frontera "ningun componente accede al filesystem del Registry sin pasar por la interfaz" (solo tendra sentido cuando exista un consumidor).
**Riesgo:** medio. **Reversible:** si (nada lo consume aun).

---

### E3 - Builder minimo sobre conocimiento existente

**Alcance:** la arquitectura del compiler completa, alimentada **unicamente con el conocimiento que ya existe**. Sin LLM.

- [x] `knowledge_builder/` con la estructura de RES-002 §11 Opcion A (`frontend/`, `kir/`, `passes/`, `validate/`, `model/`, `backend/`, `publish/`)
- [x] Definicion del **KIR lossless**
- [x] **Tres extractores deterministas** convergiendo al mismo KIR: `doc_cards.py`, `equivalences_manager.py`, `entity_extractor.py`
- [x] Knowledge Pass API (`run(kir) -> kir`)
- [x] Passes: `NormalizePass`, `CanonicalizePass`, `DeduplicationPass`
- [x] Validation: Structural + Evidence
- [x] Confidence Policy configurable (default: `weighted`)
- [x] Knowledge Model con Layers **Document + Entity**
- [x] Back-end: Warm codegen + Cold codegen
- [x] `build_knowledge.py` (batch standalone, RES-002 §10.1)
- [x] Publicar y promover `ka_v1.0.0`
- [x] **Diff report** que demuestra equivalencia semantica (`OVERALL: EQUIVALENT`)
- [x] 46 tests cubriendo KIR, extractors, passes, validation, codegen, end-to-end

**Por que tres extractores y no uno:** valida empiricamente "Multiple Extractors -> Same KIR" (ADR-0018.3). Con un solo extractor esa decision arquitectonica queda sin verificar. Si el KIR absorbe tres fuentes deterministas heterogeneas, absorbe un LLM.

**Gate de salida:** `ka_v1.0.0` promovido; **diff report** que demuestra equivalencia semantica entre el conocimiento compilado y el hardcodeado actual; ningun Cold Artifact referenciado en el manifest.
**Riesgo:** medio. **Reversible:** si (el Consumer todavia no resuelve).

---

### E4 - Consumer resuelve Warm Artifacts

**Alcance:** el Consumer deja de reconstruir conocimiento. **Primer A/B real.**

- [x] Resolution Protocol cableado en `bootstrap.py`; resolver inyectado (P13)
- [x] `KnowledgeSystemAdapter.get_entity()` deja de ser stub y resuelve contra `canonical_entities` + `entity_index`
- [x] `EntityExpansionCapability` lee `alias_index` en vez de `_DEFAULT_ALIASES`
- [x] `PlannerCapability` lee `doc_roles` en vez de roles keyword-based
- [x] `RetrievalCapability` / `TwoStageRetrievalCapability` usan `entity_index`
- [x] Thresholds de confidence por capability, configurables (RES-003 §2.1)
- [x] Feature flag `knowledge.warm_artifacts.enabled` (default `true` post-BM-005 — gate superado con dos sets independientes)
- [x] Decidir bootstrap: carga total vs lazy por layer (RES-003 open question 1) — **carga total eager**

**Gate de salida — paridad, no mejora:** A/B vs BM-004 debe dar **>= 54.5% pass**. ✅ **SUPERADO: BM-005 = 63.6% (7/11)** vs baseline 54.5% (6/11). +9.1pp, sin regresiones. Registrar BM-005.
**Riesgo:** alto (primer cruce de frontera end-to-end). **Reversible:** feature flag + rollback del Registry. ✅ **Completado.**

---

### E5 - Granite como extractor LLM + infraestructura ADR-0021

**Alcance:** ahora si, conocimiento nuevo, contra una arquitectura ya validada por E4. Se subdivide en tres sub-etapas porque ADR-0021 cambia la interfaz del Builder (arquitectura) y E5.2 introduce conocimiento nuevo (contenido). I8 exige separacion.

#### E5.1 - Infraestructura ADR-0021 (CLI + cache + validation-before-codegen)

**Por que antes:** el cache es prerequisito para no perder horas de extraccion LLM en las fases posteriores. Sin cache, cada re-compilacion re-extrae todo el corpus.

- [ ] `build_knowledge.py` con subcomandos: `extract`, `compile`, `validate`, `publish`
- [ ] `build_knowledge.py` (sin subcomando) ejecuta los cuatro en secuencia (retrocompatibilidad)
- [ ] **KIR cache por chunk**: `cache/<doc_slug>/chunk_N.kir.json` + `meta.json` con hash por chunk
- [ ] `extract` produce cache; `compile` lee cache sin llamar al LLM; `validate` opera sobre KnowledgeModel (no sobre artifacts); `publish` hace codegen desde modelo validado + publica al Registry
- [ ] **Validation-before-codegen**: codegen ocurre dentro de `publish`, solo si validation paso. Jamas existen Warm Artifacts invalidos (I9)
- [ ] **Catalogo de predicados v2** (9 predicados): `equivalent_to`, `depends_on`, `implements`, `extends`, `references`, `governs`, `contains`, `uses`, `creates`
- [ ] `_PREDICATE_FALLBACK` ampliado en `canonicalize.py` para mapear lenguaje natural al catalogo v2
- [ ] **Prompt domain-agnostico**: el LLM produce predicados en lenguaje natural; el compilador normaliza (I10)
- [ ] Roles de documento universales v2 (reemplazan taxonomia cybersec)
- [ ] `predicate_catalog.catalog_version` = `"2.0.0"`, `doc_roles` incluye `role_taxonomy_version: "2.0.0"`
- [ ] Tests: cache hit/miss, invalidacion por hash, separacion de fases, retrocompatibilidad, mapeo de predicados

**Gate de salida:** los cuatro comandos funcionan independientemente. Re-ejecutar `compile` con mismo cache produce modelo identico. Cache hit evita llamadas LLM para docs sin cambios. `build_knowledge.py` sin subcomando produce el mismo resultado que antes.
**Riesgo:** medio (cambia la interfaz del Builder). **Reversible:** retrocompatibilidad de `build_knowledge.py`.

#### E5.2 - Build ka_v2.0.0 con LLM usando cache

**Alcance:** generar ka_v2.0.0 con conocimiento LLM, usando la infraestructura de E5.1.

- [ ] `build_knowledge.py extract --use-llm --max-docs N` — genera cache con KIR parcial por chunk
- [ ] `build_knowledge.py compile` — mergea cache, corre passes, produce KnowledgeModel
- [ ] `build_knowledge.py validate` — valida modelo (structural + semantic + contract)
- [ ] `build_knowledge.py publish --build-id ka_v2.0.0` — codegen + publish al Registry
- [ ] Semantic Validation activada
- [ ] Cuarentena de claims sin evidencia suficiente (Cold, nunca Warm)
- [ ] Confidence Policy combinando extractores deterministas + LLM
- [ ] Docs ya cacheados (test previo de 10 docs) se reusan si el hash coincide

**Gate de salida:** ka_v2.0.0 promovido en el Registry.
**Riesgo:** medio (la arquitectura ya esta probada; solo varia la calidad del conocimiento). **Reversible:** rollback del Registry a `ka_v1.0.0`.

#### E5.3 - BM-006: A/B ka_v2.0.0 vs ka_v1.0.0

**Alcance:** benchmark comparativo.

- [ ] Registrar BM-006: ka_v2.0.0 vs ka_v1.0.0 (baseline BM-005 = 63.6%)
- [ ] Objetivo: cierre sustancial de la brecha hacia el monolito (81.8%)
- [ ] Si hay regresion, rollback del Registry a `ka_v1.0.0`

**Gate de salida:** BM-006 registrado.
**Riesgo:** bajo. **Reversible:** rollback del Registry.

---

### E6 - Retrieval Layer

**Por que antes que Relation Layer:** la brecha medida es de retrieval. Esto la ataca directo. Re-ejecuta `compile` sobre cache existente (sin re-extraer docs); solo cambia passes y codegen.

- [ ] Layer 5 en el Knowledge Model
- [ ] Poblar `retrieval_metadata` y `entity_index` rico
- [ ] Two-stage **guiado por artifact**, no como fallback de retry
- [ ] Preferencias de scoping compiladas
- [ ] `build_knowledge.py compile` reusa cache de E5.2 (I11: compile nunca invoca extractores)
- [ ] Publicar `ka_v3.0.0` via `build_knowledge.py publish`

**Gate de salida:** A/B; mejora en doc hit@K y MRR. Registrar BM-007.
**Riesgo:** medio. **Reversible:** rollback del Registry.

---

### E7 - Relation Layer + Concept Layer

**Por que ultimo del knowledge:** hoy ninguna capability consume relaciones tipadas. Se implementa junto a su consumidor, no antes. Reusa cache de E5.2; solo añade relation/concept extraction si es necesario.

- [ ] Layers 3 y 4 en el Knowledge Model
- [ ] Poblar `entity_relations` como triples del catalogo v2 (9 predicados)
- [ ] Evidence Validation estricta sobre relaciones
- [ ] Capability consumidora: comparison balancing leyendo relations
- [ ] Poblar `taxonomy`
- [ ] Verificar export nativo a GraphRAG desde Relation Layer
- [ ] Cache existente se reusa para docs sin cambios (I11)
- [ ] Publicar `ka_v4.0.0` via `build_knowledge.py publish`

**Gate de salida:** A/B sobre queries comparativas. Registrar BM-008.
**Riesgo:** medio. **Reversible:** rollback del Registry.

---

### E8 - Deprecacion del conocimiento embebido

**Precondicion dura:** A/B acumulado >= monolito. Cache del LLM persiste; solo se deprecan extractores deterministas.

- [ ] Retirar `_DEFAULT_ALIASES` de `src/capabilities/entity_expansion.py`
- [ ] Retirar roles keyword-based de `src/capabilities/planner.py`
- [ ] Retirar `entity_aliases` y `EQUIVALENCES_EMBEDDED_TEXT` del monolito
- [ ] `doc_cards` deja de ejecutarse en runtime
- [ ] `kernel.enabled=true` por defecto
- [ ] Monolito reducido a fachada (ADR-0010)
- [ ] Deprecar `EquivalencesExtractor` y `EntityAliasesExtractor` del Builder (cache del LLM persiste)
- [ ] **Test de frontera**: falla si aparece conocimiento de dominio hardcodeado en `src/`
- [ ] Publicar `ka_v5.0.0` via `build_knowledge.py publish`

**Gate de salida:** suite completa en verde; el contrato Warm es la unica fuente de conocimiento estable de dominio. Registrar BM-009.
**Riesgo:** bajo si los gates previos se respetaron. **Reversible:** git.

---

## 5. Track B - LLMSupport (independiente)

### B0 - RES-004

- [ ] Extraer §3 de RES-003 a `RES-004-llmsupport-observador-paralelo.md`
- [ ] Ejecutado dentro de E0

### B1 - ADR de LLMSupport

- [ ] ADR nuevo: LLMSupport como **cuarto plano transversal** (junto a Observability, Evaluation, Configuration)
- [ ] Contrato `Hypothesis` (`suggestion`, `confidence`, `reasoning`, `stage`, `run_id`) — distinto de `EvaluationSignal` y de `ActionDecision`
- [ ] Fronteras: read-only sobre `ExecutionState`, no invoca capabilities, no escribe `signals` ni `last_decision`

**Por que ADR:** ningun ADR actual cubre LLMSupport. Introduce un plano transversal nuevo y un tipo de output nuevo.

### B2 - LLMSupport pasivo

- [ ] `FanoutTraceSink` que compone sinks — **`TraceSink` ya es push-based (`emit`), no requiere modificar ADR-0005**
- [ ] `ModelProvider` dedicado con modelo pequeno (~3B) en CPU, inyectado en Composition Root (P13)
- [ ] Modelo reactivo incremental sobre `TraceEvent`
- [ ] `llm_support.mode` = `off` (default) | `passive`
- [ ] Presupuesto acotado de llamadas (`max_hypothesis_updates`)

**No es gate:** la ausencia de latencia en el camino critico esta dada por diseno — ejecucion paralela en CPU con recursos dedicados, sin competir por GPU con el pipeline. No requiere validacion previa.

**Gate de salida:** precision y recall de hipotesis vs decisiones reales del Policy Engine (P4). Umbral de referencia de RES-003: >80% precision en deteccion de retrieval malos.

### B3 - LLMSupport advisory

- [ ] **ADR separado, obligatorio.** Aca LLMSupport deja de ser observabilidad y pasa a influir el control: P17 deja de aplicar y entra P16 (ownership del Policy Engine)
- [ ] `llm_support.mode = "advisory"`
- [ ] Policy Engine consume hipotesis como input **opcional**; funciona igual sin ellas

---

## 6. Trazabilidad ADR / etapa

| Etapa | ADR / RES que la gobierna | Documento de evidencia |
|---|---|---|
| E0 | ADR-0017 | BM-004, RES-004 |
| E1 | ADR-0018.1, .8, .9 / RES-001 §7 | DEC |
| E2 | ADR-0018.6 / RES-001 §5 | DEC (storage) |
| E3 | ADR-0018.2-.5 / RES-002 | EXP + diff report |
| E4 | ADR-0018.11 / RES-003 §2 | BM-005 |
| E5.1 | ADR-0021 | Tests CLI + cache |
| E5.2 | ADR-0018.12 / RES-002 §8.2 | ka_v2.0.0 publicado |
| E5.3 | — | BM-006 |
| E6 | RES-002 §7.1 L5 | BM-007 |
| E7 | ADR-0018.8 / RES-002 §7.1 L3-L4 | BM-008 |
| E8 | ADR-0010, ADR-0018 | BM-009 |
| B1 | ADR nuevo | — |
| B2 | ADR-0005, ADR-0007, P17 | EXP |
| B3 | ADR nuevo + ADR-0013, P16 | EXP |

## 7. Documentos a crear antes de codificar

| Documento | Momento | Motivo |
|---|---|---|
| BM-004 | E0 | Baseline citada por ADR-0018, ausente |
| RES-004 | E0 | Seccionamiento de LLMSupport |
| DEC — storage backend del Registry | E2 | RES-001 open question 1 |
| DEC — fasing de poblado de artifacts | E1 | Confirmar §4/E1 |
| ADR — LLMSupport transversal | B1 | Plano nuevo sin ADR |
| ADR — LLMSupport advisory | B3 | Cruce observabilidad -> control |

## 8. Criterio de aborto

Detener el track y abrir postmortem (`knowledge/postmortems/`) si:

- E4 no alcanza paridad tras dos iteraciones de correccion
- Una etapa exige violar un invariante de §2
- El Consumer necesita leer documentos crudos para funcionar (senal de que el contrato es insuficiente)
