"""
Gestión de equivalencias y glosario de acrónimos para expansión de consultas.
Extrae la lógica de equivalencias de rag_hybrid.py para responsabilidad única.
"""
import re
import unicodedata
from typing import Dict, List, Optional, Set


class EquivalencesManager:
    """
    Carga, parsea y aplica equivalencias de términos para expansión de consultas.

    Args:
        embedded_text: Texto embebido con equivalencias (formato 'A = B = C').
        flags: Diccionario de flags de configuración (comparte referencia con HybridRAG).
    """

    def __init__(self, embedded_text: str, flags: Optional[Dict] = None):
        self.flags = flags if flags is not None else {}
        self.equivalences: List[Set[str]] = []
        self.equivalences_map: Dict[str, List[str]] = {}
        self.definitions_map: Dict[str, str] = {}
        self._load(embedded_text)

    # ------------------------------------------------------------------
    # Carga y construcción de mapas
    # ------------------------------------------------------------------

    def _load(self, embedded_text: str) -> None:
        """Parsea texto de equivalencias en clusters de frases equivalentes."""

        def _clean_token(tok: str) -> str:
            t = tok.strip()
            t = re.sub(r"\(.*?\)", "", t)
            t = t.replace("}", "").replace("{", "").strip()
            t = re.sub(r"\s+", " ", t)
            return t.lower()

        clusters: List[Set[str]] = []
        lines = (embedded_text or "").splitlines()
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            if line.lower().startswith('tabla de equivalencias'):
                continue
            parts = line.split('=')
            tokens = []
            for p in parts:
                cleaned = _clean_token(p)
                if cleaned:
                    tokens.append(cleaned)
            tokens = list(dict.fromkeys(tokens))
            if len(tokens) >= 2:
                clusters.append(set(tokens))
        self.equivalences = clusters
        self._build_maps()

    def _build_maps(self) -> None:
        eq_map: Dict[str, Set[str]] = {}
        def_map: Dict[str, str] = {}
        for cluster in self.equivalences:
            toks = list(cluster)
            for t in toks:
                others = set(toks)
                others.discard(t)
                eq_map.setdefault(t, set()).update(others)
            candidates = [t for t in toks if (" " in t) or any(ch.islower() for ch in t)]
            if not candidates:
                candidates = sorted(toks, key=len, reverse=True)
            definition = max(candidates, key=len) if candidates else (toks[0] if toks else '')
            for t in toks:
                if len(t) <= 8 and (" " not in t) and t.replace('-', '').replace('_', '').isalpha():
                    def_map[t.upper()] = definition
        self.equivalences_map = {k: list(v) for k, v in eq_map.items()}
        self.definitions_map = def_map

    # ------------------------------------------------------------------
    # Expansión de consultas
    # ------------------------------------------------------------------

    def expand(self, query: str) -> str:
        """Expande la query con sinónimos del mapa de equivalencias."""
        try:
            if not self.equivalences_map:
                return query
            ql = (query or '').lower()
            add = []
            for tok in sorted(self.equivalences_map.keys(), key=len, reverse=True):
                if not tok:
                    continue
                if len(tok) <= 2 and tok.isalpha():
                    continue
                try:
                    if any(ch.isalpha() for ch in tok):
                        pat = rf"\b{re.escape(tok)}\b"
                        found = bool(re.search(pat, ql, flags=re.IGNORECASE))
                    else:
                        found = tok in ql
                except Exception:
                    found = tok in ql
                if found:
                    syns = [s for s in self.equivalences_map.get(tok, []) if s not in ql]
                    if syns:
                        add.extend(syns[:3])
            if add:
                return f"{query} {' '.join(add)}"
            return query
        except Exception:
            return query

    def build_glossary(self, query: str) -> str:
        """Construye un glosario de acrónimos presentes en la query."""
        try:
            if not self.definitions_map:
                return ''
            q_orig = query or ''
            ql = q_orig.lower()
            try:
                allow: set = set(self.flags.get('glossary_allowlist') or [])
                deny: set = set(self.flags.get('glossary_denylist') or [])
                require_explicit: bool = bool(self.flags.get('glossary_require_explicit', True))
            except Exception:
                allow, deny, require_explicit = set(), set(), True
            ban = {
                'SYSTEM', 'NETWORK', 'COMPUTER', 'SERVER', 'CLIENT', 'HOST',
                'DEVICE', 'EQUIPMENT', 'SECURITY', 'SEGURIDAD',
            }
            items: List[str] = []
            keys = sorted(self.definitions_map.keys(), key=len, reverse=True)
            for k in keys:
                if k in ban:
                    continue
                d = self.definitions_map.get(k)
                if not d:
                    continue
                if k in deny:
                    continue
                if allow and k not in allow:
                    continue
                if require_explicit:
                    patterns = [rf"\b{k}\b"]
                    if k == 'ES':
                        patterns.extend([r"\bE/S\b", r"\bE\/S\b"])
                    if not any(re.search(p, q_orig) for p in patterns):
                        continue
                if all(k not in it for it in items):
                    items.append(f"- {k}: {d}")
                if len(items) >= 10:
                    break
            return "GLOSARIO DE ACRONIMOS\n" + "\n".join(items) if items else ''
        except Exception:
            return ''

    # ------------------------------------------------------------------
    # Normalización de queries
    # ------------------------------------------------------------------

    def normalize_query(self, query: str) -> str:
        """Normaliza códigos, números romanos y variaciones de nombres."""
        query_expanded = query
        try:
            if self.equivalences:
                def _strip_accents(s: str) -> str:
                    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
                q_norm = _strip_accents(query.lower())
                additions: set = set()
                for cluster in self.equivalences:
                    for phrase in cluster:
                        p_norm = _strip_accents(phrase)
                        pat = r"\b" + re.escape(p_norm) + r"\b" if any(ch.isalnum() for ch in p_norm) else re.escape(p_norm)
                        if re.search(pat, q_norm, flags=re.IGNORECASE):
                            for alt in cluster:
                                if alt != phrase:
                                    additions.add(alt)
                            break
                if additions:
                    query_expanded = query_expanded + " " + " ".join(sorted(additions))
        except Exception:
            pass
        name_variations = {
            'pentest': ['pentest', 'penetration test', 'pen testing', 'ethical hacking'],
            'firewall': ['firewall', 'firewalls', 'fire wall', 'cortafuegos'],
            'ids': ['ids', 'intrusion detection', 'sistema deteccion intrusiones'],
            'ips': ['ips', 'intrusion prevention', 'sistema prevencion intrusiones'],
            'siem': ['siem', 'security information event management', 'splunk', 'qradar', 'sentinel'],
            'resetear': ['resetear', 'reset', 'reiniciar', 'reseteo'],
            'reiniciar': ['reiniciar', 'reset', 'resetear', 'reseteo'],
        }
        query_lower = query.lower()
        for key, variations in name_variations.items():
            if key in query_lower:
                query_expanded += " " + " ".join(variations)
        pattern_codes = r"\b([A-Z]{1,3})(\d{1,2})\b"
        matches_codes = re.findall(pattern_codes, query, re.IGNORECASE)
        if matches_codes:
            variations = []
            for prefix, num in matches_codes:
                try:
                    num_clean = str(int(num))
                except Exception:
                    num_clean = num
                variations.extend([f"{prefix}{num}", f"{prefix}_{num}", f"{prefix}_{num_clean}", f"{prefix} {num_clean}"])
            query_expanded = query_expanded + " " + " ".join(set(variations))
        pattern_roman = r"\b([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*)\s+(\d{1,2})\b"
        matches_roman = re.findall(pattern_roman, query_expanded, re.IGNORECASE)
        if matches_roman:
            roman_numerals = {1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V', 6: 'VI', 7: 'VII', 8: 'VIII', 9: 'IX', 10: 'X'}
            variations_roman = []
            for name, num_str in matches_roman:
                try:
                    num = int(num_str)
                except Exception:
                    continue
                if num in roman_numerals:
                    variations_roman.append(f"{name} {roman_numerals[num]}")
            if variations_roman:
                query_expanded = query_expanded + " " + " ".join(variations_roman)
        return query_expanded
