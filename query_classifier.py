"""
Clasificación de intención de consultas RAG.
Extrae la lógica de clasificación de rag_hybrid.py para responsabilidad única.
"""
import re
import unicodedata
from typing import Callable, Dict, List, Optional


class QueryClassifier:
    """
    Clasifica la intención de una consulta RAG para guiar la estrategia de recuperación.

    Args:
        flags: Diccionario de flags de configuración (comparte referencia con HybridRAG).
        extract_entities_fn: Callable que recibe una query y devuelve lista de entidades.
                             Necesario para clasificadores que usan extracción de entidades.
    """

    def __init__(
        self,
        flags: Optional[Dict] = None,
        extract_entities_fn: Optional[Callable[[str], List[str]]] = None,
    ):
        self.flags = flags if flags is not None else {}
        self._extract_entities = extract_entities_fn or (lambda _q: [])

    # ------------------------------------------------------------------
    # Clasificadores de alto nivel
    # ------------------------------------------------------------------

    def is_out_of_domain(self, query: str) -> bool:
        """Detecta consultas evidentemente ajenas al dominio (fuera de trabajo)."""
        try:
            ql = (query or '').lower()
            ood_keywords = {
                'minecraft', 'videojuego', 'videojuegos', 'juego', 'juegos',
                'twitch', 'youtube', 'tiktok', 'instagram', 'facebook', 'netflix', 'spotify',
                'pelicula', 'película', 'serie', 'anime', 'manga',
                'receta', 'recetas', 'cocina', 'cocinar', 'hornear', 'horneado', 'pan', 'panes', 'panecillos',
                'masa', 'harina', 'levadura', 'azucar', 'azúcar', 'huevo', 'leche', 'postre', 'pastel', 'bizcocho',
                'malteada', 'batido', 'licuado', 'smoothie', 'helado', 'torta', 'galleta', 'galletas',
                'vainilla', 'chocolate', 'fresa', 'frutilla', 'cafe', 'café', 'asado', 'parrilla', 'carne', 'chorizo',
                'medicina', 'salud', 'horoscopo', 'horóscopo', 'clima', 'chiste', 'meme',
                'deporte', 'futbol', 'fútbol', 'basquet', 'tenis', 'mundial', 'copa', 'campeonato',
                'matematica', 'matemática', 'historia', 'geografia', 'geografía', 'literatura',
                'viaje', 'turismo', 'hotel', 'restaurante', 'compra', 'tienda', 'ropa', 'moda',
            }
            domain_keywords = {
                'ciberseguridad', 'ciber', 'seguridad', 'informática', 'informatica', 'it', 'computación',
                'hacking', 'ethical', 'pentesting', 'penetration', 'testing', 'vulnerabilidad',
                'amenaza', 'threat', 'ataque', 'attack', 'brecha', 'breach', 'exploit',
                'cissp', 'ceh', 'oscp', 'cism', 'cisa', 'iso', '27001', 'nist', 'cybersecurity',
                'mitre', 'att&ck', 'framework', 'csf', 'pci', 'dss', 'gdpr', 'hipaa',
                'soc', 'soc2', 'iso27001', 'iso27002',
                'firewall', 'ids', 'ips', 'siem', 'edr', 'xdr', 'mdr', 'antivirus',
                'encriptación', 'encryption', 'criptografía', 'crypto', 'rsa', 'aes', 'sha',
                'red', 'network', 'lan', 'wan', 'vpn', 'proxy', 'dns', 'ip', 'tcp', 'udp',
                'http', 'https', 'ssl', 'tls', 'certificado', 'certificate',
                'auditoría', 'auditoria', 'compliance', 'cumplimiento', 'gobierno', 'governance',
                'riesgo', 'risk', 'incidente', 'incident', 'forense', 'forensic',
                'respuesta', 'response', 'recuperación', 'recovery', 'dr', 'bcp',
                'cloud', 'nube', 'aws', 'azure', 'gcp', 'kubernetes', 'docker', 'devsecops',
                'zero', 'trust', 'iam', 'identity', 'access', 'sso', 'mfa', '2fa', 'otp',
                'malware', 'ransomware', 'phishing', 'spear', 'apt', 'botnet', 'ddos',
                'pentest', 'redteam', 'blueteam', 'purpleteam', 'bugbounty',
            }
            has_ood = any(k in ql for k in ood_keywords)
            has_domain = any(k in ql for k in domain_keywords)
            return bool(has_ood and not has_domain)
        except Exception:
            return False

    def is_detailed(self, query: str) -> bool:
        """Detecta si el usuario pide información completa/detallada."""
        query_lower = query.lower()
        list_patterns = [r'\blista\b', r'\blistado\b', r'\bcuáles\b', r'\bcuales\b', r'\bqué\b', r'\bque\b']
        if any(re.search(p, query_lower) for p in list_patterns):
            if 'toda' not in query_lower and 'todo' not in query_lower:
                return False
        detailed_keywords = [
            'toda la información', 'toda la informacion', 'toda la infomacion',
            'toda informacion', 'toda información', 'toda info', 'toda la info',
            'todo sobre', 'todos los datos', 'todos los detalles',
            'completa', 'completo', 'completas', 'completos',
            'detallada', 'detallado', 'detalladas', 'detallados',
            'exhaustiva', 'exhaustivo', 'extensa', 'extenso', 'amplia', 'amplio',
            'profundidad', 'profunda', 'profundo',
            'explica', 'explicame', 'explícame',
            'describe', 'descripción', 'descripcion',
            'dame todo', 'dame toda',
            'informacion disponible', 'información disponible', 'infomacion disponible',
        ]
        if re.search(r'\b(minimo|mínimo|al menos|como minimo|como mínimo)\s+\d+\s+(palabra|palabras|caracteres)\b', query_lower):
            return True
        if re.search(r'\b\d+\s+(palabra|palabras|caracteres)\b', query_lower):
            return True
        return any(kw in query_lower for kw in detailed_keywords)

    def is_multi_document(self, query: str) -> bool:
        """Detecta si la pregunta requiere información de múltiples documentos/entidades."""
        multi_keywords = [
            'todos', 'todas', 'todo',
            'compara', 'comparar', 'comparación', 'diferencia',
            'resumen', 'lista completa', 'listado',
            'cuáles', 'cuales', 'qué', 'que',
            'varios', 'múltiples', 'diferentes',
            'total', 'suma', 'sumar',
            'cada', 'cada uno',
            'más de', 'menos de', 'mayor', 'menor',
            'entre',
        ]
        query_lower = query.lower()
        query_trimmed = query_lower.strip()
        if not query_trimmed.startswith('y '):
            if ' y ' in query_lower or ' o ' in query_lower or ',' in query_lower:
                words = query.split()
                if any(w[0].isupper() for w in words if len(w) > 2):
                    return True
        return any(kw in query_lower for kw in multi_keywords)

    def is_comparison(self, query: str) -> bool:
        """Detecta si es una comparación entre dos entidades específicas."""
        query_lower = query.lower()
        comparison_keywords = ['compara', 'comparar', 'comparación', 'diferencia', 'vs', 'versus']
        has_comparison_word = any(kw in query_lower for kw in comparison_keywords)
        has_multiple = ' con ' in query_lower or ' y ' in query_lower or ' vs ' in query_lower
        return has_comparison_word and has_multiple

    def is_aggregation(self, query: str) -> bool:
        """Detecta si la pregunta requiere sumar/agregar información de todos los documentos."""
        query_lower = query.lower()
        specific_info_keywords = [
            'información sobre', 'informacion sobre', 'datos de', 'detalles de',
            'háblame de', 'hablame de', 'dame información de', 'dame informacion de',
        ]
        if any(kw in query_lower for kw in specific_info_keywords):
            return False
        type_keywords = ['network', 'cloud', 'endpoint', 'application', 'identity', 'iam', 'firewall', 'ids', 'ips']
        if any(kw in query_lower for kw in type_keywords):
            return False
        aggregation_keywords = [
            'total', 'en total', 'suma total',
            'cuántos controles', 'cuantos controles',
            'cuántos requisitos', 'cuantos requisitos',
            'todos los controles', 'todas las políticas',
            'todas juntas', 'sumar todas',
            'total de requisitos', 'todos los frameworks',
            'de todos', 'de todas', 'entre todos', 'entre todas',
            'todos los que', 'todas las que',
        ]
        comparative_all_keywords = [
            'cuál tiene más', 'cual tiene más', 'cuál tiene menos', 'cual tiene menos',
            'qué tiene más', 'que tiene más', 'qué tiene menos', 'que tiene menos',
            'cuál es el mayor', 'cual es el mayor', 'cuál es el menor', 'cual es el menor',
        ]
        has_aggregation = any(kw in query_lower for kw in aggregation_keywords)
        has_comparative_all = any(kw in query_lower for kw in comparative_all_keywords)
        if self.flags.get('aggregation_ignore_when_specific_entities', True):
            try:
                entities = self._extract_entities(query)
            except Exception:
                entities = []
            generic = {"iso", "nist", "pci", "framework", "control", "politica", "política", "requisito"}
            has_specific_entity = any(e.lower() not in generic for e in entities)
            if (has_aggregation or has_comparative_all) and has_specific_entity:
                return False
        try:
            if self.is_listing(query):
                return False
        except Exception:
            pass
        return has_aggregation or has_comparative_all

    def is_listing(self, query: str) -> bool:
        """Detecta si el usuario pide un listado/enumeración de frameworks/controles/políticas."""
        q = query.lower()
        listing_words = [
            'listado', 'lista', 'listar', 'listame', 'listáme', 'listá todas',
            'listado completo', 'enumerar', 'enumerá', 'enumera',
            'todos los controles', 'todas las políticas', 'todos los frameworks',
            'que frameworks', 'qué frameworks', 'que controles', 'qué controles',
            'que certificaciones', 'qué certificaciones', 'que politicas', 'qué políticas',
        ]
        targets = ['controles', 'control', 'frameworks', 'framework', 'politicas', 'políticas', 'certificaciones', 'requisitos']
        return any(w in q for w in listing_words) and any(t in q for t in targets)

    def is_direct_comparison(self, query: str) -> bool:
        """Detecta comparación directa uno-a-uno entre entidades específicas."""
        q = query.lower()
        comparison_words = ['compara', 'comparar', 'comparación', 'diferencia', 'diferencias', 'vs', 'versus']
        has_comparison = any(w in q for w in comparison_words)
        has_connectors = ' con ' in q or ' y ' in q or ' vs ' in q or ' versus ' in q
        try:
            if self.is_aggregation(query):
                return False
        except Exception:
            pass
        return has_comparison and has_connectors

    def is_simple_numeric(self, query: str) -> bool:
        """Detecta pregunta numérica simple que requiere un solo dato."""
        q = query.lower()
        numeric_starters = [
            'cuántos', 'cuantos', 'cuántas', 'cuantas',
            'cuál es la versión', 'cual es la versión', 'qué versión', 'que versión',
            'versión de', 'version de', 'cuántas veces', 'cuantas veces',
        ]
        has_numeric_starter = any(s in q for s in numeric_starters)
        try:
            if self.is_comparison(query) or self.is_aggregation(query):
                return False
        except Exception:
            pass
        entities = self._extract_entities(query)
        return has_numeric_starter and len(entities) >= 1

    def is_troubleshooting(self, query: str) -> bool:
        """Detecta consulta de diagnóstico/troubleshooting."""
        q = query.lower()
        troubleshooting_starters = [
            'por qué', 'por que', 'porque', 'a qué se debe', 'a que se debe',
            'qué causa', 'que causa', 'cuál es la causa', 'cual es la causa',
            'cómo solucionar', 'como solucionar', 'cómo resolver', 'como resolver',
            'qué hacer si', 'que hacer si', 'qué hacer cuando', 'que hacer cuando',
            'problema', 'falla', 'error', 'no funciona', 'no arranca',
        ]
        return any(s in q for s in troubleshooting_starters)

    def is_follow_up(self, query: str) -> bool:
        """Detecta si es una pregunta de follow-up que requiere contexto previo."""
        q = query.lower().strip()
        if q.startswith('y '):
            return True
        if len(q.split()) <= 3:
            follow_up_patterns = [
                'que tipo', 'cuantos', 'cuantas', 'donde', 'cuando', 'quien',
                'y su', 'y la', 'y el', 'su potencia', 'su ubicacion', 'sus',
                'este parque', 'esta central', 'estos', 'estas',
                'tiene?', 'opera?', 'usa?', 'cuantos tiene',
            ]
            if any(p in q for p in follow_up_patterns):
                return True
        anaphoric_words = ['este', 'esta', 'estos', 'estas', 'ese', 'esa', 'esos', 'esas', 'su', 'sus']
        if any(word in q.split() for word in anaphoric_words):
            return True
        return False

    def is_conceptual(self, query: str) -> bool:
        """Detecta si es una pregunta conceptual/general sobre tecnología o funcionamiento."""
        query_lower = query.lower()
        conceptual_keywords = [
            'como funciona una', 'cómo funciona una', 'como funciona un', 'cómo funciona un',
            'que es una', 'qué es una', 'que es un', 'qué es un',
            'tipos de', 'clases de', 'en general', 'en términos generales',
            'principio de funcionamiento', 'tecnología de', 'tecnologías de',
        ]
        has_conceptual = any(kw in query_lower for kw in conceptual_keywords)
        specific_names = re.findall(r'\b[A-Z][a-záéíóúñ]+(?:\s+[A-Z][a-záéíóúñ]+)*\b', query)
        specific_names = [n for n in specific_names if n.lower() not in ['cómo', 'qué', 'cuál']]
        return has_conceptual and len(specific_names) == 0

    def is_procedural(self, query: str) -> bool:
        """Detecta si es una pregunta sobre cómo hacer algo (procedimiento)."""
        procedural_keywords = [
            'como', 'cómo', 'como hacer', 'cómo hacer',
            'procedimiento', 'proceso', 'pasos para', 'forma de',
            'manera de', 'modo de', 'instrucciones para', 'protocolo', 'protocolos',
            'resetear', 'reset', 'reiniciar', 'configurar', 'instalar', 'operar',
        ]
        return any(kw in query.lower() for kw in procedural_keywords)

    def is_specific_count(self, query: str) -> bool:
        """Detecta si piden una cantidad específica (controles, requisitos, dominios, etc.)."""
        q = (query or '').lower()
        kw_count = ['cuantos', 'cuántos', 'cantidad', 'cuenta', 'número', 'numero', 'how many']
        kw_items = ['control', 'controles', 'requisito', 'requisitos', 'dominio', 'dominios',
                    'categoria', 'categorías', 'categorias', 'modulo', 'módulo', 'modulos', 'módulos']
        has_count = any(k in q for k in kw_count)
        has_item = any(k in q for k in kw_items)
        if has_item and any(k in q for k in ['versión', 'version', 'cvss', 'severidad', 'cada uno', 'por control']):
            return False
        return has_count and has_item

    def is_doc_explanation(self, query: str) -> bool:
        """Detecta si el usuario pide explicación de un documento específico citado."""
        query_lower = query.lower()
        explanation_keywords = [
            'explica', 'explicame', 'explícame', 'detalla', 'detallame',
            'profundiza', 'profundizá', 'a fondo', 'en profundidad',
            'más sobre', 'más info', 'más información', 'amplia', 'ampliá',
        ]
        has_doc_ref = '[Doc' in query or 'documento' in query_lower
        has_explanation_word = any(kw in query_lower for kw in explanation_keywords)
        return has_doc_ref and has_explanation_word

    def is_sum(self, query: str) -> bool:
        """Detecta si el usuario pide sumar/agregar valores."""
        q = (query or '').lower()
        triggers_any = ['suma', 'sumá', 'sumar', 'sumatoria', 'total',
                        'total de controles', 'total de requisitos', 'suma los controles']
        if any(t in q for t in triggers_any):
            if 'total' in q and not any(w in q for w in ['control', 'requisito', 'framework', 'politica', 'política']):
                return False
            return True
        return False

    def requires_full_coverage(self, query: str) -> bool:
        """Detecta si el usuario pide revisar todos los documentos/controles/frameworks."""
        q = query.lower()
        return (
            'cada control' in q or 'cada framework' in q or
            'todos los controles' in q or 'todos los frameworks' in q or
            'cada documento' in q or 'todos los documentos' in q
        )

    # ------------------------------------------------------------------
    # Extracción de filtros
    # ------------------------------------------------------------------

    def extract_tech_filter(self, query: str) -> str:
        """Devuelve categoría canónica de ciberseguridad o '' si no hay filtro."""
        def _norm(s: str) -> str:
            return ''.join(c for c in unicodedata.normalize('NFD', s or '') if unicodedata.category(c) != 'Mn').lower()
        q = _norm(query)
        if any(t in q for t in ['network', 'networking', 'red', 'redes', 'firewall', 'ids', 'ips']):
            return 'Network'
        if any(t in q for t in ['cloud', 'nube', 'aws', 'azure', 'gcp', 'container', 'kubernetes']):
            return 'Cloud'
        if any(t in q for t in ['application', 'appsec', 'owasp', 'web', 'api']):
            return 'Application'
        if any(t in q for t in ['endpoint', 'edr', 'xdr', 'workstation', 'servidor']):
            return 'Endpoint'
        if any(t in q for t in ['identity', 'iam', 'access', 'mfa', 'sso', 'autenticacion', 'autenticación']):
            return 'Identity'
        return ''

    def extract_vendor_filter(self, query: str) -> str:
        """Devuelve vendor canónico o '' si no hay filtro."""
        q = ''.join(c for c in unicodedata.normalize('NFD', query or '') if unicodedata.category(c) != 'Mn').lower()
        if 'crowdstrike' in q:
            return 'CROWDSTRIKE'
        if 'paloalto' in q or 'palo alto' in q:
            return 'PALOALTO'
        if 'fortinet' in q:
            return 'FORTINET'
        if 'cisco' in q:
            return 'CISCO'
        if 'microsoft' in q:
            return 'MICROSOFT'
        if 'splunk' in q:
            return 'SPLUNK'
        return ''
