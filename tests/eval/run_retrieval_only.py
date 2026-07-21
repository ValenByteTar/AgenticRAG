"""
FASE C.RETR: Harness de evaluacion retrieval-only.

Evalua SOLO la capa de recuperacion (hybrid_search + reranker) sin llamar al LLM.
Esto permite iterar en tuning de semantic_weight, candidate_pool, etc. en segundos
en lugar de ~60 minutos.

Reutiliza validate_retrieval y _src_matches del eval completo.

Uso:
    python tests/eval/run_retrieval_only.py
    python tests/eval/run_retrieval_only.py --semantic-weight 0.5
    python tests/eval/run_retrieval_only.py --ids 1,5,21
    python tests/eval/run_retrieval_only.py --limit 10
    python tests/eval/run_retrieval_only.py --top-k 10
"""

import json
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path

# FASE C.CHARMAP: Forzar UTF-8 en stdout/stderr
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ROOT_SRC = Path(__file__).parent.parent.parent
if str(ROOT_SRC) not in sys.path:
    sys.path.insert(0, str(ROOT_SRC))
if str(ROOT_SRC / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_SRC / "src"))

# Reutilizar funciones del eval completo
from tests.eval.run_cybersec_eval import (
    load_questions,
    validate_retrieval,
    _src_matches,
    _get_semantic_weight,
)

QUESTIONS_FILE = Path(__file__).parent / "cybersec_eval_questions.json"
REPORTS_DIR = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def query_retrieval_only(question: str, top_k: int, semantic_weight: float) -> dict:
    """Llama HybridRAG.query con use_llm=False. Solo retrieval + reranker."""
    from rag_hybrid import HybridRAG
    if not hasattr(query_retrieval_only, "_rag"):
        print("Inicializando HybridRAG (modo retrieval-only, sin LLM)...")
        query_retrieval_only._rag = HybridRAG(
            variant="bge", heuristics="balanced", use_llm=False
        )
        print(f"OK: RAG listo ({len(query_retrieval_only._rag.all_docs)} documentos)\n")
    rag = query_retrieval_only._rag

    t0 = time.time()
    result = rag.query(
        question,
        top_k=top_k,
        semantic_weight=semantic_weight,
        use_llm=False,
        entity_filter=True,
        two_stage=True,
        stream=False,
        return_prerank=True,
    )
    latency_ms = round((time.time() - t0) * 1000)

    raw_results = result.get("results") or []
    prerank_results = result.get("prerank_results") or []
    sources = []
    seen = set()
    for r in raw_results[:top_k]:
        meta = r.get("metadata", {})
        name = meta.get("source", "")
        page = meta.get("page", 0)
        score = r.get("final_score", r.get("hybrid_score", 0.0))
        key = (name, page)
        if key not in seen:
            seen.add(key)
            sources.append({"name": name, "page": page, "score": round(score, 4)})

    def _to_sources(raw: list, k: int) -> list:
        out = []
        seen = set()
        for r in raw[:k]:
            meta = r.get("metadata", {})
            name = meta.get("source", "")
            page = meta.get("page", 0)
            score = r.get("final_score", r.get("hybrid_score", 0.0))
            key = (name, page)
            if key not in seen:
                seen.add(key)
                out.append({"name": name, "page": page, "score": round(score, 4)})
        return out

    return {
        "sources": sources,
        "prerank_sources": _to_sources(prerank_results, top_k),
        "latency_ms": latency_ms,
    }


def evaluate_retrieval_case(question: dict, api_sources: list, prerank_sources: list, tolerance: int) -> dict:
    """Evalua solo retrieval: doc_hit, page_hit, recall, MRR, precision@k."""
    retrieval = validate_retrieval(
        api_sources,
        question.get("expected_sources", []),
        question.get("expected_pages", []),
        tolerance,
    )
    prerank_retrieval = validate_retrieval(
        prerank_sources,
        question.get("expected_sources", []),
        question.get("expected_pages", []),
        tolerance,
    )

    failure_reasons = []
    if not retrieval.get("skipped") and question.get("is_answerable", True):
        if not retrieval["hit_doc"]:
            failure_reasons.append("retrieval_doc_miss")

    return {
        "id": question["id"],
        "query": question["query"],
        "category": question.get("category", ""),
        "is_answerable": question.get("is_answerable", True),
        "retrieval": retrieval,
        "prerank_retrieval": prerank_retrieval,
        "failure_reasons": failure_reasons,
        "sources_returned": api_sources,
        "prerank_sources_returned": prerank_sources,
    }


def analyze_results(results: list) -> dict:
    """Calcula metricas agregadas de retrieval incluyendo pre/post reranker."""
    total = len(results)
    answerable = [r for r in results if r.get("is_answerable", True)]
    n_answerable = len(answerable)

    def _agg(field: str, key: str):
        vals = [r[field][key] for r in answerable
                if r.get(field) and r[field].get(key) is not None]
        return round(sum(vals) / len(vals), 3) if vals else 0

    def _hit_rate(field: str, key: str):
        hits = sum(1 for r in answerable if r.get(field) and r[field].get(key))
        return round(hits / n_answerable, 3) if n_answerable else 0

    doc_hits = sum(1 for r in answerable if r["retrieval"].get("hit_doc"))
    page_hits = sum(1 for r in answerable if r["retrieval"].get("hit_page"))
    doc_misses = n_answerable - doc_hits

    recalls = [r["retrieval"]["recall"] for r in answerable
               if r["retrieval"].get("recall") is not None]
    mrrs = [r["retrieval"]["mrr"] for r in answerable
            if r["retrieval"].get("mrr") is not None]
    precisions = [r["retrieval"]["precision_at_k"] for r in answerable
                  if r["retrieval"].get("precision_at_k") is not None]
    latencies = [r.get("latency_ms", 0) for r in results]

    # P-TS.2.b: Metricas sobre subconjunto no-ambiguo (excluye categoria 'ambiguous')
    ambiguous_ids = {41, 42, 43, 44, 46, 47, 50}
    core = [r for r in answerable if r.get("id") not in ambiguous_ids]
    n_core = len(core)
    core_doc_hits = sum(1 for r in core if r["retrieval"].get("hit_doc"))
    core_mrrs = [r["retrieval"]["mrr"] for r in core
                 if r["retrieval"].get("mrr") is not None]
    core_page_hits = sum(1 for r in core if r["retrieval"].get("hit_page"))

    first_ranks = [r["retrieval"]["first_relevant_rank"] for r in answerable
                   if r["retrieval"].get("first_relevant_rank") is not None]

    # FASE 6: metricas Top-K antes/después del reranker
    prerank_doc_hit = _hit_rate("prerank_retrieval", "hit_doc")
    postrank_doc_hit = _hit_rate("retrieval", "hit_doc")
    prerank_recall = _agg("prerank_retrieval", "recall")
    postrank_recall = _agg("retrieval", "recall")
    prerank_mrr = _agg("prerank_retrieval", "mrr")
    postrank_mrr = _agg("retrieval", "mrr")
    prerank_precision = _agg("prerank_retrieval", "precision_at_k")
    postrank_precision = _agg("retrieval", "precision_at_k")

    improvements = []
    regressions = []
    for r in answerable:
        pre_rank = r.get("prerank_retrieval", {}).get("first_relevant_rank")
        post_rank = r["retrieval"].get("first_relevant_rank")
        if pre_rank is not None and post_rank is not None:
            if post_rank < pre_rank:
                improvements.append(r["id"])
            elif post_rank > pre_rank:
                regressions.append(r["id"])

    return {
        "total_questions": total,
        "answerable": n_answerable,
        "doc_hit_rate": round(doc_hits / n_answerable, 3) if n_answerable else 0,
        "page_hit_rate": round(page_hits / n_answerable, 3) if n_answerable else 0,
        "doc_miss_count": doc_misses,
        "avg_recall": round(sum(recalls) / len(recalls), 3) if recalls else 0,
        "avg_mrr": round(sum(mrrs) / len(mrrs), 3) if mrrs else 0,
        "avg_precision_at_k": round(sum(precisions) / len(precisions), 3) if precisions else 0,
        "avg_first_rank": round(sum(first_ranks) / len(first_ranks), 1) if first_ranks else None,
        "median_first_rank": sorted(first_ranks)[len(first_ranks)//2] if first_ranks else None,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 0) if latencies else 0,
        "total_elapsed_s": round(sum(latencies) / 1000, 1),
        # P-TS.2.b: metricas core (no-ambiguo)
        "core_answerable": n_core,
        "core_doc_hit_rate": round(core_doc_hits / n_core, 3) if n_core else 0,
        "core_page_hit_rate": round(core_page_hits / n_core, 3) if n_core else 0,
        "core_avg_mrr": round(sum(core_mrrs) / len(core_mrrs), 3) if core_mrrs else 0,
        # FASE 6
        "prerank_doc_hit_rate": prerank_doc_hit,
        "postrank_doc_hit_rate": postrank_doc_hit,
        "prerank_avg_recall": prerank_recall,
        "postrank_avg_recall": postrank_recall,
        "prerank_avg_mrr": prerank_mrr,
        "postrank_avg_mrr": postrank_mrr,
        "prerank_avg_precision_at_k": prerank_precision,
        "postrank_avg_precision_at_k": postrank_precision,
        "reranker_improvements": improvements,
        "reranker_regressions": regressions,
    }


def main():
    parser = argparse.ArgumentParser(description="Eval retrieval-only (sin LLM)")
    parser.add_argument("--ids", type=str, default=None,
                        help="IDs separados por coma (ej: 1,5,21)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limitar a primeras N preguntas")
    parser.add_argument("--category", type=str, default=None,
                        help="Filtrar por categoria (simple, multi_document, etc.)")
    parser.add_argument("--top-k", type=int, default=10,
                        help="Top-K resultados a recuperar (default: 10)")
    parser.add_argument("--semantic-weight", type=float, default=None,
                        help="Override semantic_weight (default: lee config.yaml)")
    args = parser.parse_args()

    if not QUESTIONS_FILE.exists():
        print(f"ERROR: No se encontro el dataset en {QUESTIONS_FILE}", file=sys.stderr)
        sys.exit(1)

    dataset = load_questions(QUESTIONS_FILE)
    questions = dataset["questions"]
    tolerance = dataset.get("page_tolerance", 2)

    if args.ids:
        id_set = set(int(x) for x in args.ids.split(","))
        questions = [q for q in questions if q["id"] in id_set]
    if args.category:
        questions = [q for q in questions if q.get("category") == args.category]
    if args.limit:
        questions = questions[:args.limit]
    if not questions:
        print("No hay preguntas que coincidan con los filtros.", file=sys.stderr)
        sys.exit(1)

    sw = args.semantic_weight if args.semantic_weight is not None else _get_semantic_weight()

    print(f"Modo:     retrieval-only (sin LLM)")
    print(f"Preguntas: {len(questions)}")
    print(f"Top-K:    {args.top_k}")
    print(f"SemW:     {sw}")
    print(f"Tolerance: {tolerance}")
    print("=" * 80)

    results = []
    t_start = time.time()

    for i, q in enumerate(questions, 1):
        qid = q["id"]
        query = q["query"]
        print(f"[{i}/{len(questions)}] ID {qid}: {query[:70]}...", end=" ", flush=True)

        try:
            api_result = query_retrieval_only(query, top_k=args.top_k,
                                               semantic_weight=sw)
            sources = api_result["sources"]
            prerank_sources = api_result["prerank_sources"]
            latency = api_result["latency_ms"]
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({
                "id": qid,
                "query": query,
                "category": q.get("category", ""),
                "is_answerable": q.get("is_answerable", True),
                "retrieval": {"hit_doc": False, "hit_page": False,
                              "recall": 0, "mrr": 0, "precision_at_k": 0,
                              "first_relevant_rank": None, "matched": [],
                              "skipped": False},
                "failure_reasons": ["exception"],
                "sources_returned": [],
                "latency_ms": 0,
                "error": str(e),
            })
            continue

        case = evaluate_retrieval_case(q, sources, prerank_sources, tolerance)
        case["latency_ms"] = latency
        results.append(case)

        hit = "HIT" if case["retrieval"].get("hit_doc") else "MISS"
        rank = case["retrieval"].get("first_relevant_rank", "-")
        print(f"{hit} rank={rank} ({latency}ms)")

    elapsed = time.time() - t_start
    analysis = analyze_results(results)
    analysis["total_elapsed_s"] = round(elapsed, 1)

    print("\n" + "=" * 80)
    print(f"RESULTADOS RETRIEVAL-ONLY (semantic_weight={sw}, top_k={args.top_k})")
    print("=" * 80)
    print(f"  Preguntas:         {analysis['total_questions']} ({analysis['answerable']} answerable)")
    print(f"  Doc hit rate:      {analysis['doc_hit_rate']:.1%} ({analysis['answerable'] - analysis['doc_miss_count']}/{analysis['answerable']})")
    print(f"  Page hit rate:     {analysis['page_hit_rate']:.1%}")
    print(f"  Doc misses:        {analysis['doc_miss_count']}")
    print(f"  Avg recall:        {analysis['avg_recall']:.3f}")
    print(f"  Avg MRR:           {analysis['avg_mrr']:.3f}")
    print(f"  Avg precision@k:   {analysis['avg_precision_at_k']:.3f}")
    if analysis.get("avg_first_rank"):
        print(f"  Avg first rank:    {analysis['avg_first_rank']:.1f}")
    if analysis.get("median_first_rank"):
        print(f"  Median first rank: {analysis['median_first_rank']}")
    print(f"  Avg latency:       {analysis['avg_latency_ms']:.0f}ms")
    print(f"\n  --- Core metrics (no-ambiguo, {analysis.get('core_answerable', 0)} preguntas) ---")
    print(f"  Core doc hit rate: {analysis.get('core_doc_hit_rate', 0):.1%}")
    print(f"  Core page hit rate:{analysis.get('core_page_hit_rate', 0):.1%}")
    print(f"  Core avg MRR:      {analysis.get('core_avg_mrr', 0):.3f}")
    print("\n  --- Top-K pre/post reranker (FASE 6) ---")
    print(f"  Doc hit rate pre:  {analysis['prerank_doc_hit_rate']:.1%}")
    print(f"  Doc hit rate post: {analysis['postrank_doc_hit_rate']:.1%}")
    print(f"  Avg recall pre:    {analysis['prerank_avg_recall']:.3f}")
    print(f"  Avg recall post:   {analysis['postrank_avg_recall']:.3f}")
    print(f"  Avg MRR pre:       {analysis['prerank_avg_mrr']:.3f}")
    print(f"  Avg MRR post:      {analysis['postrank_avg_mrr']:.3f}")
    print(f"  Avg precision@k pre:  {analysis['prerank_avg_precision_at_k']:.3f}")
    print(f"  Avg precision@k post: {analysis['postrank_avg_precision_at_k']:.3f}")
    if analysis["reranker_improvements"]:
        print(f"  Mejorados por reranker: {analysis['reranker_improvements']}")
    if analysis["reranker_regressions"]:
        print(f"  Empeorados por reranker: {analysis['reranker_regressions']}")
    print(f"  Total elapsed:     {analysis['total_elapsed_s']:.1f}s")

    misses = [r for r in results if "retrieval_doc_miss" in r.get("failure_reasons", [])]
    if misses:
        print(f"\n  Doc misses ({len(misses)}):")
        for m in misses:
            top_src = m["sources_returned"][0]["name"] if m["sources_returned"] else "(none)"
            print(f"    ID {m['id']}: {m['query'][:60]}... -> top: {top_src[:50]}")

    # Guardar reporte
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sw_str = f"sw{int(sw*100):02d}"
    report_path = REPORTS_DIR / f"retrieval_only_{timestamp}_{sw_str}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": timestamp,
            "mode": "retrieval_only",
            "semantic_weight": sw,
            "top_k": args.top_k,
            "elapsed_s": round(elapsed, 1),
            "analysis": analysis,
            "results": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n  Reporte guardado: {report_path}")


if __name__ == "__main__":
    main()
