# -*- coding: utf-8 -*-
"""
FASE 2.1 - Pre-reranking check para los IDs reclasificados (docs confirmados EN corpus
en FASE 0.1) mas los originales RERANKER_O_HYBRID_DESCARTO.

Ejecuta hybrid_search (embedding+BM25, SIN reranker) con top_k=50 y verifica si el
doc esperado aparece. Distingue:
  - HYBRID_NO_ENCONTRO: el doc nunca llega al pool (problema embedding/BM25/fusion)
  - RERANKER_DESCARTO: el doc SI esta en el pool pre-reranking (problema del reranker)

Solo lectura. No modifica config ni codigo del pipeline.
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

OUT_FILE = "_fase2_output.txt"
_lines = []
_builtin_print = print

def print(*args, **kwargs):
    s = " ".join(str(a) for a in args)
    _lines.append(s)
    _builtin_print(*args, **kwargs)

# IDs reclasificados (doc confirmado en corpus) + query + expected_sources
CASES = [
    {"id": 6, "query": "Que hace el comando chmod en Linux?", "expected": ["100 Essential Linux Commands.pdf"]},
    {"id": 9, "query": "Que es SQL injection?", "expected": ["100 web vulnerabilities categorized into various types.pdf"]},
    {"id": 10, "query": "Que es cross-site scripting (XSS)?", "expected": ["100 web vulnerabilities categorized into various types.pdf"]},
    {"id": 12, "query": "Que es information security governance segun CISM?", "expected": ["200 IT Security Job Interview Questions  (2).pdf"]},
    {"id": 18, "query": "Que es la Zero Trust Architecture segun NIST?", "expected": ["API Security Best Practices.pdf", "Implementing a Zero Trust Architecture.pdf", "NIST Zero Trust Architecture.pdf"]},
    {"id": 23, "query": "Cuales son las principales vulnerabilidades web segun OWASP y como se mencionan en las guias de pentest disponibles?", "expected": ["100 web vulnerabilities categorized into various types.pdf", "2023 Pen Testing Report.pdf"]},
    {"id": 26, "query": "Compara las estrategias de un SOC de clase mundial con las recomendaciones de Zero Trust para la microsegmentacion.", "expected": ["11_Strategies_of_a_World_Class_Cybersecurity_Operations_Center.pdf", "API Security Best Practices.pdf"]},
    {"id": 29, "query": "Que comandos Linux son utiles para un analista de seguridad segun los recursos disponibles?", "expected": ["100 Essential Linux Commands.pdf", "101 Linux commands .pdf"]},
    {"id": 42, "query": "Como me preparo para la certificacion?", "expected": ["CISSP All-in-One Exam Guide, Ninth Edition.pdf", "200 IT Security Job Interview Questions  (2).pdf"]},
    {"id": 59, "query": "Como se protege una infraestructura critica segun los marcos de ciberseguridad disponibles en el corpus?", "expected": ["Cyber Security of Critical Infrastructures.pdf"]},
    {"id": 68, "query": "Que es la ingenieria social segun los documentos disponibles?", "expected": ["Social Engineering.pdf"]},
    {"id": 75, "query": "Describe como implementar Zero Trust desde cero en una organizacion: principios, herramientas, fases de madurez y casos de uso mencionados en los documentos disponibles.", "expected": ["Implementing a Zero Trust Architecture.pdf", "API Security Best Practices.pdf"]},
]

# IDs originales RERANKER_O_HYBRID_DESCARTO (para comparar el efecto real del reranker)
ORIGINAL_RERANKER_IDS = [1, 3, 4, 5, 8, 13, 15, 19, 22, 48, 52, 58, 68, 69, 70, 73]


def main():
    print("=" * 70)
    print("FASE 2.1: Pre-reranking check (hybrid_search sin reranker, top_k=50)")
    print("=" * 70)

    from rag_hybrid import HybridRAG
    print("\nInicializando HybridRAG (use_llm=False, sin planner/doc_roles para aislar variables)...")
    rag = HybridRAG(variant="bge", heuristics="balanced", use_llm=False)
    print(f"OK: RAG listo\n")

    results_summary = []

    for case in CASES:
        qid = case["id"]
        query = case["query"]
        expected = case["expected"]

        try:
            results = rag.hybrid_search(query, top_k=50, semantic_weight=0.6)
        except Exception as e:
            print(f"[ID {qid}] ERROR en hybrid_search: {e}")
            continue

        found_docs = []
        for r in results:
            src = (r.get("metadata", {}) or {}).get("source", "") or r.get("source", "")
            found_docs.append(src)

        hit_rank = None
        hit_doc = None
        for exp in expected:
            for rank, src in enumerate(found_docs, start=1):
                if exp.lower() in src.lower() or src.lower() in exp.lower():
                    if hit_rank is None or rank < hit_rank:
                        hit_rank = rank
                        hit_doc = src

        classification = "RERANKER_DESCARTO (doc SI en pool pre-rerank)" if hit_rank else "HYBRID_NO_ENCONTRO (doc NUNCA llega al pool)"
        print(f"\n[ID {qid}] query='{query[:60]}...'")
        print(f"  Expected: {expected}")
        print(f"  Hit en pre-reranking: {'SI' if hit_rank else 'NO'} (rank={hit_rank}, doc='{hit_doc}')")
        print(f"  Clasificacion: {classification}")
        print(f"  Top-5 pre-reranking encontrados: {found_docs[:5]}")

        results_summary.append({
            "id": qid, "hit_rank": hit_rank, "classification": classification
        })

    print("\n" + "=" * 70)
    print("RESUMEN FASE 2.1")
    print("=" * 70)
    hybrid_fail = [r["id"] for r in results_summary if r["hit_rank"] is None]
    reranker_fail = [r["id"] for r in results_summary if r["hit_rank"] is not None]
    print(f"\nHYBRID_NO_ENCONTRO ({len(hybrid_fail)} casos): {hybrid_fail}")
    print(f"RERANKER_DESCARTO ({len(reranker_fail)} casos): {reranker_fail}")

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines))


if __name__ == "__main__":
    main()
