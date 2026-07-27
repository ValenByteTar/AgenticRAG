"""
Construcción de contexto y prompts para el LLM.
Extrae la lógica de armado de contexto de rag_hybrid.py.
"""
import json
import re
from typing import TYPE_CHECKING, List, Optional

import requests
from rich.console import Console

if TYPE_CHECKING:
    from rag_hybrid import HybridRAG

console = Console()


class ContextBuilder:
    """
    Ensambla el contexto de documentos y construye los prompts de FOCUS para el LLM.

    Args:
        rag: Back-reference al HybridRAG para acceder a ollama_model y num_gpu_tuned.
    """

    def __init__(self, rag: "HybridRAG"):
        self._rag = rag

    # ------------------------------------------------------------------
    # Construcción de contexto (sin dependencias externas)
    # ------------------------------------------------------------------

    def build_context_from_results(self, results: list) -> str:
        """Construye el contexto concatenando [Doc - src p.X] + texto."""
        try:
            parts = []
            for r in results or []:
                md = r.get('metadata', {}) or {}
                src = md.get('source', 'Unknown')
                page = md.get('page', 0)
                prefix = f"[Doc - {src} p.{page}]"
                parts.append(prefix + "\n" + (r.get('text') or ''))
            return "\n\n".join(parts)
        except Exception:
            return ''

    def build_structured_context(self, results: list, max_chars: int = 6000) -> str:
        """Construye contexto estructurado por categorías de información."""
        if not results:
            return ""
        by_category: dict = {'definition': [], 'procedure': [], 'example': [], 'mention': []}
        for r in results:
            cat = r.get('content_category', 'mention')
            by_category[cat].append(r)
        context_parts = []
        total_chars = 0
        summary_parts = [f"{len(items)} {cat}" for cat, items in by_category.items() if items]
        if summary_parts:
            context_parts.append(f"[RESUMEN] Documentos organizados: {', '.join(summary_parts)}")
        section_names = {
            'definition': '=== DEFINICIONES Y CONCEPTOS ===',
            'procedure': '=== PROCEDIMIENTOS Y MEJORES PRÁCTICAS ===',
            'example': '=== EJEMPLOS Y CASOS ===',
            'mention': '=== MENCIONES ADICIONALES ===',
        }
        doc_counter = 0
        for category in ['definition', 'procedure', 'example', 'mention']:
            items = by_category.get(category, [])
            if not items:
                continue
            section_text = f"\n{section_names[category]}\n"
            if total_chars + len(section_text) > max_chars:
                break
            context_parts.append(section_text)
            total_chars += len(section_text)
            for r in items:
                doc_counter += 1
                source = r.get('metadata', {}).get('source', 'Unknown')
                page = r.get('metadata', {}).get('page', 0)
                text = r.get('text', '')[:700]
                fragment = f"[Doc {doc_counter} - {source[:50]} p.{page}]\n{text}\n"
                if total_chars + len(fragment) > max_chars:
                    context_parts.append("[Contexto truncado por límite de tamaño]")
                    break
                context_parts.append(fragment)
                total_chars += len(fragment)
        return '\n'.join(context_parts)

    def collect_snippets_for_llm_scoring(self, results: list, entities: list,
                                          top_n: int = 12) -> list:
        """Prepara snippets compactos con índice original para ser puntuados por el LLM."""
        snippets: list = []
        try:
            for i, r in enumerate(results[:top_n]):
                txt = (r.get('text', '') or '').strip()
                md = r.get('metadata', {}) or {}
                src = md.get('source', 'Unknown')
                pg = md.get('page', 0)
                label = f"[Doc {i + 1} - {str(src).split('.pdf')[0]} p.{pg}]"
                if len(txt) > 600:
                    txt = txt[:600] + '\u2026'
                snippets.append({'i': i, 'label': label, 'text': txt})
            return snippets
        except Exception:
            return snippets

    # ------------------------------------------------------------------
    # Construcción de prompts FOCUS (sin dependencias externas)
    # ------------------------------------------------------------------

    def build_focus_prompt(self, question: str, attribute: str, entities: list,
                            length_mode: str) -> str:
        """Construye instrucciones FOCUS para orientar al LLM."""
        try:
            ql = (question or '').lower()
            ent = ''
            try:
                ent = (entities[0] if entities else '').strip()
            except Exception:
                pass
            lines = [
                "FOCUS:",
                f"- Responde SOLO el atributo '{attribute or 'dato solicitado'}'" + (f" para la entidad '{ent}'." if ent else "."),
                "- Usa SOLO evidencia de los fragmentos proporcionados (no inventes).",
                "- Si no hay evidencia explícita en los fragmentos, responde EXACTAMENTE: INSUFICIENTE.",
                "- Incluye al menos una cita en formato [Doc i - fuente p.X].",
            ]
            if any(k in ql for k in ['potencia', 'mw', 'kilowatt', 'kw']) and any(k in ql for k in ['wtg', 'aerogenerador', 'turbina']):
                lines.append("- No confundas potencia TOTAL del parque con potencia por WTG (unidad).")
            if 'celda' in ql or 'celdas' in ql:
                lines.append("- Evita tablas; entrega líneas simples con citas.")
            if any(k in ql for k in ['protección', 'proteccion', 'protecciones', 'ansi', 'relé', 'rele', 'relay']):
                lines.append("- Consulta de protecciones: responde con funciones/dispositivos (ANSI) o pasos relevantes; no incluyas plantilla de WTG/inversores salvo evidencia directa.")
            if isinstance(length_mode, str) and length_mode.strip().lower() == 'short':
                lines.append("- Respuesta CORTA y PRECISA, sin preámbulos ni razonamiento visible.")
            return "\n".join(lines)
        except Exception:
            return "FOCUS: Usa SOLO evidencia de los fragmentos. Si no hay evidencia, responde EXACTAMENTE: INSUFICIENTE."

    def build_detailed_focus_prompt(self, question: str, entities: list,
                                     length_mode: str) -> str:
        """FOCUS para modo detallado: fuerza cobertura amplia por secciones con citas."""
        try:
            ent = ''
            try:
                ent = (entities[0] if entities else '').strip()
            except Exception:
                pass
            ql = (question or '').lower()
            ents_low = ' '.join([e.lower() for e in (entities or []) if e])
            is_solar = any(k in ql or k in ents_low for k in [
                'solar', 'fotovoltaico', 'fotovoltaica', 'panel', 'paneles',
                'inversor', 'inverter', 'ct', 'centro de transformación',
                'centro de transformacion', 'mppt', 'string',
            ])
            is_eolico = any(k in ql or k in ents_low for k in [
                'eólico', 'eolico', 'wtg', 'aerogenerador', 'turbina', 'turbinas',
            ])
            is_prot = any(k in ql for k in [
                'protección', 'proteccion', 'protecciones', 'ansi', 'relé', 'rele', 'relay',
            ])
            lines = [
                "FOCUS DETALLADO:",
                f"- Entidad objetivo: '{ent}'." if ent else "- Entidad objetivo: la indicada en la pregunta.",
                "- Proporciona TODOS los detalles disponibles, organizados en puntos (sin preámbulos):",
            ]
            if is_prot:
                lines += [
                    "  1) Protecciones/funciones ANSI aplicables [Doc i - fuente p.X]",
                    "  2) Ajustes/umbrales y condiciones de actuación [Doc i - fuente p.X]",
                    "  3) Dispositivos y relés involucrados [Doc i - fuente p.X]",
                    "  4) Procedimientos o recomendaciones de operación [Doc i - fuente p.X]",
                ]
            else:
                lines += [
                    "  1) Definición y propósito del concepto/certificación [Doc i - fuente p.X]",
                    "  2) Requisitos y prerequisitos [Doc i - fuente p.X]",
                    "  3) Estructura y dominios/componentes clave [Doc i - fuente p.X]",
                    "  4) Aplicabilidad y casos de uso [Doc i - fuente p.X]",
                    "  5) Relación con otros frameworks/estándares [Doc i - fuente p.X]",
                    "  6) Referencias adicionales en documentos [Doc i - fuente p.X]",
                ]
            lines += [
                "- Usa SOLO evidencia de los fragmentos proporcionados (no inventes).",
                "- Cada dato debe incluir al menos UNA cita [Doc i - fuente p.X].",
                "- Si algún punto no tiene evidencia explícita, omítelo sin inventar.",
            ]
            if isinstance(length_mode, str) and length_mode.strip().lower() == 'short':
                lines.append("- Sé conciso, pero no omitas secciones con evidencia.")
            return "\n".join(lines)
        except Exception:
            return (
                "FOCUS DETALLADO:\n"
                "- Proporciona TODOS los detalles disponibles, cada uno con cita.\n"
                "- Usa SOLO evidencia de los fragmentos."
            )

    # ------------------------------------------------------------------
    # Métodos que dependen de ollama_model (back-reference)
    # ------------------------------------------------------------------

    def llm_score_snippets(self, snippets: list, question: str, attribute: str,
                            entities: list) -> list:
        """Pide al LLM puntuar snippets por alineación con entidad/atributo."""
        rag = self._rag
        if not snippets:
            return []
        try:
            ents = ', '.join([e for e in (entities or []) if e])
            lines = [f"- i={sn['i']} {sn['label']}\n{sn['text']}" for sn in snippets]
            prompt = (
                "Eres un evaluador. Puntúa cada snippet por alineación con la PREGUNTA, la ENTIDAD (si hay) y el ATRIBUTO.\n"
                f"PREGUNTA: {question}\nENTIDAD: {ents or 'N/A'}\nATRIBUTO: {attribute or 'N/A'}\n\n"
                "SNIPPETS:\n" + "\n\n".join(lines) + "\n\n"
                "FORMATO JSON ESTRICTO (salida SOLO JSON, sin comentarios):\n"
                "[ {\"i\": <int>, \"entity_aligned\": true/false, \"attribute_aligned\": true/false, \"has_numbers\": true/false, \"score\": 0.0-1.0 } , ... ]"
            )
            payload = {
                'model': rag.ollama_model,
                'prompt': prompt,
                'stream': False,
                'options': {
                    'num_predict': 220, 'temperature': 0.2, 'top_k': 30,
                    'top_p': 0.85, 'num_ctx': getattr(rag, 'num_ctx_tuned', 2048),
                    'num_gpu': getattr(rag, 'num_gpu_tuned', 99),
                },
                'keep_alive': '10m',
            }
            r = requests.post("http://localhost:11434/api/generate", json=payload, timeout=40)
            if r.status_code != 200:
                return []
            raw = (r.json().get('response', '') or '').strip()
            m = re.search(r"\[.*\]", raw, flags=re.DOTALL)
            data = json.loads(m.group(0) if m else raw)
            scored = []
            for it in data:
                try:
                    scored.append((float(it.get('score', 0.0)), int(it.get('i', -1))))
                except Exception:
                    continue
            scored = sorted([t for t in scored if t[1] >= 0], key=lambda x: x[0], reverse=True)
            return [i for _, i in scored]
        except Exception:
            return []

    def llm_extract_json(self, context: str, question: str, focus_block: str) -> Optional[dict]:
        """Pide al LLM extraer el valor solicitado en JSON estricto."""
        rag = self._rag
        try:
            prompt = (
                "Eres un extractor. Usa SOLO el CONTEXTO para responder la PREGUNTA.\n"
                f"{focus_block}\n\n"
                f"PREGUNTA: {question}\n\n"
                "CONTEXTO:\n" + context + "\n\n"
                "FORMATO JSON ESTRICTO (salida SOLO JSON, sin comentarios):\n"
                "{\n  \"value\": string,\n  \"unit\": string|null,\n  \"per\": string|null,\n  \"citations\": [string,...],\n  \"entity_aligned\": boolean,\n  \"attribute_aligned\": boolean,\n  \"confidence\": number\n}"
            )
            payload = {
                'model': rag.ollama_model,
                'prompt': prompt,
                'stream': False,
                'options': {
                    'num_predict': 260, 'temperature': 0.1, 'top_k': 40,
                    'top_p': 0.9, 'num_ctx': 4096,
                    'num_gpu': getattr(rag, 'num_gpu_tuned', 99),
                },
                'keep_alive': '10m',
            }
            r = requests.post("http://localhost:11434/api/generate", json=payload, timeout=60)
            if r.status_code != 200:
                return None
            raw = (r.json().get('response', '') or '').strip()
            m = re.search(r"\{[\s\S]*\}$", raw)
            js = raw if not m else m.group(0)
            data = json.loads(js)
            if isinstance(data.get('citations'), list):
                data['citations'] = [str(c) for c in data['citations'] if isinstance(c, str) and c.strip()]
            else:
                data['citations'] = []
            return data
        except Exception:
            return None

    def format_from_json(self, data: dict) -> str:
        """Crea respuesta corta a partir del JSON extraído."""
        try:
            val = str(data.get('value', '') or '').strip()
            unit = (data.get('unit') or '').strip()
            per = (data.get('per') or '').strip()
            cits = data.get('citations') or []
            core = val
            if unit:
                core = f"{core} {unit}"
            if per:
                if per.lower() in ['wtg', 'aerogenerador', 'aerogeneradores', 'turbina', 'turbinas']:
                    core = f"{core} por WTG"
                else:
                    core = f"{core} {per}"
            if cits:
                tail = "\n".join(cits[:2])
                return f"{core} {tail}"
            return core
        except Exception:
            return ''
