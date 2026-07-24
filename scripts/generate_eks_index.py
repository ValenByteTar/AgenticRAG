"""
Genera el indice EKS a partir de los documentos en knowledge/.

Parsea el frontmatter YAML de cada .md y produce:
- knowledge/INDEX.md  — tabla legible para humanos
- knowledge/_eks_index.json — maquina para consumo programatico (Skills, Cascade)

Uso:
    python scripts/generate_eks_index.py
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# --- Config -------------------------------------------------------------------

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"
INDEX_MD = KNOWLEDGE_DIR / "INDEX.md"
INDEX_JSON = KNOWLEDGE_DIR / "_eks_index.json"

CATEGORY_ORDER = ["decision", "experiment", "benchmark", "pattern", "postmortem", "research"]
CATEGORY_LABELS = {
    "decision": "Decisions",
    "experiment": "Experiments",
    "benchmark": "Benchmarks",
    "pattern": "Patterns",
    "postmortem": "Postmortems",
    "research": "Research",
}
CATEGORY_PREFIX = {
    "decision": "DEC",
    "experiment": "EXP",
    "benchmark": "BM",
    "pattern": "PAT",
    "postmortem": "PM",
    "research": "RES",
}

# --- Model --------------------------------------------------------------------


@dataclass
class EksEntry:
    id: str
    category: str
    status: str
    title: str
    path: str
    created: str = ""
    updated: str = ""
    author: str = ""
    components: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    related: List[str] = field(default_factory=list)
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None


# --- Frontmatter parser -------------------------------------------------------


def parse_frontmatter(text: str) -> Dict[str, Any]:
    """Extrae el bloque YAML entre --- y --- al inicio del archivo."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return {}
    yaml_block = match.group(1)

    result: Dict[str, Any] = {}
    current_key: Optional[str] = None
    current_list: List[str] = []

    for line in yaml_block.split("\n"):
        stripped = line.strip()

        # Inline list: key: [a, b, c]
        m_inline = re.match(r"^(\w+):\s*\[(.*)\]\s*$", stripped)
        if m_inline:
            key, val = m_inline.group(1), m_inline.group(2)
            items = [v.strip().strip("'\"") for v in val.split(",") if v.strip()]
            result[key] = items
            current_key = None
            continue

        # key: value
        m_kv = re.match(r"^(\w+):\s*(.*)$", stripped)
        if m_kv and not stripped.startswith("-"):
            key, val = m_kv.group(1), m_kv.group(2).strip()
            if val == "" or val.lower() == "null":
                result[key] = None
                current_key = key
                current_list = []
            else:
                result[key] = val.strip("'\"")
                current_key = None
            continue

        # List item: - value
        if stripped.startswith("-") and current_key:
            current_list.append(stripped.lstrip("- ").strip("'\""))
            result[current_key] = current_list
            continue

    return result


def extract_title(text: str) -> str:
    """Extrae el primer encabezado # del documento."""
    for line in text.split("\n"):
        m = re.match(r"^#\s+(.+)$", line)
        if m:
            return m.group(1).strip()
    return ""


# --- Main ---------------------------------------------------------------------


def collect_entries() -> List[EksEntry]:
    entries: List[EksEntry] = []
    for md_path in sorted(KNOWLEDGE_DIR.rglob("*.md")):
        rel = md_path.relative_to(KNOWLEDGE_DIR)

        # Skip meta files
        if rel.parts[0] in ("_schema", "_templates"):
            continue
        if rel.name == "README.md":
            continue

        text = md_path.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if not fm or "id" not in fm:
            continue

        title = extract_title(text)
        entry = EksEntry(
            id=fm.get("id", ""),
            category=fm.get("category", ""),
            status=fm.get("status", ""),
            title=title,
            path=str(rel).replace("\\", "/"),
            created=fm.get("created", ""),
            updated=fm.get("updated", ""),
            author=fm.get("author", ""),
            components=fm.get("components", []) or [],
            tags=fm.get("tags", []) or [],
            related=fm.get("related", []) or [],
            supersedes=fm.get("supersedes"),
            superseded_by=fm.get("superseded_by"),
        )
        entries.append(entry)
    return entries


def build_index_md(entries: List[EksEntry]) -> str:
    lines: List[str] = []
    lines.append("# EKS Index")
    lines.append("")
    lines.append(f"Generado: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append(f"Documentos indexados: {len(entries)}")
    lines.append("")
    lines.append("> Auto-generado por `scripts/generate_eks_index.py`. No editar a mano.")
    lines.append("")

    # Group by category
    by_cat: Dict[str, List[EksEntry]] = {}
    for e in entries:
        by_cat.setdefault(e.category, []).append(e)

    for cat in CATEGORY_ORDER:
        cat_entries = by_cat.get(cat, [])
        if not cat_entries:
            continue
        label = CATEGORY_LABELS.get(cat, cat.title())
        lines.append(f"## {label} ({len(cat_entries)})")
        lines.append("")
        lines.append("| ID | Status | Title | Updated | Components |")
        lines.append("|----|--------|-------|---------|------------|")
        for e in sorted(cat_entries, key=lambda x: x.id):
            comps = ", ".join(e.components) if e.components else "-"
            title_short = e.title if len(e.title) <= 80 else e.title[:77] + "..."
            lines.append(f"| `{e.id}` | {e.status} | [{title_short}]({e.path}) | {e.updated} | {comps} |")
        lines.append("")

    # Cross-references
    lines.append("## Cross-references")
    lines.append("")
    for e in sorted(entries, key=lambda x: x.id):
        refs = e.related or []
        if e.supersedes:
            refs.append(f"supersedes:{e.supersedes}")
        if e.superseded_by:
            refs.append(f"superseded_by:{e.superseded_by}")
        if refs:
            lines.append(f"- **{e.id}** -> {', '.join(refs)}")
    lines.append("")

    return "\n".join(lines)


def build_index_json(entries: List[EksEntry]) -> str:
    data = {
        "generated": datetime.now().strftime("%Y-%m-%d"),
        "count": len(entries),
        "entries": [asdict(e) for e in entries],
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


def main() -> int:
    entries = collect_entries()
    if not entries:
        print("WARN: no se encontraron documentos con frontmatter valido")
        return 1

    INDEX_MD.write_text(build_index_md(entries), encoding="utf-8")
    INDEX_JSON.write_text(build_index_json(entries), encoding="utf-8")

    print(f"OK: {len(entries)} documentos indexados")
    print(f"  -> {INDEX_MD}")
    print(f"  -> {INDEX_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
