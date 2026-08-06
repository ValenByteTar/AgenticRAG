---
id: BM-006
category: benchmark
status: pending
created: 2026-08-03
updated: 2026-08-03
author: human
components: [retrieval, planner, doc-cards, canonical-id, warm-artifacts, knowledge-builder]
tags: [baseline, post-migration, canonical-contract, retrieval-boost]
related: [ADR-0022, RES-010, BM-005, DEC-013, DEC-014]
supersedes: null
superseded_by: null
---

# BM-006 - Baseline post-migracion contrato canonico

## Goal

Establecer el baseline de retrieval despues de la migracion al contrato canonico
(ADR-0022). Comparar contra BM-005 (pre-migracion) para medir el impacto de:

1. `canonical_doc_id` como key unica (fin del key mismatch).
2. Roles v2 alineados en planner, retrieval y doc_cards.
3. Retrieval boost funcional (ahora matchea `canonical_doc_id`).
4. DocCards desacoplado de Chroma.
5. Attributes preservados en warm artifacts.

## Environment

- Commit / tag: post-Fase 0B + Fase 3 (HEAD al momento de este benchmark)
- `kernel.enabled`: true
- Modelo LLM: segun config.yaml (ibm/granite4.1:3b-q6_K)
- Coleccion / indice: chroma_bge_m3 / crom_protocols_bge_m3
- Hardware: local (Ollama)

## Dataset

Suite de preguntas estandar (misma que BM-005 para comparacion directa).
Path: `scripts/tests/test_reasoning_exhaustive.py` o suite equivalente.

## Metrics

| Metrica | Definicion |
|---------|-----------|
| `boost_hit_rate` | % de queries donde al menos un resultado boosted aparece en top-K |
| `candidate_match_rate` | % de `candidate_docs` que matchean `canonical_doc_id` en Chroma |
| `role_alignment_rate` | % de docs donde el rol en DocCards == rol en Warm Artifacts |
| `attribute_preservation_rate` | % de docs donde attributes en KIR == attributes en artifact |
| `retrieval_precision@5` | % de queries con >=1 resultado relevante en top-5 |
| `retrieval_recall@10` | % de queries con >=1 resultado relevante en top-10 |
| `latency_p50` | Latencia mediana de retrieval (ms) |

## Results

Pendiente hasta ejecutar Fase 5 (run limpio del Builder sobre corpus depurado).

| Metrica | BM-005 (pre) | BM-006 (post) | Delta |
|---------|-------------|--------------|-------|
| `boost_hit_rate` | ~0% (key mismatch) | TBD | TBD |
| `candidate_match_rate` | ~0% | TBD | TBD |
| `role_alignment_rate` | ~0% (roles divergentes) | TBD | TBD |
| `attribute_preservation_rate` | 0% (se perdian) | TBD | TBD |
| `retrieval_precision@5` | baseline BM-005 | TBD | TBD |
| `retrieval_recall@10` | baseline BM-005 | TBD | TBD |
| `latency_p50` | baseline BM-005 | TBD | TBD |

Artefactos: path a reportes crudos cuando se ejecuten.
