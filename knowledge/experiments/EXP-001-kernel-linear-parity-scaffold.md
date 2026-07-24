---
id: EXP-001
category: experiment
status: accepted
created: 2026-07-22
updated: 2026-07-23
author: cascade
components: [kernel, control, capabilities, policies, facade, evaluation]
tags: [kernel, phase1, parity, query_via_kernel, linear-rag, assess, close]
related: [ADR-0002, ADR-0003, ADR-0006, ADR-0009, ADR-0010, ADR-0013, ADR-0017, BM-001, DEC-002]
supersedes: null
superseded_by: null
---

# EXP-001 - Paridad Kernel lineal vs HybridRAG.query

## Hypothesis

Si se ejecuta el camino kernel (`query()` con `kernel.enabled=true` / `--kernel`) con la cadena F1.c, las metricas de retrieval (doc_hit, page_hit, MRR) y groundedness no regresan respecto a BM-001 en el subset de 25q.

## Motivation

Fase 1 cableo fachada + Controller. Antes de `kernel.enabled=true` por default hace falta A/B medible vs BM-001.

## Configuration

- Scaffold unitario: 24 tests kernel/phase1 green (incl. `test_phase1_close_gates.py`)
- Default config: `kernel.enabled=false`, `max_iterations=12`
- Path kernel F1.c: classify -> memory_read -> retrieve(+sticky+rerank) -> build_context(+mem) -> assess -> generate -> finalize_turn
- Policies: `AssessGatePolicy` + `LinearRagPolicy`
- Memory: read-only (`MemorySystem.search_memory`); write no migrado
- Harness: `python tests/eval/run_cybersec_eval.py --kernel --limit 25`
- Baseline: `tests/eval/baselines/baseline_pre_agentic_phase0/` (BM-001)
- Modelo: `config.yaml` `llm.model_name`

## Metrics

- doc_hit@K, page_hit@K, MRR, groundedness, anti-alucinacion vs BM-001
- Diff absoluto (umbral: no bajar)
- Latencia p50 (informativa)
- method == `kernel_linear` en respuestas kernel

## Results

### A. Scaffold / cierre de codigo (2026-07-23)

| Check | Resultado |
|-------|-----------|
| Cadena policy F1.c completa | PASS |
| Contrato fachada ADR-0010 en retorno kernel | PASS |
| Despacho `kernel.enabled` true/false | PASS |
| Memory hits inyectados + sticky finalize | PASS |
| OOD decline sin retrieval | PASS |
| Assess fail -> decline sin generate | PASS |
| Suite unit kernel | **24 passed** |

### B. A/B offline vs BM-001 (suite eval)

**No ejecutado en este entorno de cierre.**

Bloqueantes observados al intentar smoke HybridRAG:

- `ModuleNotFoundError: No module named 'rank_bm25'`
- Requiere indice Chroma `cybersec_docs_bge_m3` + Ollama `mistral:7b`

Protocolo listo:

```bash
# baseline path (default)
python tests/eval/run_cybersec_eval.py --limit 25

# kernel path
python tests/eval/run_cybersec_eval.py --kernel --limit 25
```

Comparar contra `MANIFEST.json` metrics_from_md / report del baseline.

## Conclusion

**Codigo Fase 1 cerrado** detras de flag con paridad estructural y contrato estable.

**Paridad de calidad vs BM-001** queda como corrida operativa pendiente (mismo EXP, seccion B) cuando el entorno tenga deps+indice+LLM. Hasta entonces `kernel.enabled` default permanece **false** (DEC-002).

## Recommendation

Should this become:

- [x] Experiment (cerrado en scaffold; seccion B abierta)
- [ ] Benchmark (si seccion B pasa: BM-002 kernel_linear_phase1)
- [ ] ADR (no: no cambia frontera; DEC-002 basta)
- [x] Decision (DEC-002)
- [ ] Nothing
