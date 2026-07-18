# -*- coding: utf-8 -*-
"""Verificacion rapida FASE 4.BIS: BM25 con lexical expansion vs sin ella."""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

QUERIES = [
    "Que es el modelo de responsabilidad compartida en la nube?",
    "Que es un agente?",
    "Que es la nube?",
]


def main():
    from rag_hybrid import HybridRAG
    from retrieval_engine import expand_query_for_bm25
    rag = HybridRAG(variant="bge", heuristics="balanced", use_llm=False)

    for q in QUERIES:
        normalized = rag._normalize_query(q)
        expanded = expand_query_for_bm25(normalized)
        tokens_before = rag._tokenize_for_bm25(normalized)
        tokens_after = rag._tokenize_for_bm25(expanded)
        scores_before = rag.bm25.get_scores(tokens_before)
        scores_after = rag.bm25.get_scores(tokens_after)
        print(f"\nquery: '{q}'")
        print(f"  expandida: '{expanded}'")
        print(f"  max score ANTES: {max(scores_before):.3f}")
        print(f"  max score DESPUES: {max(scores_after):.3f}")


if __name__ == "__main__":
    main()
