# -*- coding: utf-8 -*-
"""
FASE 0.1 y 0.5(E1) - Diagnostico de ground truth y corpus.
Script temporal de solo lectura. No modifica el pipeline ni el indice.

Uso:
    python _fase0_diagnostico.py
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import chromadb
from collections import defaultdict

DB_PATH = "chroma_bge_m3"
COLLECTION_NAME = "cybersec_docs_bge_m3"
OUT_FILE = "_fase0_output.txt"
_lines = []
_builtin_print = print

def print(*args, **kwargs):
    s = " ".join(str(a) for a in args)
    _lines.append(s)
    _builtin_print(*args, **kwargs)

# Docs del ground truth que nunca aparecen en resultados (FASE 0.1)
DOCS_TO_CHECK = [
    "100 Essential Linux Commands.pdf",
    "100 web vulnerabilities categorized into various types.pdf",
    "ISO 42001 2023 A Guide to Implementation.pdf",
    "200 IT Security Job Interview Questions  (2).pdf",
    "API Security Best Practices.pdf",
    "Cyber Security of Critical Infrastructures.pdf",
    "Social Engineering.pdf",
    # Docs NIST relevantes para corregir ID 11 e ID 18 (C3)
    "NIST Cybersecurity Framework 2.0. Implementation Guide.pdf",
    "NIST SP 1800-28.pdf",
    "Implementing a Zero Trust Architecture.pdf",
    "Zero Trust Maturity Model.pdf",
    "Playbook for Implementing Zero Trust Security.pdf",
    "A Complete Guide to Cybersecurity Risk Management.pdf",
]


def main():
    print("=" * 70)
    print("FASE 0.1: Verificacion de existencia en ChromaDB")
    print("=" * 70)

    client = chromadb.PersistentClient(path=DB_PATH)

    try:
        col = client.get_collection(COLLECTION_NAME)
    except Exception as e:
        print(f"ERROR: no se pudo abrir la coleccion '{COLLECTION_NAME}': {e}")
        print("\nColecciones disponibles:")
        for c in client.list_collections():
            print(f"  - {c.name if hasattr(c, 'name') else c}")
        return

    total_count = col.count()
    print(f"\nColeccion '{COLLECTION_NAME}' -> {total_count} chunks totales\n")

    print("-" * 70)
    print("Verificacion doc por doc (ground truth faltante + alternativas NIST/ZT):")
    print("-" * 70)

    found_summary = {}
    for doc in DOCS_TO_CHECK:
        try:
            result = col.get(where={"source": {"$eq": doc}}, limit=5)
            n = len(result.get("ids", []))
        except Exception as e:
            n = f"ERROR: {e}"
        found_summary[doc] = n
        status = "EN CORPUS" if isinstance(n, int) and n > 0 else "NO EN CORPUS"
        print(f"  [{status:>13}] {doc}  (chunks encontrados: {n})")

    print("\n" + "=" * 70)
    print("FASE 0.5 (E1): Auditoria de duplicados / documentos similares")
    print("=" * 70)

    # Obtener todos los sources unicos y su conteo de chunks
    all_data = col.get(include=["metadatas"])
    metadatas = all_data.get("metadatas", [])
    source_counts = defaultdict(int)
    for m in metadatas:
        src = m.get("source", "UNKNOWN") if m else "UNKNOWN"
        source_counts[src] += 1

    print(f"\nTotal documentos unicos en corpus: {len(source_counts)}")
    print(f"Total chunks: {sum(source_counts.values())}\n")

    # Buscar pares de titulos similares (heuristica simple: normalizar y comparar)
    def normalize_title(t):
        t = t.lower()
        for ch in [".pdf", "  ", "-", "_", "(", ")"]:
            t = t.replace(ch, " ")
        return " ".join(t.split())

    sources = list(source_counts.keys())
    normalized = {s: normalize_title(s) for s in sources}

    print("-" * 70)
    print("Pares de documentos con titulos potencialmente similares:")
    print("-" * 70)

    def word_overlap(a, b):
        wa, wb = set(a.split()), set(b.split())
        if not wa or not wb:
            return 0.0
        return len(wa & wb) / len(wa | wb)

    pairs_found = 0
    for i, s1 in enumerate(sources):
        for s2 in sources[i + 1:]:
            sim = word_overlap(normalized[s1], normalized[s2])
            if sim >= 0.5:
                pairs_found += 1
                print(f"  similitud={sim:.2f}  '{s1}' ({source_counts[s1]} chunks)  <->  '{s2}' ({source_counts[s2]} chunks)")

    if pairs_found == 0:
        print("  Ningun par con similitud >= 0.5 encontrado.")

    print(f"\nTotal pares sospechosos: {pairs_found}")

    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    en_corpus = [d for d, n in found_summary.items() if isinstance(n, int) and n > 0]
    no_en_corpus = [d for d, n in found_summary.items() if not (isinstance(n, int) and n > 0)]
    print(f"Docs verificados EN corpus ({len(en_corpus)}):")
    for d in en_corpus:
        print(f"  - {d}")
    print(f"\nDocs verificados NO en corpus ({len(no_en_corpus)}):")
    for d in no_en_corpus:
        print(f"  - {d}")

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines))


if __name__ == "__main__":
    main()
