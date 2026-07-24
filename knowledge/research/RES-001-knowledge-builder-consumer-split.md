---
id: RES-001
category: research
status: draft
created: 2026-07-24
updated: 2026-07-24
author: human
components: [rag_hybrid, entity_extractor, doc_cards, equivalences_manager, conceptual_map, kernel, capabilities]
tags: [architecture, index-time, query-time, agentic, llm, knowledge-builder, knowledge-consumer, heuristicas]
related: [ADR-0009, ADR-0012, ADR-0013, ADR-0015, ADR-0017, DEC-008, BM-002, BM-003, BM-004, EXP-006b]
supersedes: null
superseded_by: null
---

# RES-001 - Knowledge Builder / Knowledge Consumer split

## Topic

Separacion arquitectonica entre la construccion de conocimiento sobre documentos (index-time, agentic, LLM-driven) y el consumo de ese conocimiento en retrieval (query-time, kernel, sin heuristicas de dominio).

## Sources

- BM-002: A/B Kernel+VERIFY vs Monolito — brecha de 36.3pp causada enteramente por retrieval
- BM-003: A/B Kernel Fase 6 vs Monolito — sin regresion pero brecha persistente
- BM-004: A/B Kernel Fase 6 + bug fixes (wiring + two-stage en policy) — brecha reducida a 27.3pp
- DEC-008: Planner + EntityExpansion tunings — wiring completado, impacto medido en BM-004
- ADR-0009: Memory Port (read-only en kernel)
- ADR-0015: Knowledge System (retrieval + get_entity)
- ADR-0017: EKS (Engineering Knowledge System dev-time)
- Monolito: `rag_hybrid.py`, `doc_cards.py`, `equivalences_manager.py`, `conceptual_map.py`, `src/rag/entity_extractor.py`, `retrieval_engine.py`

## Motivacion

### El problema de fondo

El monolito (`rag_hybrid.py`) mezcla responsabilidades de index-time y query-time en un solo flujo. Cada query ejecuta trabajo que deberia haberse hecho una vez durante la indexacion:

| Trabajo | Donde se hace hoy | Cuando se ejecuta | Deberia ser |
|---|---|---|---|
| Extraer entidades de documentos | `entity_extractor.update_domain_from_collection()` | Init + cada query | Index-time |
| Clasificar roles de documentos | `doc_cards.build_doc_cards()` / `build_doc_cards_llm()` | Init (con fallback en query) | Index-time |
| Descubrir sinonimos/aliases | `entity_aliases` dict hardcoded + `memory.get_synonyms()` | Cada query | Index-time + cache |
| Expandir equivalencias | `equivalences_manager.expand()` (92 grupos hardcoded) | Cada query | Index-time |
| Inferir atributos de documentos | `doc_cards._infer_attributes_presence()` | Init | Index-time |
| Estimar centralidad | `doc_cards._estimate_centrality()` | Init | Index-time |
| Construir gazetteer de dominio | `entity_extractor` + `doc_roles` + `domain_map` | Init + cada query | Index-time |
| Expansion ligera de query | `extra_terms` (control, incidente, troubleshooting) | Cada query | Query-time (pero con data del Builder) |
| Mapa conceptual (hechos aprendidos) | `conceptual_map.py` | Cada query (read) + aprendizaje diferido | Index-time + runtime learning |
| Filtrado por tecnologia | `_filter_results_by_technology()` | Cada query | Query-time (usa roles del Builder) |

### Sintomas observados en A/B

**BM-002** (Fase 4): 45.5% pass rate vs 81.8% monolito. Brecha de 36.3pp.
**BM-003** (Fase 6): 45.5% pass rate (sin regresion). Las capabilities de planner y entity expansion no mejoraron pass rate porque los datos no llegaban a la query de busqueda.
**BM-004** (Fase 6 + bug fixes): 54.5% pass rate. Brecha reducida a 27.3pp. Los bug fixes cerraron dos gaps de data flow:

1. ~~`EntityExpansionCapability` computa entidades expandidas pero `RetrievalCapability` no las inyecta en la query de busqueda~~ — **FIXED en BM-004**: `RetrievalCapability` y `TwoStageRetrievalCapability` ahora inyectan `expanded_entities` en la query.
2. `PlannerCapability` produce `candidate_docs` pero el soft boost (+0.05) es insignificante frente a scores de reranker (0.0-0.99).
3. ~~Las queries que fallan necesitan two-stage retrieval con entity matching, que el kernel tiene registrado pero no activa automaticamente~~ — **FIXED en BM-004**: `LinearRagPolicy` ahora activa `two_stage_retrieval` en el primer pass cuando hay entidades detectadas.
4. El monolito resuelve las queries restantes (21, 24, 45, 51, 55) con heuristicas que no queremos replicar en el kernel.

**Mejora observada en BM-004**: +1 pregunta PASS (Q41 ambiguous), +11.1pp doc hit@K, +0.111 MRR. Las 5 queries que siguen fallando necesitan mecanismos que residen en el monolito (comparison detection, equivalences, domain gazetteer completo, technology filtering).

### Por que pegar parches no funciona

Cada heuristica del monolito que intentamos replicar en el kernel:
- **Entity aliases hardcoded**: `entity_aliases` dict con 7 entidades de ciberseguridad. No escala, no generaliza, es conocimiento de dominio embebido en codigo.
- **Equivalences manuales**: 92 grupos de equivalencias en texto embebido (`EQUIVALENCES_EMBEDDED_TEXT`). Mismo problema.
- **Extra terms**: Expansion ligera con triggers como `'cuant'`, `'incidente'`, `'control'`. Heuristica ad-hoc.
- **Role guessing**: `_guess_role_by_name()` en `doc_cards.py` usa keywords hardcoded (`"listado"`, `"catalog"`, `"inventory"` -> `entity_list`).
- **Technology filtering**: `_filter_results_by_technology()` con keywords hardcoded (`"framework"`, `"certification"`, `"threat"`).

Cada parche que agregamos al kernel:
1. Acopla el kernel a un dominio especifico (ciberseguridad)
2. Duplica logica que ya existe en el monolito
3. No escala a otros dominios
4. Violacion de clean boundaries (user rule: "Never introduce hidden coupling")
5. Violacion de architecture-first (user rule: "Never bypass architectural layers")

## Propuesta: Knowledge Builder / Knowledge Consumer

### Vision

```
┌─────────────────────────────────────────────────────────────┐
│                     KNOWLEDGE BUILDER                         │
│                   (index-time, agentic)                       │
│                                                              │
│  Por cada documento (o batch):                               │
│  1. LLM extrae entidades (nombres propios, terminos tecnicos)│
│  2. LLM descubre sinonimos y aliases dinamicamente            │
│  3. LLM clasifica rol del documento (entity_profile,          │
│     analysis_report, procedure, manual, etc.)                 │
│  4. LLM infiere atributos presentes (controles, metricas,     │
│     procedimientos, etc.)                                     │
│  5. LLM estima centralidad/topicalidad                        │
│  6. LLM construye resumen/abstract                            │
│  7. LLM identifica relaciones entre entidades                 │
│  8. Persiste todo a metadata store (JSON/SQLite/Chroma)       │
│                                                              │
│  Output: indice enriquecido con conocimiento estructurado     │
│  - entity_index: {entity: [doc_ids]}                         │
│  - alias_index: {alias: canonical_entity}                    │
│  - doc_roles: {doc_id: {role, attributes, centrality, ...}}  │
│  - entity_relations: {entity: {related: [], attributes: {}}} │
│  - doc_summaries: {doc_id: summary}                          │
│                                                              │
│  Caracteristicas:                                             │
│  - Agnostic al dominio (el LLM descubre, no se hardcodea)     │
│  - Incremental (nuevos docs se procesan solos)                │
│  - Cacheable (re-ejecutar solo si cambia el documento)        │
│  - Versionable (cada build tiene version y modelo)            │
│  - Validable (human-in-the-loop opcional)                     │
└───────────────────────┬─────────────────────────────────────┘
                        │ (indice enriquecido persistido)
                        │
┌───────────────────────▼─────────────────────────────────────┐
│                    KNOWLEDGE CONSUMER                          │
│               (query-time, Agentic RAG kernel)                │
│                                                              │
│  Query → PlannerCapability                                   │
│          lee doc_roles (pre-computado) → candidate_docs       │
│        → EntityExpansionCapability                           │
│          lee alias_index (pre-computado) → expanded_entities  │
│        → RetrievalCapability                                 │
│          usa entity_index para two-stage (pre-computado)      │
│          inyecta expanded_entities en query de busqueda       │
│          aplica soft boost para candidate_docs                │
│        → Rerank → Generate → Verify → Repair                  │
│                                                              │
│  Cero heuristicas de dominio hardcoded.                      │
│  Solo lee metadata persistida por el Builder.                 │
│  Agnostic al dominio.                                         │
└─────────────────────────────────────────────────────────────┘
```

### Contrato entre Builder y Consumer

El Builder produce un **Knowledge Artifact** (KA) versionado con:

```json
{
  "version": "1.0.0",
  "builder_model": "mistral:7b",
  "built_at": "2026-07-24T18:00:00Z",
  "domain": "ciberseguridad",
  "stats": {
    "total_docs": 861,
    "total_entities": 1240,
    "total_aliases": 3100
  },
  "entity_index": {
    "iso 27001": ["iso27001.pdf", "isms_guide.pdf"],
    "nist csf": ["nist-csf.pdf", "framework_overview.pdf"]
  },
  "alias_index": {
    "iso27001": "iso 27001",
    "iso 27k": "iso 27001",
    "isms": "iso 27001",
    "nist cybersecurity framework": "nist csf"
  },
  "doc_roles": {
    "iso27001.pdf": {
      "role": "entity_profile",
      "name": "ISO 27001 Standard",
      "centrality": 0.92,
      "entities": ["iso 27001", "isms", "access control"],
      "attributes": ["controls", "risk assessment", "annex a"],
      "summary": "International standard for information security management systems..."
    }
  },
  "entity_relations": {
    "iso 27001": {
      "related": ["nist csf", "cobit", "pci dss"],
      "attributes": {"controls": "Annex A", "certification": "ISMS"}
    }
  }
}
```

El Consumer lee este artifact en init y lo expone via capabilities. **No computa nada de dominio**.

### Que reemplaza el Builder

| Componente del monolito | Que hace | Reemplazo del Builder |
|---|---|---|
| `entity_aliases` dict (7 entidades hardcoded) | Gazetteer de aliases | `alias_index` generado por LLM |
| `EQUIVALENCES_EMBEDDED_TEXT` (92 grupos) | Equivalencias manuales | `alias_index` + `entity_relations` |
| `entity_extractor.update_domain_from_collection()` | Construye gazetteer desde docs | `entity_index` + `alias_index` |
| `doc_cards._guess_role_by_name()` | Heuristica de rol por nombre | LLM clasifica rol |
| `doc_cards._extract_basic_entities()` | Heuristica de entidades | LLM extrae entidades |
| `doc_cards._infer_attributes_presence()` | Heuristica de atributos | LLM infiere atributos |
| `doc_cards._estimate_centrality()` | Heuristica de centralidad | LLM estima topicalidad |
| `doc_cards.build_doc_cards()` | Build heuristico | Builder con LLM |
| `doc_cards.build_doc_cards_llm()` | Build con LLM (granite) | Builder unificado |
| `conceptual_map.entity_aliases` | Aliases aprendidos | `alias_index` del Builder |
| `conceptual_map.entity_facts` | Hechos verificados | `entity_relations` del Builder |
| `_filter_results_by_technology()` | Filtrado por tipo | Usa `doc_roles` del Builder |
| `extra_terms` expansion ligera | Expansion ad-hoc | `alias_index` + `entity_relations` |
| `_plan_retrieval()` roles preferred | Heuristica de roles | LLM en Builder asigna roles |

### Que queda en el Consumer (kernel)

| Capability | Que hace ahora | Que hace con Builder |
|---|---|---|
| `PlannerCapability` | Detecta tipo de query (determinista) | Igual — lee `doc_roles` pre-computados |
| `EntityExpansionCapability` | Lee `_DEFAULT_ALIASES` hardcoded | Lee `alias_index` del Builder |
| `RetrievalCapability` | Busca sin entidades | Inyecta `expanded_entities` en query + usa `entity_index` para two-stage |
| `TwoStageRetrievalCapability` | Busca por entidad (F3) | Usa `entity_index` pre-computado |
| `MemoryReadCapability` | Lee memoria | Igual — memoria es runtime, no index |
| `VerifyCapability` | Evalua groundedness | Igual |

### Modelo de ejecucion del Builder

#### Opcion A: Batch standalone (recomendado inicial)

```bash
python build_knowledge.py --docs /path/to/docs --model mistral:7b --output knowledge_artifact.json
```

- Corre fuera del kernel, como un script independiente
- Procesa todos los documentos (o incrementales)
- Persiste el artifact a disco
- El Consumer carga el artifact en init

**Ventajas**: Simple, reutilizable, no acoplado al kernel.
**Desventajas**: Re-ejecucion completa para updates.

#### Opcion B: Incremental con watch

```bash
python build_knowledge.py --watch /path/to/docs --model mistral:7b
```

- Monitorea cambios en el directorio de documentos
- Procesa solo documentos nuevos/modificados
- Merge con artifact existente

**Ventajas**: Auto-mantenimiento.
**Desventajas**: Complejidad de watch + merge.

#### Opcion C: Agentic pipeline (Fase 8+)

El Builder es un agente con tools:
- `read_document(doc_id)` — lee un documento
- `extract_entities(text)` — LLM call
- `classify_role(text, entities)` — LLM call
- `discover_aliases(entity, context)` — LLM call
- `persist_artifact(data)` — guarda a store
- `validate_quality(artifact)` — LLM auto-valida

El agente decide el orden, maneja errores, re-intenta, valida.

**Ventajas**: Maxima flexibilidad, auto-mejora.
**Desventajas**: Complejidad alta, no necesario inicialmente.

### Prompt design para el Builder

#### Extraccion de entidades

```
You are a knowledge engineer analyzing a cybersecurity document.

Document: {doc_name}
Text (first 2000 chars): {text}

Extract:
1. Named entities (frameworks, standards, certifications, organizations, tools)
2. Technical terms specific to this domain
3. For each entity, provide:
   - Canonical name
   - All aliases/abbreviations found in the text
   - Entity type (framework, certification, organization, tool, concept)

Respond in JSON:
{"entities": [{"canonical": "ISO 27001", "aliases": ["iso27001", "iso 27k", "isms"], "type": "framework"}]}
```

#### Clasificacion de roles

```
You are a knowledge engineer classifying a document.

Document: {doc_name}
Text (first 2000 chars): {text}
Entities found: {entities}

Classify this document into one of these roles:
- entity_profile: Document that profiles/describes a specific entity (standard, framework, certification)
- analysis_report: Document that analyzes, compares, or evaluates entities
- procedure: Document with step-by-step procedures, playbooks, or protocols
- manual: Technical manual or reference guide
- entity_list: Catalog, inventory, or directory listing
- other: Does not fit above categories

Also identify:
- Key attributes present (controls, metrics, procedures, requirements, etc.)
- A one-sentence summary
- Centrality score (0-1): how central is this document to the domain

Respond in JSON:
{"role": "entity_profile", "attributes": ["controls", "risk assessment"], "summary": "...", "centrality": 0.92}
```

#### Descubrimiento de sinonimos

```
You are a knowledge engineer building a synonym map for a cybersecurity corpus.

Entities found across corpus: {entities}

For each entity, list all known synonyms, abbreviations, and alternative spellings.
Include domain-specific abbreviations and common misspellings.

Respond in JSON:
{"aliases": {"iso 27001": ["iso27001", "iso 27k", "isms", "iso/iec 27001"], ...}}
```

### Comparativa: monolito vs kernel+Fase6 vs Builder/Consumer

| Aspecto | Monolito | Kernel Fase 6 | Builder/Consumer |
|---|---|---|---|
| **Conocimiento de dominio** | Hardcoded en codigo | Hardcoded en `_DEFAULT_ALIASES` | LLM en Builder, zero en Consumer |
| **Entity expansion** | Dict + memory + heuristica | `_DEFAULT_ALIASES` + memory (inyectado en query desde BM-004) | `alias_index` pre-computado, inyectado en query |
| **Doc roles** | Heuristica + LLM opcional | `select_docs_by_roles` con soft boost | LLM en Builder, Consumer solo lee |
| **Equivalences** | 92 grupos manuales | No integrado | `alias_index` + `entity_relations` |
| **Two-stage** | Automatico con entity matching | Activado en primer pass desde BM-004 | `entity_index` pre-computado |
| **Comparaciones** | `_search_for_comparison()` | No implementado | `entity_relations` guia balanceo |
| **Latencia query** | ~55s (mucho trabajo en query) | ~54s (sin trabajo extra) | ~40s estimado (sin LLM pre-retrieval) |
| **Escalabilidad dominio** | No (hardcoded ciberseguridad) | No (hardcoded ciberseguridad) | Si (LLM agnostic) |
| **Mantenibilidad** | Baja (heuristicas dispersas) | Media (capabilities pero con hardcoded) | Alta (separacion limpia) |
| **Acoplamiento** | Alto (todo en `rag_hybrid.py`) | Medio (kernel + monolito wiring) | Bajo (contrato entre Builder y Consumer) |

### Donde vive el Builder

#### Opcion A: Mismo repo, paquete separado

```
AgenticRAG/
  src/                    # Kernel (Consumer)
  knowledge_builder/      # Builder
    __init__.py
    builder.py            # Orquestador
    extractors.py         # LLM extractors (entities, roles, aliases)
    artifact.py           # KnowledgeArtifact schema + persist
    pipeline.py           # Batch/incremental pipeline
  knowledge_artifacts/    # Output del Builder (versionado)
    ka_v1.0.0.json
  tests/
    test_knowledge_builder.py
```

**Ventajas**: Simple, mismo venv, mismo config.
**Desventajas**: Acoplamiento de repo.

#### Opcion B: Repo separado, shared contract

```
AgenticRAG/               # Consumer (kernel)
  src/
  knowledge_artifacts/    # Artifacts descargados del Builder

KnowledgeBuilder/         # Builder (repo separado)
  src/
  contract.py             # KnowledgeArtifact schema (shared)
```

**Ventajas**: Separacion total, deploy independiente.
**Desventajas**: Contrato compartido requiere coordinacion.

#### Recomendacion: Opcion A inicial, migrar a B si crece

### Esquema de versionado del Knowledge Artifact

```
knowledge_artifacts/
  ka_v1.0.0.json          # Full build, mistral:7b
  ka_v1.0.1.json          # Incremental: 3 docs nuevos
  ka_v1.1.0.json          # Re-build con modelo mejorado
  ka_manifest.json        # Pointer al artifact activo
```

El Consumer carga el artifact indicado por `ka_manifest.json`. Permite A/B testing de artifacts.

### Migracion incremental

No es big-bang. Fases propuestas:

**Fase 7a**: Builder standalone con LLM
- `knowledge_builder/` con extraccion de entidades + aliases + roles
- Output: `ka_v1.0.0.json`
- Consumer carga artifact en `bootstrap.py`
- `EntityExpansionCapability` lee `alias_index` en lugar de `_DEFAULT_ALIASES`
- `PlannerCapability` lee `doc_roles` del artifact en lugar de `rag.doc_roles`
- **No se eliminan heuristicas del monolito** (compatibilidad)

**Fase 7b**: Two-stage con entity_index
- ~~`RetrievalCapability` inyecta `expanded_entities` en query de busqueda~~ — **Hecho en BM-004**
- ~~`LinearRagPolicy` activa two-stage cuando planner detecta entidades~~ — **Hecho en BM-004**
- `TwoStageRetrievalCapability` usa `entity_index` pre-computado del Builder para busqueda dirigida (actualmente usa fallback que delega a `retrieve_fn`)
- **No se eliminan heuristicas del monolito** (compatibilidad)

**Fase 7c**: A/B Builder/Consumer vs monolito
- Correr eval con `--kernel` usando artifact del Builder
- Medir pass rate, doc hit, recall, MRR
- Objetivo: paridad o mejora vs monolito (81.8%)

**Fase 8**: Deprecar heuristicas del monolito
- Si A/B es positivo, eliminar `_DEFAULT_ALIASES`, `entity_aliases` dict, `EQUIVALENCES_EMBEDDED_TEXT`
- El monolito queda como facade que delega al kernel
- `kernel.enabled=true` por defecto

### Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigacion |
|---|---|---|---|
| LLM alucina entidades/aliases | Media | Medio | Validacion post-extraccion + human-in-the-loop opcional |
| Costo de re-indexar 100k docs | Alta | Alto | Builder incremental + cache por documento |
| Artifact demasiado grande para memoria | Baja | Medio | Lazy load + SQLite en lugar de JSON |
| LLM del Builder vs LLM del Consumer | Media | Bajo | Builder puede usar modelo distinto (mas capaz) |
| Contrato Builder/Consumer se rompe | Media | Alto | Schema versionado + validacion en carga |
| Calidad del Builder peor que heuristicas | Baja | Alto | A/B antes de deprecar monolito |

### Open questions

1. **Modelo del Builder**: ¿mistral:7b (mismo del Consumer) o un modelo mas capaz (granite, llama3:70b)?
2. **Granularidad**: ¿Por documento o por chunk? (El monolito indexa por chunk en ChromaDB)
3. **Persistencia**: ¿JSON file, SQLite, o metadata en ChromaDB?
4. **Trigger**: ¿Manual, watch, o on-demand desde el Consumer?
5. **Validacion**: ¿Human-in-the-loop, LLM self-validation, o ambos?
6. **Relaciones entre entidades**: ¿Graph, flat dict, o embeddings?
7. **Multi-idioma**: ¿El Builder detecta idioma y adapta prompts?
8. **Update de artifact**: ¿Como manejar documentos que cambian de contenido?
9. **A/B de artifacts**: ¿Como comparar calidad entre versiones del artifact?
10. **Dependencia circular**: ¿Builder necesita el vector store? ¿O solo texto crudo?

### Takeaways

1. **El problema no es de heuristicas, es de arquitectura.** El monolito mezcla index-time con query-time. El kernel hereda esta confusion.
2. **Builder/Consumer split es la decision arquitectonica que desbloquea el cierre de la brecha.** No es un parche, es una separacion de responsabilidades.
3. **El Builder reemplaza 14+ heuristicas hardcoded con LLM agentic.** El Consumer queda agnostic al dominio.
4. **Migracion incremental posible.** No requiere big-bang. Fase 7a-7c antes de deprecar el monolito.
5. **El Knowledge Artifact es el contrato.** Versionado, validable, A/B-testeable.
6. **No se implementa ahora.** Se documenta como research para tener entre ceja y ceja. Cuando se decida, se promueve a ADR.
