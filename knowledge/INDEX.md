# EKS Index

Generado: 2026-08-06
Documentos indexados: 42

> Auto-generado por `scripts/generate_eks_index.py`. No editar a mano.

## Decisions (6)

| ID | Status | Title | Updated | Components |
|----|--------|-------|---------|------------|
| `DEC-001` | accepted | [DEC-001 - Renombrar centrales_map a domain_map](decisions/DEC-001-rename-centrales-map-to-domain-map.md) | 2026-07-22 | facade, capabilities |
| `DEC-003` | accepted | [DEC-003 - Fase 2: ASSESS enriquecido con senales blandas](decisions/DEC-003-phase2-assess-enriched.md) | 2026-07-23 | evaluation, assess, policies, kernel |
| `DEC-004` | accepted | [DEC-004 - Fase 3: Multi-retry con two-stage entity retrieval](decisions/DEC-004-phase3-multi-retry-two-stage.md) | 2026-07-23 | policies, retrieval, kernel, two-stage |
| `DEC-005` | accepted | [DEC-005 - Limpieza dominio electrico, streaming kernel y EKS index](decisions/DEC-005-cleanup-streaming-eks-index.md) | 2026-07-23 | facade, generation, kernel, knowledge |
| `DEC-013` | accepted | [DEC-013 - Migracion a canonical_doc_id como key unica de documento](decisions/DEC-013-canonical-doc-id-migration.md) |  | - |
| `DEC-014` | accepted | [DEC-014 - Desacoplamiento de DocCards del Vector Store](decisions/DEC-014-doccards-decouple-vector-store.md) |  | - |

## Experiments (4)

| ID | Status | Title | Updated | Components |
|----|--------|-------|---------|------------|
| `EXP-002` | accepted | [EXP-002 - ASSESS enriquecido: senales blandas + retry signal](experiments/EXP-002-assess-enriched.md) | 2026-07-23 | evaluation, assess, policies, kernel |
| `EXP-003` | accepted | [EXP-003 - Multi-retry con two-stage entity retrieval](experiments/EXP-003-multi-retry-two-stage.md) | 2026-07-23 | policies, retrieval, kernel, two-stage |
| `EXP-004` | accepted | [EXP-004 - Limpieza dominio electrico, streaming kernel y EKS index](experiments/EXP-004-cleanup-streaming-eks-index.md) | 2026-07-23 | facade, generation, kernel, knowledge |
| `EXP-008` | completed | [EXP-008 - Auditoria de cobertura de fallback de predicados](experiments/EXP-008-predicate-fallback-audit.md) | 2026-08-03 | knowledge-builder, canonicalize, predicate-catalog, entity-relations |

## Benchmarks (4)

| ID | Status | Title | Updated | Components |
|----|--------|-------|---------|------------|
| `BM-001` | accepted | [BM-001 - Baseline pre-agentic Fase 0](benchmarks/BM-001-baseline-pre-agentic-phase0.md) | 2026-07-22 | evaluation, facade, retrieval, generation |
| `BM-004` | completed | [BM-004 - A/B Kernel Fase 6 + bug fixes de data flow vs Monolito](benchmarks/BM-004-kernel-fase6-bugfixes.md) | 2026-07-28 | kernel, retrieval, two-stage-retrieval, entity-expansion, planner |
| `BM-005` | completed | [BM-005 - A/B Consumer con Warm Artifacts (E4) vs Baseline Kernel (BM-004)](benchmarks/BM-005-consumer-warm-artifacts.md) | 2026-07-29 | kernel, retrieval, entity-expansion, planner, knowledge-system, warm-artifacts, artifact-registry |
| `BM-006` | pending | [BM-006 - Baseline post-migracion contrato canonico](benchmarks/BM-006-baseline-post-canonical-migration.md) | 2026-08-03 | retrieval, planner, doc-cards, canonical-id, warm-artifacts, knowledge-builder |

## Patterns (2)

| ID | Status | Title | Updated | Components |
|----|--------|-------|---------|------------|
| `PAT-001` | accepted | [PAT-001 - Materialized View Pattern](patterns/PAT-001-materialized-view-pattern.md) | 2026-08-03 | knowledge-builder, warm-artifacts, doc-cards, entity-index, retrieval, planner |
| `PAT-002` | accepted | [PAT-002 - Canonical Identity Propagation](patterns/PAT-002-canonical-identity-propagation.md) | 2026-08-03 | chunker, vector-store, doc-cards, retrieval, knowledge-builder, canonical-id |

## Postmortems (1)

| ID | Status | Title | Updated | Components |
|----|--------|-------|---------|------------|
| `PM-001` | resolved | [PM-001 - Key mismatch entre Chroma y DocCards: retrieval boost silenciosament...](postmortems/PM-001-key-mismatch-chroma-doccards.md) | 2026-08-03 | retrieval, doc-cards, vector-store, planner, canonical-id |

## Research (13)

| ID | Status | Title | Updated | Components |
|----|--------|-------|---------|------------|
| `RES-001` | accepted | [RES-001 - El contrato Warm como centro arquitectonico](research/RES-001-knowledge-builder-consumer-split.md) | 2026-07-28 | contract, artifact-registry, warm-artifacts, cold-artifacts, hot-artifacts |
| `RES-002` | accepted | [RES-002 - Knowledge Builder (Knowledge Compiler)](research/RES-002-knowledge-builder-compiler.md) | 2026-07-28 | knowledge_builder, kir, entity_extractor, doc_cards, equivalences_manager, conceptual_map |
| `RES-003` | accepted | [RES-003 - Knowledge Consumer / evolucion del Agentic RAG runtime](research/RES-003-knowledge-consumer-llm-support.md) | 2026-07-28 | kernel, capabilities, rag_hybrid, planner, retrieval, verify, assess |
| `RES-004` | accepted | [RES-004 - LLMSupport: observador paralelo de hipotesis](research/RES-004-llmsupport-observador-paralelo.md) | 2026-07-28 | llm_support, trace_sink, model_provider, policy_engine, execution_state |
| `RES-005` | proposed | [RES-005 - Unified Ingestion Pipeline](research/RES-005-unified-ingestion-pipeline.md) | 2026-07-29 | ingest_incremental, knowledge_builder, vector_store, artifact_registry, hash_registry, kir_cache |
| `RES-006` | proposed | [RES-006 - Multimodal Ingestion: Knowledge Sources, Normalizers & Acquisition ...](research/RES-006-multimodal-ingestion.md) | 2026-07-29 | knowledge_builder, pdf_extractor, llm_entity_extractor, vector_store, kir_cache, acquisition_connectors, normalizers, canonical_document, cir |
| `RES-007` | accepted | [RES-007 — Estrategia de modelos LLM locales: Granite 3B vs 8B segun hardware ...](research/RES-007-llm-model-strategy-3b-vs-8b.md) |  | - |
| `RES-008` | draft | [RES-008 - Capability-Oriented Execution Model (Exploratory)](research/RES-008-capability-oriented-execution-model.md) | 2026-07-31 | policy-engine, capability-registry, execution-state, kernel, builder, consumer, artifact-registry |
| `RES-009` | proposed | [RES-009 - Erradicacion de modulos legacy de memoria y aprendizaje](research/RES-009-eradication-legacy-memory-modules.md) | 2026-08-03 | rag_hybrid, memory_system, learning_queue, conceptual_map, warm-artifacts, artifact-registry, knowledge-builder |
| `RES-010` | proposed | [RES-010 — Contrato canonico de documento](research/RES-010-canonical-document-contract.md) |  | - |
| `RES-011` | proposed | [RES-011 — Auditoría y evolución de la arquitectura Consumer basada en evidencia](research/RES-011-consumer-evidence-architecture.md) | 2026-08-06 | consumer, kernel, capabilities, retrieval, evidence, evidence-evaluation, evidence-selection, context-package, planner, reasoning, verify, warm-artifacts |
| `RES-012` | accepted | [RES-012 — Migración del benchmark histórico hacia evaluación canónica por evi...](research/RES-012-benchmark-migration-canonical-evaluation.md) | 2026-08-06 | evaluation, benchmark, legacy-rag, knowledge-builder, knowledge-consumer, retrieval, evidence, verify, corpus, warm-artifacts |
| `RES-013` | proposed | [RES-013 — Benchmark v3 como contrato autoritativo de evaluación para Agentic RAG](research/RES-013-benchmark-v3-authoritative-evaluation-contract.md) | 2026-08-06 | evaluation, benchmark, knowledge-builder, knowledge-consumer, retrieval, generation, policies, observability, facade |

## Cross-references

- **BM-001** -> ADR-0006, ADR-0017
- **BM-002** -> DEC-006, EXP-005, BM-001, ADR-0006, ADR-0013
- **BM-003** -> DEC-008, EXP-006b, BM-002, ADR-0006, ADR-0013
- **BM-004** -> BM-003, DEC-008, DEC-010, EXP-006b, ADR-0006, ADR-0018, RES-001, RES-002, RES-003
- **BM-005** -> BM-004, RES-001, RES-002, RES-003, ADR-0018
- **BM-006** -> ADR-0022, RES-010, BM-005, DEC-013, DEC-014
- **DEC-001** -> ADR-0017
- **DEC-003** -> ADR-0006, ADR-0013, ADR-0017, EXP-001, EXP-002, DEC-002
- **DEC-004** -> ADR-0006, ADR-0013, ADR-0017, EXP-001, EXP-002, EXP-003, DEC-003
- **DEC-005** -> ADR-0017, DEC-001, DEC-004, EXP-003
- **DEC-006** -> ADR-0006, ADR-0013, DEC-005
- **DEC-007** -> ADR-0009, ADR-0015, ADR-0014, DEC-006
- **DEC-008** -> ADR-0012, ADR-0013, DEC-006, DEC-007, BM-002
- **DEC-010** -> ADR-0020, DEC-009, BM-004
- **DEC-011** -> ADR-0018, RES-001, RES-002, RES-003
- **DEC-012** -> ADR-0018, RES-001, DEC-011
- **DEC-013** -> ADR-0022, RES-010, DEC-014
- **DEC-014** -> ADR-0022, RES-010, DEC-013
- **EXP-002** -> ADR-0006, ADR-0013, ADR-0017, EXP-001, DEC-002, DEC-003
- **EXP-003** -> ADR-0006, ADR-0013, ADR-0017, EXP-001, EXP-002, DEC-003, DEC-004
- **EXP-004** -> ADR-0017, DEC-005, DEC-001, DEC-004, EXP-003
- **EXP-005** -> DEC-006, ADR-0006, ADR-0013
- **EXP-006** -> DEC-007, ADR-0009, ADR-0015
- **EXP-006b** -> DEC-008, BM-002
- **EXP-007** -> RES-002, ADR-0018, DEC-011, BM-004
- **EXP-008** -> ADR-0022, RES-010, DEC-011
- **PAT-001** -> ADR-0022, RES-010, PAT-002
- **PAT-002** -> ADR-0022, RES-010, PAT-001, DEC-013
- **PM-001** -> ADR-0022, RES-010, DEC-013, BM-006
- **RES-001** -> RES-002, RES-003, RES-004, ADR-0009, ADR-0012, ADR-0013, ADR-0015, ADR-0017, ADR-0018, DEC-008, BM-002, BM-003, BM-004, EXP-006b
- **RES-002** -> RES-001, RES-003, RES-004, ADR-0015, ADR-0017, ADR-0018, DEC-008, BM-002, BM-003, BM-004
- **RES-003** -> RES-001, RES-002, RES-004, ADR-0005, ADR-0006, ADR-0009, ADR-0012, ADR-0013, ADR-0015, ADR-0016, ADR-0019, ADR-0020, DEC-008, BM-002, BM-003, BM-004
- **RES-004** -> RES-001, RES-002, RES-003, ADR-0005, ADR-0006, ADR-0007, ADR-0013, ADR-0014, ADR-0020, BM-004
- **RES-005** -> RES-002, RES-006, ADR-0021, ADR-0018, BM-005, BM-006
- **RES-006** -> RES-005, RES-002, ADR-0021, ADR-0018
- **RES-007** -> RES-002, RES-004, EXP-007, ADR-0007, ADR-0018, DEC-011
- **RES-008** -> ADR-0004, ADR-0009, ADR-0012, ADR-0013, ADR-0018, ADR-0019, ADR-0020, RES-001, RES-003, RES-004
- **RES-009** -> ADR-0018, ADR-0019, ADR-0020, RES-001, RES-002, RES-003, RES-008
- **RES-010** -> RES-001, RES-002, RES-003, RES-007, ADR-0018, ADR-0021, DEC-011
- **RES-011** -> RES-001, RES-003, RES-008, RES-010, ADR-0015, ADR-0018, ADR-0019, ADR-0020, ADR-0022, DEC-008, DEC-009, DEC-010, BM-005
- **RES-012** -> RES-001, RES-002, RES-003, RES-010, RES-011, RES-013, ADR-0006, ADR-0018, ADR-0019, ADR-0020, ADR-0022, DEC-009, BM-001, BM-005, BM-006
- **RES-013** -> RES-001, RES-002, RES-003, RES-011, RES-012, ADR-0006, ADR-0018, ADR-0019, ADR-0020, ADR-0022, DEC-009, BM-005
