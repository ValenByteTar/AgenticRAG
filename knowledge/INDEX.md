# EKS Index

Generado: 2026-07-24
Documentos indexados: 17

> Auto-generado por `scripts/generate_eks_index.py`. No editar a mano.

## Decisions (4)

| ID | Status | Title | Updated | Components |
|----|--------|-------|---------|------------|
| `DEC-001` | accepted | [DEC-001 - Renombrar centrales_map a domain_map](decisions/DEC-001-rename-centrales-map-to-domain-map.md) | 2026-07-22 | facade, capabilities |
| `DEC-003` | accepted | [DEC-003 - Fase 2: ASSESS enriquecido con senales blandas](decisions/DEC-003-phase2-assess-enriched.md) | 2026-07-23 | evaluation, assess, policies, kernel |
| `DEC-004` | accepted | [DEC-004 - Fase 3: Multi-retry con two-stage entity retrieval](decisions/DEC-004-phase3-multi-retry-two-stage.md) | 2026-07-23 | policies, retrieval, kernel, two-stage |
| `DEC-005` | accepted | [DEC-005 - Limpieza dominio electrico, streaming kernel y EKS index](decisions/DEC-005-cleanup-streaming-eks-index.md) | 2026-07-23 | facade, generation, kernel, knowledge |

## Experiments (3)

| ID | Status | Title | Updated | Components |
|----|--------|-------|---------|------------|
| `EXP-002` | accepted | [EXP-002 - ASSESS enriquecido: senales blandas + retry signal](experiments/EXP-002-assess-enriched.md) | 2026-07-23 | evaluation, assess, policies, kernel |
| `EXP-003` | accepted | [EXP-003 - Multi-retry con two-stage entity retrieval](experiments/EXP-003-multi-retry-two-stage.md) | 2026-07-23 | policies, retrieval, kernel, two-stage |
| `EXP-004` | accepted | [EXP-004 - Limpieza dominio electrico, streaming kernel y EKS index](experiments/EXP-004-cleanup-streaming-eks-index.md) | 2026-07-23 | facade, generation, kernel, knowledge |

## Benchmarks (1)

| ID | Status | Title | Updated | Components |
|----|--------|-------|---------|------------|
| `BM-001` | accepted | [BM-001 - Baseline pre-agentic Fase 0](benchmarks/BM-001-baseline-pre-agentic-phase0.md) | 2026-07-22 | evaluation, facade, retrieval, generation |

## Research (1)

| ID | Status | Title | Updated | Components |
|----|--------|-------|---------|------------|
| `RES-001` | draft | [RES-001 - Knowledge Builder / Knowledge Consumer split](research/RES-001-knowledge-builder-consumer-split.md) | 2026-07-24 | rag_hybrid, entity_extractor, doc_cards, equivalences_manager, conceptual_map, kernel, capabilities |

## Cross-references

- **BM-001** -> ADR-0006, ADR-0017
- **BM-002** -> DEC-006, EXP-005, BM-001, ADR-0006, ADR-0013
- **BM-003** -> DEC-008, EXP-006b, BM-002, ADR-0006, ADR-0013
- **DEC-001** -> ADR-0017
- **DEC-003** -> ADR-0006, ADR-0013, ADR-0017, EXP-001, EXP-002, DEC-002
- **DEC-004** -> ADR-0006, ADR-0013, ADR-0017, EXP-001, EXP-002, EXP-003, DEC-003
- **DEC-005** -> ADR-0017, DEC-001, DEC-004, EXP-003
- **DEC-006** -> ADR-0006, ADR-0013, DEC-005
- **DEC-007** -> ADR-0009, ADR-0015, ADR-0014, DEC-006
- **DEC-008** -> ADR-0012, ADR-0013, DEC-006, DEC-007, BM-002
- **EXP-002** -> ADR-0006, ADR-0013, ADR-0017, EXP-001, DEC-002, DEC-003
- **EXP-003** -> ADR-0006, ADR-0013, ADR-0017, EXP-001, EXP-002, DEC-003, DEC-004
- **EXP-004** -> ADR-0017, DEC-005, DEC-001, DEC-004, EXP-003
- **EXP-005** -> DEC-006, ADR-0006, ADR-0013
- **EXP-006** -> DEC-007, ADR-0009, ADR-0015
- **EXP-006b** -> DEC-008, BM-002
- **RES-001** -> ADR-0009, ADR-0012, ADR-0013, ADR-0015, ADR-0017, DEC-008, BM-002, BM-003, EXP-006b
