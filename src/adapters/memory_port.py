"""
MemoryPortAdapter: implementacion concreta del contrato MemoryPort (ADR-0009).

Envuelve MemorySystem (SQLite) y agrega provenance a cada record.
Read-only en Fase 5; write es controlado y verificado (diferido a Fase 7).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class MemoryPortAdapter:
    """
    Adapter que satisface MemoryPort (ADR-0009) sobre MemorySystem.

    Provenance: cada record incluye source, timestamp, origin y record_id.
    Read es directo; write es passthrough pero marca origin='kernel_write'.
    """

    def __init__(self, memory_system: Any) -> None:
        self._mem = memory_system

    def read(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        try:
            hits = list(self._mem.search_memory(query, limit=limit) or [])
        except Exception:
            return []
        for h in hits:
            h.setdefault("source", "user_memory")
            h.setdefault("origin", "user_input")
            h.setdefault("provenance", {
                "source": h.get("source", "user_memory"),
                "origin": h.get("origin", "user_input"),
                "record_id": h.get("id"),
                "timestamp": h.get("timestamp"),
            })
        return hits

    def write(self, record: Dict[str, Any]) -> bool:
        try:
            question = record.get("question") or record.get("query") or ""
            answer = record.get("answer") or record.get("content") or ""
            if not question or not answer:
                return False
            category = record.get("category")
            keywords = record.get("keywords")
            rid = self._mem.add_knowledge(question, answer, category=category, keywords=keywords)
            return rid is not None and rid > 0
        except Exception:
            return False
