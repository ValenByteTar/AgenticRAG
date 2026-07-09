"""
Test aislado de razonamiento del LLM (Fase D del plan).
Evalua la capacidad de razonamiento del LLM sin retrieval (no_context),
para determinar si el modelo actual (qwen3-4b) es suficiente o necesita migracion.
"""
import sys, os, json, time, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, r'C:\Users\Valen\Desktop\Proyectos\Asunto RAG\SistemaGraniteEXP')
sys.path.insert(0, r'C:\Users\Valen\Desktop\Proyectos\Asunto RAG\SistemaGraniteEXP\src')
os.chdir(r'C:\Users\Valen\Desktop\Proyectos\Asunto RAG\SistemaGraniteEXP')

log_file = open('llm_isolated_reasoning_test.log', 'w', encoding='utf-8')
class Tee:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, data):
        for s in self.streams:
            s.write(data)
            s.flush()
    def flush(self):
        for s in self.streams:
            s.flush()
sys.stdout = Tee(sys.stdout, log_file)

import requests
import yaml

# Cargar config
with open('config.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# Usar mistral:7b (7B params, ~4.4GB VRAM) para mejor razonamiento
LLM_MODEL = "mistral:7b"
OLLAMA_URL = config.get('ollama', {}).get('url', 'http://localhost:11434')

print("=" * 80)
print("TEST AISLADO DE RAZONAMIENTO DEL LLM (SIN RAG)")
print("=" * 80)
print(f"Modelo: {LLM_MODEL}")
print(f"Fecha: {time.strftime('%Y-%m-%d %H:%M:%S')}")
print()

# Consultas de razonamiento puro (las mismas del test exhaustivo)
REASONING_TESTS = [
    {
        "id": "LLM-01",
        "question": "Si todos los firewalls stateful inspeccionan conexiones activas, y el producto X es un firewall stateful, ¿el producto X puede bloquear una conexión TCP establecida? Explica tu razonamiento.",
        "expected_elements": ["silogismo", "stateful", "conexión", "bloquear"],
        "rationale": "Razonamiento lógico puro (silogismo)"
    },
    {
        "id": "LLM-02",
        "question": "Imagina que mañana se descubre un fallo fundamental en el algoritmo RSA. ¿Qué implicaciones tendría para PKI, HTTPS, y firmas digitales? Razona paso a paso.",
        "expected_elements": ["RSA", "PKI", "HTTPS", "implicación", "criptografía"],
        "rationale": "Razonamiento hipotético con conocimiento de criptografía"
    },
    {
        "id": "LLM-03",
        "question": "Un auditor dice que 'la seguridad por oscuridad nunca funciona'. Un desarrollador responde que 'ocultar la implementación es una defensa válida'. ¿Quién tiene razón? Analiza ambos argumentos.",
        "expected_elements": ["oscuridad", "ofuscación", "defensa", "argumento"],
        "rationale": "Análisis de contradicciones con conocimiento de seguridad"
    },
    {
        "id": "LLM-04",
        "question": "El término 'seguridad' puede referirse a: seguridad física, ciberseguridad, seguridad laboral, o seguridad nacional. ¿Cómo determinarías qué tipo se discute en un texto ambiguo? Proporciona criterios.",
        "expected_elements": ["criterio", "ambigüedad", "determinar", "contexto"],
        "rationale": "Razonamiento abductivo (determinar tipo de información)"
    },
    {
        "id": "LLM-05",
        "question": "Considerando la tendencia de ataques supply chain (como SolarWinds y log4j), ¿qué tipo de controles serían más efectivos y por qué? Razona sobre trade-offs.",
        "expected_elements": ["supply chain", "control", "efectivo", "trade-off"],
        "rationale": "Análisis de tendencias con conocimiento de amenazas"
    },
    {
        "id": "LLM-06",
        "question": "Diseña una arquitectura de seguridad para una startup fintech con 50 empleados, presupuesto limitado, y requerimientos de cumplimiento PCI-DSS. ¿Qué componentes priorizarías y por qué?",
        "expected_elements": ["arquitectura", "fintech", "PCI-DSS", "prioridad", "componente"],
        "rationale": "Diseño de sistema con restricciones"
    },
    {
        "id": "LLM-07",
        "question": "¿Por qué el modelo Zero Trust está reemplazando gradualmente el modelo de perímetro tradicional? Analiza factores técnicos y de negocio.",
        "expected_elements": ["Zero Trust", "perímetro", "factor", "reemplazo"],
        "rationale": "Análisis de tendencias tecnológicas"
    },
    {
        "id": "LLM-08",
        "question": "El término 'seguridad' puede referirse a: seguridad física, ciberseguridad, seguridad laboral, o seguridad nacional. ¿Cómo determinarías qué tipo se discute en un texto ambiguo? Proporciona criterios.",
        "expected_elements": ["criterio", "ambigüedad", "determinar", "contexto"],
        "rationale": "Resolución de ambigüedad con criterios"
    }
]

def query_ollama_no_context(question: str) -> tuple:
    """Query Ollama en modo no_context (sin retrieval)."""
    prompt = f"""Responde la siguiente pregunta basándote en tu conocimiento general de ciberseguridad/IT.
No tienes acceso a documentos externos, solo tu conocimiento entrenado.

Pregunta: {question}

Responde de forma clara, estructurada y completa."""

    start = time.time()
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": LLM_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 2048
                }
            },
            timeout=120
        )
        elapsed = time.time() - start
        if resp.status_code == 200:
            return resp.json().get("response", ""), elapsed
        else:
            return f"[ERROR] Ollama status {resp.status_code}", elapsed
    except Exception as e:
        return f"[ERROR] {str(e)}", time.time() - start

def evaluate_response(response: str, expected_elements: list) -> dict:
    """Evalua la respuesta buscando elementos esperados (coincidencia flexible)."""
    resp_lower = response.lower()
    found = []
    missing = []
    
    for elem in expected_elements:
        # Buscar elemento o sinonimos/variantes
        elem_lower = elem.lower()
        if elem_lower in resp_lower:
            found.append(elem)
        else:
            # Buscar variantes (ej: "ofuscacion" vs "ofuscación")
            elem_variants = [elem_lower, elem_lower.replace('ó', 'o'), elem_lower.replace('í', 'i')]
            if any(v in resp_lower for v in elem_variants):
                found.append(elem)
            else:
                missing.append(elem)
    
    coverage = len(found) / len(expected_elements) if expected_elements else 0
    
    # Calcular score: 1.0 si todos los elementos, 0.5 si >= 50%, 0.25 si < 50%
    if coverage == 1.0:
        score = 1.0
    elif coverage >= 0.5:
        score = 0.5
    else:
        score = 0.25
    
    return {
        "elements_found": found,
        "elements_missing": missing,
        "coverage": coverage,
        "score": score
    }

# Ejecutar tests
results = []
total_score = 0

for test in REASONING_TESTS:
    print(f"\n{'='*80}")
    print(f"PRUEBA {test['id']} | {test['rationale']}")
    print(f"{'='*80}")
    print(f"Pregunta: {test['question'][:100]}...")
    print(f"Elementos esperados: {test['expected_elements']}")
    
    response, elapsed = query_ollama_no_context(test['question'])
    
    eval_result = evaluate_response(response, test['expected_elements'])
    total_score += eval_result['score']
    
    print(f"Tiempo: {elapsed:.2f}s | Longitud: {len(response)} chars")
    print(f"Cobertura elementos: {eval_result['coverage']*100:.0f}%")
    print(f"Encontrados: {eval_result['elements_found']}")
    print(f"Faltantes: {eval_result['elements_missing']}")
    print(f"Score: {eval_result['score']:.2f}")
    print(f"Respuesta (primeros 300 chars): {response[:300]}...")
    
    results.append({
        **test,
        "response": response,
        "time_seconds": elapsed,
        "evaluation": eval_result
    })

# Resumen
print(f"\n{'='*80}")
print("RESUMEN EJECUTIVO - RAZONAMIENTO AISLADO DEL LLM")
print(f"{'='*80}")
avg_score = total_score / len(REASONING_TESTS)
success_rate = sum(1 for r in results if r['evaluation']['score'] >= 0.5) / len(REASONING_TESTS) * 100

print(f"\nModelo evaluado: {LLM_MODEL}")
print(f"Total pruebas: {len(REASONING_TESTS)}")
print(f"Score promedio: {avg_score:.2f}")
print(f"Tasa éxito (score >= 0.5): {success_rate:.1f}%")

print(f"\nDistribución de scores:")
for r in results:
    status = "✓" if r['evaluation']['score'] >= 0.5 else "✗"
    print(f"  {status} {r['id']}: {r['evaluation']['score']:.2f} ({r['rationale'][:40]}...)")

# Recomendación
print(f"\n{'='*80}")
print("RECOMENDACIÓN")
print(f"{'='*80}")
if avg_score >= 0.7:
    rec = "El modelo actual (qwen3-4b) demuestra buena capacidad de razonamiento. NO es necesaria migración inmediata."
elif avg_score >= 0.5:
    rec = "El modelo tiene capacidad de razonamiento ACEPTABLE pero mejorable. Considerar migración a 8b/14b para mejores resultados en razonamiento complejo."
else:
    rec = "El modelo tiene dificultades significativas con razonamiento. RECOMENDADA migración a modelo mayor (8b/14b) o fine-tuning específico."

print(rec)

# Guardar resultados
output = {
    "model": LLM_MODEL,
    "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
    "test_count": len(REASONING_TESTS),
    "average_score": avg_score,
    "success_rate": success_rate,
    "recommendation": rec,
    "tests": results
}

with open('llm_isolated_reasoning_results.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"\nResultados guardados en: llm_isolated_reasoning_results.json")
print("Log completo en: llm_isolated_reasoning_test.log")

log_file.close()
