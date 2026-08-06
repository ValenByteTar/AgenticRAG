#!/usr/bin/env python3
"""
PRUEBAS EXHAUSTIVAS DE RAZONAMIENTO Y COMPLEJIDAD
Evalúa capacidad de razonamiento del sistema RAG
Guarda resultados detallados en .log para análisis posterior
"""

import json
import time
import sys
import os
import re
from pathlib import Path
from datetime import datetime
from contextlib import redirect_stdout, redirect_stderr
import io

# Configurar UTF-8 para Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Cambiar al directorio del script
script_dir = Path(__file__).parent
os.chdir(script_dir)
sys.path.insert(0, str(script_dir / 'src'))

from rag_hybrid import HybridRAG
from utils import get_console

console = get_console()

# ============================================================================
# CONJUNTOS DE PRUEBA POR CATEGORÍA
# ============================================================================

# 1. Razonamiento basado en documentos (requiere síntesis de múltiples fuentes)
DOCUMENT_REASONING_TESTS = [
    {
        "id": "DR-01",
        "category": "Síntesis Multi-Documento",
        "question": "Compara CISSP con CEH: ¿Cuáles son las diferencias principales en enfoque, requisitos y aplicación práctica?",
        "expected_elements": ["CISSP", "CEH", "gestión", "técnico", "experiencia", "certificación"],
        "complexity": "Alta"
    },
    {
        "id": "DR-02",
        "category": "Inferencia Causal",
        "question": "Según los frameworks de seguridad, ¿por qué NIST CSF e ISO 27001 se consideran complementarios y no competidores?",
        "expected_elements": ["NIST", "ISO", "complementario", "marco", "gestión"],
        "complexity": "Alta"
    },
    {
        "id": "DR-03",
        "category": "Análisis de Procedimientos",
        "question": "Explica el flujo completo de respuesta a incidentes según los documentos: desde detección hasta recuperación y lecciones aprendidas.",
        "expected_elements": ["detección", "respuesta", "recuperación", "incidente", "proceso"],
        "complexity": "Muy Alta"
    },
    {
        "id": "DR-04",
        "category": "Evaluación Crítica",
        "question": "¿Qué limitaciones tienen los frameworks tradicionales de ciberseguridad frente a amenazas APT modernas según MITRE ATT&CK?",
        "expected_elements": ["framework", "limitación", "APT", "MITRE", "amenaza"],
        "complexity": "Alta"
    },
    {
        "id": "DR-05",
        "category": "Síntesis Comparativa",
        "question": "Diferencia entre penetration testing según OWASP y red teaming según los documentos: metodología, alcance y objetivos.",
        "expected_elements": ["penetration", "OWASP", "red team", "metodología", "diferencia"],
        "complexity": "Muy Alta"
    },
    {
        "id": "DR-06",
        "category": "Razonamiento Secuencial",
        "question": "Describe paso a paso cómo un SOC detectaría, analizaría y respondería a un ransomware según los procedimientos documentados.",
        "expected_elements": ["SOC", "ransomware", "detección", "análisis", "respuesta", "paso"],
        "complexity": "Muy Alta"
    },
    {
        "id": "DR-07",
        "category": "Análisis de Trade-offs",
        "question": "¿Cuáles son los trade-offs entre seguridad y usabilidad según los frameworks de control de acceso mencionados?",
        "expected_elements": ["trade-off", "seguridad", "usabilidad", "control", "acceso"],
        "complexity": "Alta"
    },
    {
        "id": "DR-08",
        "category": "Validación Lógica",
        "question": "Si una empresa implementa ISO 27001 pero no hace penetration testing regular, ¿qué vulnerabilidades deja expuestas según los documentos?",
        "expected_elements": ["ISO 27001", "penetration testing", "vulnerabilidad", "exposición"],
        "complexity": "Alta"
    }
]

# 2. Razonamiento con conocimiento propio del LLM (fuera del dominio documentado)
LLM_REASONING_TESTS = [
    {
        "id": "LLM-01",
        "category": "Razonamiento Lógico Puro",
        "question": "Si todos los firewalls stateful inspeccionan conexiones activas, y el producto X es un firewall stateful, ¿el producto X puede bloquear una conexión TCP establecida? Explica tu razonamiento.",
        "expected_elements": ["silogismo", "stateful", "conexión", "bloquear"],
        "complexity": "Media",
        "domain": "lógica"
    },
    {
        "id": "LLM-02",
        "category": "Razonamiento Hipotético",
        "question": "Imagina que mañana se descubre un fallo fundamental en el algoritmo RSA. ¿Qué implicaciones tendría para PKI, HTTPS, y firmas digitales? Razona paso a paso.",
        "expected_elements": ["RSA", "PKI", "HTTPS", "implicación", "criptografía"],
        "complexity": "Muy Alta",
        "domain": "criptografía"
    },
    {
        "id": "LLM-03",
        "category": "Análisis de Contradicciones",
        "question": "Un auditor dice que 'la seguridad por oscuridad nunca funciona'. Un desarrollador responde que 'ocultar la implementación es una defensa válida'. ¿Quién tiene razón? Analiza ambos argumentos.",
        "expected_elements": ["oscuridad", "ofuscación", "defensa", "argumento"],
        "complexity": "Alta",
        "domain": "filosofía seguridad"
    },
    {
        "id": "LLM-04",
        "category": "Razonamiento Abductivo",
        "question": "Un servidor muestra tráfico saliente hacia una IP desconocida en el puerto 4444 durante las noches. Lista 3 hipótesis posibles, explica cuál es más probable y por qué.",
        "expected_elements": ["hipótesis", "tráfico", "puerto 4444", "probable"],
        "complexity": "Alta",
        "domain": "forense"
    },
    {
        "id": "LLM-05",
        "category": "Razonamiento Ético",
        "question": "¿Es ético que un pentester use una vulnerabilidad zero-day encontrada en un cliente para demostrar impacto, sin reportarla primero al vendor? Argumenta pros y contras.",
        "expected_elements": ["ético", "zero-day", "responsable", "divulgación"],
        "complexity": "Alta",
        "domain": "ética"
    },
    {
        "id": "LLM-06",
        "category": "Diseño de Sistema",
        "question": "Diseña una arquitectura de seguridad para una startup fintech con 50 empleados, presupuesto limitado, y requerimientos de cumplimiento PCI-DSS. ¿Qué componentes priorizarías y por qué?",
        "expected_elements": ["arquitectura", "fintech", "PCI-DSS", "prioridad", "componente"],
        "complexity": "Muy Alta",
        "domain": "arquitectura"
    },
    {
        "id": "LLM-07",
        "category": "Análisis de Tendencias",
        "question": "¿Por qué el modelo Zero Trust está reemplazando gradualmente el modelo de perímetro tradicional? Analiza factores técnicos y de negocio.",
        "expected_elements": ["Zero Trust", "perímetro", "reemplazo", "factor"],
        "complexity": "Alta",
        "domain": "arquitectura"
    },
    {
        "id": "LLM-08",
        "category": "Resolución de Ambigüedad",
        "question": "El término 'seguridad' puede referirse a: seguridad física, ciberseguridad, seguridad laboral, o seguridad nacional. ¿Cómo determinarías qué tipo se discute en un texto ambiguo? Proporciona criterios.",
        "expected_elements": ["ambigüedad", "criterio", "contexto", "determinar"],
        "complexity": "Media",
        "domain": "semántica"
    }
]

# 3. Preguntas complejas que cruzan documentos + conocimiento LLM
HYBRID_TESTS = [
    {
        "id": "HYB-01",
        "category": "Aplicación Práctica",
        "question": "Los documentos mencionan ISO 27001. Aplicando ese conocimiento: si una empresa tiene 3 sedes, 200 empleados remotos, y usa AWS + Azure, ¿qué controles de ISO 27001 serían más críticos implementar primero?",
        "expected_elements": ["ISO 27001", "aplicación", "control", "crítico", "prioridad"],
        "complexity": "Muy Alta"
    },
    {
        "id": "HYB-02",
        "category": "Validación Cruzada",
        "question": "Los documentos describen MITRE ATT&CK. ¿Coincide esa descripción con lo que sabes sobre tácticas reales de APT29 (Cozy Bear)? Identifica similitudes y diferencias.",
        "expected_elements": ["MITRE", "APT29", "táctica", "similitud", "diferencia"],
        "complexity": "Muy Alta"
    },
    {
        "id": "HYB-03",
        "category": "Extensión de Concepto",
        "question": "Los documentos definen qué es un SOC. Basado en eso y en conocimiento del dominio: ¿cómo evolucionará el rol del SOC en los próximos 5 años con la adopción de IA/ML?",
        "expected_elements": ["SOC", "evolución", "IA", "ML", "futuro", "rol"],
        "complexity": "Muy Alta"
    },
    {
        "id": "HYB-04",
        "category": "Evaluación de Gaps",
        "question": "Los documentos cubren pentesting. Considerando el estado actual de la ciberseguridad: ¿qué aspectos del pentesting tradicional ya no son suficientes contra amenazas modernas?",
        "expected_elements": ["pentesting", "insuficiente", "amenaza moderna", "gap"],
        "complexity": "Alta"
    }
]

class ExhaustiveTester:
    def __init__(self, rag_system):
        self.rag = rag_system
        self.log_file = Path(f"reasoning_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        self.results = []
        self.log_buffer = []
        
    def log(self, message: str, level: str = "INFO"):
        """Escribe al log interno y a consola"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_line = f"[{timestamp}] [{level}] {message}"
        self.log_buffer.append(log_line)
        console.print(f"[dim]{message}[/dim]" if level == "DEBUG" else message)
    
    def save_log(self):
        """Guarda el log completo a archivo"""
        with open(self.log_file, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write("PRUEBAS EXHAUSTIVAS DE RAZONAMIENTO - RAG PIPELINE\n")
            f.write(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Modelo: ibm/granite4.1:3b-q6_K\n")
            f.write(f"Documentos Indexados: 100,480\n")
            f.write("="*80 + "\n\n")
            
            # Resumen ejecutivo
            f.write("RESUMEN EJECUTIVO\n")
            f.write("-"*40 + "\n")
            total = len(self.results)
            success = len([r for r in self.results if r['quality_score'] >= 0.6])
            f.write(f"Total pruebas: {total}\n")
            f.write(f"Exitosas (score >= 0.6): {success}/{total}\n")
            f.write(f"Tasa éxito: {success/total*100:.1f}%\n\n")
            
            # Logs detallados
            f.write("\n".join(self.log_buffer))
            
            # Resultados estructurados
            f.write("\n\n" + "="*80 + "\n")
            f.write("RESULTADOS ESTRUCTURADOS (JSON)\n")
            f.write("="*80 + "\n")
            f.write(json.dumps(self.results, indent=2, ensure_ascii=False))
        
        return self.log_file
    
    def evaluate_response(self, response: str, expected_elements: list, test_type: str) -> dict:
        """Evalúa la calidad de la respuesta"""
        if not response:
            return {"score": 0, "issues": ["Respuesta vacía"], "elements_found": []}
        
        response_lower = response.lower()
        issues = []
        
        # 1. Verificar elementos esperados
        elements_found = []
        for elem in expected_elements:
            if elem.lower() in response_lower:
                elements_found.append(elem)
        
        element_coverage = len(elements_found) / len(expected_elements) if expected_elements else 0
        
        # 2. Detectar problemas
        # Contradicciones
        has_contradiction = (
            ("no se encontró" in response_lower and len(response) > 200) or
            "¿por qué?" in response_lower[-100:] or
            "fue incorrecta" in response_lower
        )
        if has_contradiction:
            issues.append("Posible contradiccción detectada")
        
        # Truncamiento
        has_truncation = (
            response.rstrip().endswith('**') or
            response.rstrip().endswith('##') or
            (len(response) > 50 and not any(c in response[-20:] for c in '.!?]'))
        )
        if has_truncation:
            issues.append("Respuesta posiblemente truncada")
        
        # Repetición de frases negativas
        negative_count = response_lower.count('no se encontró información')
        if negative_count > 1:
            issues.append(f"Frase negativa repetida {negative_count} veces")
        
        # Respuesta genérica
        generic_phrases = ['según los documentos', 'la información proporcionada']
        if all(p in response_lower for p in generic_phrases[:2]) and len(response) < 150:
            issues.append("Respuesta posiblemente genérica/evasiva")
        
        # 3. Calcular score
        base_score = element_coverage * 0.6  # 60% por elementos
        
        # Bonus por longitud apropiada
        if 300 < len(response) < 1500:
            base_score += 0.2
        
        # Penalizaciones
        if has_contradiction:
            base_score -= 0.3
        if has_truncation:
            base_score -= 0.2
        if negative_count > 1:
            base_score -= 0.15 * (negative_count - 1)
        
        # Asegurar rango 0-1
        final_score = max(0, min(1, base_score))
        
        return {
            "score": round(final_score, 2),
            "element_coverage": round(element_coverage, 2),
            "elements_found": elements_found,
            "elements_missing": [e for e in expected_elements if e not in elements_found],
            "issues": issues,
            "response_length": len(response),
            "has_contradiction": has_contradiction,
            "has_truncation": has_truncation
        }
    
    def run_test(self, test: dict, test_type: str) -> dict:
        """Ejecuta una prueba individual"""
        self.log(f"\n{'='*70}", "INFO")
        self.log(f"PRUEBA {test['id']} | {test_type} | Complejidad: {test['complexity']}", "INFO")
        self.log(f"Categoría: {test['category']}", "INFO")
        self.log(f"Pregunta: {test['question']}", "INFO")
        self.log(f"Elementos esperados: {', '.join(test['expected_elements'])}", "DEBUG")
        
        # FASE E: Tracking de entidades extraídas
        try:
            from src.rag.entity_extractor import EntityExtractor
            extractor = EntityExtractor()
            extracted_entities = extractor.extract_entities(test['question'])
            self.log(f"Entidades detectadas: {extracted_entities}", "DEBUG")
            # Detectar entidades basura (indicativo de problemas en el extractor)
            garbage_patterns = ['completo del', 'respuesta del', 'flujo del', 'paso del']
            garbage_entities = [e for e in extracted_entities if any(g in e for g in garbage_patterns)]
            if garbage_entities:
                self.log(f"[ALERTA] Entidades basura detectadas: {garbage_entities}", "WARN")
        except Exception as e:
            extracted_entities = []
            self.log(f"No se pudo extraer entidades: {e}", "DEBUG")
        
        start_time = time.time()
        
        try:
            # Ejecutar consulta
            result = self.rag.query(
                question=test['question'],
                top_k=20,
                length_mode='long',  # Usar modo largo para razonamiento complejo
                use_llm=True
            )
            
            elapsed = time.time() - start_time
            
            # Extraer respuesta
            if isinstance(result, dict):
                answer = result.get('answer', '')
                docs_retrieved = len(result.get('sources', []))
            else:
                answer = str(result)
                docs_retrieved = 0
            
            self.log(f"Tiempo: {elapsed:.2f}s | Documentos: {docs_retrieved} | Respuesta: {len(answer)} chars", "INFO")
            self.log(f"Respuesta (primeros 500 chars):\n{answer[:500]}...", "DEBUG")
            
            # Evaluar calidad
            eval_result = self.evaluate_response(answer, test['expected_elements'], test_type)
            
            self.log(f"Score de calidad: {eval_result['score']:.2f}", "INFO")
            self.log(f"Cobertura de elementos: {eval_result['element_coverage']*100:.0f}%", "INFO")
            
            if eval_result['elements_found']:
                self.log(f"Elementos encontrados: {', '.join(eval_result['elements_found'])}", "INFO")
            if eval_result['elements_missing']:
                self.log(f"Elementos FALTANTES: {', '.join(eval_result['elements_missing'])}", "WARN")
            if eval_result['issues']:
                self.log(f"PROBLEMAS DETECTADOS: {'; '.join(eval_result['issues'])}", "WARN")
            
            return {
                "test_id": test['id'],
                "test_type": test_type,
                "category": test['category'],
                "complexity": test['complexity'],
                "question": test['question'],
                "extracted_entities": extracted_entities,
                "response": answer,
                "response_length": len(answer),
                "time_seconds": round(elapsed, 2),
                "docs_retrieved": docs_retrieved,
                "quality_score": eval_result['score'],
                "element_coverage": eval_result['element_coverage'],
                "elements_found": eval_result['elements_found'],
                "elements_missing": eval_result['elements_missing'],
                "issues": eval_result['issues'],
                "has_contradiction": eval_result['has_contradiction'],
                "has_truncation": eval_result['has_truncation'],
                "success": eval_result['score'] >= 0.6
            }
            
        except Exception as e:
            self.log(f"ERROR: {str(e)}", "ERROR")
            import traceback
            self.log(traceback.format_exc(), "ERROR")
            return {
                "test_id": test['id'],
                "test_type": test_type,
                "category": test['category'],
                "complexity": test['complexity'],
                "question": test['question'],
                "extracted_entities": extracted_entities if 'extracted_entities' in locals() else [],
                "error": str(e),
                "quality_score": 0,
                "success": False
            }
    
    def run_all_tests(self):
        """Ejecuta todas las pruebas"""
        self.log("\n" + "="*80, "INFO")
        self.log("INICIANDO PRUEBAS EXHAUSTIVAS DE RAZONAMIENTO", "INFO")
        self.log("="*80, "INFO")
        self.log(f"Total pruebas documento: {len(DOCUMENT_REASONING_TESTS)}", "INFO")
        self.log(f"Total pruebas LLM: {len(LLM_REASONING_TESTS)}", "INFO")
        self.log(f"Total pruebas híbridas: {len(HYBRID_TESTS)}", "INFO")
        self.log(f"Total: {sum([len(DOCUMENT_REASONING_TESTS), len(LLM_REASONING_TESTS), len(HYBRID_TESTS)])}", "INFO")
        
        # Pruebas de documentos
        self.log("\n" + "-"*40, "INFO")
        self.log("FASE 1: RAZONAMIENTO BASADO EN DOCUMENTOS", "INFO")
        self.log("-"*40, "INFO")
        for test in DOCUMENT_REASONING_TESTS:
            result = self.run_test(test, "DOCUMENT")
            self.results.append(result)
        
        # Pruebas de conocimiento LLM
        self.log("\n" + "-"*40, "INFO")
        self.log("FASE 2: RAZONAMIENTO CON CONOCIMIENTO LLM", "INFO")
        self.log("-"*40, "INFO")
        for test in LLM_REASONING_TESTS:
            result = self.run_test(test, "LLM_KNOWLEDGE")
            self.results.append(result)
        
        # Pruebas híbridas
        self.log("\n" + "-"*40, "INFO")
        self.log("FASE 3: RAZONAMIENTO HÍBRIDO", "INFO")
        self.log("-"*40, "INFO")
        for test in HYBRID_TESTS:
            result = self.run_test(test, "HYBRID")
            self.results.append(result)
        
        # Generar resumen
        self.generate_summary()
        
        # Guardar log
        log_path = self.save_log()
        self.log(f"\n{'='*80}", "INFO")
        self.log(f"PRUEBAS COMPLETADAS. Log guardado en: {log_path}", "INFO")
        self.log("="*80, "INFO")
        
        return self.results
    
    def generate_summary(self):
        """Genera resumen de resultados"""
        total = len(self.results)
        by_type = {}
        by_complexity = {}
        
        for r in self.results:
            # Por tipo
            t = r['test_type']
            if t not in by_type:
                by_type[t] = {'count': 0, 'success': 0, 'avg_score': 0}
            by_type[t]['count'] += 1
            by_type[t]['success'] += 1 if r['success'] else 0
            by_type[t]['avg_score'] += r['quality_score']
            
            # Por complejidad
            c = r['complexity']
            if c not in by_complexity:
                by_complexity[c] = {'count': 0, 'success': 0, 'avg_score': 0}
            by_complexity[c]['count'] += 1
            by_complexity[c]['success'] += 1 if r['success'] else 0
            by_complexity[c]['avg_score'] += r['quality_score']
        
        # Promediar scores
        for t in by_type:
            by_type[t]['avg_score'] = round(by_type[t]['avg_score'] / by_type[t]['count'], 2)
        for c in by_complexity:
            by_complexity[c]['avg_score'] = round(by_complexity[c]['avg_score'] / by_complexity[c]['count'], 2)
        
        self.log("\n" + "="*80, "INFO")
        self.log("RESUMEN EJECUTIVO - MÉTRICAS SEPARADAS", "INFO")
        self.log("="*80, "INFO")
        
        # Calcular métricas separadas
        doc_results = [r for r in self.results if r['test_type'] == 'DOCUMENT']
        llm_results = [r for r in self.results if r['test_type'] == 'LLM_KNOWLEDGE']
        hybrid_results = [r for r in self.results if r['test_type'] == 'HYBRID']
        
        # Métricas DOCUMENT (RAG puro)
        if doc_results:
            doc_success = sum(1 for r in doc_results if r['success'])
            doc_avg = sum(r['quality_score'] for r in doc_results) / len(doc_results)
            self.log(f"\n[DOCUMENT - RAG Puro]", "INFO")
            self.log(f"  Exitosas: {doc_success}/{len(doc_results)} ({doc_success/len(doc_results)*100:.1f}%)", "INFO")
            self.log(f"  Score promedio: {doc_avg:.2f}", "INFO")
        
        # Métricas LLM_KNOWLEDGE (Razonamiento puro)
        if llm_results:
            llm_success = sum(1 for r in llm_results if r['success'])
            llm_avg = sum(r['quality_score'] for r in llm_results) / len(llm_results)
            self.log(f"\n[LLM_KNOWLEDGE - Razonamiento puro]", "INFO")
            self.log(f"  Exitosas: {llm_success}/{len(llm_results)} ({llm_success/len(llm_results)*100:.1f}%)", "INFO")
            self.log(f"  Score promedio: {llm_avg:.2f}", "INFO")
        
        # Métricas HYBRID (Documento + Conocimiento)
        if hybrid_results:
            hybrid_success = sum(1 for r in hybrid_results if r['success'])
            hybrid_avg = sum(r['quality_score'] for r in hybrid_results) / len(hybrid_results)
            self.log(f"\n[HYBRID - Documento + Conocimiento]", "INFO")
            self.log(f"  Exitosas: {hybrid_success}/{len(hybrid_results)} ({hybrid_success/len(hybrid_results)*100:.1f}%)", "INFO")
            self.log(f"  Score promedio: {hybrid_avg:.2f}", "INFO")
        
        # Totales globales
        self.log("\n" + "-"*40, "INFO")
        total_success = sum(1 for r in self.results if r['success'])
        avg_score = sum(r['quality_score'] for r in self.results) / total
        self.log(f"GLOBAL: {total_success}/{total} exitosas ({total_success/total*100:.1f}%), score avg: {avg_score:.2f}", "INFO")
        
        self.log("\n" + "="*80, "INFO")
        self.log("DETALLE POR TIPO DE PRUEBA", "INFO")
        self.log("="*80, "INFO")
        
        # Por tipo (detalle)
        for t, data in by_type.items():
            self.log(f"\n{t}: {data['success']}/{data['count']} exitosas, score avg: {data['avg_score']}", "INFO")
        
        # Por complejidad
        self.log("\nPor nivel de complejidad:", "INFO")
        for c in ['Media', 'Alta', 'Muy Alta']:
            if c in by_complexity:
                data = by_complexity[c]
                self.log(f"  {c}: {data['success']}/{data['count']} exitosas, score avg: {data['avg_score']}", "INFO")
        
        # Problemas comunes
        all_issues = []
        for r in self.results:
            all_issues.extend(r.get('issues', []))
        
        if all_issues:
            from collections import Counter
            issue_counts = Counter(all_issues)
            self.log("\nProblemas más frecuentes:", "WARN")
            for issue, count in issue_counts.most_common(5):
                self.log(f"  - {issue}: {count} ocurrencias", "WARN")
        
        # Métricas del Entity Extractor
        self.log("\n" + "="*80, "INFO")
        self.log("MÉTRICAS DEL ENTITY EXTRACTOR", "INFO")
        self.log("="*80, "INFO")
        total_entities = sum(len(r.get('extracted_entities', [])) for r in self.results)
        avg_entities = total_entities / total if total > 0 else 0
        garbage_patterns = ['completo del', 'respuesta del', 'flujo del', 'paso del']
        garbage_count = sum(
            1 for r in self.results 
            for e in r.get('extracted_entities', []) 
            if any(g in e for g in garbage_patterns)
        )
        empty_extractions = sum(1 for r in self.results if not r.get('extracted_entities'))
        
        self.log(f"Total entidades extraídas: {total_entities}", "INFO")
        self.log(f"Promedio por consulta: {avg_entities:.1f}", "INFO")
        self.log(f"Entidades basura detectadas: {garbage_count}", "WARN" if garbage_count > 0 else "INFO")
        self.log(f"Extracciones vacías: {empty_extractions}/{total}", "INFO")
        if garbage_count == 0:
            self.log("✓ Entity extractor limpio (sin entidades basura)", "INFO")
        
        self.log("="*80, "INFO")


def main():
    console.print("[bold cyan]PRUEBAS EXHAUSTIVAS DE RAZONAMIENTO[/bold cyan]")
    console.print("=" * 60)
    
    # Inicializar RAG
    console.print("\n[dim]Inicializando sistema RAG...[/dim]")
    try:
        config_path = str(Path(__file__).parent / "config.yaml")
        rag = HybridRAG(config_path=config_path, use_llm=True)
        console.print("[green]OK: Sistema RAG inicializado[/green]\n")
    except Exception as e:
        console.print(f"[red]ERROR: {e}[/red]")
        sys.exit(1)
    
    # Ejecutar pruebas
    tester = ExhaustiveTester(rag)
    results = tester.run_all_tests()
    
    console.print(f"\n[bold green]Pruebas completadas. Resultados guardados en: {tester.log_file}[/bold green]")
    return results


if __name__ == "__main__":
    main()
