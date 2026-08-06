# Fase 0 — Exit criteria

Estado: **CERRADA** (fundaciones listas para Fase 1).

## Cumplido

| Criterio | Evidencia |
|----------|-----------|
| Kernel con contratos estables | `src/kernel/` |
| Registry / PolicyEngine / Controller / CompositionRoot | ADR-0012/0013/0002/0014 |
| ModelProvider + modelo desde config | `src/providers/`, `config.yaml` `llm.*` |
| Policies y capabilities fuera del Kernel | `src/policies/`, `src/capabilities/` |
| Factory de wiring | `src/bootstrap.py` |
| Observability substrate | `TraceSink`, trazas en `ExecutionState` |
| `rebuild_on_build: false` | `config.yaml` |
| `kernel.enabled: false` (query lineal) | `config.yaml` |
| Fachada `query()` sin cambio de contrato | ADR-0010 |
| Camino experimental A/B | `HybridRAG.query_via_kernel()` |
| Tests unitarios | 13 passed |
| Baseline pre-agentic | `tests/eval/baselines/baseline_pre_agentic_phase0/` |
| Docs canonicos + ADRs 0000–0016 | `docs/` |

## Diferido (no bloquea Fase 1)

- Limpieza profunda de heuristicas/prompts del dominio electrico residual en `rag_hybrid.py` (WTG, centrales en prompts, etc.).
- Re-ejecucion del harness completo (75 preguntas) para baseline full-suite.

## Gates de entrada a Fase 1

1. Comparar metricas contra `baseline_pre_agentic_phase0`.
2. No alterar la forma del dict de retorno de `query()` sin bump de version.
3. Migracion detras de flag; default sigue siendo camino lineal hasta paridad demostrada.
4. Capabilities se agregan por registro, no tocando el Controller.

## Comando de regresion rapida

```bash
python -m pytest tests/unit/test_kernel_phase0.py tests/unit/test_capabilities_bootstrap.py -q
```
