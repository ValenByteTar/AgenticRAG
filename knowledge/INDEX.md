# EKS Index

Generado: 2026-07-27
Documentos indexados: 23

> Auto-generado por `scripts/generate_eks_index.py`. No editar a mano.

## Decisions (10)

| ID | Status | Title | Updated | Components |
|----|--------|-------|---------|------------|
| `DEC-001` | accepted | [DEC-001 - Renombrar centrales_map a domain_map](decisions/DEC-001-rename-centrales-map-to-domain-map.md) | 2026-07-22 | facade, capabilities |
| `DEC-002` | accepted | [DEC-002 - Cierre Fase 1: camino kernel lineal detras de flag](decisions/DEC-002-phase1-kernel-path-flag.md) | 2026-07-23 | kernel, control, capabilities, policies, facade, evaluation |
| `DEC-003` | accepted | [DEC-003 - Fase 2: ASSESS enriquecido con senales blandas](decisions/DEC-003-phase2-assess-enriched.md) | 2026-07-23 | evaluation, assess, policies, kernel |
| `DEC-004` | accepted | [DEC-004 - Fase 3: Multi-retry con two-stage entity retrieval](decisions/DEC-004-phase3-multi-retry-two-stage.md) | 2026-07-23 | policies, retrieval, kernel, two-stage |
| `DEC-005` | accepted | [DEC-005 - Limpieza dominio electrico, streaming kernel y EKS index](decisions/DEC-005-cleanup-streaming-eks-index.md) | 2026-07-23 | facade, generation, kernel, knowledge |
| `DEC-006` | accepted | [DEC-006 - VERIFY + REPAIR: groundedness post-generacion con presupuesto de reparacion](decisions/DEC-006-verify-repair-groundedness.md) | 2026-07-23 | verify, repair, groundedness, fase-4, evaluation |
| `DEC-007` | accepted | [DEC-007 - MemoryPortAdapter + KnowledgeSystemAdapter: contratos concretos Fase 5](decisions/DEC-007-memory-knowledge-adapters.md) | 2026-07-24 | memory, knowledge, adapters, fase-5 |
| `DEC-008` | accepted | [DEC-008 - Fase 6: Planner determinista + Entity Expansion + Tunings](decisions/DEC-008-planner-expansion-tunings.md) | 2026-07-24 | planner, entity-expansion, retrieval, tuning, fase-6 |
| `DEC-009` | accepted | [DEC-009 - Taxonomia de metricas en dos niveles: producto vs ingenieria](decisions/DEC-009-metricas-dos-niveles.md) | 2026-07-27 | evaluation, metrics, product-gates, engineering-metrics |
| `DEC-010` | accepted | [DEC-010 - Modo de entidades en retrieval: de filtro duro a boost acotado](decisions/DEC-010-modo-entidades-retrieval.md) | 2026-07-27 | retrieval, entity_filter, entity_mode, boost |

## Experiments (7)

| ID | Status | Title | Updated | Components |
|----|--------|-------|---------|------------|
| `EXP-001` | accepted | [EXP-001 - Paridad Kernel lineal vs HybridRAG.query](experiments/EXP-001-kernel-linear-parity-scaffold.md) | 2026-07-23 | kernel, control, capabilities, policies, facade, evaluation |
| `EXP-002` | accepted | [EXP-002 - ASSESS enriquecido: senales blandas + retry signal](experiments/EXP-002-assess-enriched.md) | 2026-07-23 | evaluation, assess, policies, kernel |
| `EXP-003` | accepted | [EXP-003 - Multi-retry con two-stage entity retrieval](experiments/EXP-003-multi-retry-two-stage.md) | 2026-07-23 | policies, retrieval, kernel, two-stage |
| `EXP-004` | accepted | [EXP-004 - Limpieza dominio electrico, streaming kernel y EKS index](experiments/EXP-004-cleanup-streaming-eks-index.md) | 2026-07-23 | facade, generation, kernel, knowledge |
| `EXP-005` | completed | [EXP-005 - VERIFY + REPAIR: experimento de groundedness post-generacion](experiments/EXP-005-verify-repair-groundedness.md) | 2026-07-23 | verify, repair, groundedness, fase-4, evaluation |
| `EXP-006` | completed | [EXP-006 - Fase 5: MemoryPortAdapter + KnowledgeSystemAdapter](experiments/EXP-006-memory-knowledge-adapters.md) | 2026-07-24 | memory, knowledge, adapters, fase-5, provenance |
| `EXP-006b` | completed | [EXP-006b - Fase 6: Planner + Entity Expansion + Tunings](experiments/EXP-006b-planner-expansion-tunings.md) | 2026-07-24 | planner, entity-expansion, retrieval, tuning, fase-6 |

## Benchmarks (3)

| ID | Status | Title | Updated | Components |
|----|--------|-------|---------|------------|
| `BM-001` | accepted | [BM-001 - Baseline pre-agentic Fase 0](benchmarks/BM-001-baseline-pre-agentic-phase0.md) | 2026-07-22 | evaluation, facade, retrieval, generation |
| `BM-002` | completed | [BM-002 - A/B Kernel+VERIFY vs Monolito — muestra estratificada 11q](benchmarks/BM-002-kernel-verify-vs-monolito.md) | 2026-07-23 | ab, kernel, verify, repair, monolito, fase-4 |
| `BM-003` | completed | [BM-003 - A/B Kernel Fase 6 vs Monolito — misma muestra 11q](benchmarks/BM-003-kernel-fase6-vs-monolito.md) | 2026-07-24 | ab, kernel, fase-6, planner, entity-expansion, monolito |

## Research (3)

| ID | Status | Title | Updated | Components |
|----|--------|-------|---------|------------|
| `RES-001` | accepted | [RES-001 - El contrato Warm como centro arquitectonico](research/RES-001-knowledge-builder-consumer-split.md) | 2026-07-27 | contract, artifact-registry, warm-artifacts, cold-artifacts, hot-artifacts |
| `RES-002` | draft | [RES-002 - Knowledge Builder (Knowledge Compiler)](research/RES-002-knowledge-builder-compiler.md) | 2026-07-27 | knowledge_builder, kir, entity_extractor, doc_cards, equivalences_manager, conceptual_map |
| `RES-003` | draft | [RES-003 - Knowledge Consumer / evolucion del Agentic RAG runtime](research/RES-003-knowledge-consumer-llm-support.md) | 2026-07-27 | kernel, capabilities, rag_hybrid, planner, retrieval, generation, verify, assess, llm_support, model_provider |

## Postmortems (0)

Sin documentos.

## Patterns (0)

Sin documentos.

## Cross-references

- **BM-001** -> ADR-0006, ADR-0017
- **BM-002** -> DEC-006, EXP-005, BM-001, ADR-0006, ADR-0013
- **BM-003** -> DEC-008, EXP-006b, BM-002, ADR-0006, ADR-0013
- **DEC-001** -> ADR-0017
- **DEC-002** -> ADR-0002, ADR-0003, ADR-0006, ADR-0009, ADR-0010, ADR-0013, ADR-0017, BM-001, EXP-001
- **DEC-003** -> ADR-0006, ADR-0013, ADR-0017, EXP-001, EXP-002, DEC-002
- **DEC-004** -> ADR-0006, ADR-0013, ADR-0017, EXP-001, EXP-002, EXP-003, DEC-003
- **DEC-005** -> ADR-0017, DEC-001, DEC-004, EXP-003
- **DEC-006** -> ADR-0006, ADR-0013, DEC-005
- **DEC-007** -> ADR-0009, ADR-0015, ADR-0014, DEC-006
- **DEC-008** -> ADR-0012, ADR-0013, DEC-006, DEC-007, BM-002
- **DEC-009** -> ADR-0006, ADR-0019, ADR-0020, BM-001, BM-002, BM-003
- **DEC-010** -> ADR-0020, DEC-009, BM-004
- **EXP-001** -> ADR-0002, ADR-0003, ADR-0006, ADR-0009, ADR-0010, ADR-0013, ADR-0017, BM-001, DEC-002
- **EXP-002** -> ADR-0006, ADR-0013, ADR-0017, EXP-001, DEC-002, DEC-003
- **EXP-003** -> ADR-0006, ADR-0013, ADR-0017, EXP-001, EXP-002, DEC-003, DEC-004
- **EXP-004** -> ADR-0017, DEC-005, DEC-001, DEC-004, EXP-003
- **EXP-005** -> DEC-006, ADR-0006, ADR-0013
- **EXP-006** -> DEC-007, ADR-0009, ADR-0015
- **EXP-006b** -> DEC-008, BM-002
- **RES-001** -> RES-002, RES-003, ADR-0009, ADR-0012, ADR-0013, ADR-0015, ADR-0017, ADR-0018, DEC-008, BM-002, BM-003, EXP-006b
- **RES-002** -> RES-001, RES-003, ADR-0015, ADR-0017, ADR-0018, DEC-008, BM-002, BM-003, BM-004
- **RES-003** -> RES-001, RES-002, ADR-0005, ADR-0006, ADR-0009, ADR-0012, ADR-0013, ADR-0015, ADR-0016, ADR-0019, ADR-0020, DEC-008, BM-002, BM-003, BM-004

> **Nota:** BM-004 es referenciado en DEC-010, RES-002 y RES-003 pero no existe como archivo en `benchmarks/`. Es un benchmark pendiente de publicacion.
