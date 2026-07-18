"""
FASE P.1 - Diagnostico per-query de misses de prerank.

Para cada uno de los 12 misses, ejecuta hybrid_search directamente (sin two-stage,
sin planner) con pool=75 y reporta:
  - Rank del doc correcto en el pool
  - Score hibrido del doc correcto vs top-1
  - Si el doc correcto esta fuera del pool (rank > 75)
  - Clasificacion: miss por pool insuficiente vs miss por score bajo vs ambiguedad real

Uso:
    python tests/eval/diagnose_prerank_misses.py
"""

import json
import sys
import os
import time
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ROOT_SRC = Path(__file__).parent.parent.parent
if str(ROOT_SRC) not in sys.path:
    sys.path.insert(0, str(ROOT_SRC))
if str(ROOT_SRC / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_SRC / "src"))

os.environ.setdefault('PYTHONHASHSEED', '0')
os.environ.setdefault('CE_MINIMAL_ENABLED', '0')

from tests.eval.run_cybersec_eval import load_questions, _src_matches

QUESTIONS_FILE = Path(__file__).parent / "cybersec_eval_questions.json"

MISS_IDS = [11, 29, 41, 42, 43, 44, 46, 47, 50, 58, 64, 68]

DIAG_POOL = 75
SEM_WEIGHT = 0.6


def run_diagnosis():
    data = load_questions(str(QUESTIONS_FILE))
    questions = data.get("questions", data) if isinstance(data, dict) else data
    q_by_id = {q["id"]: q for q in questions}

    print(f"Diagnostico de misses de prerank (pool={DIAG_POOL}, sw={SEM_WEIGHT})")
    print(f"IDs a diagnosticar: {MISS_IDS}")
    print("=" * 100)

    from rag_hybrid import HybridRAG
    print("Inicializando HybridRAG (modo retrieval-only)...")
    rag = HybridRAG(variant="bge", heuristics="balanced", use_llm=False)
    print(f"OK: RAG listo ({len(rag.all_docs)} documentos)\n")

    results = []

    for qid in MISS_IDS:
        q = q_by_id.get(qid)
        if not q:
            print(f"[{qid}] ID no encontrada en questions.json")
            continue

        query = q["query"]
        expected_sources = q.get("expected_sources", [])
        is_answerable = q.get("is_answerable", True)

        print(f"\n[{qid}] {query[:80]}...")
        print(f"  Expected sources: {expected_sources}")

        t0 = time.time()
        raw = rag.hybrid_search(
            query,
            top_k=DIAG_POOL,
            semantic_weight=SEM_WEIGHT,
        )
        latency = time.time() - t0

        found_rank = None
        found_source = None
        found_score = None

        seen = set()
        for rank, doc in enumerate(raw[:DIAG_POOL], 1):
            meta = doc.get("metadata", {}) or {}
            source = meta.get("source", "")
            key = source.lower()
            if key in seen:
                continue
            seen.add(key)

            for exp in expected_sources:
                if _src_matches(source, exp):
                    found_rank = rank
                    found_source = source
                    found_score = doc.get("hybrid_score", 0.0)
                    break
            if found_rank:
                break

        top1_source = ""
        top1_score = 0.0
        if raw:
            top1_meta = raw[0].get("metadata", {}) or {}
            top1_source = top1_meta.get("source", "")
            top1_score = raw[0].get("hybrid_score", 0.0)

        if found_rank is not None:
            classification = "EN_POOL"
            if found_rank <= 10:
                classification = "EN_TOP10 (deberia ser hit)"
            elif found_rank <= 35:
                classification = "EN_POOL_35 (pool actual insuficiente)"
            else:
                classification = "EN_POOL_75 (necesita pool >= 75)"
        else:
            classification = "FUERA_DEL_POOL (no recuperable con pool=75)"

        print(f"  Top-1: {top1_source} (score={top1_score:.4f})")
        if found_rank is not None:
            print(f"  Doc esperado: rank={found_rank}, source={found_source}, score={found_score:.4f}")
        else:
            print(f"  Doc esperado: NO ENCONTRADO en top-{DIAG_POOL}")
        print(f"  Clasificacion: {classification}")
        print(f"  Latencia: {latency:.1f}s")

        results.append({
            "id": qid,
            "query": query[:80],
            "expected_sources": expected_sources,
            "top1_source": top1_source,
            "top1_score": round(top1_score, 4),
            "expected_rank": found_rank,
            "expected_source_found": found_source,
            "expected_score": round(found_score, 4) if found_score else None,
            "classification": classification,
            "latency_s": round(latency, 1),
        })

    print("\n" + "=" * 100)
    print("RESUMEN:")
    print(f"{'ID':>4} {'Rank':>6} {'Clasificacion':<40} {'Top-1':<50} {'Esperado':<50}")
    print("-" * 150)
    for r in results:
        rank_str = str(r["expected_rank"]) if r["expected_rank"] else "N/A"
        print(f"{r['id']:>4} {rank_str:>6} {r['classification']:<40} {r['top1_source'][:48]:<50} {r['expected_sources'][0][:48] if r['expected_sources'] else 'N/A':<50}")

    report_path = Path(__file__).parent / "reports" / "prerank_misses_diagnosis.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nReporte guardado: {report_path}")


if __name__ == "__main__":
    run_diagnosis()
