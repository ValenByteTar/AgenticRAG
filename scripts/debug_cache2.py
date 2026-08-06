"""Debug: check chunk hashes with real extractor chunker."""
import hashlib
import json
from pathlib import Path

from knowledge_builder.frontend.llm_entity_extractor import LLMEntityExtractor

ext = LLMEntityExtractor(max_docs=0, use_cache=False, verbose=False)
text = Path("data/extracted_texts/02 ISOIEC 27001 Implementation Guide.txt").read_text(encoding="utf-8")
chunks = ext._chunk_text(text, 4000)
print(f"Real chunker: {len(chunks)} chunks")

# Load cached meta
meta = json.loads(Path("cache/02-isoiec-27001-implementation-guide-pdf/meta.json").read_text(encoding="utf-8"))
chunks_meta = meta.get("chunks", {})
print(f"Cache meta: {len(chunks_meta)} chunks")
print()

for i, chunk in enumerate(chunks[:15]):
    actual_hash = hashlib.sha256(chunk.encode("utf-8")).hexdigest()[:16]
    stored_hash = chunks_meta.get(str(i), {}).get("hash", "?")
    match = "OK" if actual_hash == stored_hash else "MISMATCH"
    print(f"  chunk {i}: actual={actual_hash} stored={stored_hash} {match} len={len(chunk)}")

# Also check: does the extractor pass chunk_size=4000 or self.chunk_size?
print(f"\nExtractor chunk_size: {ext.chunk_size}")
