# -*- coding: utf-8 -*-
"""
FASE 3.1-3.2 - Diagnostico BM25 puro para los 5 casos HYBRID_NO_ENCONTRO
confirmados en FASE 2.1 (IDs 10, 12, 23, 42, 75) + los 4 EMBEDDING_BM25_FALLO
originales (17, 41, 46, 49).
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

OUT_FILE = "_fase3_output.txt"
_lines = []
_builtin_print = print

def print(*args, **kwargs):
    s = " ".join(str(a) for a in args)
    _lines.append(s)
    _builtin_print(*args, **kwargs)

CASES = [
    {"id": 10, "query": "Que es cross-site scripting (XSS)?", "expected": "100 web vulnerabilities categorized into various types.pdf"},
    {"id": 12, "query": "Que es information security governance segun CISM?", "expected": "200 IT Security Job Interview Questions  (2).pdf"},
    {"id": 23, "query": "Cuales son las principales vulnerabilidades web segun OWASP y como se mencionan en las guias de pentest disponibles?", "expected": "100 web vulnerabilities categorized into various types.pdf"},
    {"id": 42, "query": "Como me preparo para la certificacion?", "expected": "CISSP All-in-One Exam Guide, Ninth Edition.pdf"},
    {"id": 75, "query": "Describe como implementar Zero Trust desde cero en una organizacion: principios, herramientas, fases de madurez y casos de uso mencionados en los documentos disponibles.", "expected": "Implementing a Zero Trust Architecture.pdf"},
    {"id": 17, "query": "Que es el modelo de responsabilidad compartida en la nube?", "expected": "11_Strategies_of_a_World_Class_Cybersecurity_Operations_Center.pdf"},
    {"id": 41, "query": "Que es un framework de seguridad?", "expected": None},
    {"id": 46, "query": "Que es un agente?", "expected": None},
    {"id": 49, "query": "Que es la nube?", "expected": None},
]

import heapq


def main():
    from rag_hybrid import HybridRAG
    print("Inicializando HybridRAG (use_llm=False)...")
    rag = HybridRAG(variant="bge", heuristics="balanced", use_llm=False)

    for case in CASES:
        qid, query, expected = case["id"], case["query"], case["expected"]
        normalized = rag._normalize_query(query)
        tokens = rag._tokenize_for_bm25(normalized)
        bm25_scores = rag.bm25.get_scores(tokens)

        top_idx = heapq.nlargest(10, range(len(bm25_scores)), key=lambda i: bm25_scores[i])
        print(f"\n[ID {qid}] query='{query[:60]}'")
        print(f"  tokens BM25: {tokens}")
        print(f"  expected_source: {expected}")
        print(f"  Top-10 BM25 puro:")
        expected_found = False
        for rank, idx in enumerate(top_idx, start=1):
            src = rag.all_metadata[idx].get("source", "") if hasattr(rag, 'all_metadata') else "?"
            score = bm25_scores[idx]
            marker = ""
            if expected and expected.lower() in src.lower():
                marker = " <-- EXPECTED"
                expected_found = True
            print(f"    rank={rank:2d} score={score:.3f} src='{src}'{marker}")
        if expected and not expected_found:
            print(f"  RESULTADO: expected_source NO aparece en top-10 BM25 puro")

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines))


if __name__ == "__main__":
    main()
