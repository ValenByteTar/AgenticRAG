# ADR-0021 - Builder CLI: extract / compile / validate / publish + KIR Cache

- **Estado:** Aceptado
- **Fecha:** 2026-07-29
- **Relaciona con:** ADR-0018, ADR-0015, ADR-0017, RES-002

## Contexto

ADR-0018 define el Builder como un Knowledge Compiler con fases: front-end (Knowledge Acquisition) → KIR (lossless) → IR Passes (middle-end) → Validation → Knowledge Model → back-end (Artifact Generation). Hoy `build_knowledge.py` ejecuta todo en un solo proceso monolitico.

Esto genera tres problemas:

1. **Reingesta costosa**: cada cambio de configuracion (passes, validation, confidence policy, codegen) requiere re-ejecutar la extraccion LLM completa. Con 100 docs a ~30-60s por chunk, un build completo toma 2-3 horas. Con 861 docs, 20-40 horas. La extraccion es el cuello de botella y no hay razon para repetirla si el corpus no cambio.

2. **Fases invisibles**: las cuatro responsabilidades del Builder (extraer, compilar, validar, publicar) son fases conceptualmente distintas pero operacionalmente indistinguibles. No se puede recompilar sin reextraer. No se puede validar sin recompilar. No se puede publicar sin revalidar.

3. **Acoplamiento temporal**: un error en validation descarta horas de extraccion. Un error en publish descarta horas de compilacion. No hay puntos de checkpoint.

## Decision

### 1. Cuatro comandos como interfaz explicita del Builder

El Builder expone cuatro comandos independientes, cada uno con responsabilidad unica:

```
knowledge extract   — front-end: extractores → KIR crudo (con cache)
knowledge compile   — middle-end: KIR → passes → KnowledgeModel (sin codegen)
knowledge validate  — validation: structural + semantic + contract sobre KnowledgeModel
knowledge publish   — back-end: codegen desde modelo validado → Artifact Registry
```

**Orden de fases**:

```
extract → KIR (cache/)
compile → KnowledgeModel (model/)
validate → modelo validado + report (validated/)
publish → Warm Artifacts + Cold Artifacts → Registry (registry/)
```

**Validation antes de Codegen**: el codegen (serializacion a Warm Artifacts) ocurre despues de validation, dentro de `publish`. Esto garantiza que **jamás existen Warm Artifacts inválidos**. Si validation falla, el modelo no se serializa. No tiene sentido generar artifacts para luego validarlos — los artifacts son el producto compilado final, no un input intermedio de validacion.

Cada comando lee la salida del anterior desde disco. Ningun comando depende en runtime de otro.

**Retrocompatibilidad**: `build_knowledge.py` (sin subcomando) ejecuta los cuatro en secuencia. No rompe workflows existentes.

### 2. KIR Cache por chunk

El cache materializa KIR parcial por chunk de documento:

```
cache/
  <doc_slug>/
    meta.json          — {doc_name, text_hash, chunks, model, processed_at}
    chunk_0.kir.json   — KIR parcial serializado (entity_claims, alias_claims, relation_claims, document_claim)
    chunk_1.kir.json
    ...
```

**Protocolo del cache**:

- `extract` calcula `hash(text_chunk)` para cada chunk.
- Si `chunk_N.kir.json` existe y `meta.json` registra el mismo hash + modelo, se reusa sin llamar al LLM.
- Si el doc cambio o el modelo cambio, se re-extrae solo ese chunk.
- Si el doc no existe en cache, se extrae desde cero.
- El cache es invalidable por doc, por modelo, o globalmente (`--flush-cache`).

**KIR parcial serializado**: cada `chunk_N.kir.json` contiene claims ya parseados y validados tipicamente. No es la respuesta cruda del LLM. Es KIR listo para merge. El compilador no parsea JSON del LLM; lee KIR serializado.

### 3. Separacion de outputs por fase

```
cache/          — KIR parcial por chunk (extract output)
kir/            — KIR global merged (compile input)
model/          — KnowledgeModel serializado (compile output, validate input)
validated/      — Validation report + Cold Artifacts (validate output, publish input)
registry/       — Warm Artifacts + manifest (publish output, Artifact Registry)
```

Cada fase es idempotente: re-ejecutar con los mismos inputs produce los mismos outputs.

### 4. Catalogo de predicados v2 (deliberadamente pequeno)

El catalogo controlado se reduce y simplifica. Sigue siendo cerrado y versionado (ADR-0018 §8), pero se mantiene deliberadamente pequeno para evitar ambiguedad y crecimiento indefinido:

**Predicados v2 (9)**:

| Predicado | Semantica |
|---|---|
| `equivalent_to` | A es equivalente a B |
| `depends_on` | A depende de B |
| `implements` | A implementa B |
| `extends` | A extiende B |
| `references` | A referencia B |
| `governs` | A gobierna/regula B |
| `contains` | A contiene a B |
| `uses` | A usa B |
| `creates` | A crea/define B |

**Mapeo desde predicados v1 y lenguaje natural**:

| Predicado v1 / natural | Predicado v2 | Atributo |
|---|---|---|
| `defines` | `creates` | — |
| `belongs_to` | `contains` (inverso) | — |
| `part_of` | `contains` (inverso) | — |
| `supersedes` | `extends` | `supersedes: true` |
| `located_in` | `references` | `location: <value>` |
| `certifies` | `governs` | `certifies: true` |
| `compares_with` | `references` | `comparison: true` |

Los atributos viven en la arista del grafo, no como predicados separados. Esto preserva la semantica fuerte del grafo (GraphRAG) sin proliferar predicados.

**Versionado**: `predicate_catalog.catalog_version` pasa de `"1.0.0"` a `"2.0.0"`. El contract `warm-v1` no cambia (los artifacts tienen la misma estructura); solo el contenido del catalogo se actualiza. El Consumer ignora predicados que no conoce (forward compatibility).

### 5. Desacoplamiento extractor-ontologia

**El extractor no conoce el catalogo.** El LLM produce predicados en lenguaje natural (ej: `"certifies"`, `"is certification for"`, `"is used by"`). El `CanonicalizePass` mapea el predicado del LLM al catalogo v2 via fallback mapping.

```
LLM produce:              CanonicalizePass mapea:
"certifies"           →   governs + atributo certifies
"is certification for" →  governs + atributo certifies
"is used by"          →   uses
"defines"             →   creates
"belongs to"          →   contains (inverso)
"part of"             →   contains (inverso)
"supersedes"          →   extends + atributo supersedes
"located in"          →   references + atributo location
"compares with"       →   references + atributo comparison
```

**Beneficios**:
- El extractor es agnostico a la ontologia interna.
- Cambiar el catalogo no toca el prompt del LLM.
- El LLM produce semantica mas rica (lenguaje natural) que el compilador normaliza.
- Multiples LLMs con distintos prompts convergen al mismo catalogo via canonicalizacion.
- El fallback mapping ya existe en `canonicalize.py` — solo se amplian las entradas.

### 6. Roles de documento universales

La taxonomia de roles deja de ser cybersec-specific:

| Rol v1 (cybersec) | Rol v2 (universal) |
|---|---|
| `framework_list` | `list` |
| `cert_list` | `list` |
| `standard_profile` | `entity_profile` |
| `entity_profile` | `entity_profile` |
| `procedure` | `guide` |
| `manual_reference` | `reference` |
| `security_ops` | `guide` |
| `analysis_report` | `analysis` |
| `threat_intel` | `analysis` |
| `policy_compliance` | `reference` |
| `other` | `other` |

**Versionado**: `doc_roles` en el artifact incluye `role_taxonomy_version: "2.0.0"`. El Consumer que use roles para boosting (E6) debe declarar que version consume.

### 7. Prompt LLM domain-agnostico

El prompt del `LLMEntityExtractor` no prescribe un dominio. Extrae entidades de cualquier topico. Los tipos de entidad son libres (inferidos por el LLM), no una lista cerrada. Los predicados se producen en lenguaje natural y se mapean al catalogo v2 via `CanonicalizePass`.

## Consecuencias

- **Reingesta selectiva**: solo docs nuevos o modificados se re-extraen. Recompilar con nueva configuracion toma segundos, no horas.
- **Checkpointing natural**: cada fase persiste a disco. Un error en validation no descarta la extraccion.
- **Artifacts invalidos imposibles**: validation ocurre antes de codegen. Si validation falla, no se generan Warm Artifacts.
- **Observabilidad**: se puede inspeccionar el KIR crudo (`cache/`), el KIR merged (`kir/`), el modelo (`model/`), y el validation report (`validated/`) independientemente.
- **A/B testing trivial**: dos compiles con distinta confidence policy o passes sobre el mismo KIR cacheado producen dos modelos para comparar.
- **Cache portability**: el cache se puede mover entre maquinas. Si dos maquinas tienen el mismo corpus + modelo, comparten cache sin re-extraer.
- **Ontologia desacoplada**: cambiar el catalogo de predicados no requiere cambiar el prompt del LLM. El compilador absorbe el cambio via fallback mapping.
- **Costo asumido**: 4 comandos vs 1. Mayor superficie de CLI. Mitigado por retrocompatibilidad de `build_knowledge.py`.

## Alternativas consideradas

1. **Cache de respuesta cruda del LLM (JSON)** — rechazado: requiere re-parsear en cada compile. Cachear KIR parcial elimina el paso de parseo. El KIR ya tiene tipos validados, evidence, y estructura.
2. **Cache global (un solo archivo)** — rechazado: no permite invalidacion por doc. Un doc nuevo requiere re-extraer todo.
3. **No separar comandos, solo cachear** — rechazado: no resuelve el acoplamiento temporal. Un error en validation sigue descartando horas de extraccion.
4. **Validation despues de Codegen** — rechazado: genera Warm Artifacts potencialmente invalidos. Conceptualmente incorrecto: los artifacts son el producto final, no un input intermedio de validacion.
5. **Catalogo de 13+ predicados (v1)** — rechazado: crecimiento indefinido. Predicados como `located_in`, `certifies`, `compares_with` se modelan mejor como atributos de aristas con predicados base.
6. **Catalogo de 7 predicados** — rechazado: pierde semantica grafo-level. `governs` no es un matiz de `references`; es una relacion estructuralmente distinta que GraphRAG necesita como arista propia.
7. **LLM conoce el catalogo** — rechazado: acopla el extractor a la ontologia interna. Cambiar el catalogo requiere cambiar el prompt. El LLM fuerza predicados incorrectos cuando no encuentra uno que encaje.
8. **Predicados libres (sin catalogo)** — rechazado (ADR-0018 §8): el catalogo es cerrado y versionado. El LLM produce lenguaje natural; el compilador normaliza.
9. **Congelar roles cybersec** — rechazado: el sistema debe ser domain-agnostico. Los roles universales son un superset.
10. **Bumping contract_version a warm-v2** — rechazado: la estructura del artifact no cambia. Solo el contenido del catalogo y la taxonomia de roles se actualiza. Forward compatibility preservada.

## Criterios de aceptacion

- `knowledge extract` produce `cache/` con KIR parcial por chunk.
- `knowledge compile` lee `cache/` y produce `model/` (KnowledgeModel serializado) sin llamar al LLM y sin generar artifacts.
- `knowledge validate` lee `model/` y produce `validated/` (report + Cold Artifacts) sin generar Warm Artifacts.
- `knowledge publish` lee `validated/` y produce Warm Artifacts via codegen + publica al Artifact Registry.
- `build_knowledge.py` (sin subcomando) ejecuta los cuatro pasos en secuencia.
- Re-ejecutar `knowledge compile` con el mismo cache produce un modelo identico.
- Un doc nuevo solo dispara extraccion de ese doc, no del corpus entero.
- `predicate_catalog.catalog_version == "2.0.0"` en artifacts.
- El catalogo contiene exactamente 9 predicados: `equivalent_to`, `depends_on`, `implements`, `extends`, `references`, `governs`, `contains`, `uses`, `creates`.
- Roles de documento en artifacts usan la taxonomia v2.
- Prompt del LLM no contiene la palabra "cybersecurity" ni restringe dominio.
- Prompt del LLM no menciona el catalogo de predicados. El LLM produce predicados en lenguaje natural.
- `CanonicalizePass` mapea predicados del LLM al catalogo v2 via fallback mapping ampliado.
- Tests cubren: cache hit/miss, invalidacion por hash, separacion de fases, retrocompatibilidad, mapeo de predicados.
