"""EquivalencesExtractor — parsea EQUIVALENCES_EMBEDDED_TEXT a KIR (RES-002 §3.3).

Fuente: ``rag_hybrid.py`` lineas 119-307 (92 grupos de equivalencias).

Cada linea con formato ``A = B = C`` produce:
    - Un EntityClaim por cada token (canonical_name = el mas largo/descriptivo)
    - Un AliasClaim por cada token no-canonico -> canonico
    - Un RelationClaim ``equivalent_to`` entre pares

El extractor es determinista: mismo texto de entrada -> mismo KIR.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from ..kir import AliasClaim, EntityClaim, EvidenceItem, KIR, RelationClaim, normalize_text


_EXTRACTOR_ID = "deterministic:equivalences-text"


class EquivalencesExtractor:
    """Extrae entidades, aliases y relaciones de equivalencia desde texto embebido."""

    def __init__(self, embedded_text: str):
        self.embedded_text = embedded_text or ""

    def extract(self) -> KIR:
        kir = KIR(metadata={"extractor": _EXTRACTOR_ID})
        clusters = self._parse_clusters(self.embedded_text)
        for cluster in clusters:
            canonical = self._pick_canonical(cluster)
            types = self._infer_types(canonical)
            for token in cluster:
                entity_claim = EntityClaim(
                    surface_form=token,
                    canonical_name=canonical,
                    entity_types=list(types),
                    extractor_id=_EXTRACTOR_ID,
                    confidence=0.95,
                    evidence=[EvidenceItem(source_doc_id="doc:equivalences-text", quote=f"Equivalence: {' = '.join(sorted(cluster))}")],
                    raw={"cluster": sorted(cluster), "source": "EQUIVALENCES_EMBEDDED_TEXT"},
                )
                kir.entity_claims.append(entity_claim)

                if token != canonical:
                    kir.alias_claims.append(AliasClaim(
                        alias=token,
                        canonical_name=canonical,
                        extractor_id=_EXTRACTOR_ID,
                        confidence=0.95,
                        evidence=[EvidenceItem(source_doc_id="doc:equivalences-text", quote=f"Equivalence: {' = '.join(sorted(cluster))}")],
                        raw={"cluster": sorted(cluster)},
                    ))

            tokens = sorted(cluster)
            for i in range(len(tokens)):
                for j in range(i + 1, len(tokens)):
                    kir.relation_claims.append(RelationClaim(
                        subject_name=tokens[i],
                        predicate="equivalent_to",
                        object_name=tokens[j],
                        extractor_id=_EXTRACTOR_ID,
                        confidence=0.9,
                        evidence=[EvidenceItem(source_doc_id="doc:equivalences-text", quote=f"Equivalence: {' = '.join(sorted(cluster))}")],
                        raw={"cluster": sorted(cluster)},
                    ))
        return kir

    def _parse_clusters(self, text: str) -> List[Set[str]]:
        """Parsea lineas 'A = B = C' en clusters de tokens equivalentes."""
        clusters: List[Set[str]] = []
        for raw_line in (text or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.lower().startswith("tabla de equivalencias"):
                continue
            parts = line.split("=")
            tokens = []
            for p in parts:
                cleaned = self._clean_token(p)
                if cleaned:
                    tokens.append(cleaned)
            tokens = list(dict.fromkeys(tokens))
            if len(tokens) >= 2:
                clusters.append(set(tokens))
        return clusters

    @staticmethod
    def _clean_token(tok: str) -> str:
        t = tok.strip()
        t = re.sub(r"\(.*?\)", "", t)
        t = t.replace("}", "").replace("{", "").strip()
        t = re.sub(r"\s+", " ", t)
        return normalize_text(t)

    @staticmethod
    def _pick_canonical(cluster: Set[str]) -> str:
        """Selecciona el nombre canonico: el mas descriptivo (largo, con espacios)."""
        tokens = list(cluster)
        candidates = [t for t in tokens if " " in t or any(ch.islower() for ch in t)]
        if not candidates:
            candidates = sorted(tokens, key=len, reverse=True)
        return max(candidates, key=len) if candidates else (tokens[0] if tokens else "")

    @staticmethod
    def _infer_types(name: str) -> List[str]:
        """Heuristica ligera para inferir tipos de entidad."""
        n = name.lower()
        types: List[str] = []
        type_map = {
            "framework": ["iso", "nist", "cobit", "itil", "owasp"],
            "standard": ["iso", "nist", "pci"],
            "certification": ["cissp", "ceh", "oscp", "cism", "cisa", "ccsp", "crisc", "gsec", "gcih"],
            "concept": ["cia", "risk", "governance", "compliance"],
            "technology": ["siem", "soc", "edr", "xdr", "waf", "ids", "ips", "dlp", "pam", "sso"],
            "protocol": ["tls", "ssl", "dns", "tcp", "ospf", "bgp", "mpls"],
            "regulation": ["gdpr", "dora", "nis2", "hipaa", "sox"],
            "methodology": ["devsecops", "sdlc", "sast", "dast"],
        }
        for t, keywords in type_map.items():
            if any(k in n for k in keywords):
                types.append(t)
        if not types:
            types.append("concept")
        return list(dict.fromkeys(types))
