"""
Utilitario read-only para anclar verdad de terreno (source, page) a partir de un
fragmento de texto conocido. Consulta directamente la base SQLite de Chroma sin
modificarla.

Uso:
    python tests/eval/build_ground_truth.py --search "The five functions of the NIST CSF"
    python tests/eval/build_ground_truth.py --search "PCI DSS requirement 6" --limit 5
    python tests/eval/build_ground_truth.py --list-sources
"""

import sqlite3
import argparse
import os
import sys
from pathlib import Path

CHROMA_DB = str(Path(__file__).parent.parent.parent / "chroma_bge_m3" / "chroma.sqlite3")

# Nombre real de la coleccion poblada (puede ser la legacy mientras re-ingesta corre)
COLLECTION_CANDIDATES = ["cybersec_docs_bge_m3", "crom_protocols_bge_m3"]
# Nota: se prueba cybersec_docs_bge_m3 primero (nueva); si esta vacia o no existe
# se cae a crom_protocols_bge_m3 (mismos docs, nombre legacy).


def _get_conn():
    if not os.path.exists(CHROMA_DB):
        print(f"ERROR: No se encontro la base Chroma en {CHROMA_DB}", file=sys.stderr)
        sys.exit(1)
    return sqlite3.connect(f"file:{CHROMA_DB}?mode=ro", uri=True)


def _get_segment_ids(cur):
    """Devuelve los segment_id del segmento VECTOR de la coleccion preferida."""
    for name in COLLECTION_CANDIDATES:
        cur.execute("SELECT id FROM collections WHERE name = ?", (name,))
        row = cur.fetchone()
        if row:
            coll_id = row[0]
            cur.execute("SELECT id FROM segments WHERE collection = ?", (coll_id,))
            segs = [r[0] for r in cur.fetchall()]
            return segs, name
    cur.execute("SELECT id, name FROM collections")
    rows = cur.fetchall()
    if rows:
        coll_id, cname = rows[0]
        print(f"ADVERTENCIA: se usa primera coleccion encontrada: {cname}", file=sys.stderr)
        cur.execute("SELECT id FROM segments WHERE collection = ?", (coll_id,))
        segs = [r[0] for r in cur.fetchall()]
        return segs, cname
    print("ERROR: No hay colecciones en la base Chroma", file=sys.stderr)
    sys.exit(1)


def list_sources(limit=50):
    """Lista los top-N documentos por cantidad de chunks."""
    conn = _get_conn()
    cur = conn.cursor()
    seg_ids, cname = _get_segment_ids(cur)
    placeholders = ",".join("?" * len(seg_ids))
    cur.execute(
        f"""
        SELECT em.string_value, COUNT(e.id) as n
        FROM embeddings e
        JOIN embedding_metadata em ON em.id = e.id
        WHERE e.segment_id IN ({placeholders})
          AND em.key = 'source'
        GROUP BY em.string_value
        ORDER BY n DESC
        LIMIT ?
        """,
        seg_ids + [limit],
    )
    rows = cur.fetchall()
    conn.close()
    print(f"\nColeccion: {cname}")
    print(f"{'Chunks':>8}  Fuente")
    print("-" * 80)
    for src, count in rows:
        print(f"{count:>8}  {src}")


def search_text(keyword, limit=10):
    """
    Busca chunks cuyo texto contenga la cadena (case-insensitive) y devuelve
    (source, page, chunk_index, texto_parcial).
    """
    conn = _get_conn()
    cur = conn.cursor()
    seg_ids, cname = _get_segment_ids(cur)
    placeholders = ",".join("?" * len(seg_ids))

    cur.execute(
        f"""
        SELECT
            e.id,
            src.string_value  AS source,
            pg.int_value      AS page,
            ci.int_value      AS chunk_index,
            doc.string_value  AS text
        FROM embeddings e
        LEFT JOIN embedding_metadata src ON src.id = e.id AND src.key = 'source'
        LEFT JOIN embedding_metadata pg  ON pg.id  = e.id AND pg.key  = 'page'
        LEFT JOIN embedding_metadata ci  ON ci.id  = e.id AND ci.key  = 'chunk_index'
        LEFT JOIN embedding_metadata doc ON doc.id = e.id AND doc.key = 'chroma:document'
        WHERE e.segment_id IN ({placeholders})
          AND LOWER(doc.string_value) LIKE LOWER(?)
        ORDER BY src.string_value, pg.int_value
        LIMIT ?
        """,
        seg_ids + [f"%{keyword}%", limit],
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print(f"\nNo se encontraron chunks con '{keyword}' en coleccion '{cname}'")
        return []

    results = []
    print(f"\nColeccion: {cname}")
    print(f"Resultados para: '{keyword}'  ({len(rows)} chunks)\n")
    for eid, src, page, ci, text in rows:
        snippet = (text or "")[:200].replace("\n", " ")
        print(f"  [{src}]  p.{page}  chunk#{ci}")
        print(f"  {snippet}")
        print()
        results.append({"source": src, "page": page, "chunk_index": ci})
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Utilidad read-only para anclar ground-truth en Chroma")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--search", metavar="KEYWORD", help="Busca chunks que contengan el texto")
    group.add_argument("--list-sources", action="store_true", help="Lista top fuentes por numero de chunks")
    parser.add_argument("--limit", type=int, default=10, help="Maximo de resultados (default 10)")
    args = parser.parse_args()

    if args.list_sources:
        list_sources(args.limit)
    else:
        search_text(args.search, args.limit)
