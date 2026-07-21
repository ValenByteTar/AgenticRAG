"""
Gate determinista para preguntas factuales.
Detecta patrones (precio, CVE, version, temperatura, empleados, password, API endpoint, RFC)
y verifica evidencia literal en el contexto antes de permitir la respuesta del LLM.
Si no hay evidencia, bloquea para evitar alucinaciones.
"""
import re
from typing import Optional, Tuple


FACTUAL_PATTERNS = {
    'precio': {
        'keywords': ['precio', 'costo', 'cuanto cuesta', 'cuanto cuesta', 'price', 'cost', 'tarifa', 'arancel'],
        'evidence': [
            r'\$\s*\d',
            r'\b\d+\s*(?:USD|ARS|EUR|dolares|d[óo]lares|pesos|euros)\b',
            r'(?:price|cost|precio|costo)\s*[:\-]\s*\d',
            r'\b\d{2,5}\s*(?:USD|ARS|EUR)\b',
        ],
    },
    'cve': {
        'keywords': ['cve', 'cve id', 'cve especifico', 'cve espec[íi]fico'],
        'evidence': [r'CVE-\d{4}-\d{4,}'],
    },
    'temperatura': {
        'keywords': ['temperatura', 'temperature', 'grados', 'celsius', 'fahrenheit'],
        'evidence': [
            r'\b\d{2,3}\s*[°º]?\s*(?:C|F|Celsius|Fahrenheit)\b',
            r'(?:temperature|temperatura)\s*[:\-]\s*\d',
            r'\b\d{2,3}\s*(?:grados|degrees)\b',
        ],
    },
    'empleados': {
        'keywords': ['cuantos empleados', 'cu[áa]ntos empleados', 'numero de empleados', 'n[úu]mero de empleados', 'how many employees', 'plantilla'],
        'evidence': [
            r'\b\d{2,6}\s*(?:employees|empleados|staff|trabajadores)\b',
            r'(?:employees|empleados|plantilla)\s*[:\-]\s*\d',
        ],
    },
    'password': {
        'keywords': ['contrase[ñn]a por defecto', 'default password', 'contrase[ñn]a', 'password'],
        'evidence': [
            r'(?:password|contrase[ñn]a)\s*[:\-]\s*\S+',
            r'default\s+(?:password|contrase[ñn]a)\s*[:\-]?\s*\S+',
        ],
    },
    'api_endpoint': {
        'keywords': ['endpoint', 'api de', 'api endpoint', 'endpoints de la api'],
        'evidence': [
            r'https?://\S+',
            r'/api/\S+',
            r'endpoint\s*[:\-]\s*\S+',
        ],
    },
    'rfc': {
        'keywords': [r'rfc\s*\d', 'request for comments'],
        'evidence': [
            r'RFC\s*\d{3,5}',
            r'Request for Comments\s*\d{3,5}',
        ],
        'exact_match': True,
    },
    'cantidad_requisitos': {
        'keywords': ['cuantos requisitos', 'cu[áa]ntos requisitos', 'numero de requisitos', 'n[úu]mero de requisitos', 'how many requirements'],
        'evidence': [
            r'\b\d{2,4}\s*(?:requisitos|requirements)\b',
            r'(?:requisitos|requirements)\s*[:\-]\s*\d',
            r'\b\d{2,4}\s*(?:controls|controles)\b',
        ],
    },
    'version_especifica': {
        'keywords': [r'versi[óo]n\s+\d+\.\d+', r'version\s+\d+\.\d+', r'v\s*\d+\.\d+\.?\d*'],
        'evidence': [
            r'v?\d+\.\d+\.\d+',
            r'versi[óo]n\s+\d+\.\d+',
            r'version\s+\d+\.\d+',
        ],
    },
    'fecha_especifica': {
        'keywords': ['en qu[ée] a[ñn]o', 'en que fecha', 'cuando se public', 'cu[áa]ndo se public', 'release date', 'fecha de publicaci[óo]n'],
        'evidence': [
            r'\b(?:19|20)\d{2}\b',
            r'(?:released?|publicado|publicaci[óo]n)\s*(?:en|on|in)?\s*(?:19|20)\d{2}',
        ],
    },
}


def detect_factual_type(question: str) -> Optional[str]:
    """Detecta si la pregunta es factual y retorna el tipo."""
    ql = question.lower()
    for ftype, config in FACTUAL_PATTERNS.items():
        for kw in config['keywords']:
            if '\\' in kw:
                if re.search(kw, ql):
                    return ftype
            elif kw in ql:
                return ftype
    return None


def has_evidence_in_context(factual_type: str, context: str) -> bool:
    """Verifica si el contexto contiene evidencia del tipo factual."""
    config = FACTUAL_PATTERNS.get(factual_type)
    if not config:
        return True
    ctx_lower = context.lower() if context else ''
    for pattern in config['evidence']:
        if re.search(pattern, ctx_lower, re.IGNORECASE):
            return True
    return False


def extract_entity_from_question(question: str) -> Optional[str]:
    """Extrae la entidad principal de la pregunta (para verificar presencia en contexto)."""
    q = question.strip()
    patterns = [
        r'(?:precio|costo|tarifa)\s+(?:de(?:l| la)?\s+)?(.+?)(?:\s+en\s+\d{4}|\s+en argentina|\?|$)',
        r'(?:cu[áa]ntos|n[úu]mero de)\s+(?:empleados|requisitos)\s+(?:tiene|de)?\s*(.+?)(?:\?|$)',
        r'(?:temperatura)\s+(?:ideal|recomendada)?\s*(?:de(?:l| un)?\s+)?(.+?)(?:\?|$)',
        r'(?:cve)\s+(?:espec[íi]fico|id)?\s+(?:usado|utilizado)?\s+(?:en(?:l| el)?\s+)?(.+?)(?:\?|$)',
        r'(?:qu[ée])\s+(?:dice|habla|trata)\s+(?:el\s+)?(.+?)(?:\s+sobre)?(?:\?|$)',
        r'(?:endpoints?)\s+(?:de(?:l| la)?\s+)?(.+?)(?:\?|$)',
        r'(?:versi[óo]n)\s+(\d+\.\d+\.?\d*)',
        r'(?:contrase[ñn]a)\s+(?:por defecto\s+)?(?:de(?:l| la)?\s+)?(.+?)(?:\?|$)',
    ]
    for pat in patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m and m.group(1):
            entity = m.group(1).strip().strip('.,;:?')
            if len(entity) > 2:
                return entity
    return None


def entity_in_context(entity: str, context: str) -> bool:
    """Verifica si la entidad aparece en el contexto (case-insensitive, partial match)."""
    if not entity or not context:
        return True
    el = entity.lower().strip()
    cl = context.lower()
    tokens = [t for t in el.split() if len(t) > 2]
    if not tokens:
        return True
    matches = sum(1 for t in tokens if t in cl)
    return matches >= max(1, len(tokens) // 2)


def check_factual_gate(question: str, context: str) -> Tuple[bool, str]:
    """
    Gate determinista para preguntas factuales.
    Retorna (allow, reason).
    - allow=True: la pregunta puede pasar al LLM
    - allow=False: bloquear con reason
    """
    ftype = detect_factual_type(question)
    if ftype is None:
        return True, ''

    if not context or len(context.strip()) < 30:
        return False, f'factual_gate: tipo={ftype}, contexto vacio o insuficiente'

    if not has_evidence_in_context(ftype, context):
        return False, f'factual_gate: tipo={ftype}, sin evidencia literal en contexto'

    config = FACTUAL_PATTERNS.get(ftype, {})
    if config.get('exact_match'):
        m = re.search(r'(?:rfc|request for comments)\s*(\d{3,5})', question, re.IGNORECASE)
        if m:
            rfc_num = m.group(1)
            if rfc_num not in context.lower():
                return False, f'factual_gate: tipo={ftype}, RFC {rfc_num} no encontrado en contexto'

    entity = extract_entity_from_question(question)
    if entity and not entity_in_context(entity, context):
        return False, f'factual_gate: tipo={ftype}, entidad "{entity}" no encontrada en contexto'

    return True, f'factual_gate: tipo={ftype}, evidencia encontrada'
