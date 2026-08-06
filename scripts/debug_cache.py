"""Debug cache state for a specific doc."""
import json
import hashlib
from pathlib import Path

doc_slug = "02-isoiec-27001-implementation-guide-pdf"
cache_dir = Path("cache") / doc_slug
meta_file = cache_dir / "meta.json"

if not meta_file.exists():
    print(f"No cache found for {doc_slug}")
    exit()

meta = json.loads(meta_file.read_text(encoding="utf-8"))
chunks_meta = meta.get("chunks", {})
print(f"Total chunks in meta: {len(chunks_meta)}")
print()

# Check which chunks have files
for idx in sorted(chunks_meta.keys(), key=int)[:15]:
    chunk_file = cache_dir / f"chunk_{idx}.kir.json"
    has_file = chunk_file.exists()
    stored_hash = chunks_meta[idx].get("hash", "?")
    print(f"  chunk {idx}: hash={stored_hash}, file={'YES' if has_file else 'NO'}")

# Now check: are the chunks being re-processed because hash changed?
# Read the actual document and re-chunk it to see if hashes match
print()
print("=== Checking if chunk text hashes match ===")

# Read the doc
doc_path = Path("data/extracted_texts/02 ISOIEC 27001 Implementation Guide.txt")
if doc_path.exists():
    text = doc_path.read_text(encoding="utf-8")
    chunk_size = 4000
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        # Try to break at paragraph boundary
        if end < len(text):
            last_nl = text.rfind("\n", start, end)
            if last_nl > start + chunk_size // 2:
                end = last_nl
        chunks.append(text[start:end])
        start = end

    print(f"Re-chunked: {len(chunks)} chunks (meta has {len(chunks_meta)})")
    for i, chunk in enumerate(chunks[:15]):
        actual_hash = hashlib.sha256(chunk.encode("utf-8")).hexdigest()[:16]
        stored_hash = chunks_meta.get(str(i), {}).get("hash", "?")
        match = "OK" if actual_hash == stored_hash else "MISMATCH"
        print(f"  chunk {i}: actual={actual_hash} stored={stored_hash} {match}")
else:
    print(f"Doc not found: {doc_path}")
