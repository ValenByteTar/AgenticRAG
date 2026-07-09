"""
Extractor de entidades y referencias de documentos
Extrae la lógica de extracción de rag_hybrid.py
"""

import re
import unicodedata
from typing import List, Dict, Optional, Set, Tuple


class EntityExtractor:
    """
    Extractor de entidades, referencias a documentos y otros elementos de queries
    """
    
    def __init__(self, domain_map: Optional[Dict] = None):
        """
        Args:
            domain_map: Mapa de entidades de dominio conocidas (opcional)
        """
        self.domain_map = domain_map or {}
        self.stopwords = self._initialize_stopwords()
        # Gazetteer de dominio: alias -> (canonical, extra)
        self.domain_entities: Dict[str, Tuple[str, str]] = {}
        # Precompilar regex para rendimiento
        # Regex para nombres propios compuestos (frameworks, certificaciones, empresas)
        self._re_compound = [
            re.compile(r"\b(?:ISO|NIST|CISSP|CEH|OSCP|AWS|Azure|GCP)\s+[0-9]*[A-Z][A-Za-z0-9\s/-]*"),
            re.compile(r"\b[A-Z][a-z]+\s+(?:Security|Framework|Institute|Council)\b"),
        ]
        # Certificaciones con formato "prefijo + número" sin espacio obligatorio (ej: NSE4, SC-100)
        self._re_cert_codes = re.compile(
            r"\b(?:NSE|GSEC|GCIH|GPEN|GCFA|GCFE|GPPA|CCSP|CCNA|CCNP|CCIE|CASP|CRISC|CISM|CISA|SC-\d+|AZ-\d+|MS-\d+)\s?-?\s?[0-9]{0,3}\b",
            re.IGNORECASE,
        )
        # Certificaciones con sufijo "+" estilo CompTIA (Security+, Network+, PenTest+, CySA+, A+)
        self._re_cert_plus = re.compile(
            r"\b(?:Security|Network|PenTest|CySA|Cloud|Server|Linux|A)\s?\+", re.IGNORECASE
        )
        self._re_models = re.compile(r"\b[A-Z]{2,}[0-9-]+[A-Z0-9-]*\b", re.IGNORECASE)
        # Regex para prefijos de entidades de seguridad
        self._re_prefix_lower = re.compile(r"\b(?:certified|professional|associate)\s+([a-z][\w\s-]{3,})", re.IGNORECASE)
        # Flags de capacidades opcionales
        self._have_spacy = False
        self._spacy_nlp = None
        self._phrase_matcher = None
        self._entity_ruler = None
        self._have_rapidfuzz = False
        # Intentar cargar librerías opcionales de forma perezosa
        try:
            import spacy  # type: ignore
            from spacy.lang.es import Spanish  # noqa: F401
            from spacy.matcher import PhraseMatcher  # noqa: F401
            from spacy.pipeline import EntityRuler  # noqa: F401
            # Construir un pipeline mínimo sin modelos pesados
            try:
                self._spacy_nlp = spacy.blank("es")
            except Exception:
                self._spacy_nlp = spacy.blank("xx")
            from spacy.matcher import PhraseMatcher
            from spacy.pipeline import EntityRuler
            self._phrase_matcher = PhraseMatcher(self._spacy_nlp.vocab, attr="LOWER")
            self._entity_ruler = EntityRuler(self._spacy_nlp, validate=True)
            self._spacy_nlp.add_pipe(self._entity_ruler)
            self._have_spacy = True
        except Exception:
            self._have_spacy = False
        try:
            from rapidfuzz import process as _rf_process  # noqa: F401
            self._have_rapidfuzz = True
        except Exception:
            self._have_rapidfuzz = False
        # Cargar aliases de ciberseguridad para cross-lingual retrieval
        self._load_cybersecurity_aliases()

    def _load_cybersecurity_aliases(self):
        """Carga aliases para términos de ciberseguridad (cross-lingual español/inglés)"""
        # MITRE ATT&CK mappings - incluir todas las variaciones posibles
        mitre_aliases = [
            ("mitre attck", "mitre att&ck"),
            ("mitre attack", "mitre att&ck"),
            ("mitre att&ck", "mitre att&ck"),
            ("attack framework", "mitre att&ck"),
            ("marco mitre", "mitre att&ck"),
            ("marco attack", "mitre att&ck"),
            ("marco attck", "mitre att&ck"),
            ("marco att&ck", "mitre att&ck"),
            ("framework mitre", "mitre att&ck"),
            ("mitre attack framework", "mitre att&ck"),
            ("attck", "mitre att&ck"),
            ("mitre", "mitre att&ck"),
        ]
        # Pentest / Penetration testing mappings
        pentest_aliases = [
            ("prueba de penetracion", "penetration testing"),
            ("prueba del penetracion", "penetration testing"),
            ("prueba penetracion", "penetration testing"),
            ("pruebas de penetracion", "penetration testing"),
            ("pentest", "penetration testing"),
            ("pentesting", "penetration testing"),
            ("ethical hacking", "penetration testing"),
            ("pen test", "penetration testing"),
            ("pen testing", "penetration testing"),
        ]
        # Certificaciones Fortinet NSE
        nse_aliases = [
            ("fortinet nse", "nse"),
            ("network security expert", "nse"),
            ("nse fortinet", "nse"),
        ]
        # Autenticación multifactor
        mfa_aliases = [
            ("doble factor", "mfa"),
            ("doble autenticacion", "mfa"),
            ("autenticacion de dos factores", "mfa"),
            ("segundo factor", "mfa"),
            ("2fa", "mfa"),
            ("multi factor authentication", "mfa"),
        ]
        # Gestión de vulnerabilidades
        vuln_aliases = [
            ("gestion de vulnerabilidades", "vulnerability management"),
            ("manejo de vulnerabilidades", "vulnerability management"),
            ("escaneo de vulnerabilidades", "vulnerability scanning"),
        ]
        for alias, canonical in mitre_aliases + pentest_aliases + nse_aliases + mfa_aliases + vuln_aliases:
            self._add_domain_alias(alias, canonical, "cybersecurity_alias")

    def _initialize_stopwords(self) -> Set[str]:
        """Inicializa stopwords en español - incluye verbos imperativos y palabras de accion"""
        return {
            # Artículos, preposiciones, pronombres
            'que', 'qué', 'quien', 'quién', 'cual', 'cuál', 'cuales', 'cuáles',
            'como', 'cómo', 'donde', 'dónde', 'cuando', 'cuándo', 'cuánto', 'cuántos',
            'cuanto', 'cuantos', 'por', 'para', 'con', 'sin', 'sobre', 'entre',
            'hasta', 'desde', 'en', 'total', 'de', 'del', 'al', 'el', 'la', 'los',
            'las', 'una', 'unos', 'unas', 'este', 'esta', 'estos', 'estas',
            # Verbos imperativos y de acción comunes en queries
            'dame', 'tiene', 'hay', 'son', 'sea', 'marca', 'información', 'informacion',
            'tenemos', 'funciona', 'funcionan', 'alguna', 'algún', 'tipo', 'tipos',
            'manera', 'forma', 'modo', 'hacer', 'dice', 'explica', 'hablame', 'háblame',
            'hazme', 'quiero', 'ahi', 'ahí', 'haz', 'haga', 'intenta', 'intente',
            'responde', 'responder', 'corrige', 'vuelve', 'vuelva', 'otra', 'vez',
            'datos', 'detalles', 'ahora', 'solo', 'respuesta',
            'puedes', 'puede', 'busca', 'buscar', 'dime', 'decime', 'decí',
            'toda', 'todo', 'disponible', 'nuevamente',
            # Verbos imperativos adicionales (FASE 3)
            'describe', 'describir', 'analiza', 'analizar', 'proporciona', 'proporcionar',
            'imagina', 'imaginar', 'lista', 'listar', 'diseña', 'diseñar', 'explica', 'explicar',
            'compara', 'comparar', 'evalua', 'evaluar', 'identifica', 'identificar',
            'menciona', 'mencionar', 'demuestra', 'demostrar', 'discute', 'discutir',
            'argumenta', 'argumentar', 'justifica', 'justificar', 'recomienda', 'recomendar',
            'sugiere', 'sugerir', 'explica', 'explicar', 'detalla', 'detallar',
            'completo', 'completa', 'flujo', 'proceso', 'paso', 'pasos',
            # Palabras de contexto/ambiguas
            'segun', 'según', 'basado', 'basada', 'referente', 'referencia',
            'ejemplo', 'ejemplos', 'mencionas', 'mencionan', 'documentos'
        }

    @staticmethod
    def normalize_text(s: str) -> str:
        """Minúsculas sin acentos/diacríticos y espacios normalizados"""
        if not isinstance(s, str):
            return ''
        s = s.strip().lower()
        s = unicodedata.normalize('NFD', s)
        s = ''.join(ch for ch in s if unicodedata.category(ch) != 'Mn')
        s = re.sub(r"\s+", " ", s)
        return s

    def _add_domain_alias(self, alias: str, canonical: str, extra: str = ""):
        a = self.normalize_text(alias)
        c = self.normalize_text(canonical)
        if a and c and a not in self.domain_entities:
            self.domain_entities[a] = (c, extra)
        # Registrar patrón en spaCy si disponible
        try:
            if self._have_spacy and self._phrase_matcher is not None:
                from spacy.tokens import Doc
                pat = self._spacy_nlp.make_doc(alias)
                self._phrase_matcher.add("ENTITY_ALIAS", [pat])
        except Exception:
            pass

    def update_domain_from_collection(self, collection_data: Dict, doc_roles: Optional[Dict] = None, domain_map: Optional[Dict] = None):
        """Construye un diccionario de dominio/sinónimos a partir de la colección y roles.
        collection_data: salida de collection.get() con metadatas, documents, ids
        """
        try:
            if domain_map:
                self.domain_map = dict(domain_map)
        except Exception:
            pass

        try:
            metadatas = collection_data.get('metadatas', []) if isinstance(collection_data, dict) else []
            for md in metadatas:
                src = (md or {}).get('source', '')
                if not src:
                    continue
                src_norm = self.normalize_text(src)
                # Extraer nombres de documentos para construir alias de frameworks/certificaciones
                # Ej: "ISO 27001 Guide.pdf" -> alias "iso 27001"
                m = re.search(r'([a-z]+)\s+([0-9]+).*?\.pdf', src_norm)
                if m:
                    name = f"{m.group(1)} {m.group(2)}".strip()
                    if len(name) >= 3:
                        self._add_domain_alias(name, name, extra=src)
        except Exception:
            pass

        # Incorporar doc_roles (perfiles de entidad)
        try:
            if doc_roles and isinstance(doc_roles.get('docs'), dict):
                for doc, info in doc_roles['docs'].items():
                    role = (info or {}).get('role', '')
                    if str(role).lower() == 'entity_profile':
                        name = self.normalize_text((info or {}).get('name', '') or doc)
                        if name:
                            self._add_domain_alias(name, name, extra=doc)
        except Exception:
            pass
    
    def extract_entities(self, question: str) -> List[str]:
        """
        Extrae nombres propios y términos técnicos de la pregunta
        
        Args:
            question: Pregunta del usuario
        
        Returns:
            Lista de entidades detectadas
        """
        entities: List[str] = []
        q_raw = question or ''
        q_norm = self.normalize_text(q_raw)
        # Registrar coincidencias exactas fuertes (gazetteer de dominio) para filtrar ruido
        exact_hits: Set[str] = set()
        
        # 0) Coincidencias exactas/fuzzy contra gazetteer dominial
        try:
            if self.domain_entities:
                # Exactas rápidas (con registro en exact_hits)
                for alias, (canon, _extra) in self.domain_entities.items():
                    if alias and alias in q_norm:
                        if canon not in entities:
                            entities.append(canon)
                        exact_hits.add(canon)
                # Fuzzy opcional: solo si NO hubo exactas y manteniendo umbral alto
                if self._have_rapidfuzz and not exact_hits and len(entities) < 2:
                    from rapidfuzz import process, fuzz
                    choices = list(self.domain_entities.keys())
                    added = 0
                    for cand, score, _ in process.extract(q_norm, choices, scorer=fuzz.WRatio, limit=5):
                        if score >= 92 and len(cand) >= 5:
                            canon = self.domain_entities[cand][0]
                            if canon not in entities:
                                entities.append(canon)
                                added += 1
                        if added >= 1:
                            break
        except Exception:
            pass

        # 1. Buscar nombres compuestos de frameworks/certificaciones (patrones capitalizados)
        for creg in self._re_compound:
            try:
                matches = creg.findall(q_raw)
            except Exception:
                matches = []
            for match in matches:
                clean_match = self.normalize_text(match)
                clean_match = re.sub(r"\s+(de|del|la|el|framework|certification)$", "", clean_match)
                if len(clean_match) > 5:
                    entities.append(clean_match)

        # 1b. Buscar certificaciones con formato "prefijo+número" (NSE4, SC-100, etc.)
        try:
            for match in self._re_cert_codes.findall(q_raw):
                clean_match = self.normalize_text(match).replace(' ', '').replace('-', '')
                if len(clean_match) > 2 and clean_match not in entities:
                    entities.append(clean_match)
        except Exception:
            pass

        # 1c. Buscar certificaciones con sufijo "+" (Security+, Network+, CySA+, etc.)
        try:
            for match in self._re_cert_plus.findall(q_raw):
                clean_match = self.normalize_text(match).replace(' ', '')
                if clean_match not in entities:
                    entities.append(clean_match)
        except Exception:
            pass
        
        # 2. Agrupar secuencias de palabras capitalizadas
        words = q_raw.split()
        i = 0
        while i < len(words):
            token = re.sub(r'[^\wáéíóúñÁÉÍÓÚÑ-]', '', words[i])
            nxt = re.sub(r'[^\wáéíóúñÁÉÍÓÚÑ-]', '', words[i+1]) if i+1 < len(words) else ''
            
            def is_cap(w: str) -> bool:
                return bool(w) and w[0].isupper() and w.lower() not in self.stopwords and len(w) > 2
            
            def is_article(w: str) -> bool:
                return w in {'El', 'La', 'Los', 'Las'}
            
            group = []
            j = i
            if is_article(token) and (i+1) < len(words) and is_cap(nxt):
                group.append(token)
                j += 1
                token = re.sub(r'[^\wáéíóúñÁÉÍÓÚÑ-]', '', words[j])
            
            added = 0
            while j < len(words) and added < 3:
                t = re.sub(r'[^\wáéíóúñÁÉÍÓÚÑ-]', '', words[j])
                if is_cap(t):
                    group.append(t)
                    added += 1
                    j += 1
                else:
                    break
            
            if len(group) >= 2:
                phrase = self.normalize_text(' '.join(group).strip())
                if phrase not in entities:
                    entities.append(phrase)
                i = j
                continue
            
            if is_cap(token):
                wlow = self.normalize_text(token)
                if wlow not in entities:
                    entities.append(wlow)
            i += 1
        
        # 2b. ELIMINADO - Regla "x del y" generaba entidades basura (ej: "completo del respuesta")
        # Era util para dominio electrico ("salida de servicio") pero ahora corrompe la busqueda.
        # Solo agregar entidades concretas del dominio, no frases genericas.
        pass
        
        # 3. Buscar términos específicos de ciberseguridad
        specific_entities = [
            'cissp', 'ceh', 'oscp', 'oswe', 'osep', 'cism', 'cisa', 'crisc',
            'aws', 'azure', 'gcp', 'cloud', 'security', 'pentest',
            'firewall', 'siem', 'soc', 'ids', 'ips', 'vpn', '零信任',
            'nse1', 'nse2', 'nse3', 'nse4', 'nse5', 'nse6', 'nse7', 'nse8',
            'gsec', 'gcih', 'gpen', 'gcfa', 'gcfe',
            'ccna', 'ccnp', 'ccie', 'casp', 'ccsp',
            'securityplus', 'networkplus', 'pentestplus', 'cysaplus',
            'sc-100', 'sc-200', 'sc-300', 'sc-400', 'az-500',
        ]
        
        question_lower = q_norm
        for term in specific_entities:
            if term in question_lower and term not in entities:
                entities.append(term)
        
        # 4. Extraer números de modelos
        model_numbers = self._re_models.findall(q_raw)
        for model in model_numbers:
            m = self.normalize_text(model)
            if m not in entities:
                entities.append(m)
        
        # 5. Detectar entidades con prefijo común en minúsculas
        try:
            ql = q_norm
            # Términos genéricos que NO son entidades (términos de IT muy generales)
            generic_terms = {
                'system', 'network', 'security', 'audit', 'test', 'scan',
                'server', 'client', 'host', 'device', 'endpoint',
                'policy', 'procedure', 'process', 'guide', 'manual',
            }
            for m in self._re_prefix_lower.findall(ql):
                cand = m.strip()
                # Limitar a 3 palabras y filtrar genéricos
                words = cand.split()[:3]
                # Eliminar palabras genéricas del final
                while words and words[-1] in generic_terms:
                    words.pop()
                if not words:
                    continue
                cand = ' '.join(words).strip()
                # Solo agregar si tiene al menos 4 chars y no es puramente genérico
                if len(cand) >= 4 and cand not in generic_terms and cand not in entities:
                    entities.append(cand)
        except Exception:
            pass
        
        # 6. Buscar en mapa de entidades de dominio conocidas
        try:
            if self.domain_map:
                ql = q_norm
                for alias, (canonical, _) in self.domain_map.items():
                    alias_n = self.normalize_text(alias)
                    canon_n = self.normalize_text(canonical)
                    if re.search(r'\b' + re.escape(alias_n) + r'\b', ql):
                        if canon_n not in entities:
                            entities.append(canon_n)
                        exact_hits.add(canon_n)
                        break
        except Exception:
            pass

        # 7. ELIMINADO - Heuristica de centrales electricas (Loma Blanca, etc)

        # 8. NER con spaCy + EntityRuler/PhraseMatcher (opcional)
        try:
            if self._have_spacy and self._spacy_nlp is not None:
                # Construir patrones de EntityRuler a partir de domain_entities (una sola vez)
                if self._entity_ruler and len(self._entity_ruler.patterns) == 0 and self.domain_entities:
                    patterns = [{"label": "ENT", "pattern": alias} for alias in self.domain_entities.keys() if alias]
                    if patterns:
                        self._entity_ruler.add_patterns(patterns)
                doc = self._spacy_nlp(q_raw)
                ner_hits = set()
                for ent in doc.ents:
                    val = self.normalize_text(ent.text)
                    if val:
                        ner_hits.add(val)
                # PhraseMatcher sobre doc en minúsculas
                if self._phrase_matcher is not None and self.domain_entities:
                    matches = self._phrase_matcher(doc)
                    for _mid, start, end in matches:
                        val = self.normalize_text(doc[start:end].text)
                        if val:
                            ner_hits.add(val)
                for hit in ner_hits:
                    # mapear a canónico si está en gazetteer
                    canon = self.domain_entities.get(hit, (hit, ''))[0]
                    if canon not in entities:
                        entities.append(canon)
        except Exception:
            pass

        # 9. Limpieza: filtrar términos genéricos y negación contextual
        try:
            ql2 = q_norm
            neg_trigs = ['errone', 'error', 'equivoc', 'incorrect', 'no corresponde']
            # Términos genéricos a eliminar si aparecen solos
            generic_solo = {
                'system', 'network', 'security', 'server', 'client',
                'policy', 'procedure', 'process', 'guide',
                'tengo', 'tiene', 'entonces', 'este', 'ese', 'esa', 'esta',
            }
            filtered = []
            for e in entities:
                e_l = e.strip()
                e_low = e_l.lower()
                # Filtrar entidades que sean solo stopwords o genericos
                if all(w in generic_solo for w in e_l.split()):
                    continue
                # Filtrar genéricos solos
                if e_l in generic_solo:
                    continue
                # Filtrar frases que son solo genéricos concatenados
                words = e_l.split()
                if all(w in generic_solo for w in words):
                    continue
                # Negación contextual
                idx = ql2.find(e_l)
                if idx >= 0:
                    window = ql2[max(0, idx - 80): idx]
                    if any(t in window for t in neg_trigs):
                        continue
                filtered.append(e)
            entities = filtered
            # Filtro de dominancia: si hay coincidencias exactas, mantener coherencia
            if exact_hits:
                def tokset(s: str) -> Set[str]:
                    ws = [w for w in s.split() if len(w) >= 3 and w not in generic_solo]
                    return set(ws)
                dominant_tokens = set()
                for ex in exact_hits:
                    dominant_tokens |= tokset(ex)
                kept: List[str] = []
                for e in entities:
                    if e in exact_hits:
                        kept.append(e)
                        continue
                    e_tokens = tokset(e)
                    # mantener si comparte suficiente contexto o es sub/supercadena
                    if any((e in ex or ex in e) for ex in exact_hits):
                        kept.append(e)
                        continue
                    if len(e_tokens & dominant_tokens) >= 2:
                        kept.append(e)
                entities = kept if kept else list(exact_hits)
        except Exception:
            pass
        
        return entities
    
    def extract_doc_reference(self, query: str) -> Optional[Dict]:
        """
        Extrae referencia a un documento citado en formato [Doc N - nombre p.X]
        
        Args:
            query: Query del usuario
            
        Returns:
            Dict con 'doc_name' y 'page' si encuentra referencia, None si no
        """
        patterns = [
            r'\[Doc \d+ - ([^\]]+) p\.(\d+)\]',
            r'\[Doc \d+ - ([^\]]+) pág\.(\d+)\]',
            r'documento \[Doc \d+ - ([^\]]+) p\.(\d+)\]',
            r'el \[Doc \d+ - ([^\]]+) p\.(\d+)\]',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query)
            if match:
                doc_name = match.group(1).strip()
                page = int(match.group(2))
                return {'doc_name': doc_name, 'page': page}
        
        return None
    
    def extract_doc_scope(self, query: str) -> str:
        """
        Intenta extraer un nombre de documento para limitar la búsqueda
        
        Args:
            query: Query del usuario
            
        Returns:
            Nombre del documento o cadena vacía
        """
        q = query.strip()
        
        # 1. Documento entre comillas
        m = re.search(r'"([^"]+\.pdf)"', q, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
        
        # 2. Patrones comunes
        m2 = re.search(
            r'(?:buscar en|busca en|apunta(?: tu)?\s+b(?:ú|u)squeda a|solo en|solamente en|en\s+(?:el\s+documento|documento|el\s+anexo|anexo|archivo))\s+([^\n\r]+?\.pdf)\b',
            q, flags=re.IGNORECASE
        )
        if m2:
            return m2.group(2 if m2.lastindex and m2.lastindex >= 2 else 1).strip()
        
        # 3. ELIMINADO - Caso especial Listado Centrales (dominio electrico)
        
        return ''
    
    def extract_doc_pages_hint(self, query: str) -> Optional[Dict]:
        """
        Extrae pista explícita de documento y páginas
        
        Args:
            query: Query del usuario
            
        Returns:
            Dict con 'doc' y 'pages' o None
        """
        try:
            q = query or ''
            
            # Buscar nombre de doc
            doc_match = re.search(r"['\"]([^'\"]+?\.pdf)['\"]|([A-Za-zÁÉÍÓÚÑáéíóúñ0-9 \-]+?\.pdf)", q)
            if not doc_match:
                return None
            doc = (doc_match.group(1) or doc_match.group(2) or '').strip()
            
            # Buscar páginas
            pages = []
            for pat in [
                r"p[aá]g(?:ina|inas)?\s*(\d{1,3})\s*(?:y|e|,|-)\s*(\d{1,3})",
                r"p\.?\s*(\d{1,3})\s*(?:y|e|,|-)\s*(\d{1,3})",
                r"p[aá]g(?:ina|inas)?\s*(\d{1,3})",
                r"\b(\d{1,3})\s*[-–]\s*(\d{1,3})\b",
            ]:
                m = re.search(pat, q, flags=re.IGNORECASE)
                if m:
                    if m.lastindex and m.lastindex >= 2 and m.group(2):
                        a = int(m.group(1))
                        b = int(m.group(2))
                        if a <= b:
                            pages = list(range(a, b+1))
                        else:
                            pages = [a, b]
                    else:
                        pages = [int(m.group(1))]
                    break
            
            if not pages:
                return None
            
            return {'doc': doc, 'pages': pages}
        except Exception:
            return None
