# Documentacion InfraPolus

Fuente de verdad arquitectonica del proyecto.

## Documentos canonicos

| Documento | Rol | Estabilidad |
|-----------|-----|-------------|
| [philosophy.md](philosophy.md) | Porques / prioridades | Muy alta |
| [vision.md](vision.md) | Que es InfraPolus, Kernel, planos, cadena runtime | Muy alta |
| [principles.md](principles.md) | Principios inviolables (P1-P15) | Muy alta |
| [adr/](adr/) | Decisiones atomicas e inmutables | Inmutable (se supersede) |
| [roadmap.md](roadmap.md) | Fases de implementacion | Baja (cambia por ciclo) |
| [plan-orquestacion-knowledge.md](plan-orquestacion-knowledge.md) | Ejecucion de Fase 7-8 (Builder/Consumer) | Baja (cambia por etapa) |
| [phase0-exit.md](phase0-exit.md) | Exit criteria Fase 0 | Historico |

## Engineering Knowledge System (dev-time)

Memoria de ingenieria (no runtime). Ver [ADR-0017](adr/ADR-0017-engineering-knowledge-system.md) y [`../knowledge/README.md`](../knowledge/README.md).

| Path | Rol |
|------|-----|
| `knowledge/` | Experiencia: DEC, EXP, BM, PM, PAT, RES |
| `knowledge/skills/` | Context Builder, Experiment Logging, ADR Proposal |
| `docs/adr/` | **Unica** casa de ADRs (no hay `knowledge/adr/`) |

## Codigo del Kernel (Fase 0)

```
src/kernel/          # contratos + runtime (ADR-0016)
src/providers/       # ModelProvider concretos (Ollama)
src/policies/        # Policies concretas (fuera del Kernel)
src/capabilities/    # Capabilities concretas (retrieval, context, generation)
src/bootstrap.py     # Composition factory (ADR-0014)
```

Cadena de runtime:

> Evaluation produce senales -> Policy interpreta -> Controller ejecuta -> Registry resuelve -> Capability trabaja

## Configuracion relevante

- `config.yaml` -> `llm.*` (modelo, no hardcodear)
- `config.yaml` -> `kernel.enabled` (false = camino lineal HybridRAG.query)
- `config.yaml` -> `vectordb.rebuild_on_build` (default false)

## Hybrid RAG actual (capacidad Ola 1)

| Modulo | Responsabilidad |
|--------|----------------|
| `rag_hybrid.py` | Fachada legacy + `query_via_kernel()` experimental |
| `retrieval_engine.py` | Busqueda hibrida + reranking |
| `context_builder.py` | Contexto y prompts |
| `answer_postprocessor.py` | Postprocesado |
| `query_classifier.py` | Clasificacion de intencion |
| `ollama_manager.py` | Ciclo de vida Ollama |
| `src/providers/ollama_provider.py` | ModelProvider (ADR-0007) |
| `src/bootstrap.py` | Wiring Kernel desde RAG |

## Tests

```bash
python -m pytest tests/unit/test_kernel_phase0.py tests/unit/test_capabilities_bootstrap.py -q
```
