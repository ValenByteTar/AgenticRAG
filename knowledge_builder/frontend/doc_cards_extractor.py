"""DocCardsExtractor — lee doc_roles.json a KIR (RES-002 §3.3).

Fuente: ``doc_cards.py`` (build_doc_cards, _guess_role_by_name,
_infer_attributes_presence, _estimate_centrality).

Produce DocumentClaim por cada documento con:
    - rol, atributos, centralidad, entity_mentions, summary
    - evidence desde el corpus (source_path)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from ..kir import DocumentClaim, EntityClaim, EvidenceItem, KIR, normalize_text, slugify


_EXTRACTOR_ID = "deterministic:doc-cards"


class DocCardsExtractor:
    """Extrae conocimiento documental desde doc_roles.json o dict equivalente."""

    def __init__(self, doc_roles: Optional[Mapping[str, Any]] = None, path: Optional[Path | str] = None):
        if doc_roles is not None:
            self.doc_roles = dict(doc_roles)
        elif path is not None:
            p = Path(path)
            if p.exists():
                self.doc_roles = json.loads(p.read_text(encoding="utf-8"))
            else:
                self.doc_roles = {}
        else:
            self.doc_roles = {}

    def extract(self) -> KIR:
        kir = KIR(metadata={"extractor": _EXTRACTOR_ID})
        docs = self.doc_roles.get("docs", {}) if isinstance(self.doc_roles, dict) else {}
        for source_path, info in docs.items():
            info = info or {}
            name = info.get("name", source_path)
            role = info.get("role", "other")
            attributes = info.get("attributes_index", info.get("attributes", []))
            centrality = float(info.get("centrality", 0.0))
            entity_mentions = info.get("entities_index", info.get("entity_mentions", []))
            summary = info.get("summary", "")

            doc_claim = DocumentClaim(
                source_path=source_path,
                name=name,
                role=role,
                attributes=list(attributes),
                centrality=centrality,
                entity_mentions=[normalize_text(e) for e in entity_mentions],
                summary=summary,
                extractor_id=_EXTRACTOR_ID,
                confidence=0.7,
                evidence=[EvidenceItem(source_doc_id=f"doc:{slugify(name)}", quote=summary[:200])],
                raw=dict(info),
            )
            kir.document_claims.append(doc_claim)

            for ent_mention in entity_mentions:
                ent_norm = normalize_text(ent_mention)
                if ent_norm:
                    kir.entity_claims.append(EntityClaim(
                        surface_form=ent_mention,
                        canonical_name=ent_norm,
                        entity_types=[],
                        extractor_id=_EXTRACTOR_ID,
                        confidence=0.6,
                        evidence=[EvidenceItem(source_doc_id=f"doc:{slugify(name)}", quote=f"Entity mentioned in {name}")],
                        raw={"source": "doc_cards", "doc": source_path},
                    ))
        return kir
