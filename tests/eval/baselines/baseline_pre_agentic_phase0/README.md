# Baseline pre-agentic (Fase 0)

**ID:** `baseline_pre_agentic_phase0`  
**ADR:** 0006 (Evaluation suite v1)  
**kernel.enabled:** `false`

## Proposito

Congelar el comportamiento del HybridRAG lineal **antes** de migrar `query()` al Controller (Fase 1).

Cualquier cambio agentico debe compararse contra este baseline.

## Artefactos

| Archivo | Descripcion |
|---------|-------------|
| `MANIFEST.json` | Metadatos, gates de aceptacion, metricas |
| `report.json` | Reporte crudo del harness |
| `report.md` | Resumen legible |

## Metricas clave (subset 25 q)

| Metrica | Valor |
|---------|-------|
| Overall pass | 64.0% |
| Retrieval success | 80.0% |
| Doc hit@K | 78.3% |
| Page hit@K | 43.5% |
| Groundedness | 96.0% |
| Anti-alucinacion | 0.0% |
| MRR | 0.528 |
| Latency avg | 61341 ms |

## Como regenerar

```bash
python tests/eval/run_cybersec_eval.py
# copiar report_* mas reciente aqui y actualizar MANIFEST.json
```

## Nota

Baseline tomado de `report_20260712_191655` (25 preguntas).
Para suite completa (75), re-ejecutar el harness sin `--limit` cuando LLM/indice esten listos.
