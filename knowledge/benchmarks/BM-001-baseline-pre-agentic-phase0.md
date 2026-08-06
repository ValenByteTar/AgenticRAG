---
id: BM-001
category: benchmark
status: accepted
created: 2026-07-22
updated: 2026-07-22
author: cascade
components: [evaluation, facade, retrieval, generation]
tags: [baseline, phase0, cybersec, no-regression, pre-agentic]
related: [ADR-0006, ADR-0017]
supersedes: null
superseded_by: null
---

# BM-001 - Baseline pre-agentic Fase 0

## Goal

Congelar metricas del HybridRAG lineal **antes** de migrar `query()` al Controller (Fase 1). Toda version agentica se compara contra este baseline (no-regresion).

## Environment

- Source report: `tests/eval/reports/report_20260712_191655`
- `kernel.enabled`: false
- Modelo LLM: mistral:7b
- Coleccion: `cybersec_docs_bge_m3`
- `vectordb.rebuild_on_build`: false
- `retrieval.semantic_weight`: 0.6

## Dataset

Subset de **25 preguntas** del harness `tests/eval/run_cybersec_eval.py` (no suite completa 75). Artefactos en:

`tests/eval/baselines/baseline_pre_agentic_phase0/`

## Metrics

| Metrica | Definicion breve |
|---------|------------------|
| Overall pass | % preguntas aprobadas |
| Retrieval success | Capa retrieval OK |
| Doc hit@K | Doc esperado en top-K fuentes |
| Page hit@K | Pagina dentro de tolerancia |
| Groundedness | Sin forbidden / citas coherentes |
| Anti-alucinacion | Decline correcto en no_answer |
| MRR | Mean reciprocal rank |
| Latency avg | ms promedio por query |

## Results

| Metrica | Valor |
|---------|-------|
| n_questions | 25 |
| Overall pass | 64.0% |
| Pass answerable | 69.6% |
| Retrieval success | 80.0% |
| Doc hit@K | 78.3% |
| Page hit@K | 43.5% |
| Groundedness | 96.0% |
| Generation kw | 80.0% |
| Anti-alucinacion | 0.0% |
| Recall avg multi-doc | 0.551 |
| MRR avg | 0.528 |
| Precision@K avg | 0.300 |
| Keyword score avg | 0.488 |
| Latency avg | 61341 ms |
| Latency p50 | 54714 ms |
| Latency p95 | 122248 ms |

Ver `MANIFEST.json` y `report.md` en el directorio de baseline para gates de aceptacion Fase 1.
