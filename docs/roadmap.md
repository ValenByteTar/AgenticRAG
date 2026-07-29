# InfraPolus - Roadmap de Implementacion

Documento de baja estabilidad (cambia por ciclo). Fuente: arquitectura v2 + EKS v3 (ADR-0017).

Leyenda: P prioridad, D dificultad, I impacto, R riesgo.

## EKS - Engineering Knowledge System (transversal dev-time)

**ADR-0017 — CERRADO (foundation)**

Plano meta **fuera de `src/`**. No es el Knowledge System runtime (ADR-0015).

- [x] `knowledge/` con 6 categorias (decisions, experiments, benchmarks, postmortems, patterns, research)
- [x] Schema de metadata compartido (`knowledge/_schema/metadata.md`)
- [x] Templates fijos (`knowledge/_templates/`)
- [x] Skills: Engineering Context Builder, Experiment Logging, ADR Proposal
- [x] Semilla: DEC-001, BM-001, EXP-001
- [x] **No** `knowledge/adr/` — ADRs solo en `docs/adr/`
- [ ] Index generado (disparo ~30-40 docs)
- [ ] Knowledge Curator dev-time (nombre distinto del Knowledge Architect runtime)

Uso: antes de implementar → skill Context Builder; tras experimentos → Experiment Logging.

## Fase 0 - Kernel y fundaciones

**P1 D alta I habilitante R medio — CERRADA (codigo + baseline)**

- [x] Contratos del Kernel (ADR-0016) y `ExecutionState` (ADR-0004) → `src/kernel/`
- [x] Capability Registry (ADR-0012), Policy Engine (ADR-0013), Composition Root (ADR-0014)
- [x] `ModelProvider` Ollama + modelo desde `config.yaml` `llm.*` (ADR-0007)
- [x] Observability substrate (ADR-0005) → `TraceSink` / trazas en `ExecutionState`
- [x] `rebuild_on_build: false` por defecto
- [x] Docs canonicos: philosophy, vision, principles, adr/0000-0016, roadmap
- [x] Tests unitarios Kernel: `tests/unit/test_kernel_phase0.py` + `test_capabilities_bootstrap.py` (13 passed)
- [x] Capabilities adapters (`src/capabilities/`) + factory `src/bootstrap.py`
- [x] `HybridRAG.query_via_kernel()` (F0 experimental; F1 usado cuando `kernel.enabled=true`)
- [x] Baseline Evaluation suite v1: `tests/eval/baselines/baseline_pre_agentic_phase0/` (ADR-0006)
- [x] Renombre `centrales_map` → `domain_map` (alias de compatibilidad)
- [ ] Limpieza profunda dominio electrico residual en prompts/heuristicas — diferida a refactor incremental (no bloquea Fase 1)
- **Gates Fase 0 cumplidos:** `kernel.enabled=false`, fachada `query()` intacta, baseline congelado, Kernel testeado.
- **Nota:** baseline actual = subset 25q (`report_20260712_191655`).

## Fase 1 - Controller FSM 1:1 y cadena de responsabilidad

**P1 D alta I alto R alto — CERRADA (codigo + gates estructurales; A/B calidad operativo pendiente)**

- [x] Controller-runtime como FSM (ADR-0003) que solo ejecuta (ADR-0002)
- [x] Fachada `query()` despacha por `kernel.enabled` (ADR-0010): false -> `_query_linear_impl`, true -> `query_via_kernel`
- [x] Camino kernel F1.c: classify -> memory_read -> retrieve(+sticky+rerank) -> build_context(+mem) -> assess -> generate -> finalize_turn
- [x] `MemoryReadCapability` (ADR-0009 read-only) + sticky en retrieve/finalize
- [x] `ClassifyCapability` + OOD decline; `AssessEvidenceEvaluator` + `AssessGatePolicy`
- [x] Harness `--kernel` para A/B sin cambiar default (`tests/eval/run_cybersec_eval.py`)
- [x] Gates cierre: `tests/unit/test_phase1_close_gates.py` + suite kernel (**24 passed**)
- [x] DEC-002 + EXP-001 (scaffold accepted; seccion B A/B offline pendiente de entorno)
- [ ] Entity two-stage / streaming en camino kernel — diferido (no bloquea cierre F1)
- [ ] A/B offline 25q vs BM-001 con `--kernel` — **operativo** (requiere rank_bm25 + Chroma + Ollama)
- [ ] `kernel.enabled=true` por default — solo tras seccion B de EXP-001 en verde
- **Default:** `kernel.enabled=false`, `max_iterations=12`
- **Siguiente:** Fase 2 (ASSESS online enriquecido / metricas assess_*) en paralelo a corrida EXP-001-B cuando haya entorno.

## Fase 2 - Evaluation online: ASSESS (enriquecido)

**P1 D media I alto R bajo — CERRADA**

- [x] Base F1: `AssessEvidenceEvaluator` + `AssessGatePolicy` (pass/decline)
- [x] Senal blanda: `entity_coverage_ratio` (0..1, matched/total entidades en contexto)
- [x] Senal blanda: `source_diversity` (nº de sources distintos en results)
- [x] Senal blanda: `context_density` (tokens unicos / tokens totales)
- [x] Senal blanda: `assess_precision_proxy` (quality_results / total_results)
- [x] Hard gate 5: entity coverage = 0 con entidades presentes (configurable floor)
- [x] Flags blandos: `entity_coverage_low`, `source_diversity_low` para F3
- [x] `RetrySignalPolicy` (observa senales blandas; decide retry con max_retries=1)
- [x] `RetrievalCapability` maneja retry: limpia context/assessed stale
- [x] Score enriquecido: bonuses por coverage, diversity, density
- [x] Tests: 44 passed (incl. e2e retry flow, hard fail, gate decline)
- **Validacion:** groundedness y anti-alucinacion pendientes de corrida offline (EXP-002)


## Fase 3 - Policies de retry / re-retrieval

**P1 D media I alto R medio — CERRADA**

- [x] Base F2: `RetrySignalPolicy` observa senales blandas y decide retry
- [x] Multi-retry con budget: `max_retries=2`, respeta `max_iterations` y `max_llm_calls`
- [x] Retry 1: `retrieval` con `relax_entity_filter` + `boost_diversity` (lower sw, wider net)
- [x] Retry 2: `two_stage_retrieval` con entity-focused search + stage_boost
- [x] `TwoStageRetrievalCapability`: per-entity search + dedup + rerank + boost
- [x] `RetrievalCapability`: maneja `widen_top_k` (1.5x) y `boost_diversity` (sw - 0.15)
- [x] Adapter `_two_stage_retrieve` en `build_kernel_bundle_from_rag`
- [x] Tests: 54 passed (incl. e2e multi-retry, budget stop, two-stage fallback)
- **Validacion:** retry_yield positivo pendiente de corrida offline (EXP-003)

## Items pendientes (Fases 0-3) — CERRADOS

- [x] Limpieza de dominio electrico residual en `rag_hybrid.py` (prompts, heuristicas, entity extraction, ban_tokens, evidence_words, anforas) — DEC-005, EXP-004
- [x] Streaming en camino kernel (`ExecutionState.token_callback`/`cancel_checker` + `GenerationCapability` passthrough + `query_via_kernel` propagation) — DEC-005, EXP-004
- [x] EKS index generado (`scripts/generate_eks_index.py` -> `knowledge/INDEX.md` + `knowledge/_eks_index.json`, 8 docs) — DEC-005, EXP-004
- [x] Tests: 90 passed (23 nuevos en `test_phase3_cleanup_streaming_eks.py`)
- **Diferido:** Knowledge Curator (dev-time)

## Fase 4 - Evaluation online: VERIFY + policy de reparacion

**P1 D media I medio-alto R medio**

- [x] `VerifyGroundednessEvaluator`: groundedness (overlap de tokens), hedge detection (justificado vs injustificado), citation fidelity — `src/evaluation/verify_groundedness.py`
- [x] `VerifyCapability`: adapter que corre evaluator y atacha `EvaluationSignal(name="verify")` — `src/capabilities/verify.py`
- [x] `VerifyRepairPolicy`: repair con presupuesto (default 1), decline si agotado — `src/policies/verify_repair.py`
- [x] `LinearRagPolicy`: verify despues de generation, antes de finalize_turn
- [x] `GenerationCapability`: soporte `repair_hint` en params (reset verified, prepend instrucciones)
- [x] `bootstrap.py`: wiring completo (VerifyCapability + VerifyRepairPolicy + VerifyGroundednessEvaluator)
- [x] Tests: 20 nuevos en `test_phase4_verify_repair.py` (evaluator, capability, policy, E2E repair pass/fail/decline)
- [x] Documentacion: DEC-006, EXP-005
- **Validacion:** A/B con dataset completo pendiente (requiere Ollama + ~75 preguntas)

## Fase 5 - Knowledge System minimo + Memory de lectura

**P2 D alta I medio-alto R medio**

- [x] `MemoryPortAdapter` (`src/adapters/memory_port.py`) — envuelve MemorySystem bajo contrato MemoryPort, agrega provenance — ADR-0009
- [x] `KnowledgeSystemAdapter` (`src/adapters/knowledge_system.py`) — envuelve hybrid_search+rerank bajo contrato KnowledgeSystem, get_entity stub (esquema diferido P11) — ADR-0015
- [x] `MemoryReadCapability` actualizado para aceptar MemoryPort (con `.read()`) ademas de callable
- [x] `bootstrap.py` — wiring automatico de adapters en `build_kernel_bundle_from_rag`
- [x] Tests: 17 nuevos en `test_phase5_knowledge_memory.py` (protocol compliance, provenance, E2E)
- [x] Documentacion: DEC-007, EXP-006
- **Validacion:** 127 passed sin regresion

## Fase 6 - Planner y decomposition

**P2 D alta I medio R medio-alto**

- [x] `PlannerCapability` (`src/capabilities/planner.py`) — planner determinista: detecta tipo de query, asigna roles, ajusta semantic_weight
- [x] `EntityExpansionCapability` (`src/capabilities/entity_expansion.py`) — gazetteer de aliases (iso 27001 -> iso27001, iso 27k, isms)
- [x] `LinearRagPolicy` actualizada: cadena classify -> memory_read -> planner -> entity_expansion -> retrieval -> ...
- [x] `bootstrap.py` — wiring de planner_fn y entity_expand_fn
- [x] Integracion entity_extractor: `_expand_entities` usa rag.entity_aliases + memory.get_synonyms + entity_extractor.domain_entities + _DEFAULT_ALIASES
- [x] Integracion doc_roles: `_planner_fn` usa select_docs_by_roles de doc_cards.py -> candidate_docs -> soft boost post-retrieval
- [x] `RetrievalCapability` — aplica soft boost (+0.05 score) para candidate_docs, no hard filtering
- [x] Tuning: adaptive reranker pool (10/15/20 vs 35 fijo)
- [x] Tuning: repair_hint mejorado (instrucciones enumeradas, citacion [N])
- [x] Tuning: groundedness floor 0.3 -> 0.25
- [x] Tests: 23 nuevos en `test_phase6_planner_expansion.py` (planner, expansion, E2E, tunings, wiring)
- [x] Documentacion: DEC-008, EXP-006b, BM-003
- **Validacion:** 150 passed sin regresion; A/B BM-003: 45.5% pass (sin regresion vs BM-002), brecha con monolito persistente (retrieval: two-stage, equivalences)

## Fase 7 - Knowledge Builder / Consumer split

**P1 D alta I alto R alto**

Detalle de ejecucion en [plan-orquestacion-knowledge.md](plan-orquestacion-knowledge.md) (etapas E0-E8 + track B).

- Contrato Warm, Artifact Registry, Knowledge Compiler, Consumer que resuelve — ADR-0018, RES-001/002/003
- LLMSupport como observador paralelo (track independiente) — RES-004
- **Validacion:** A/B por etapa; objetivo cerrar la brecha de 27.3pp vs monolito

## Fase 9 - Compuestas

**P3 D alta I incierto R alto**

- Memoria escritura verificada; Tools; multi-modelo via ModelProvider
- **Validacion:** A/B por capacidad; sin alucinaciones aprendidas

## Dependencias

```
F0 -> F1 -> F2 -> F3 -> F4 -+-> F5 -> F6 -+
                            +-------------+-> F7 -> F8 -> F9
```

## Criterio de aceptacion global

1. Respeta Filosofia y Principios
2. No rompe contratos ADR sin ADR que supersede
3. Agrega capacidades registrando, sin tocar Kernel ni Controller (P15)
4. Toda decision es senal -> policy -> accion trazada
5. Corre la suite de Evaluation sin romper el harness
6. No regresa en groundedness / anti-alucinacion / doc_hit / page_hit
