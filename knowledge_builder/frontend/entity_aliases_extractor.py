"""EntityAliasesExtractor — lee el dict entity_aliases hardcoded a KIR (RES-002 §3.3).

Fuente: ``rag_hybrid.py`` lineas 519-535 (dict entity_aliases con 7 entradas).

Cada entrada ``canonical: [alias1, alias2, ...]`` produce:
    - Un EntityClaim para el canonico
    - Un AliasClaim por cada alias -> canonico
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

from ..kir import AliasClaim, EntityClaim, EvidenceItem, KIR, normalize_text


_EXTRACTOR_ID = "deterministic:entity-aliases-dict"


class EntityAliasesExtractor:
    """Extrae entidades y aliases desde el dict entity_aliases hardcoded."""

    def __init__(self, aliases_dict: Mapping[str, List[str]]):
        self.aliases_dict = dict(aliases_dict or {})

    def extract(self) -> KIR:
        kir = KIR(metadata={"extractor": _EXTRACTOR_ID})
        for canonical_raw, aliases in self.aliases_dict.items():
            canonical = normalize_text(canonical_raw)
            entity_claim = EntityClaim(
                surface_form=canonical_raw,
                canonical_name=canonical,
                entity_types=["concept"],
                extractor_id=_EXTRACTOR_ID,
                confidence=0.9,
                evidence=[EvidenceItem(source_doc_id="doc:entity-aliases-dict", quote=f"Hardcoded alias: {canonical_raw} -> {aliases}")],
                raw={"canonical": canonical_raw, "aliases": list(aliases)},
            )
            kir.entity_claims.append(entity_claim)

            for alias_raw in aliases:
                alias = normalize_text(alias_raw)
                if alias == canonical:
                    continue
                kir.alias_claims.append(AliasClaim(
                    alias=alias,
                    canonical_name=canonical,
                    extractor_id=_EXTRACTOR_ID,
                    confidence=0.9,
                    evidence=[EvidenceItem(source_doc_id="doc:entity-aliases-dict", quote=f"Hardcoded alias: {alias_raw} -> {canonical_raw}")],
                    raw={"canonical": canonical_raw, "alias": alias_raw},
                ))
        return kir
