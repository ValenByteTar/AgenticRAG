# -*- coding: utf-8 -*-
"""
Diagnostico dirigido de la anomalia ID 68: Social Engineering.pdf en rank 1
pre-reranking pero pass_retrieval=false en el eval completo.

Ejecuta hybrid_search + rerank_results explicitamente y compara scores.
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

OUT_FILE = "_fase2_anomalia68_output.txt"
_lines = []
_builtin_print = print

def print(*args, **kwargs):
    s = " ".join(str(a) for a in args)
    _lines.append(s)
    _builtin_print(*args, **kwargs)


def main():
    from rag_hybrid import HybridRAG
    print("Inicializando HybridRAG (use_llm=False)...")
    rag = HybridRAG(variant="bge", heuristics="balanced", use_llm=False)

    query = "Que es la ingenieria social segun los documentos disponibles?"

    print("=" * 70)
    print("PRE-RERANKING (hybrid_search top_k=20, = candidate_pool)")
    print("=" * 70)
    pre = rag.hybrid_search(query, top_k=20, semantic_weight=0.6)
    for i, r in enumerate(pre, start=1):
        src = (r.get("metadata", {}) or {}).get("source", "") or r.get("source", "")
        text_preview = (r.get("text", "") or r.get("document", "") or "")[:80].replace("\n", " ")
        print(f"  rank={i:2d} hybrid_score={r.get('hybrid_score', r.get('score', 'N/A'))} src='{src}' text='{text_preview}...'")

    print("\n" + "=" * 70)
    print("POST-RERANKING (rerank_results top_k=10)")
    print("=" * 70)
    try:
        post = rag._retrieval.rerank_results(query, pre, top_k=10)
    except Exception as e:
        print(f"ERROR llamando rerank_results directamente: {e}")
        print("Intentando via rag.rerank_results...")
        post = rag.rerank_results(query, pre, top_k=10) if hasattr(rag, 'rerank_results') else []

    for i, r in enumerate(post, start=1):
        src = (r.get("metadata", {}) or {}).get("source", "") or r.get("source", "")
        text_preview = (r.get("text", "") or r.get("document", "") or "")[:80].replace("\n", " ")
        print(f"  rank={i:2d} rerank_score={r.get('rerank_score', 'N/A')} rerank_norm={r.get('rerank_norm', 'N/A')} "
              f"final_score={r.get('final_score', 'N/A')} hybrid_score={r.get('hybrid_score', 'N/A')} src='{src}' text='{text_preview}...'")

    print("\n" + "=" * 70)
    print("BUSQUEDA ESPECIFICA: chunks de Social Engineering.pdf en el pool pre-rerank")
    print("=" * 70)
    se_chunks = [r for r in pre if "social engineering" in ((r.get("metadata", {}) or {}).get("source", "") or r.get("source", "")).lower()]
    print(f"Total chunks de Social Engineering.pdf en pool: {len(se_chunks)}")
    for i, r in enumerate(se_chunks, start=1):
        text_full = (r.get("text", "") or r.get("document", "") or "")
        print(f"  [{i}] hybrid_score={r.get('hybrid_score', r.get('score'))} len_text={len(text_full)} preview='{text_full[:150]}'")

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines))


if __name__ == "__main__":
    main()
