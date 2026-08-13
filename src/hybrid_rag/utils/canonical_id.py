"""Canonical Document Identity (RES-010, Fase 0A).

Single source of truth for generating canonical_doc_id from any filename.
All components (Chroma, DocCards, Builder, Retrieval) must use this function
to produce the same identity for the same document.

canonical_doc_id = "doc:{slug(filename_without_extension)}"
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path


def _normalize_text(s: str) -> str:
    s = s.lower().strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s


def slugify(s: str) -> str:
    n = _normalize_text(s)
    n = re.sub(r"[^a-z0-9]+", "-", n)
    n = n.strip("-")
    return n or "unknown"


def canonical_doc_id(filename: str) -> str:
    """Generate the canonical document ID from a filename.

    Args:
        filename: Any filename (e.g. "ISO 27001 Guide.pdf", "iso-27001-guide.txt")

    Returns:
        canonical_doc_id string (e.g. "doc:iso-27001-guide")
    """
    stem = Path(filename).stem
    return f"doc:{slugify(stem)}"
