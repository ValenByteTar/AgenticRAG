"""Predicate Audit Script (Fase 3).

Analyzes the entity_relations Warm Artifact and reports:
  - Predicate distribution (which predicates are used, how often)
  - Out-of-catalog predicates (not in the controlled catalog)
  - Fallback coverage (which out-of-catalog predicates have a fallback mapping)
  - Unmapped predicates (no fallback, defaulting to "references")
  - Edge attributes coverage (how many relations have attributes)

Usage:
    python scripts/predicate_audit.py [--artifact-path path/to/entity_relations.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from collections import Counter


_CATALOG_PREDICATES = {
    "equivalent_to", "depends_on", "implements", "extends",
    "references", "governs", "contains", "uses", "creates",
}

_FALLBACK_MAP = {
    "related_to": "references",
    "requires": "depends_on",
    "contradicts": "references",
    "provides": "creates",
    "includes": "contains",
    "describes": "references",
    "covers": "references",
    "applies_to": "references",
    "supports": "implements",
    "aligned_with": "equivalent_to",
    "complies_with": "governs",
    "defines": "creates",
    "belongs_to": "contains",
    "part_of": "contains",
    "supersedes": "extends",
    "located_in": "references",
    "certifies": "governs",
    "compares_with": "references",
    "enforces": "governs",
    "mandates": "governs",
    "replaces": "extends",
    "based_on": "depends_on",
    "composed_of": "contains",
    "utilizes": "uses",
    "specializes": "extends",
    "maps_to": "references",
    "documents": "references",
    "specifies": "creates",
    "categorizes": "references",
    "groups": "contains",
}


def audit(artifact_path: Path) -> None:
    if not artifact_path.exists():
        print(f"[ERROR] Artifact not found: {artifact_path}")
        sys.exit(1)

    data = json.loads(artifact_path.read_text(encoding="utf-8"))
    relations = data.get("relations", [])

    if not relations:
        print("[INFO] No relations in artifact. Nothing to audit.")
        return

    total = len(relations)
    pred_counts = Counter()
    out_of_catalog = Counter()
    unmapped = Counter()
    with_attributes = 0
    attribute_counts = Counter()

    for rel in relations:
        pred = rel.get("predicate", "")
        pred_counts[pred] += 1

        if pred not in _CATALOG_PREDICATES:
            out_of_catalog[pred] += 1
            if pred not in _FALLBACK_MAP:
                unmapped[pred] += 1

        attrs = rel.get("attributes", [])
        if attrs:
            with_attributes += 1
            for a in attrs:
                attribute_counts[a] += 1

    print(f"\n{'='*60}")
    print(f"PREDICATE AUDIT REPORT")
    print(f"{'='*60}")
    print(f"Total relations: {total}")
    print(f"Relations with edge attributes: {with_attributes} ({with_attributes/total*100:.1f}%)")

    print(f"\n--- Predicate Distribution ---")
    for pred, count in pred_counts.most_common():
        marker = "  " if pred in _CATALOG_PREDICATES else "!!"
        print(f"  {marker} {pred:40s} {count:5d} ({count/total*100:.1f}%)")

    if out_of_catalog:
        print(f"\n--- Out-of-Catalog Predicates ({len(out_of_catalog)} unique) ---")
        for pred, count in out_of_catalog.most_common():
            fallback = _FALLBACK_MAP.get(pred, "references (default)")
            print(f"  {pred:40s} count={count:3d}  fallback={fallback}")
    else:
        print(f"\n--- All predicates are in catalog. ---")

    if unmapped:
        print(f"\n--- UNMAPPED Predicates (no fallback, defaulting to 'references') ---")
        for pred, count in unmapped.most_common():
            print(f"  {pred:40s} count={count:3d}")
    else:
        print(f"\n--- All out-of-catalog predicates have fallback mappings. ---")

    if attribute_counts:
        print(f"\n--- Edge Attribute Distribution ---")
        for attr, count in attribute_counts.most_common():
            print(f"  {attr:40s} {count:5d}")
    else:
        print(f"\n--- No edge attributes found in any relation. ---")

    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  In-catalog:     {total - sum(out_of_catalog.values())} / {total}")
    print(f"  Out-of-catalog: {sum(out_of_catalog.values())} / {total}")
    print(f"  Unmapped:       {sum(unmapped.values())} / {total}")
    print(f"  With attrs:     {with_attributes} / {total}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--artifact-path":
        path = Path(args[1])
    else:
        path = Path("data/warm_artifacts/artifacts/entity_relations.json")
    audit(path)
