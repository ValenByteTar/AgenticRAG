import sqlite3
from pathlib import Path

DB = str(Path(__file__).parent.parent.parent / "chroma_bge_m3" / "chroma.sqlite3")
c = sqlite3.connect(DB)
cur = c.cursor()
cur.execute("SELECT name FROM collections")
for (name,) in cur.fetchall():
    cur.execute("""
        SELECT COUNT(e.id) FROM embeddings e
        JOIN segments s ON e.segment_id = s.id
        JOIN collections col ON s.collection = col.id
        WHERE col.name = ?
    """, (name,))
    count = cur.fetchone()[0]
    print(f"{name}: {count} embeddings")
c.close()
