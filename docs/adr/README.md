# Architecture Decision Records (ADR)

ADRs atomicos e inmutables. No se editan una vez aceptados; se superseden con un nuevo ADR.

Formato: `ADR-XXXX-titulo-kebab.md`

Estados: `Propuesto` | `Aceptado` | `Superseded-by-XXXX`

## Indice

| ADR | Titulo | Estado |
|-----|--------|--------|
| [0000](ADR-0000-proceso-y-formato.md) | Proceso y formato de ADR | Aceptado |
| [0001](ADR-0001-modelo-de-planos.md) | Modelo de planos: 3 verticales + 3 transversales | Propuesto |
| [0002](ADR-0002-contrato-controller.md) | Contrato de Controller: solo ejecuta acciones decididas | Propuesto |
| [0003](ADR-0003-fsm-primera-implementacion.md) | FSM como primera implementacion del Controller | Propuesto |
| [0004](ADR-0004-execution-state.md) | ExecutionState explicito y serializable | Propuesto |
| [0005](ADR-0005-observability-transversal.md) | Observability como substrato transversal | Propuesto |
| [0006](ADR-0006-evaluation-transversal.md) | Evaluation transversal: offline + online | Propuesto |
| [0007](ADR-0007-model-provider.md) | ModelProvider | Propuesto |
| [0008](ADR-0008-knowledge-store-vs-retrieval.md) | KnowledgeStore vs RetrievalPipeline | Superseded-by-0015 |
| [0009](ADR-0009-memory-y-tool.md) | Contratos de Memory y Tool | Propuesto |
| [0010](ADR-0010-fachada-consulta-estable.md) | Fachada de consulta estable y versionada | Propuesto |
| [0011](ADR-0011-local-first.md) | Local-first como invariante | Aceptado |
| [0012](ADR-0012-capability-registry.md) | Capability Registry | Propuesto |
| [0013](ADR-0013-policy-engine.md) | Policy Engine (policies de primera clase) | Propuesto |
| [0014](ADR-0014-inyeccion-dependencias.md) | Inyeccion de dependencias y Composition Root | Propuesto |
| [0015](ADR-0015-knowledge-system.md) | Knowledge System (subsistema, no store) | Propuesto |
| [0016](ADR-0016-definicion-kernel.md) | Definicion del Kernel | Propuesto |
| [0017](ADR-0017-engineering-knowledge-system.md) | Engineering Knowledge System (EKS) dev-time | Aceptado |

## Decisiones diferidas (a proposito)

- Planner (refactor cuando haya 2+ estrategias)
- Esquema interno del Knowledge System
- Taxonomia de memoria y politica de aprendizaje
- Segunda implementacion del Controller (grafo/hibrido)
- Multi-agente
- Knowledge Index generado / Knowledge Curator (disparo: ~30-40 docs en `knowledge/`)

## Relacion con EKS

Los ADRs viven **solo** aqui (`docs/adr/`). El EKS vive en `knowledge/` (experiencia de ingenieria). No hay `knowledge/adr/`. Ver ADR-0017 y `knowledge/README.md`.

