"""
Harness de evaluacion RAG - dominio ciberseguridad.

Consulta POST /api/chat por cada pregunta del dataset y valida:
  1. Recuperacion (nivel pagina + rank): rank del primer doc correcto, MRR,
     recall multi-doc, precision@K.
  2. Respuesta: keywords como metrica auxiliar (no criterio de fallo duro),
     ausencia de must_not_contain.
  3. Alucinacion: en preguntas no respondibles, la respuesta debe declinar
     (contener palabras de rechazo) y NO contener los terminos de must_not_contain.
  4. Fidelidad de citas: los marcadores [Doc N - ...] en la respuesta deben
     corresponder a fuentes devueltas por la API.

Uso:
    python tests/eval/run_cybersec_eval.py              # modo directo (sin HTTP)
    python tests/eval/run_cybersec_eval.py --ids 1,5,21
    python tests/eval/run_cybersec_eval.py --category no_answer
    python tests/eval/run_cybersec_eval.py --limit 10
    python tests/eval/run_cybersec_eval.py --kw-threshold 0.5
    python tests/eval/run_cybersec_eval.py --http --url http://localhost:5000  # modo HTTP
"""

import json
import re
import sys
import time
import argparse
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
import yaml
import traceback as _tb

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# Agregar raiz del proyecto al path para importar HybridRAG
ROOT_SRC = Path(__file__).parent.parent.parent
if str(ROOT_SRC) not in sys.path:
    sys.path.insert(0, str(ROOT_SRC))
if str(ROOT_SRC / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_SRC / "src"))

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = ROOT_SRC
QUESTIONS_FILE = Path(__file__).parent / "cybersec_eval_questions.json"
REPORTS_DIR = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Palabras que indican que el modelo declino responder
# ---------------------------------------------------------------------------
DECLINE_PHRASES = [
    "no hay evidencia",
    "no hay informacion",
    "no se menciona",
    "no tengo informacion",
    "no encontre",
    "no se encuentra",
    "fuera de mi alcance",
    "fuera del alcance",
    "no puedo responder",
    "no dispongo",
    "no esta disponible",
    "insuficiente",
    "no hay suficiente",
    "no hay datos",
    "no hay documentos",
    "no se documenta",
    # FASE C.3: variantes adicionales
    "no se proporciona",
    "no se contiene",
    "no existe",
    "no hay referencia",
    "no se encuentra informacion",
    "no se encontro informacion",
    # variantes en ingles (el LLM a veces responde en ingles)
    "no information",
    "not provided",
    "does not contain",
    "is not available",
    "not found",
    "i don't have",
    "i do not have",
    "i'm sorry",
    "i am sorry",
    "the text does not",
    "the document does not",
    "not mentioned",
    "no data available",
    "insufficient information",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_questions(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def normalize(text: str) -> str:
    return text.lower()


def check_server(base_url: str, timeout: int = 5) -> bool:
    try:
        urllib.request.urlopen(base_url + "/", timeout=timeout)
        return True
    except Exception:
        return False


def query_api(base_url: str, question: str, timeout: int = 180) -> dict:
    payload = json.dumps({
        "query": question,
        "length_mode": "long",
        "no_context": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        base_url + "/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


_rag_instance = None

def _get_rag():
    global _rag_instance
    if _rag_instance is None:
        from rag_hybrid import HybridRAG
        print("Inicializando HybridRAG (modo directo)...")
        _rag_instance = HybridRAG(variant="bge", heuristics="balanced")
        print(f"OK: RAG listo ({len(_rag_instance.all_docs)} documentos)\n")
    return _rag_instance


def _get_semantic_weight() -> float:
    """Lee semantic_weight de config.yaml; fallback a 0.6 si no existe."""
    try:
        cfg_path = ROOT_SRC / "config.yaml"
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return float(cfg.get("retrieval", {}).get("semantic_weight", 0.6))
    except Exception:
        return 0.6


def query_direct(question: str) -> dict:
    """Llama a HybridRAG directamente sin pasar por HTTP."""
    rag = _get_rag()
    t0 = time.time()
    result = rag.query(
        question,
        top_k=10,
        semantic_weight=_get_semantic_weight(),
        entity_filter=True,
        two_stage=True,
        stream=False,
    )
    latency_ms = round((time.time() - t0) * 1000)

    # Mapear al formato que consume evaluate_case
    raw_results = result.get("results") or []
    sources = []
    seen = set()
    for r in raw_results[:10]:
        meta = r.get("metadata", {})
        name = meta.get("source", "")
        page = meta.get("page", 0)
        score = r.get("final_score", r.get("hybrid_score", 0.0))
        key = (name, page)
        if key not in seen:
            seen.add(key)
            sources.append({"name": name, "page": page, "score": round(score, 4)})

    answer = result.get("answer", "") or ""
    # Normalizar caracteres Unicode problemáticos en Windows (charmap)
    answer = (answer
              .replace("\u2265", ">=").replace("\u2264", "<=")
              .replace("\u2192", "->").replace("\u2190", "<-")
              .replace("\u2022", "-").replace("\u2019", "'")
              .replace("\u201c", '"').replace("\u201d", '"')
              .replace("\u2013", "-").replace("\u2014", "--"))

    timing = result.get("timing_breakdown", {})

    return {
        "response": answer,
        "sources": sources,
        "latency_ms": latency_ms,
        "timing_breakdown": timing,
    }


def extract_citation_sources(answer: str) -> list:
    """Extrae los nombres de fuente de los marcadores [Doc N - nombre p.X]."""
    pattern = r"\[Doc\s*\d+[^\]]*?-\s*([^\]]+?)\s*p\.\d+"
    return re.findall(pattern, answer, re.IGNORECASE)


# ---------------------------------------------------------------------------
# Validadores individuales
# ---------------------------------------------------------------------------

def _src_matches(api_name: str, exp_name: str) -> bool:
    """Match parcial bidireccional entre nombres de fuente."""
    a, e = api_name.lower(), exp_name.lower()
    return e in a or a in e


def validate_retrieval(sources_api: list, expected_sources: list,
                        expected_pages: list, tolerance: int) -> dict:
    """
    Devuelve:
      - hit_doc (bool): al menos un expected_source en top-K
      - hit_page (bool): hit_doc Y pagina dentro de la tolerancia
      - recall (float): fraccion de expected_sources encontrados (multi-doc)
      - first_relevant_rank (int|None): posicion 1-K del primer doc correcto
      - mrr (float): mean reciprocal rank del primer doc correcto
      - precision_at_k (float): fraccion de los K recuperados que son relevantes
      - matched: lista de hits con rank incluido
    """
    if not expected_sources:
        return {
            "hit_doc": None, "hit_page": None, "recall": None,
            "first_relevant_rank": None, "mrr": None,
            "precision_at_k": None, "matched": [], "skipped": True,
        }

    matched = []
    hit_doc = False
    hit_page = False
    found_expected = set()  # indices de expected_sources encontrados
    first_rank = None       # rango 1-K del primer doc correcto
    relevant_positions = [] # posiciones (1-K) de docs relevantes

    for rank, api_src in enumerate(sources_api, start=1):
        api_name = (api_src.get("name") or "").lower()
        api_page = api_src.get("page") or 0
        for idx, exp_src in enumerate(expected_sources):
            if _src_matches(api_name, exp_src):
                hit_doc = True
                found_expected.add(idx)
                if first_rank is None:
                    first_rank = rank
                relevant_positions.append(rank)
                exp_pages = expected_pages[idx] if idx < len(expected_pages) else None
                if exp_pages is not None:
                    pages_list = exp_pages if isinstance(exp_pages, list) else [exp_pages]
                    if any(abs(api_page - ep) <= tolerance for ep in pages_list):
                        hit_page = True
                matched.append({
                    "source": api_src.get("name"),
                    "page": api_page,
                    "score": api_src.get("score"),
                    "rank": rank,
                })

    k = len(sources_api) if sources_api else 1
    recall = len(found_expected) / len(expected_sources) if expected_sources else 0.0
    mrr = (1.0 / first_rank) if first_rank else 0.0
    precision_at_k = len(relevant_positions) / k if k else 0.0

    return {
        "hit_doc": hit_doc,
        "hit_page": hit_page if hit_doc else False,
        "recall": round(recall, 3),
        "first_relevant_rank": first_rank,
        "mrr": round(mrr, 3),
        "precision_at_k": round(precision_at_k, 3),
        "matched": matched,
        "skipped": False,
    }


def validate_response_keywords(answer: str, keywords: list,
                                forbidden: list) -> dict:
    """
    Keywords son metrica AUXILIAR, no criterio de fallo duro.
    El caller decide si keyword_score < umbral implica fallo.
    forbidden_pass sigue siendo criterio duro.
    """
    ans_lower = normalize(answer)
    present = [kw for kw in keywords if kw.lower() in ans_lower]
    missing = [kw for kw in keywords if kw.lower() not in ans_lower]
    found_forbidden = [ph for ph in forbidden if ph.lower() in ans_lower]
    keyword_score = len(present) / len(keywords) if keywords else 1.0
    return {
        "keyword_score": round(keyword_score, 3),
        "present": present,
        "missing": missing,
        "found_forbidden": found_forbidden,
        "keywords_pass": len(missing) == 0,      # auxiliar
        "forbidden_pass": len(found_forbidden) == 0,  # duro
    }


def validate_hallucination(answer: str, is_answerable: bool,
                            forbidden: list) -> dict:
    """
    Solo relevante cuando is_answerable=False.
    Pasa si la respuesta contiene alguna frase de declive Y no contiene terminos prohibidos.
    """
    if is_answerable:
        return {"applicable": False}
    ans_lower = normalize(answer)
    declined = any(ph in ans_lower for ph in DECLINE_PHRASES)
    hallucinated = any(ph.lower() in ans_lower for ph in forbidden) if forbidden else False
    return {
        "applicable": True,
        "declined": declined,
        "hallucinated": hallucinated,
        "pass": declined and not hallucinated,
    }


def validate_citation_fidelity(answer: str, sources_api: list) -> dict:
    """
    Extrae marcadores de cita de la respuesta y verifica que la fuente
    mencionada este entre las devueltas por la API.
    """
    cited = extract_citation_sources(answer)
    if not cited:
        return {"cited": [], "verified": [], "unverified": [], "score": None}
    api_names = [normalize(s.get("name") or "") for s in sources_api]
    verified = []
    unverified = []
    for c in cited:
        c_norm = normalize(c.strip())
        if any(c_norm in an or an in c_norm for an in api_names):
            verified.append(c)
        else:
            unverified.append(c)
    score = len(verified) / len(cited) if cited else 1.0
    return {
        "cited": cited,
        "verified": verified,
        "unverified": unverified,
        "score": round(score, 3),
    }


# ---------------------------------------------------------------------------
# Resultado por caso
# ---------------------------------------------------------------------------

def evaluate_case(question: dict, api_response: dict, tolerance: int,
                  kw_threshold: float = 0.3) -> dict:
    """
    kw_threshold: keyword_score minimo para no marcar fallo por keywords.
    Por defecto 0.3 (umbral suave). Las keywords son metrica auxiliar;
    el fallo duro solo ocurre si score < umbral O hay forbidden.
    """
    answer = api_response.get("response", "")
    sources = api_response.get("sources", [])
    latency = api_response.get("latency_ms", 0)
    timing_breakdown = api_response.get("timing_breakdown", {})

    retrieval = validate_retrieval(
        sources,
        question.get("expected_sources", []),
        question.get("expected_pages", []),
        tolerance,
    )
    resp_val = validate_response_keywords(
        answer,
        question.get("answer_keywords", []),
        question.get("must_not_contain", []),
    )
    halluc = validate_hallucination(
        answer,
        question.get("is_answerable", True),
        question.get("must_not_contain", []),
    )
    citation = validate_citation_fidelity(answer, sources)

    # -----------------------------------------------------------------------
    # Veredictos independientes por capa
    # -----------------------------------------------------------------------
    failure_reasons = []
    warnings = []

    # --- Retrieval ---
    pass_retrieval = True
    if not retrieval.get("skipped") and question.get("is_answerable", True):
        if not retrieval["hit_doc"]:
            pass_retrieval = False
            failure_reasons.append("retrieval_doc_miss")
        else:
            if not retrieval["hit_page"]:
                warnings.append("retrieval_page_miss")
            if retrieval["recall"] < 1.0:
                warnings.append(f"recall={retrieval['recall']:.2f} (multi-doc incompleto)")

    # --- Groundedness (forbidden phrases) ---
    pass_groundedness = resp_val["forbidden_pass"]
    if not pass_groundedness:
        failure_reasons.append(f"found_forbidden: {resp_val['found_forbidden']}")

    # --- Generation (keyword score como metrica auxiliar) ---
    pass_generation = True
    if question.get("is_answerable", True):
        kw_score = resp_val["keyword_score"]
        if resp_val["present"] == [] and resp_val["missing"]:
            pass_generation = False
            failure_reasons.append(f"kw_score=0 missing={resp_val['missing']}")
        elif kw_score < kw_threshold:
            pass_generation = False
            failure_reasons.append(f"kw_score={kw_score:.2f}<{kw_threshold} missing={resp_val['missing']}")
        else:
            if resp_val["missing"]:
                warnings.append(f"kw_partial={kw_score:.2f} missing={resp_val['missing']}")

    # --- Anti-alucinacion (solo para is_answerable=False) ---
    pass_hallucination = True
    if not question.get("is_answerable", True):
        pass_hallucination = halluc.get("pass", True)
        if not halluc.get("pass", True):
            if not halluc["declined"]:
                failure_reasons.append("hallucination_no_decline")
            if halluc["hallucinated"]:
                failure_reasons.append("hallucination_forbidden_content")

    # --- Overall: falla si cualquier capa falla ---
    passed = pass_retrieval and pass_groundedness and pass_generation and pass_hallucination

    return {
        "id": question["id"],
        "category": question["category"],
        "difficulty": question["difficulty"],
        "is_answerable": question["is_answerable"],
        "query": question["query"],
        "passed": passed,
        "pass_retrieval": pass_retrieval,
        "pass_groundedness": pass_groundedness,
        "pass_generation": pass_generation,
        "pass_hallucination": pass_hallucination,
        "failure_reasons": failure_reasons,
        "warnings": warnings,
        "retrieval": retrieval,
        "response_validation": resp_val,
        "hallucination": halluc,
        "citation_fidelity": citation,
        "answer_snippet": answer[:300],
        "sources_returned": [
            {"name": s.get("name"), "page": s.get("page"), "score": s.get("score")}
            for s in sources
        ],
        "latency_ms": latency,
        "timing_breakdown": timing_breakdown,
    }


# ---------------------------------------------------------------------------
# Analisis de resultados
# ---------------------------------------------------------------------------

def _percentile(sorted_vals: list, p: float) -> float:
    """Percentil p (0-100) sobre lista ya ordenada."""
    if not sorted_vals:
        return 0.0
    idx = int(len(sorted_vals) * p / 100)
    idx = min(idx, len(sorted_vals) - 1)
    return sorted_vals[idx]


def analyze_results(results: list) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])

    by_category = {}
    for r in results:
        cat = r["category"]
        if cat not in by_category:
            by_category[cat] = {
                "total": 0, "passed": 0,
                "retrieval_doc": 0, "retrieval_page": 0,
                "recall_sum": 0.0, "recall_n": 0,
                "mrr_sum": 0.0, "mrr_n": 0,
                "citation_score_sum": 0.0, "citation_n": 0,
                "kw_score_sum": 0.0, "kw_n": 0,
            }
        c = by_category[cat]
        c["total"] += 1
        if r["passed"]:
            c["passed"] += 1
        ret = r["retrieval"]
        if not ret.get("skipped"):
            if ret.get("hit_doc"):
                c["retrieval_doc"] += 1
            if ret.get("hit_page"):
                c["retrieval_page"] += 1
            if ret.get("recall") is not None:
                c["recall_sum"] += ret["recall"]
                c["recall_n"] += 1
            if ret.get("mrr") is not None:
                c["mrr_sum"] += ret["mrr"]
                c["mrr_n"] += 1
        cit = r["citation_fidelity"]
        if cit.get("score") is not None:
            c["citation_score_sum"] += cit["score"]
            c["citation_n"] += 1
        kw = r.get("response_validation", {}).get("keyword_score")
        if kw is not None:
            c["kw_score_sum"] += kw
            c["kw_n"] += 1

    # Tipos de fallo
    retrieval_doc_misses = sum(
        1 for r in results if "retrieval_doc_miss" in r["failure_reasons"]
    )
    retrieval_page_misses = sum(
        1 for r in results if any("retrieval_page_miss" in w for w in r.get("warnings", []))
    )
    llm_kw_misses = sum(
        1 for r in results if any(
            fr.startswith("kw_score") or fr.startswith("kw_score=0")
            for fr in r["failure_reasons"]
        )
    )
    hallucinations = sum(
        1 for r in results if "hallucination_no_decline" in r["failure_reasons"]
        or "hallucination_forbidden_content" in r["failure_reasons"]
    )
    answerable_results = [r for r in results if r["is_answerable"]]
    not_answerable_results = [r for r in results if not r["is_answerable"]]

    # Citation fidelity global
    citation_scores = [
        r["citation_fidelity"]["score"]
        for r in results
        if r["citation_fidelity"].get("score") is not None
    ]
    avg_citation = sum(citation_scores) / len(citation_scores) if citation_scores else None

    # Keyword scores
    kw_scores = [
        r["response_validation"]["keyword_score"]
        for r in results
        if r.get("response_validation") and r["response_validation"].get("keyword_score") is not None
    ]
    avg_kw = sum(kw_scores) / len(kw_scores) if kw_scores else None

    # MRR y Recall globales
    mrr_vals = [
        r["retrieval"]["mrr"]
        for r in results
        if not r["retrieval"].get("skipped") and r["retrieval"].get("mrr") is not None
    ]
    avg_mrr = sum(mrr_vals) / len(mrr_vals) if mrr_vals else None

    recall_vals = [
        r["retrieval"]["recall"]
        for r in results
        if not r["retrieval"].get("skipped") and r["retrieval"].get("recall") is not None
    ]
    avg_recall = sum(recall_vals) / len(recall_vals) if recall_vals else None

    precision_vals = [
        r["retrieval"]["precision_at_k"]
        for r in results
        if not r["retrieval"].get("skipped") and r["retrieval"].get("precision_at_k") is not None
    ]
    avg_precision = sum(precision_vals) / len(precision_vals) if precision_vals else None

    # Latencias
    latencies = sorted(
        [r["latency_ms"] for r in results if r.get("latency_ms") and r["latency_ms"] > 0]
    )
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    p50_latency = _percentile(latencies, 50)
    p95_latency = _percentile(latencies, 95)
    max_latency = latencies[-1] if latencies else 0

    # Rank distribution y Recall@K
    rank_dist = {}
    recall_at: dict = {1: 0, 3: 0, 5: 0}  # Recall@1, Recall@3, Recall@5
    retrieval_total = sum(1 for r in results if not r["retrieval"].get("skipped"))
    for r in results:
        if r["retrieval"].get("skipped"):
            continue
        rk = r["retrieval"].get("first_relevant_rank")
        if rk is not None:
            rank_dist[rk] = rank_dist.get(rk, 0) + 1
            for cutoff in (1, 3, 5):
                if rk <= cutoff:
                    recall_at[cutoff] += 1
    recall_at_k = {
        f"recall_at_{k}": round(recall_at[k] / retrieval_total, 3) if retrieval_total else None
        for k in (1, 3, 5)
    }

    # Conteo de veredictos de capa (para top_problems)
    layer_counts = {
        "retrieval_miss": sum(1 for r in results if not r.get("pass_retrieval", True)),
        "page_miss":      sum(1 for r in results if any("retrieval_page_miss" in w for w in r.get("warnings", []))),
        "hallucination":  sum(1 for r in results if not r.get("pass_hallucination", True)),
        "low_kw_score":   sum(1 for r in results if not r.get("pass_generation", True)),
        "forbidden":      sum(1 for r in results if not r.get("pass_groundedness", True)),
    }

    # Breakdown de latencia por etapa (solo modo directo)
    timing_keys = ('t_embed_ms', 't_semantic_ms', 't_bm25_ms',
                   't_fusion_ms', 't_rerank_ms', 't_llm_estimated_ms', 't_total_ms')
    timing_sums = {k: 0.0 for k in timing_keys}
    timing_counts = {k: 0 for k in timing_keys}
    for r in results:
        tb = r.get('timing_breakdown') or {}
        for k in timing_keys:
            v = tb.get(k)
            if v is not None:
                timing_sums[k] += v
                timing_counts[k] += 1
    timing_avg = {
        k: round(timing_sums[k] / timing_counts[k], 1) if timing_counts[k] else None
        for k in timing_keys
    }

    # Enriquecer by_category con promedios
    for cat, c in by_category.items():
        c["avg_recall"] = round(c["recall_sum"] / c["recall_n"], 3) if c["recall_n"] else None
        c["avg_mrr"] = round(c["mrr_sum"] / c["mrr_n"], 3) if c["mrr_n"] else None
        c["avg_citation"] = round(c["citation_score_sum"] / c["citation_n"], 3) if c["citation_n"] else None
        c["avg_kw_score"] = round(c["kw_score_sum"] / c["kw_n"], 3) if c["kw_n"] else None
        # limpiar acumuladores internos del JSON
        for k in ("recall_sum","recall_n","mrr_sum","mrr_n",
                   "citation_score_sum","citation_n","kw_score_sum","kw_n"):
            del c[k]

    return {
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": round(passed / total, 3) if total else 0,
            "answerable_pass_rate": round(
                sum(1 for r in answerable_results if r["passed"])
                / max(1, len(answerable_results)), 3
            ),
            "no_answer_pass_rate": round(
                sum(1 for r in not_answerable_results if r["passed"])
                / max(1, len(not_answerable_results)), 3
            ),
            # Veredictos por capa
            "pass_retrieval_rate": round(
                sum(1 for r in results if r.get("pass_retrieval", True)) / total, 3
            ) if total else 0,
            "pass_groundedness_rate": round(
                sum(1 for r in results if r.get("pass_groundedness", True)) / total, 3
            ) if total else 0,
            "pass_generation_rate": round(
                sum(1 for r in results if r.get("pass_generation", True)) / total, 3
            ) if total else 0,
            "pass_hallucination_rate": round(
                sum(1 for r in not_answerable_results if r.get("pass_hallucination", True))
                / max(1, len(not_answerable_results)), 3
            ),
            # Retrieval detallado
            "retrieval_doc_hit_rate": round(
                sum(1 for r in results if r["retrieval"].get("hit_doc"))
                / max(1, retrieval_total), 3
            ),
            "retrieval_page_hit_rate": round(
                sum(1 for r in results if r["retrieval"].get("hit_page"))
                / max(1, retrieval_total), 3
            ),
            "recall_at_1": recall_at_k["recall_at_1"],
            "recall_at_3": recall_at_k["recall_at_3"],
            "recall_at_5": recall_at_k["recall_at_5"],
            "avg_recall": round(avg_recall, 3) if avg_recall is not None else None,
            "avg_mrr": round(avg_mrr, 3) if avg_mrr is not None else None,
            "avg_precision_at_k": round(avg_precision, 3) if avg_precision is not None else None,
            # Respuesta
            "avg_keyword_score": round(avg_kw, 3) if avg_kw is not None else None,
            "avg_citation_fidelity": round(avg_citation, 3) if avg_citation else None,
            # Contadores de fallo por tipo
            "retrieval_doc_miss_count": retrieval_doc_misses,
            "retrieval_page_miss_count": retrieval_page_misses,
            "llm_kw_miss_count": llm_kw_misses,
            "hallucination_count": hallucinations,
            # Latencia
            "latency_avg_ms": round(avg_latency),
            "latency_p50_ms": round(p50_latency),
            "latency_p95_ms": round(p95_latency),
            "latency_max_ms": round(max_latency),
            # Breakdown por etapa (promedio, ms)
            "timing_embed_avg_ms": timing_avg['t_embed_ms'],
            "timing_semantic_avg_ms": timing_avg['t_semantic_ms'],
            "timing_bm25_avg_ms": timing_avg['t_bm25_ms'],
            "timing_fusion_avg_ms": timing_avg['t_fusion_ms'],
            "timing_rerank_avg_ms": timing_avg['t_rerank_ms'],
            "timing_llm_avg_ms": timing_avg['t_llm_estimated_ms'],
        },
        "layer_pass_counts": {
            "pass_retrieval": sum(1 for r in results if r.get("pass_retrieval", True)),
            "pass_groundedness": sum(1 for r in results if r.get("pass_groundedness", True)),
            "pass_generation": sum(1 for r in results if r.get("pass_generation", True)),
            "pass_hallucination": sum(1 for r in not_answerable_results if r.get("pass_hallucination", True)),
        },
        "top_problems": dict(sorted(layer_counts.items(), key=lambda x: -x[1])),
        "rank_distribution": rank_dist,
        "by_category": by_category,
        "failed_cases": [
            {"id": r["id"], "query": r["query"][:80],
             "reasons": r["failure_reasons"],
             "warnings": r.get("warnings", []),
             "pass_retrieval": r.get("pass_retrieval"),
             "pass_groundedness": r.get("pass_groundedness"),
             "pass_generation": r.get("pass_generation"),
             "pass_hallucination": r.get("pass_hallucination")}
            for r in results if not r["passed"]
        ],
    }


# ---------------------------------------------------------------------------
# Reporte Markdown
# ---------------------------------------------------------------------------

def _fmt(val, fmt=".3f", fallback="N/A"):
    return format(val, fmt) if val is not None else fallback


def generate_markdown_report(analysis: dict, timestamp: str, total_time: float) -> str:
    s = analysis["summary"]
    lines = [
        "# Reporte de evaluacion RAG - Ciberseguridad",
        "",
        f"Fecha: {timestamp}  |  Tiempo total: {total_time:.1f}s",
        "",
        "## Resumen global",
        "",
        "| Metrica | Valor |",
        "|---------|-------|",
        f"| Total preguntas | {s['total']} |",
        f"| Aprobadas | {s['passed']} ({s['pass_rate']*100:.1f}%) |",
        f"| Fallidas | {s['failed']} |",
        f"| Tasa aprobacion (respondibles) | {s['answerable_pass_rate']*100:.1f}% |",
        f"| Tasa aprobacion (sin respuesta) | {s['no_answer_pass_rate']*100:.1f}% |",
        "",
        "### Veredictos por capa",
        "",
        "| Capa | Tasa de exito |",
        "|------|---------------|",
        f"| Retrieval | {s.get('pass_retrieval_rate',0)*100:.1f}% |",
        f"| Groundedness (sin forbidden) | {s.get('pass_groundedness_rate',0)*100:.1f}% |",
        f"| Generation (keyword score) | {s.get('pass_generation_rate',0)*100:.1f}% |",
        f"| Anti-alucinacion | {s.get('pass_hallucination_rate',0)*100:.1f}% |",
        f"| **Overall** | **{s['pass_rate']*100:.1f}%** |",
        "",
        "### Retrieval",
        "",
        "| Metrica | Valor |",
        "|---------|-------|",
        f"| Doc hit@K | {s['retrieval_doc_hit_rate']*100:.1f}% |",
        f"| Pag hit@K (+/-tol) | {s['retrieval_page_hit_rate']*100:.1f}% |",
        f"| Recall@1 | {_fmt(s.get('recall_at_1'))} |",
        f"| Recall@3 | {_fmt(s.get('recall_at_3'))} |",
        f"| Recall@5 | {_fmt(s.get('recall_at_5'))} |",
        f"| Recall promedio (multi-doc) | {_fmt(s.get('avg_recall'))} |",
        f"| MRR promedio | {_fmt(s.get('avg_mrr'))} |",
        f"| Precision@K promedio | {_fmt(s.get('avg_precision_at_k'))} |",
        f"| Fallos retrieval (doc miss) | {s['retrieval_doc_miss_count']} |",
        f"| Advertencias pagina miss | {s['retrieval_page_miss_count']} |",
        "",
        "### Respuesta",
        "",
        "| Metrica | Valor |",
        "|---------|-------|",
        f"| Keyword score promedio (auxiliar) | {_fmt(s.get('avg_keyword_score'))} |",
        f"| Fallos por kw score bajo | {s['llm_kw_miss_count']} |",
        f"| Fidelidad citas promedio | {_fmt(s.get('avg_citation_fidelity'))} |",
        f"| Alucinaciones detectadas | {s['hallucination_count']} |",
        "",
        "### Latencia",
        "",
        "| Metrica | Valor |",
        "|---------|-------|",
        f"| Promedio | {s['latency_avg_ms']} ms |",
        f"| P50 | {s['latency_p50_ms']} ms |",
        f"| P95 | {s['latency_p95_ms']} ms |",
        f"| Maximo | {s['latency_max_ms']} ms |",
        "",
        "### Breakdown por etapa (promedio)",
        "",
        "| Etapa | Avg ms | % del total |",
        "|-------|--------|------------|",
    ]
    _t_total = s.get('latency_avg_ms') or 1
    for _lbl, _key in [
        ("Embed query (BGE)",   "timing_embed_avg_ms"),
        ("Busqueda semantica",  "timing_semantic_avg_ms"),
        ("BM25 keyword",        "timing_bm25_avg_ms"),
        ("Fusion + ranking",    "timing_fusion_avg_ms"),
        ("Re-ranker",           "timing_rerank_avg_ms"),
        ("LLM (estimado)",      "timing_llm_avg_ms"),
    ]:
        _v = s.get(_key)
        if _v is not None:
            _pct = round(_v / _t_total * 100, 1) if _t_total else 0
            lines.append(f"| {_lbl} | {_v} | {_pct}% |")
        else:
            lines.append(f"| {_lbl} | N/A | N/A |")
    lines += [
        "",
        "## Resultados por categoria",
        "",
        "| Categoria | Total | Aprob | Tasa | DocHit | PagHit | Recall | MRR | KW |",
        "|-----------|-------|-------|------|--------|--------|--------|-----|-----||",
    ]
    for cat, c in sorted(analysis["by_category"].items()):
        rate = c["passed"] / c["total"] * 100 if c["total"] else 0
        lines.append(
            f"| {cat} | {c['total']} | {c['passed']} | {rate:.0f}% "
            f"| {c['retrieval_doc']} | {c['retrieval_page']} "
            f"| {_fmt(c.get('avg_recall'))} | {_fmt(c.get('avg_mrr'))} "
            f"| {_fmt(c.get('avg_kw_score'))} |"
        )

    # Top problemas
    tp = analysis.get("top_problems", {})
    if tp:
        lines += ["", "## Top problemas", ""]
        lines += ["| Problema | Casos |", "|---------|-------|"]
        labels = {
            "retrieval_miss": "Retrieval miss (doc no encontrado)",
            "page_miss":      "Page miss (doc correcto, pagina errada)",
            "hallucination":  "Alucinacion (no declino)",
            "low_kw_score":   "Generation baja (keyword score bajo)",
            "forbidden":      "Forbidden phrase encontrada",
        }
        for k, v in tp.items():
            if v > 0:
                lines.append(f"| {labels.get(k, k)} | {v} |")

    # Distribucion de ranks
    rd = analysis.get("rank_distribution", {})
    if rd:
        lines += ["", "## Distribucion de rank del primer documento correcto", ""]
        lines += ["| Rank | Frecuencia |", "|------|------------|"]
        for rk in sorted(rd.keys()):
            lines.append(f"| {rk} | {rd[rk]} |")
        lines.append("")
        lines.append(
            f"_Rank 1 = {rd.get(1, 0)} casos  |  "
            f"Rank 2-3 = {rd.get(2,0)+rd.get(3,0)} casos  |  "
            f"Rank 4+ = {sum(v for k,v in rd.items() if k>=4)} casos_"
        )

    if analysis["failed_cases"]:
        lines += ["", "## Casos fallidos", ""]
        for fc in analysis["failed_cases"]:
            lines.append(f"- **ID {fc['id']}**: {fc['query']}")
            for r in fc["reasons"]:
                lines.append(f"  - {r}")
            for w in fc.get("warnings", []):
                lines.append(f"  - WARN: {w}")

    lines += [
        "",
        "## Diagnostico",
        "",
        "**Prioridad de intervencion:**",
        "",
        "1. Si `retrieval_doc_hit_rate` es bajo -> ajustar top_k, score_threshold o reranker.",
        "2. Si `retrieval_page_hit_rate` es bajo pero `hit_doc` es alto -> chunking muy fino o metadata de pagina incorrecta.",
        "3. Si `avg_mrr` < 0.5 y `hit_doc` es alto -> el doc correcto llega pero en posicion baja; mejorar reranker.",
        "4. Si `avg_keyword_score` es bajo pero retrieval es bueno -> problema en LLM/prompt (no en retrieval).",
        "5. Si `hallucination_count` > 0 -> revisar evidence gate y DECLINE_PHRASES.",
        "6. `avg_precision_at_k` bajo con `hit_doc` alto -> el retriever trae mucho ruido junto con docs correctos.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Runner principal
# ---------------------------------------------------------------------------

def run_eval(questions: list, tolerance: int,
             delay: float = 0.5, kw_threshold: float = 0.3,
             http_mode: bool = False, base_url: str = "") -> tuple:
    results = []
    total = len(questions)
    mode_label = f"HTTP -> {base_url}" if http_mode else "directo (sin HTTP)"
    print(f"\n{'='*70}")
    print(f"  EVALUACION RAG CIBERSEGURIDAD  ({total} preguntas)  [{mode_label}]")
    print(f"{'='*70}\n")

    start = time.time()
    for idx, q in enumerate(questions, 1):
        cat = q.get("category", "")
        ans_tag = "" if q["is_answerable"] else " [NO_RESP]"
        label = f"[{idx:>3}/{total}] {cat:15s}{ans_tag}"
        print(f"{label}  {q['query'][:58]}...")

        query_ok = False
        for _attempt in range(2):
            try:
                if http_mode:
                    api_resp = query_api(base_url, q["query"])
                else:
                    api_resp = query_direct(q["query"])
                result = evaluate_case(q, api_resp, tolerance, kw_threshold)
                query_ok = True
                break
            except Exception as exc:
                if _attempt == 0:
                    print(f"         EXCEPTION (retry): {exc}")
                    _tb.print_exc()
                    time.sleep(5)
                    try:
                        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
                        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
                    except Exception:
                        pass
                else:
                    print(f"         EXCEPTION (final): {exc}")
                    _tb.print_exc()
        if not query_ok:
            result = {
                "id": q["id"],
                "category": q.get("category"),
                "difficulty": q.get("difficulty"),
                "is_answerable": q.get("is_answerable", True),
                "query": q["query"],
                "passed": False,
                "failure_reasons": [f"exception: {exc}"],
                "warnings": [],
                "retrieval": {"skipped": True, "hit_doc": False, "hit_page": False,
                               "recall": None, "first_relevant_rank": None,
                               "mrr": None, "precision_at_k": None, "matched": []},
                "response_validation": {"keyword_score": 0},
                "hallucination": {},
                "citation_fidelity": {},
                "answer_snippet": "",
                "sources_returned": [],
                "latency_ms": 0,
            }

        results.append(result)

        status = "PASS" if result["passed"] else "FAIL"
        ret = result["retrieval"]
        doc_ok = "D+" if ret.get("hit_doc") else ("D-" if not ret.get("skipped") else "--")
        pag_ok = "P+" if ret.get("hit_page") else ("P-" if not ret.get("skipped") else "--")
        rank_s = f"R{ret.get('first_relevant_rank') or '-'}" 
        mrr_s  = f"mrr={ret.get('mrr',0):.2f}" if not ret.get("skipped") else ""
        recall_s = f"rec={ret.get('recall',0):.2f}" if not ret.get("skipped") else ""
        lat = result.get("latency_ms", 0)
        kw = result["response_validation"].get("keyword_score", 0)
        print(f"         {status:4s}  {doc_ok}{pag_ok} {rank_s:4s}  {mrr_s:9s}  {recall_s:9s}  kw={kw:.2f}  {lat}ms")
        if result["failure_reasons"]:
            for fr in result["failure_reasons"][:2]:
                print(f"           FAIL: {fr}")
        for w in result.get("warnings", [])[:1]:
            print(f"           WARN: {w}")

        time.sleep(delay)

    elapsed = time.time() - start
    return results, elapsed


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Harness de evaluacion RAG ciberseguridad")
    parser.add_argument("--http", action="store_true",
                        help="Usar modo HTTP en lugar de llamada directa a HybridRAG")
    parser.add_argument("--url", default="http://localhost:5000",
                        help="Base URL del servidor (solo con --http)")
    parser.add_argument("--ids", type=str, default=None,
                        help="Lista de IDs separados por coma, ej: 1,5,21")
    parser.add_argument("--category", type=str, default=None,
                        help="Filtrar por categoria: simple|multi_document|no_answer|ambiguous|complex")
    parser.add_argument("--limit", type=int, default=None,
                        help="Maximo de preguntas a ejecutar")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="Pausa entre queries en segundos (default 0.5)")
    parser.add_argument("--tolerance", type=int, default=None,
                        help="Tolerancia de pagina (default: la del dataset)")
    parser.add_argument("--kw-threshold", type=float, default=0.3,
                        help="Keyword score minimo para no fallar (default 0.3, auxiliar)")
    args = parser.parse_args()

    if not QUESTIONS_FILE.exists():
        print(f"ERROR: No se encontro el dataset en {QUESTIONS_FILE}", file=sys.stderr)
        sys.exit(1)

    dataset = load_questions(QUESTIONS_FILE)
    tolerance = args.tolerance if args.tolerance is not None else dataset.get("page_tolerance", 2)
    questions = dataset["questions"]

    if args.ids:
        id_set = {int(x.strip()) for x in args.ids.split(",")}
        questions = [q for q in questions if q["id"] in id_set]
    if args.category:
        questions = [q for q in questions if q.get("category") == args.category]
    if args.limit:
        questions = questions[: args.limit]

    if not questions:
        print("No hay preguntas que coincidan con los filtros.", file=sys.stderr)
        sys.exit(1)

    print(f"Modo:     {'HTTP -> ' + args.url if args.http else 'directo (HybridRAG sin HTTP)'}")
    print(f"Dataset:  {QUESTIONS_FILE.name}  ({len(dataset['questions'])} total, {len(questions)} seleccionadas)")
    print(f"Tolerancia de pagina: +/-{tolerance}")

    if args.http:
        if not check_server(args.url):
            print(f"\nERROR: El servidor no responde en {args.url}")
            print("Inicia el servidor con:  python web_app.py")
            sys.exit(1)
        print("Servidor activo.\n")

    results, elapsed = run_eval(questions, tolerance, args.delay,
                                kw_threshold=args.kw_threshold,
                                http_mode=args.http, base_url=args.url)

    analysis = analyze_results(results)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Guardar JSON detallado
    json_report_path = REPORTS_DIR / f"report_{timestamp}.json"
    with open(json_report_path, "w", encoding="utf-8") as f:
        json.dump(
            {"timestamp": timestamp, "elapsed_s": round(elapsed, 1),
             "analysis": analysis, "results": results},
            f, indent=2, ensure_ascii=False,
        )

    # Guardar Markdown
    md_report_path = REPORTS_DIR / f"report_{timestamp}.md"
    md = generate_markdown_report(analysis, timestamp, elapsed)
    with open(md_report_path, "w", encoding="utf-8") as f:
        f.write(md)

    # Imprimir resumen en consola
    s = analysis["summary"]
    print(f"\n{'='*65}")
    print(f"  RESUMEN FINAL")
    print(f"{'='*65}")
    print(f"  Aprobadas:          {s['passed']}/{s['total']}  ({s['pass_rate']*100:.1f}%)")
    print(f"  Respondibles:       {s['answerable_pass_rate']*100:.1f}%")
    print(f"  Sin respuesta:      {s['no_answer_pass_rate']*100:.1f}%")
    print(f"")
    print(f"  --- Retrieval ---")
    print(f"  Doc hit@K:          {s['retrieval_doc_hit_rate']*100:.1f}%")
    print(f"  Pag hit@K:          {s['retrieval_page_hit_rate']*100:.1f}%")
    print(f"  Recall promedio:    {_fmt(s.get('avg_recall'))}")
    print(f"  MRR promedio:       {_fmt(s.get('avg_mrr'))}")
    print(f"  Precision@K:        {_fmt(s.get('avg_precision_at_k'))}")
    print(f"  Fallos doc miss:    {s['retrieval_doc_miss_count']}")
    print(f"  Recall@1/3/5:       {_fmt(s.get('recall_at_1'))} / {_fmt(s.get('recall_at_3'))} / {_fmt(s.get('recall_at_5'))}")
    rd = analysis.get("rank_distribution", {})
    if rd:
        rk1 = rd.get(1, 0); rk23 = rd.get(2,0)+rd.get(3,0)
        print(f"  Rank dist:          R1={rk1}  R2-3={rk23}  R4+={sum(v for k,v in rd.items() if k>=4)}")
    print(f"")
    print(f"  --- Veredictos por capa ---")
    print(f"  Retrieval:          {s.get('pass_retrieval_rate',0)*100:.1f}%")
    print(f"  Groundedness:       {s.get('pass_groundedness_rate',0)*100:.1f}%")
    print(f"  Generation (kw):    {s.get('pass_generation_rate',0)*100:.1f}%")
    print(f"  Anti-alucinacion:   {s.get('pass_hallucination_rate',0)*100:.1f}%")
    tp = analysis.get("top_problems", {})
    if any(v > 0 for v in tp.values()):
        print(f"")
        print(f"  --- Top problemas ---")
        for k, v in tp.items():
            if v > 0:
                print(f"  {k:<22} {v}")
    print(f"")
    print(f"  --- Respuesta ---")
    print(f"  KW score prom:      {_fmt(s.get('avg_keyword_score'))}  (auxiliar)")
    print(f"  Fallos KW bajo:     {s['llm_kw_miss_count']}")
    print(f"  Fidelidad citas:    {_fmt(s.get('avg_citation_fidelity'))}")
    print(f"  Alucinaciones:      {s['hallucination_count']}")
    print(f"")
    print(f"  --- Latencia ---")
    print(f"  Avg: {s['latency_avg_ms']} ms  P50: {s['latency_p50_ms']} ms  P95: {s['latency_p95_ms']} ms  Max: {s['latency_max_ms']} ms")
    _tt = s.get('latency_avg_ms') or 1
    print(f"  --- Breakdown por etapa (prom) ---")
    for _lbl, _key in [
        ("Embed (BGE)   ", "timing_embed_avg_ms"),
        ("Semantica     ", "timing_semantic_avg_ms"),
        ("BM25          ", "timing_bm25_avg_ms"),
        ("Fusion        ", "timing_fusion_avg_ms"),
        ("Re-ranker     ", "timing_rerank_avg_ms"),
        ("LLM (estim.)  ", "timing_llm_avg_ms"),
    ]:
        _v = s.get(_key)
        if _v is not None:
            _pct = round(_v / _tt * 100, 1)
            print(f"    {_lbl} {_v:>8.1f} ms  ({_pct:>5.1f}%)")
        else:
            print(f"    {_lbl}      N/A")
    print(f"  Tiempo total:       {elapsed:.1f}s")
    print(f"\n  Reporte JSON:  {json_report_path}")
    print(f"  Reporte MD:    {md_report_path}")
    print(f"{'='*65}\n")

    if analysis["failed_cases"]:
        print("Casos fallidos:")
        for fc in analysis["failed_cases"]:
            print(f"  [{fc['id']:>3}] {fc['query'][:70]}")
            for r in fc["reasons"][:2]:
                print(f"        {r}")


if __name__ == "__main__":
    main()
