"""One-shot helper: freeze baseline_pre_agentic_phase0 from latest report."""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_JSON = ROOT / "reports" / "report_20260712_191655.json"
SRC_MD = ROOT / "reports" / "report_20260712_191655.md"
BASE_DIR = Path(__file__).resolve().parent / "baseline_pre_agentic_phase0"


def main() -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    data = json.loads(SRC_JSON.read_text(encoding="utf-8"))
    analysis = data.get("analysis") or {}
    results = data.get("results") or []

    shutil.copy2(SRC_JSON, BASE_DIR / "report.json")
    if SRC_MD.exists():
        shutil.copy2(SRC_MD, BASE_DIR / "report.md")

    digest = hashlib.sha256((BASE_DIR / "report.json").read_bytes()).hexdigest()

    n_pass = sum(
        1
        for r in results
        if r.get("pass") is True or r.get("passed") is True or r.get("overall_pass") is True
    )
    n_fail = sum(
        1
        for r in results
        if r.get("pass") is False or r.get("passed") is False or r.get("overall_pass") is False
    )

    manifest = {
        "id": "baseline_pre_agentic_phase0",
        "label": "InfraPolus Fase 0 — baseline pre-agentic (ADR-0006 suite v1)",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "0",
        "kernel_enabled": False,
        "purpose": (
            "Congelar metricas del HybridRAG lineal ANTES de migrar query() al Controller (Fase 1). "
            "Toda version agentica se compara contra este baseline: no-regresion en doc_hit, page_hit, "
            "groundedness y anti-alucinacion."
        ),
        "source": {
            "report_json": "tests/eval/reports/report_20260712_191655.json",
            "report_md": "tests/eval/reports/report_20260712_191655.md",
            "sha256_report_json": digest,
        },
        "config_snapshot": {
            "llm.model_name": "mistral:7b",
            "kernel.enabled": False,
            "vectordb.rebuild_on_build": False,
            "vectordb.collection_name": "cybersec_docs_bge_m3",
            "retrieval.semantic_weight": 0.6,
        },
        "metrics_from_md": {
            "n_questions": 25,
            "pass_rate_overall": 0.64,
            "pass_rate_answerable": 0.696,
            "retrieval_success": 0.80,
            "groundedness": 0.96,
            "generation_kw": 0.80,
            "anti_hallucination": 0.0,
            "doc_hit_at_k": 0.783,
            "page_hit_at_k": 0.435,
            "recall_avg_multidoc": 0.551,
            "mrr_avg": 0.528,
            "precision_at_k_avg": 0.300,
            "keyword_score_avg": 0.488,
            "latency_avg_ms": 61341,
            "latency_p50_ms": 54714,
            "latency_p95_ms": 122248,
            "note": (
                "Subset de 25 preguntas del dataset (no suite completa 75). "
                "Usar como referencia relativa; re-correr full suite al cerrar Fase 1."
            ),
        },
        "acceptance_gates_for_phase1": {
            "no_regression_doc_hit": True,
            "no_regression_page_hit": True,
            "no_regression_groundedness": True,
            "no_regression_anti_hallucination": True,
            "query_facade_unchanged": True,
            "kernel_enabled_default_false": True,
        },
        "summary_extracted": {
            "source_timestamp": data.get("timestamp"),
            "elapsed_s": data.get("elapsed_s"),
            "n_results": len(results),
            "results_pass_true": n_pass,
            "results_pass_false": n_fail,
            "analysis_keys": sorted(analysis.keys()) if isinstance(analysis, dict) else None,
            "analysis": analysis if isinstance(analysis, dict) else None,
        },
    }

    (BASE_DIR / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    readme = """# Baseline pre-agentic (Fase 0)

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
"""
    (BASE_DIR / "README.md").write_text(readme, encoding="utf-8")
    print(f"baseline -> {BASE_DIR}")
    print(f"sha256={digest[:16]}... n_results={len(results)}")


if __name__ == "__main__":
    main()
