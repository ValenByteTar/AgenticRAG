"""Count cached vs unparseable chunks."""
from pathlib import Path
import json

cache = Path("cache")
total_cached = 0
total_meta = 0

for meta_file in cache.rglob("meta.json"):
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        chunks_meta = meta.get("chunks", {})
        total_meta += len(chunks_meta)
    except Exception:
        pass

for f in cache.rglob("chunk_*.kir.json"):
    total_cached += 1

print(f"Cached chunks (files): {total_cached}")
print(f"Meta entries: {total_meta}")
print(f"Unparseable (meta - files): {total_meta - total_cached}")
