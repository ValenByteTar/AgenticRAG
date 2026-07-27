"""
Post-procesamiento de respuestas RAG.
Extrae la lógica de limpieza, revisión automática y auditoría de rag_hybrid.py.
"""
import re
import time
from typing import TYPE_CHECKING, Optional

import requests
from rich.console import Console

if TYPE_CHECKING:
    from rag_hybrid import HybridRAG

console = Console()


class AnswerPostprocessor:
    """
    Limpia, revisa y audita las respuestas generadas por el LLM.

    Args:
        rag: Referencia al HybridRAG orquestador (back-reference para acceder a
             flags, ollama_model, num_gpu_tuned, config, conversation,
             hybrid_search y clasificadores de consulta).
    """

    def __init__(self, rag: "HybridRAG"):
        self._rag = rag

    # ------------------------------------------------------------------
    # Métodos puramente estáticos (sin dependencias externas)
    # ------------------------------------------------------------------

    def condense_text(self, text: str, max_chars: int = 600) -> str:
        if len(text) <= max_chars:
            return text
        parts = [p.strip() for p in text.split("\n\n") if p.strip()]
        acc = []
        total = 0
        for p in parts:
            if total + len(p) + 2 > max_chars:
                break
            acc.append(p)
            total += len(p) + 2
        if not acc:
            return text[:max_chars]
        return "\n\n".join(acc)

    def truncate_safe_short(self, text: str, limit: int = 1000) -> str:
        """Trunca respetando pasos si el texto parece procedimental."""
        if not text or len(text) <= limit:
            return (text or '')
        lines = [ln for ln in text.splitlines()]
        is_step = lambda ln: bool(re.match(r"^\s*(?:\d+\s*[\.)-]|[\-*•])\s+", ln.strip()))
        has_steps = sum(1 for ln in lines if is_step(ln)) >= 2
        if has_steps:
            acc = []
            total = 0
            for ln in lines:
                if total + len(ln) + 1 > limit:
                    break
                acc.append(ln)
                total += len(ln) + 1
            if acc:
                out = "\n".join(acc).rstrip()
                if out:
                    return out
        cut = text[:limit]
        last_dot = max(cut.rfind('.'), cut.rfind('!'), cut.rfind('?'))
        if last_dot >= max(300, int(limit * 0.5)):
            return cut[:last_dot + 1].strip()
        return cut.strip() + '\u2026'

    def has_numeric_evidence(self, entity: str, results: list, max_chunks: int = 5) -> bool:
        """Verifica evidencia numérica vinculada a la entidad en los resultados."""
        try:
            ent = (entity or "").lower().strip()
            if not ent or not results:
                return False
            synonyms = ['control', 'controles', 'certification', 'framework', 'policy',
                        'incident', 'incidente', 'vulnerability', 'vulnerabilidad', 'risk', 'riesgo']
            for r in results[:max_chunks]:
                txt = (r.get('text', '') or '').lower()
                src = (r.get('metadata', {}) or {}).get('source', '').lower()
                if ent and (ent in txt or ent in src):
                    if any(s in txt for s in synonyms) and any(ch.isdigit() for ch in txt):
                        return True
            return False
        except Exception:
            return False

    def numbers_match_context(self, answer: str, context: str, query: str) -> bool:
        """Comprueba si el número principal de la respuesta aparece en el contexto."""
        try:
            if not answer or not context:
                return False
            ql = (query or '').lower()
            is_numeric_q = any(k in ql for k in ['cuant', 'número', 'numero', 'cuantos', 'cuantas',
                                                   'control', 'controles', 'certification', 'framework',
                                                   'vulnerability', 'incident', 'policy', 'requirement'])
            if not is_numeric_q:
                return False
            nums = re.findall(r"\d{1,3}(?:[\.,\s]\d{3})+|\d+", answer)
            if not nums:
                return False

            def normalize(n: str) -> str:
                return re.sub(r"\D", "", n)

            nums_norm = sorted((normalize(n) for n in nums if normalize(n)), key=lambda x: (len(x), x))
            if not nums_norm:
                return False
            main_num = nums_norm[-1]

            def group_pattern(digits: str) -> str:
                parts = []
                while len(digits) > 3:
                    parts.insert(0, digits[-3:])
                    digits = digits[:-3:]
                if digits:
                    parts.insert(0, digits)
                sep = r"[\.,\s]?"
                return r"\b" + sep.join(parts) + r"\b"

            patterns = [
                re.compile(r"\b" + re.escape(main_num) + r"\b"),
                re.compile(group_pattern(main_num)),
            ]
            ctx_lower = context.lower()
            synonyms = []
            if any(k in ql for k in ['control', 'controles', 'control requirement']):
                synonyms = ['control', 'controles', 'requirement', 'requisito']
            elif any(k in ql for k in ['certification', 'certificacion', 'certified']):
                synonyms = ['certification', 'certificacion', 'certified', 'credential']
            elif any(k in ql for k in ['framework', 'marco', 'estandar', 'estándar']):
                synonyms = ['framework', 'standard', 'estandar', 'marco']
            elif any(k in ql for k in ['vulnerability', 'vulnerabilidad', 'cve']):
                synonyms = ['vulnerability', 'vulnerabilidad', 'cve', 'exploit']
            elif any(k in ql for k in ['incident', 'incidente']):
                synonyms = ['incident', 'incidente', 'breach', 'intrusion']
            if synonyms and not any(s in ctx_lower for s in synonyms):
                return False
            for pat in patterns:
                if pat.search(ctx_lower):
                    return True
            return False
        except Exception:
            return False

    def looks_like_procedural_steps(self, text: str) -> bool:
        """Heurística: detecta si la respuesta tiene formato de pasos."""
        if not text:
            return False
        num_steps = 0
        for line in text.split('\n'):
            line_s = line.strip()
            if re.match(r"^\d+[\.\)]\s+.{5,}", line_s) or re.match(r"^[-*•]\s+.{5,}", line_s):
                num_steps += 1
        return num_steps >= 2

    def has_procedural_evidence(self, context: str, min_sources: int = 2) -> bool:
        """Evidencia para respuestas procedimentales basada en múltiples fuentes."""
        if not context:
            return False
        try:
            sources = re.findall(r'\[Doc \d+ - (.+?) p\.\d+\]', context)
            unique_sources = set(sources)
            proc_kw = ['paso', 'step', 'procedimiento', 'procedure', 'instruccion', 'instrucción',
                       'protocolo', 'configurar', 'instalar', 'ejecutar']
            has_proc_kw = any(kw in context.lower() for kw in proc_kw)
            return len(unique_sources) >= min_sources and has_proc_kw
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Métodos que requieren flags
    # ------------------------------------------------------------------

    def spanish_number_variants(self, answer: str) -> str:
        mapping = {
            '16': ['dieciseis', 'dieciséis'],
            '7': ['siete'],
            '24': ['veinticuatro'],
        }
        lower = answer.lower()
        if self._rag.flags.get('postprocess_number_synonyms', True):
            for num, words in mapping.items():
                if num in answer and not any(w in lower for w in words):
                    pass  # no-op para evitar metacomentarios
        return answer

    # ------------------------------------------------------------------
    # post_process_answer (limpieza principal, depende de flags)
    # ------------------------------------------------------------------

    def post_process_answer(self, answer: str) -> str:
        """FASE 5: Post-procesamiento de la respuesta para limpiar truncamientos y repeticiones."""
        if not answer or len(answer) < 10:
            return answer
        original_len = len(answer)
        if answer.rstrip().endswith('**') or answer.rstrip().endswith('##'):
            last_sentence_end = max(answer.rfind('.'), answer.rfind('!'), answer.rfind('?'), answer.rfind(']'))
            if last_sentence_end > len(answer) * 0.7:
                answer = answer[:last_sentence_end + 1].strip()
        correction_patterns = [
            r'\n\n¿Por qué.*?(?:respuesta anterior|fue incorrecta).*',
            r'\n\nAunque tu respuesta.*?(?:errores|incorrecta|corregida).*',
            r'\n\n\*\*.*?Revisión.*?\*\*.*',
            r'\n\nCorrección:.*',
        ]
        for pattern in correction_patterns:
            try:
                match = re.search(pattern, answer, re.IGNORECASE | re.DOTALL)
                if match and match.start() > len(answer) * 0.5:
                    answer = answer[:match.start()].strip()
                    console.print("[dim]Post-proc: Eliminada sección de corrección[/dim]")
            except Exception:
                pass
        negative_phrase = "No se encontró información"
        count = answer.lower().count(negative_phrase.lower())
        if count > 1:
            lines = answer.split('\n')
            new_lines = []
            found_first = False
            for line in lines:
                if negative_phrase.lower() in line.lower():
                    if not found_first:
                        new_lines.append(line)
                        found_first = True
                else:
                    new_lines.append(line)
            answer = '\n'.join(new_lines)
            console.print(f"[dim]Post-proc: Eliminadas {count - 1} repeticiones de frase negativa[/dim]")
        answer_lower = answer.lower()
        if negative_phrase.lower() in answer_lower and len(answer) > 400:
            neg_pos = answer_lower.find(negative_phrase.lower())
            if neg_pos >= 0:
                after_neg = answer[neg_pos + len(negative_phrase):].strip()
                if len(after_neg) > 200 and ('documento' in after_neg.lower() or 'doc ' in after_neg.lower() or '[' in after_neg):
                    answer = after_neg.strip()
                    console.print("[dim]Post-proc: Eliminada contradicción 'no hay info / pero sí hay'[/dim]")
        tail_negative_patterns = [
            r'^en los documentos para esa consulta\.\s*',
            r'^en los documentos para esa entidad\.\s*',
            r'^no se encontró información en los documentos\.?\s*',
        ]
        for pattern in tail_negative_patterns:
            try:
                if re.search(pattern, answer, re.IGNORECASE):
                    answer = re.sub(pattern, '', answer, flags=re.IGNORECASE).strip()
                    console.print("[dim]Post-proc: Eliminada cola negativa residual[/dim]")
            except Exception:
                pass
        meta_comment_patterns = [
            r'\[ERROR\].*?(?=\n|$)',
            r'La respuesta es incorrecta porque:.*?(?=\n|$)',
            r'Por favor, revise la respuesta y corrija según las reglas establecidas.*?(?=\n|$)',
            r'Respuesta correcta:.*?(?=\n\n|$)',
            r'Reformule la respuesta.*?(?=\n|$)',
        ]
        for pattern in meta_comment_patterns:
            try:
                if re.search(pattern, answer, re.IGNORECASE | re.DOTALL):
                    answer = re.sub(pattern, '', answer, flags=re.IGNORECASE | re.DOTALL).strip()
                    console.print("[dim]Post-proc: Eliminado meta-comentario de auto-corrección[/dim]")
            except Exception:
                pass
        answer = answer.rstrip()
        if answer.endswith('¿Por qué?'):
            last_dot = max(answer.rfind('.'), answer.rfind('!'), answer.rfind('?'))
            if last_dot > len(answer) * 0.8:
                answer = answer[:last_dot + 1].strip()
        reasoning_prefixes = [
            'Entendido. ', 'Análisis: ', 'Respuesta final: ',
            'Basándome en los documentos: ', 'Según los documentos: ',
        ]
        for prefix in reasoning_prefixes:
            if answer.startswith(prefix):
                answer = answer[len(prefix):]
        if len(answer) > 50 and not any(answer.endswith(c) for c in '.!?)]'):
            last_end = max(answer.rfind('.'), answer.rfind('!'), answer.rfind('?'))
            if last_end > len(answer) * 0.8:
                answer = answer[:last_end + 1]
        if len(answer) != original_len:
            console.print(f"[dim]Post-proc: Respuesta limpiada ({original_len} -> {len(answer)} chars)[/dim]")
        return answer.strip()

    # ------------------------------------------------------------------
    # postprocess_answer (limpieza extendida, depende de rag.flags, rag.hybrid_search, rag._query_clf)
    # ------------------------------------------------------------------

    def postprocess_answer(self, question: str, answer: str, context: str) -> str:
        rag = self._rag
        if not answer:
            return answer
        try:
            answer = re.sub(r'\(Doc\s+\d+\)', '', answer, flags=re.IGNORECASE)
            answer = re.sub(r'\s{2,}', ' ', answer)
        except Exception:
            pass
        try:
            try:
                if rag._is_listing_query(question):
                    lines = answer.splitlines()
                    items = []
                    for ln in lines:
                        m = re.match(r"^\s*\d+\s*[\.)\-]\s*(.+?)\s*$", ln)
                        if m:
                            items.append(m.group(1).strip())
                    if not items:
                        for ln in lines:
                            if re.match(r"^\s*(?:Parque|Central|P\.?\s?E\.?|P\.?\s?S\.?)[^:]*\s+.+", ln, flags=re.IGNORECASE):
                                items.append(ln.strip())

                    def norm_name(s: str) -> str:
                        s = re.sub(r"^(?:Parque|Central|P\.?\s?E\.?|P\.?\s?S\.?)\s+", "", s, flags=re.IGNORECASE)
                        s = re.sub(r"\s*\([^)]*\)\s*$", "", s)
                        s = re.sub(r"\s{2,}", " ", s)
                        return s.strip().lower()

                    seen = set()
                    cleaned = []
                    for it in items:
                        key = norm_name(it)
                        if key and key not in seen:
                            seen.add(key)
                            display = re.sub(r"^(?:Parque|Central|P\.?\s?E\.?|P\.?\s?S\.?)\s+", "", it, flags=re.IGNORECASE).strip()
                            cleaned.append(display)
                    if cleaned:
                        return "\n".join([f"{i + 1}. {name}" for i, name in enumerate(cleaned)])
                    else:
                        return answer.strip()
            except Exception:
                pass
            al = answer.lower()
            if rag.flags.get('postprocess_number_synonyms', True):
                if '7' in answer and not any(w in al for w in ['siete']):
                    answer = re.sub(r"\b7\b", "7 (siete)", answer, count=1)
                if '16' in answer and not any(w in al for w in ['dieciseis', 'dieciséis']):
                    answer = re.sub(r"\b16\b", "16 (dieciseis)", answer, count=1)
        except Exception:
            pass
        neg_markers = ["no se encontró", "no se encontro", "no se puede", "no tengo"]
        has_negative = any(m in answer.lower() for m in neg_markers)
        if has_negative:
            try:
                qlq = (question or '').lower()
                doc_patterns = [r'\bpt\s*\d+\b', r'anexo\s+d', r'procedimiento']
                for pat in doc_patterns:
                    if re.search(pat, qlq, re.I):
                        doc_blocks = re.findall(r'\[Doc \d+ - (.+?) p\.\d+\]', context or '', re.I)
                        if doc_blocks:
                            lines = answer.splitlines()
                            cleaned_lines = [ln for ln in lines if not any(m in ln.lower() for m in neg_markers)]
                            if cleaned_lines and len(cleaned_lines) >= len(lines) // 2:
                                answer = '\n'.join(cleaned_lines).strip()
                                has_negative = False
                        break
            except Exception:
                pass
        answer = self.spanish_number_variants(answer)
        try:
            if not rag._is_centrales_list_request(question):
                lines = answer.splitlines()
                has_table = any(('|' in ln and ln.count('|') >= 2) for ln in lines)
                if has_table:
                    cleaned = []
                    for ln in lines:
                        if set(ln.strip()) <= set('-|: '):
                            continue
                        if '|' in ln and ln.count('|') >= 2:
                            parts = [p.strip() for p in ln.split('|') if p.strip()]
                            if parts:
                                take = parts[:2] if len(parts) >= 2 else parts
                                cleaned.append('- ' + ' — '.join(take))
                        else:
                            cleaned.append(ln)
                    answer = '\n'.join([ln for ln in cleaned if ln.strip()])
        except Exception:
            pass
        ql = question.lower()
        is_location = any(k in ql for k in ["donde", "dónde", "ubicaci", "coordenada", "latitud", "longitud"])
        is_comparison = any(k in ql for k in ["compara", "comparar", "comparación", "diferencia", " vs ", "versus"])
        if is_location and context and rag.flags.get('postprocess_location', True):
            ctx = context
            lat = None
            lon = None
            m1 = re.search(r"[Ll]atitud\s*[:\-]?\s*([\-\d\.]+)", ctx)
            if m1:
                lat = m1.group(1)
            m2 = re.search(r"[Ll]ongitud\s*[:\-]?\s*([\-\d\.]+)", ctx)
            if m2:
                lon = m2.group(1)
            pieces = []
            if lat and lat not in answer:
                pieces.append(lat)
            if lon and lon not in answer:
                pieces.append(lon)
            if (not lat or not lon) and rag.flags.get('postprocess_location', True):
                try:
                    extra_results = rag.hybrid_search("latitud longitud coordenadas ubicación", top_k=20, semantic_weight=0.2)
                    etext = "\n".join(r['text'] for r in extra_results)
                    if not lat:
                        m1b = re.search(r"[Ll]atitud\s*[:\-]?\s*([\-\d\.]+)", etext)
                        if m1b:
                            lat = m1b.group(1)
                            if lat not in pieces and lat not in answer:
                                pieces.append(lat)
                    if not lon:
                        m2b = re.search(r"[Ll]ongitud\s*[:\-]?\s*([\-\d\.]+)", etext)
                        if m2b:
                            lon = m2b.group(1)
                            if lon not in pieces and lon not in answer:
                                pieces.append(lon)
                except Exception:
                    pass
            if pieces:
                answer = answer.rstrip() + "\n\nDatos geográficos: " + ", ".join(pieces)
        if is_comparison and context and rag.flags.get('postprocess_comparison_summary', True):
            pass
        try:
            al = answer.lower()
            ql2 = question.lower()
            is_numeric_ans = ('cve' in al) or ('control' in ql2) or any(k in ql2 for k in ['version', 'versión', 'cuantos', 'cuántos'])
            is_coord_ans = any(k in ql2 for k in ['coordenada', 'latitud', 'longitud'])
            is_short = len(answer.strip()) < 100
            if ((is_numeric_ans or is_location or is_coord_ans or is_short) and context):
                ent = None
                m = re.search(r"\[Doc\s+\d+\s+-\s+(.+?)\s+p\.\d+\]", context)
                if m:
                    candidate = m.group(1).strip()
                    if not any(x in candidate.lower() for x in ['listado', 'framework', 'manual', 'guide', 'policy']):
                        ent = candidate
                if not ent:
                    pats = [
                        r"(?:version|versión|información|datos|detalles)\s+(?:de|del|sobre)\s+(?:framework|estándar|control|política|procedimiento)?\s*(.+?)(?:\?|$)",
                        r"cuantos?.*\s+(?:tiene|requiere|es necesario)\s+(.+?)(?:\?|$)",
                        r"(?:framework|estándar|control|política|procedimiento)\s+(?:ISO|NIST|PCI)?\s*(.+?)(?:\?|$)",
                        r"(?:de|del)\s+(.+?)(?:\?|$)",
                    ]
                    for pat in pats:
                        mm = re.search(pat, question, flags=re.IGNORECASE)
                        if mm:
                            ent = mm.group(1).strip().strip(' .?,')
                            ent = re.sub(r"\s+(incluyendo|con|y).*$", "", ent, flags=re.IGNORECASE)
                            ent = re.sub(r"\s+(de|del|la|el)$", "", ent, flags=re.IGNORECASE)
                            if len(ent) > 3:
                                break
                            else:
                                ent = None
                if ent and ent.lower() not in al:
                    ent = ent[0].upper() + ent[1:] if len(ent) > 1 else ent.upper()
                    if is_coord_ans and re.match(r"-?\d+[\.,]\d+.*-?\d+[\.,]\d+", answer.strip()):
                        coords = answer.strip().split(',')
                        if len(coords) >= 2:
                            answer = f"{ent}:\nLatitud: {coords[0].strip()}\nLongitud: {coords[1].strip()}"
                        else:
                            answer = f"{ent}: {answer.strip()}"
                    else:
                        answer = f"{ent}: {answer.strip()}"
        except Exception:
            pass
        try:
            if rag.flags.get('remove_sources_section', True):
                answer = re.split(r"^(?:📄\s*)?Fuentes\s*:\s*$", answer, flags=re.IGNORECASE | re.MULTILINE)[0]
            if rag.flags.get('suppress_followups', True):
                lines = [ln for ln in answer.splitlines() if not ln.strip().startswith('¿')]
                banned_prefixes = (
                    'Por qué', 'Por que', '¿Puedes responder', '¿Hay alguna', '¿Cuál es la tecnología',
                    'Why', 'Explanation', 'Follow-up',
                )
                lines = [ln for ln in lines if not any(ln.strip().startswith(bp) for bp in banned_prefixes)]
                answer = "\n".join(lines)
            if rag.flags.get('deduplicate_lines', True):
                seen: set = set()
                dedup = []
                for ln in [l.rstrip() for l in answer.splitlines() if l.strip()]:
                    key = ln.strip().lower()
                    if key not in seen:
                        seen.add(key)
                        dedup.append(ln)
                answer = "\n".join(dedup)
            if rag.flags.get('suppress_followups', True):
                parts = []
                for ln in answer.splitlines():
                    s = ln.strip()
                    if s.lower().startswith('no es correcta'):
                        continue
                    if s.startswith('Respuesta:'):
                        continue
                    if s.lower().startswith('nota:'):
                        continue
                    if s.startswith('->'):
                        continue
                    if s.startswith('Answer in'):
                        continue
                    if s.startswith('[') and 'Doc ' in s:
                        continue
                    if (s.startswith('(') and (('nota:' in s.lower()) or ('corrección' in s.lower()) or ('revision' in s.lower()) or ('revisión' in s.lower()))):
                        continue
                    if s.lower().startswith('sí, estoy seguro') or s.lower().startswith('si, estoy seguro'):
                        continue
                    if s.lower().startswith('sí, la información') or s.lower().startswith('si, la informacion'):
                        continue
                    if 'el error ocurrió' in s.lower() or 'documento [doc' in s.lower():
                        continue
                    parts.append(ln)
                answer = "\n".join(parts)
            try:
                patterns_inst = [
                    r"(?ims)^\s*INSTRUCCIONES\s*:.*?(?:\n\s*\n|$)",
                    r"(?ims)^\s*Restricciones\s*:.*?(?:\n\s*\n|$)",
                    r"(?ims)^\s*DOCUMENTOS\s*:.*?(?:\n\s*\n|$)",
                    r"(?ims)^\s*PREGUNTA\s*:.*?(?:\n\s*\n|$)",
                    r"(?ims)^\s*ENTIDAD OBJETIVO\s*:.*?(?:\n\s*\n|$)",
                ]
                for pat in patterns_inst:
                    answer = re.sub(pat, "", answer)
                answer = re.sub(r"^\s*(Usuario|Asistente)\s*:\s*.*$", "", answer, flags=re.IGNORECASE | re.MULTILINE)
            except Exception:
                pass
            try:
                import unicodedata as _ud

                def _strip_accents(s: str) -> str:
                    return ''.join(c for c in _ud.normalize('NFD', s) if _ud.category(c) != 'Mn')

                instruction_phrases = {
                    'extrae solo datos explicitos', 'respuesta breve y directa', 'no inventes',
                    'no aproximes numeros', 'si no encuentras info', 'no agregues secciones extra',
                    'no repitas la misma informacion', 'responde en 2-4 lineas maximo',
                }
                filtered = []
                for ln in answer.splitlines():
                    s_norm = _strip_accents(ln.strip().lower())
                    if any(p in s_norm for p in instruction_phrases):
                        continue
                    filtered.append(ln)
                answer = "\n".join(filtered)
            except Exception:
                pass
            try:
                answer = re.sub(r"(?i)(\b\d+)\s*\(\s*[a-záéíóúüñ\s]+\)\s*\.(\d+)\b", r"\1.\2", answer)
            except Exception:
                pass
            try:
                answer = re.sub(r"\n\s*\n+", "\n\n", answer).strip()
            except Exception:
                pass
            try:
                lines = answer.splitlines()
                kept = []
                for ln in lines:
                    s = ln.strip().lower()
                    is_pure_negative = (
                        s in ['no se.', 'no hay.', 'no se menciona.', 'no existe.', 'no encontrado.'] or
                        s == 'no se encontró información en los documentos para esa consulta.' or
                        (s.startswith('no se encontró información') and len(s) < 80)
                    )
                    if is_pure_negative:
                        continue
                    kept.append(ln)
                answer = '\n'.join(kept)
                if not answer.strip():
                    answer = 'No se encontró información en los documentos para esa consulta.'
            except Exception:
                pass
            max_lines = int(rag.flags.get('max_answer_lines', 0) or 0)
            if max_lines > 0:
                multi_entity_markers = ['todos', 'todas', 'cada', 'y', ',']
                is_multi_entity = any(marker in question.lower() for marker in multi_entity_markers)
                if not is_multi_entity:
                    parts = [l for l in answer.splitlines() if l.strip()]
                    if len(parts) > max_lines:
                        answer = "\n".join(parts[:max_lines])
        except Exception:
            pass
        try:
            ql2 = (question or '').lower()
            ask_es = any(k in ql2 for k in ['entrada en servicio', 'e/s', 'habilitacion comercial', 'habilitación comercial', 'puesta en marcha'])
            if not ask_es:
                remove_pats = [
                    r'(?i)^\s*entrada en servicio.*$',
                    r'(?i)^\s*e\/s.*$',
                    r'(?i)^\s*habilitaci[oó]n comercial.*$',
                    r'(?i)^\s*puesta en marcha.*$',
                ]
                filtered_lines = []
                for ln in (answer or '').splitlines():
                    s = ln.strip()
                    if any(re.search(p, s) for p in remove_pats):
                        continue
                    filtered_lines.append(ln)
                answer = "\n".join(filtered_lines).strip()
        except Exception:
            pass
        return answer

    # ------------------------------------------------------------------
    # self_review_answer (depende de rag.ollama_model, rag.conversation, etc.)
    # ------------------------------------------------------------------

    def self_review_answer(self, query: str, answer: str, context: str) -> str:
        """Auto-revisión: el LLM verifica su propia respuesta y la corrige si es necesaria."""
        rag = self._rag
        try:
            console.print(f"[cyan]Iniciando auto-revisión de la respuesta...[/cyan]")
            last_query = rag.conversation.get_last_user_message()
            conv_context_str = ""
            if last_query and last_query.strip().lower() != query.strip().lower():
                conv_context_str = f"\nCONTEXTO CONVERSACIONAL:\nPregunta anterior: {last_query}\n"
            try:
                is_proc = rag._is_procedural_question(query)
            except Exception:
                is_proc = False
            try:
                if is_proc and self.looks_like_procedural_steps(answer) and self.has_procedural_evidence(context, min_sources=2):
                    console.print(f"[green]OK Evidencia procedimental multi-documento detectada: se conserva la respuesta original[/green]")
                    try:
                        self.audit_auto_review_decision(query, context, answer, None, 'kept_original_procedural_bypass', 'short')
                    except Exception:
                        pass
                    return answer
            except Exception:
                pass
            try:
                if (not is_proc) and self.numbers_match_context(answer, context, query):
                    console.print(f"[green]OK Evidencia numérica encontrada en contexto: respuesta aprobada sin cambios[/green]")
                    try:
                        self.audit_auto_review_decision(query, context, answer, None, 'kept_original_numeric_ok', 'short')
                    except Exception:
                        pass
                    return answer
            except Exception:
                pass
            proc_extra = ""
            if is_proc:
                proc_extra = (
                    "\n6. Esta es una consulta procedimental: valida que la respuesta incluya PASOS claros y haga referencia a PROTECCIONES si corresponde. Si no hay evidencia suficiente para pasos específicos, responde: \"No hay evidencia suficiente en los documentos proporcionados\"."
                )
            review_prompt = f"""Eres un revisor técnico. SOLO aprueba respuestas con evidencia explícita del contexto.

PREGUNTA: {query}{conv_context_str}

DOCUMENTOS:
{context}

RESPUESTA A REVISAR:
{answer}

INSTRUCCIONES ESTRICTAS:

1. Si la respuesta contiene CANTIDADES (números), verifica que esos números aparezcan literalmente en DOCUMENTOS junto al tema consultado.
2. EXIGE EVIDENCIA: la salida aprobada debe poder citar con formato [Doc i - fuente p.j] donde aparece la cifra.
3. Si NO encuentras el número en DOCUMENTOS o no está asociado al tema/entidad, NO apruebes.
4. Si está completa y correcta: responde SOLO "OK".
5. Si es incompleta/incorrecta o no hay evidencia: genera la respuesta CORREGIDA DIRECTAMENTE basada SOLO en DOCUMENTOS. Si no hay evidencia suficiente, responde: "No hay evidencia suficiente en los documentos proporcionados".
 {proc_extra}

CRÍTICO - FORMATO DE SALIDA:
- Respuesta completa y correcta -> "OK"
- Respuesta incompleta/incorrecta -> [respuesta corregida DIRECTAMENTE, sin prefijos ni explicaciones]

PROHIBIDO (NUNCA INCLUYAS):
- Prefijos como "Respuesta incompleta.", "Respuesta corregida:", etc.
- Explicaciones de tu razonamiento o metacomentarios.

Revisión:"""

            review_options = {
                "num_predict": 600,
                "temperature": 0.2,
                "top_k": 30,
                "top_p": 0.85,
                "num_ctx": 4096,
                "num_thread": 12,
                "num_gpu": getattr(rag, 'num_gpu_tuned', 99),
                "num_batch": 256,
                "repeat_penalty": 1.1,
                "stop": ["VERIFICACIÓN", "VERIFICA COMPLETITUD", "DECISIÓN",
                         "**VERIFICACIÓN**", "**VERIFICA", "**DECISIÓN**",
                         "\n\nVERIFICACIÓN", "\n\nDECISIÓN"],
            }
            review_payload = {
                "model": rag.ollama_model,
                "prompt": review_prompt,
                "stream": False,
                "options": review_options,
                "keep_alive": "15m",
            }
            console.print(f"[dim]Enviando respuesta a revisión...[/dim]")
            start_time = time.time()
            context_len = len(context) + len(answer)
            review_timeout = 120 if context_len > 5000 else (90 if context_len > 3000 else 60)
            response = requests.post("http://localhost:11434/api/generate", json=review_payload, timeout=review_timeout)
            elapsed = time.time() - start_time
            console.print(f"[green]Revisión completada en {elapsed:.1f}s[/green]")
            if response.status_code == 200:
                review_result = response.json().get('response', '').strip()
                console.print(f"[dim]Preview de decisión del revisor: {review_result[:200]}{'...' if len(review_result) > 200 else ''}[/dim]")
                if review_result.upper().startswith("OK"):
                    trivial = len((answer or '').strip()) <= 4 or (not re.search(r"[A-Za-z0-9]", answer or ''))
                    if not trivial:
                        console.print(f"[green]OK Respuesta aprobada por auto-revisión[/green]")
                        try:
                            self.audit_auto_review_decision(query, context, answer, None, 'kept_original_review_ok', 'short')
                        except Exception:
                            pass
                        return answer
                    if not is_proc:
                        try:
                            m = re.search(r'CVE-\d{4}-\d{4,}', context, flags=re.IGNORECASE)
                            if m:
                                return m.group(0)
                        except Exception:
                            pass
                    return "No hay evidencia suficiente en los documentos proporcionados."
                else:
                    try:
                        if self.numbers_match_context(answer, context, query):
                            console.print(f"[green]OK Evidencia numérica valida en CONTEXTO - se conserva la respuesta original[/green]")
                            return answer
                    except Exception:
                        pass
                    if rag.flags.get('enable_salvage', False) and not is_proc:
                        try:
                            rr_low = review_result.lower()
                            neg_flags = ['no hay evidencia', 'no se puede determinar', 'no se puede', 'no se encontró información', 'no se encontro informacion']
                            if any(f in rr_low for f in neg_flags):
                                qlq = (query or '').lower()
                                ask_cve = any(k in qlq for k in ['cve', 'vulnerabilidad', 'vulnerability'])
                                ask_control = any(k in qlq for k in ['control', 'controles', 'control number'])
                                ask_cve_num = any(k in qlq for k in ['cve-', 'cve id'])
                                m_cve = re.search(r'CVE-\d{4}-\d{4,}', context, flags=re.IGNORECASE)
                                if m_cve and (ask_cve or ask_cve_num):
                                    val = m_cve.group(0)
                                    console.print(f"[green]OK Salvataje: CVE encontrado en contexto pese a revisión negativa[/green]")
                                    try:
                                        self.audit_auto_review_decision(query, context, answer, f"{val}", 'accepted_correction_salvage', 'short')
                                    except Exception:
                                        pass
                                    return f"{val}"
                                m_ctrl = re.search(r'(?:control|controles)\s+(?:[A-Z\.]+)?\s*\d+(?:\.\d+)?', context, flags=re.IGNORECASE)
                                if m_ctrl and ask_control:
                                    val2 = m_ctrl.group(0)
                                    console.print(f"[green]OK Salvataje: Número de control encontrado en contexto pese a revisión negativa[/green]")
                                    try:
                                        self.audit_auto_review_decision(query, context, answer, f"{val2}", 'accepted_correction_salvage', 'short')
                                    except Exception:
                                        pass
                                    return f"{val2}"
                        except Exception:
                            pass
                    rr_norm = re.sub(r"\s+", " ", review_result).strip()
                    rr_simple = rr_norm.lower().replace(":", "").replace("la respuesta a la pregunta es", "").strip()
                    if rr_simple.upper().startswith("OK") or rr_simple in {"ok", "ok."}:
                        trivial = len(answer.strip()) <= 4 or (not re.search(r"[A-Za-z0-9]", answer))
                        try:
                            has_ev = self.numbers_match_context(answer, context, query)
                        except Exception:
                            has_ev = False
                        if not trivial and has_ev:
                            console.print(f"[green]OK Revisión indicó OK implícito con evidencia - se conserva la respuesta original[/green]")
                            return answer
                        else:
                            console.print(f"[yellow]Revisión indicó OK pero la respuesta original es trivial o sin evidencia - intentando extraer del contexto[/yellow]")
                            review_result = ""
                    console.print(f"[yellow]ADVERTENCIA Respuesta corregida por auto-revisión[/yellow]")
                    corrected = review_result
                    corrected = re.sub(r'^(?:Respuesta incompleta|Respuesta completa|RESPUESTA INCOMPLETA|RESPUESTA COMPLETA)(?:\s+porque.*?)?(?=La respuesta correcta|$)', '', corrected, flags=re.IGNORECASE | re.DOTALL)
                    corrected = re.sub(r'^porque\s+.*?(?=La respuesta correcta|$)', '', corrected, flags=re.IGNORECASE | re.DOTALL)
                    corrected = re.sub(r'^La respuesta (?:es|está) incompleta.*?(?=La respuesta correcta|$)', '', corrected, flags=re.IGNORECASE | re.DOTALL)
                    corrected = re.sub(r'^La respuesta correcta (?:sería|es|debería ser):\s*\n*', '', corrected, flags=re.IGNORECASE)
                    corrected = re.sub(r'(?im)^(no apruebo.*)$', '', corrected)
                    corrected = re.sub(r'(?im)^(la respuesta original.*)$', '', corrected)
                    corrected = re.sub(r'(?im)^(la pregunta es.*)$', '', corrected)
                    corrected = re.sub(r'(?im)^(la respuesta correcta.*)$', '', corrected)
                    corrected = corrected.strip()
                    if not corrected or corrected.upper() == "OK" or len(corrected) <= 4:
                        if not is_proc:
                            try:
                                m = re.search(r'CVE-\d{4}-\d{4,}', context, flags=re.IGNORECASE)
                                if m:
                                    return m.group(0)
                            except Exception:
                                pass
                        try:
                            self.audit_auto_review_decision(query, context, answer, "No hay evidencia suficiente en los documentos proporcionados.", 'accepted_correction_negative', 'short')
                        except Exception:
                            pass
                        return "No hay evidencia suficiente en los documentos proporcionados."
                    if any(marker in corrected[:300].upper() for marker in ['VERIFICACIÓN', 'VERIFICA COMPLETITUD', 'DECISIÓN']):
                        match = re.search(r'(?:RESPUESTA CORREGIDA|Respuesta corregida|CORRECCIÓN|Corrección):\s*\n*(.*)', corrected, flags=re.IGNORECASE | re.DOTALL)
                        if match:
                            corrected = match.group(1).strip()
                        else:
                            lines = corrected.split('\n')
                            start_idx = 0
                            for i, line in enumerate(lines):
                                line_stripped = line.strip()
                                if line_stripped and not any(mrk in line.upper() for mrk in ['VERIFICACIÓN', 'VERIFICA', 'DECISIÓN', 'COMPLETITUD', 'EXACTITUD']):
                                    if not re.match(r'^\*\*[A-Z\s]+\*\*$', line_stripped) and not re.match(r'^\d+\.\s*\*\*[A-Z\s]+\*\*', line_stripped):
                                        start_idx = i
                                        break
                            if start_idx > 0:
                                corrected = '\n'.join(lines[start_idx:]).strip()
                            if is_proc and self.looks_like_procedural_steps(corrected):
                                if self.numbers_match_context(corrected, context, query):
                                    console.print(f"[green]OK Evidencia numérica valida en CONTEXTO - se conserva la respuesta original[/green]")
                                    return answer
                    lines = corrected.split('\n')
                    cleaned_lines = []
                    for line in lines:
                        line_lower = line.lower().strip()
                        if line_lower in ['verificación', 'decisión', 'completitud', 'exactitud', 'respuesta incompleta', 'respuesta completa']:
                            continue
                        if re.match(r'^\*\*(?:VERIFICACIÓN|VERIFICA|DECISIÓN|COMPLETITUD|EXACTITUD)\*\*', line.strip(), flags=re.IGNORECASE):
                            continue
                        if re.match(r'^\d+\.\s*\*\*(?:COMPLETITUD|EXACTITUD|VERIFICACIÓN|DECISIÓN)\*\*', line.strip(), flags=re.IGNORECASE):
                            continue
                        cleaned_lines.append(line)
                    corrected = '\n'.join(cleaned_lines).strip()
                    corrected = re.sub(r'\n\s*\n\s*\n+', '\n\n', corrected)
                    console.print(f"[dim]Longitud original: {len(answer)} chars -> Corregida: {len(corrected)} chars[/dim]")
                    if is_proc:
                        try:
                            looks_steps_orig = self.looks_like_procedural_steps(answer)
                            looks_steps_corr = self.looks_like_procedural_steps(corrected)
                        except Exception:
                            looks_steps_orig = False
                            looks_steps_corr = False
                        if (len(corrected) < max(80, int(len(answer) * 0.6))) or (looks_steps_orig and not looks_steps_corr):
                            console.print(f"[yellow]Corrección corta o no procedimental, conservando respuesta original[/yellow]")
                            try:
                                self.audit_auto_review_decision(query, context, answer, corrected, 'kept_original_reject_correction', 'short')
                            except Exception:
                                pass
                            return answer
                    if len(corrected) > 20:
                        if is_proc:
                            try:
                                looks_steps_corr = self.looks_like_procedural_steps(corrected)
                            except Exception:
                                looks_steps_corr = False
                            has_citation = ('[Doc ' in corrected) or ('[doc ' in corrected.lower())
                            if not (looks_steps_corr and has_citation):
                                console.print(f"[yellow]Corrección sin pasos o sin citas explícitas, conservando original[/yellow]")
                                try:
                                    self.audit_auto_review_decision(query, context, answer, corrected, 'kept_original_missing_citation_or_steps', 'short')
                                except Exception:
                                    pass
                                return answer
                        else:
                            has_citation_np = ('[Doc ' in corrected) or ('[doc ' in corrected.lower())
                            if not has_citation_np:
                                console.print(f"[yellow]Corrección sin citas explícitas, conservando original[/yellow]")
                                try:
                                    self.audit_auto_review_decision(query, context, answer, corrected, 'kept_original_missing_citation', 'short')
                                except Exception:
                                    pass
                                return answer
                        try:
                            self.audit_auto_review_decision(query, context, answer, corrected, 'accepted_correction', 'short')
                        except Exception:
                            pass
                        return corrected
                    else:
                        console.print(f"[yellow]Corrección muy corta, manteniendo original[/yellow]")
                        try:
                            self.audit_auto_review_decision(query, context, answer, corrected, 'kept_original_correction_too_short', 'short')
                        except Exception:
                            pass
                        return answer
            else:
                console.print(f"[yellow]Error en auto-revisión (HTTP {response.status_code}), manteniendo respuesta original[/yellow]")
                try:
                    self.audit_auto_review_decision(query, context, answer, None, 'kept_original_review_error', 'short')
                except Exception:
                    pass
                return answer
        except Exception as e:
            console.print(f"[yellow]Error en auto-revisión: {e}, manteniendo respuesta original[/yellow]")
            try:
                self.audit_auto_review_decision(query, context, answer, None, 'kept_original_exception', 'short')
            except Exception:
                pass
            return answer

    # ------------------------------------------------------------------
    # audit_auto_review_decision
    # ------------------------------------------------------------------

    def audit_auto_review_decision(
        self,
        query: str,
        context: str,
        original_answer: str,
        corrected_answer: Optional[str] = None,
        system_decision: str = '',
        length_mode: str = 'short',
    ) -> None:
        """Audita la decisión de auto-revisión usando reglas explícitas."""
        rag = self._rag
        try:
            cfg = getattr(rag, 'config', {}) or {}
            if not cfg.get('enable_audit', True):
                return
            rules = (
                "Eres un auditor técnico de un sistema RAG + LLM con filtro de auto-revisión.\n"
                "Tu tarea es evaluar si la decisión de auto-revisión fue correcta.\n\n"
                "1. Si la consulta es procedimental y la respuesta tiene formato de pasos (≥2 pasos numerados o con viñetas) "
                "y hay evidencia técnica en el contexto, entonces la respuesta original debe conservarse.\n"
                "2. Si la corrección propuesta es más corta, pierde formato de pasos, o es un rechazo genérico, "
                "debe rechazarse y conservar la original.\n"
                "3. Solo aceptar una corrección si: tiene evidencia explícita en el contexto, mantiene o mejora "
                "el formato adecuado, y aporta claridad o precisión técnica.\n"
                "4. En modo `long` nunca debe aplicarse auto-revisión.\n"
                "5. En modo `short`, si la respuesta supera 1000 caracteres, se permite truncar en el último punto "
                "completo, pero nunca cortar en medio de un paso.\n\n"
                "Salida esperada:\n- \"DECISIÓN CORRECTA\" o \"DECISIÓN INCORRECTA\"\n"
                "- Justificación breve (máx. 3 frases).\n"
                "No inventes contenido nuevo, solo evalúa la decisión según las reglas."
            )
            prompt = (
                f"{rules}\n\n"
                f"Query del usuario:\n{query}\n\n"
                f"Contexto recuperado:\n{context[:4000]}\n\n"
                f"Respuesta original del LLM:\n{(original_answer or '')[:2000]}\n\n"
                f"Respuesta corregida por el revisor:\n{(corrected_answer or 'N/A')[:2000]}\n\n"
                f"Decisión tomada por el sistema: {system_decision} | length_mode={length_mode}\n\n"
                f"Instrucción: responde SIEMPRE en español.\n\nVeredicto:"
            )
            payload = {
                "model": getattr(rag, 'ollama_model', 'mistral:7b'),
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": 160,
                    "temperature": 0.1,
                    "top_k": 30,
                    "top_p": 0.85,
                    "num_ctx": getattr(rag, 'num_ctx_tuned', 2048),
                    "num_gpu": getattr(rag, 'num_gpu_tuned', 99),
                    "stop": ["```", "JSON", "Análisis", "Analizando"],
                },
                "keep_alive": "10m",
            }
            r = requests.post("http://localhost:11434/api/generate", json=payload, timeout=30)
            if r.status_code == 200:
                verdict = r.json().get('response', '').strip()
                if verdict:
                    console.print(f"[dim]AUDITOR: {verdict}[/dim]")
        except Exception:
            pass
