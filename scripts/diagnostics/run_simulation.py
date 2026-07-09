"""
Script simplificado para ejecutar simulación desde el entorno del servidor
"""

import json
import time
from datetime import datetime
import urllib.request
import urllib.parse
import urllib.error
import sys
import argparse

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# URL del servidor (debe estar corriendo)
BASE_URL = "http://localhost:5000"

# 50 casos de prueba
TEST_CASES = [
    {"id": 1, "query": "Que tecnologia maneja la perla del chaco?", "expected": ["fotovoltaica", "huawei"], "avoid": ["no hay información", "lo siento"], "category": "entity_variant"},
    {"id": 2, "query": "Dame informacion sobre la perla de chaco", "expected": ["fotovoltaica", "25"], "avoid": ["no hay información"], "category": "entity_variant"},
    {"id": 3, "query": "Hablame sobre el parque la perla del chaco", "expected": ["fotovoltaica"], "avoid": ["no hay información"], "category": "entity_variant"},
    {"id": 4, "query": "Y no hay un Anexo D - DQD que hable de este parque?", "expected": ["anexo d"], "avoid": ["no aparece"], "category": "document_reference"},
    {"id": 5, "query": "Dame toda la informacion disponible sobre parque eolico Malaspina", "expected": ["malaspina", "eolico", "senvion"], "avoid": [], "category": "detailed_query"},
    {"id": 6, "query": "Que tipo de aerogeneradores tiene este parque?", "expected": ["senvion", "3.6m114"], "avoid": [], "category": "follow_up"},
    {"id": 7, "query": "Compara estos aerogeneradores con los que tiene parque eolico Kosten", "expected": ["malaspina", "kosten"], "avoid": ["no se menciona kosten"], "category": "comparison"},
    {"id": 8, "query": "Dame toda la información disponible sobre Vientos del Secano", "expected": ["vientos del secano"], "avoid": ["envision"], "category": "exact_entity_match"},
    {"id": 9, "query": "Potencia de Vientos del Secano", "expected": ["mw", "vientos del secano"], "avoid": [], "category": "numeric_query"},
    {"id": 10, "query": "Dame toda la informacion disponible sobre el PT8", "expected": ["pt8", "reglamento operativo"], "avoid": [], "category": "document_query"},
    {"id": 11, "query": "Y que significa COC?", "expected": ["centro", "control", "operacion"], "avoid": [], "category": "follow_up"},
    {"id": 12, "query": "COC tiene que ver con CAMMESA?", "expected": ["cammesa", "coc"], "avoid": [], "category": "follow_up"},
    {"id": 13, "query": "Lista todas las centrales operadas por el CROM", "expected": ["central", "parque"], "avoid": [], "category": "listing"},
    {"id": 14, "query": "Cuantas centrales opera el CROM?", "expected": ["total", "central"], "avoid": [], "category": "count"},
    {"id": 15, "query": "Que parques eolicos opera el CROM?", "expected": ["eolico", "parque"], "avoid": [], "category": "tech_filter"},
    {"id": 16, "query": "Que parques solares opera el CROM?", "expected": ["solar", "fotovoltaica"], "avoid": [], "category": "tech_filter"},
    {"id": 17, "query": "Donde esta ubicado el parque Kosten?", "expected": ["kosten", "pampa del castillo"], "avoid": [], "category": "location"},
    {"id": 18, "query": "Coordenadas de Malaspina", "expected": ["latitud", "longitud"], "avoid": [], "category": "location"},
    {"id": 19, "query": "Cuantos aerogeneradores tiene Kosten?", "expected": ["7", "siete", "kosten"], "avoid": [], "category": "numeric_query"},
    {"id": 20, "query": "Potencia instalada de Malaspina", "expected": ["50", "mw", "malaspina"], "avoid": [], "category": "numeric_query"},
    {"id": 21, "query": "Como se gestiona una orden de servicio en el SADI?", "expected": ["pt8", "orden", "servicio"], "avoid": [], "category": "procedural"},
    {"id": 22, "query": "Que es el PT4?", "expected": ["pt4", "ingreso"], "avoid": [], "category": "document_query"},
    {"id": 23, "query": "Que centrales opera TotalEnergies?", "expected": ["totalenergies", "malaspina"], "avoid": [], "category": "vendor_filter"},
    {"id": 24, "query": "Que centrales opera GRENERGY?", "expected": ["grenergy", "kosten"], "avoid": [], "category": "vendor_filter"},
    {"id": 25, "query": "Que protecciones tiene el parque Kosten?", "expected": ["proteccion", "kosten"], "avoid": [], "category": "protection"},
    {"id": 26, "query": "Como se monitorea el parque Kosten en SCADA?", "expected": ["scada", "kosten"], "avoid": [], "category": "scada"},
    {"id": 27, "query": "Que subestacion conecta a Kosten?", "expected": ["pampa del castillo", "kosten"], "avoid": [], "category": "substation"},
    {"id": 28, "query": "Cuantas celdas tiene la ET Pampa del Castillo?", "expected": ["celda", "pampa"], "avoid": [], "category": "cells"},
    {"id": 29, "query": "Cual es la potencia total de las centrales del CROM?", "expected": ["total", "mw"], "avoid": [], "category": "aggregation"},
    {"id": 30, "query": "Que es PT8?", "expected": ["pt8", "reglamento"], "avoid": [], "category": "acronym"},
    {"id": 31, "query": "Informacion sobre PT4", "expected": ["pt4", "ingreso"], "avoid": [], "category": "acronym"},
    {"id": 32, "query": "Cuantos parques Loma Blanca hay?", "expected": ["loma blanca"], "avoid": [], "category": "multi_entity"},
    {"id": 33, "query": "Potencia de Loma Blanca I", "expected": ["loma blanca", "mw"], "avoid": [], "category": "entity_variant"},
    {"id": 34, "query": "Cuando fue habilitada La Perla del Chaco?", "expected": ["2025", "perla"], "avoid": [], "category": "date_query"},
    {"id": 35, "query": "Que modelo de aerogeneradores tiene Malaspina?", "expected": ["senvion", "3.6m114"], "avoid": [], "category": "equipment_model"},
    {"id": 36, "query": "Que inversores usa La Perla del Chaco?", "expected": ["huawei"], "avoid": [], "category": "equipment_model"},
    {"id": 37, "query": "Que es una orden de servicio?", "expected": ["orden", "servicio"], "avoid": [], "category": "conceptual"},
    {"id": 38, "query": "Que es el SADI?", "expected": ["sistema", "argentino", "interconexion"], "avoid": [], "category": "conceptual"},
    {"id": 39, "query": "Que hacer si hay una falla en un aerogenerador?", "expected": ["proteccion", "scada"], "avoid": [], "category": "troubleshooting"},
    {"id": 40, "query": "Que documentos hablan sobre Kosten?", "expected": ["anexo d", "kosten"], "avoid": [], "category": "multi_document"},
    {"id": 41, "query": "Como se hace un asado?", "expected": ["consulta fuera", "alcance"], "avoid": [], "category": "out_of_domain"},
    {"id": 42, "query": "Quien gano el mundial 2022?", "expected": ["consulta fuera", "alcance"], "avoid": [], "category": "out_of_domain"},
    {"id": 43, "query": "Compara Kosten y Malaspina", "expected": ["kosten", "malaspina"], "avoid": ["no se menciona"], "category": "comparison"},
    {"id": 44, "query": "Dame toda la informacion disponible sobre el parque eolico Kosten incluyendo ubicacion potencia aerogeneradores protecciones y conexion a la red", "expected": ["kosten", "mw", "aerogenerador"], "avoid": [], "category": "detailed_query"},
    {"id": 45, "query": "Kosten", "expected": ["kosten"], "avoid": [], "category": "short_query"},
    {"id": 46, "query": "PT8", "expected": ["pt8"], "avoid": [], "category": "short_query"},
    {"id": 47, "query": "Informacion sobre P.S. La Perla de Chaco", "expected": ["perla", "fotovoltaica"], "avoid": [], "category": "entity_with_prefix"},
    {"id": 48, "query": "Datos de P.E. Kosten", "expected": ["kosten", "eolico"], "avoid": [], "category": "entity_with_prefix"},
    {"id": 49, "query": "Cuantos WTG tiene Kosten?", "expected": ["7", "kosten"], "avoid": [], "category": "numeric_query"},
    {"id": 50, "query": "Velocidad del viento en Malaspina", "expected": ["malaspina", "viento"], "avoid": [], "category": "numeric_query"}
]

def validate_response(test_case, answer):
    """Valida la respuesta"""
    answer_lower = answer.lower()
    
    passed = True
    reasons = []
    score = 0
    max_score = len(test_case["expected"])
    
    # Verificar keywords esperadas
    for keyword in test_case["expected"]:
        if keyword.lower() in answer_lower:
            score += 1
        else:
            passed = False
            reasons.append(f"Falta: '{keyword}'")
    
    # Verificar frases a evitar
    for phrase in test_case["avoid"]:
        if phrase.lower() in answer_lower:
            passed = False
            reasons.append(f"Contiene no deseado: '{phrase}'")
    
    # Verificar longitud mínima
    if len(answer.strip()) < 20:
        passed = False
        reasons.append("Respuesta muy corta")
    
    return {
        "passed": passed,
        "score": score,
        "max_score": max_score,
        "reasons": reasons
    }

def run_simulation(only_ids=None, limit=None):
    """Ejecuta la simulación"""
    print("\n" + "="*60)
    print("  SIMULACIÓN DE 50 CASOS - SISTEMA RAG HÍBRIDO")
    print("="*60 + "\n")
    
    # Verificar que el servidor esté corriendo
    try:
        req = urllib.request.Request(f"{BASE_URL}/")
        with urllib.request.urlopen(req, timeout=5) as response:
            pass
        print("✓ Servidor detectado y activo\n")
    except:
        print("✗ ERROR: El servidor no está corriendo en http://localhost:5000")
        print("  Por favor, inicia el servidor primero con: python web_app.py")
        return
    
    # Filtrar subconjunto si corresponde
    cases = list(TEST_CASES)
    if only_ids:
        id_set = set(int(x) for x in only_ids)
        cases = [tc for tc in cases if int(tc.get('id')) in id_set]
    if limit is not None:
        cases = cases[:int(limit)]

    results = []
    start_time = time.time()
    
    total = len(cases)
    for idx, test_case in enumerate(cases, 1):
        print(f"[{idx}/{total}] {test_case['category']:20s} - {test_case['query'][:50]}...")
        
        try:
            # Enviar query al servidor (forzar modo largo)
            payload = {
                "query": test_case["query"],
                "length_mode": "long",
                "no_context": False
            }
            data_bytes = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                f"{BASE_URL}/api/chat",
                data=data_bytes,
                headers={'Content-Type': 'application/json'}
            )
            
            with urllib.request.urlopen(req, timeout=120) as response:
                data = json.loads(response.read().decode('utf-8'))
                # El endpoint devuelve la respuesta en la clave 'response'
                answer = data.get("response", "")
                sources = data.get("sources", [])
                
                # Validar respuesta
                validation = validate_response(test_case, answer)
                
                result = {
                    "id": test_case["id"],
                    "query": test_case["query"],
                    "category": test_case["category"],
                    "answer": answer[:300],
                    "answer_length": len(answer),
                    "validation": validation,
                    "sources": sources
                }
                
                results.append(result)
                
                # Mostrar resultado
                if validation["passed"]:
                    print(f"  ✓ PASS ({validation['score']}/{validation['max_score']})")
                else:
                    print(f"  ✗ FAIL ({validation['score']}/{validation['max_score']}): {', '.join(validation['reasons'][:2])}")
        
        except Exception as e:
            print(f"  ✗ EXCEPTION: {str(e)[:50]}")
            results.append({
                "id": test_case["id"],
                "query": test_case["query"],
                "category": test_case["category"],
                "error": str(e),
                "validation": {"passed": False, "reasons": ["exception"]}
            })
        
        time.sleep(0.5)  # Pausa entre queries
    
    total_time = time.time() - start_time
    
    # Guardar resultados
    output_file = f"simulation_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "total_tests": len(TEST_CASES),
            "total_time": total_time,
            "results": results
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Resultados guardados en: {output_file}")
    
    # Análisis
    analyze_results(results)

def analyze_results(results):
    """Analiza y muestra estadísticas"""
    print("\n" + "="*60)
    print("  ANÁLISIS DE RESULTADOS")
    print("="*60 + "\n")
    
    total = len(results)
    passed = sum(1 for r in results if r.get("validation", {}).get("passed", False))
    failed = total - passed
    
    print(f"Total de pruebas: {total}")
    print(f"✓ Pasadas: {passed} ({passed/total*100:.1f}%)")
    print(f"✗ Fallidas: {failed} ({failed/total*100:.1f}%)")
    
    # Por categoría
    print("\nResultados por categoría:")
    categories = {}
    for r in results:
        cat = r.get("category", "unknown")
        if cat not in categories:
            categories[cat] = {"total": 0, "passed": 0}
        categories[cat]["total"] += 1
        if r.get("validation", {}).get("passed", False):
            categories[cat]["passed"] += 1
    
    for cat, stats in sorted(categories.items()):
        rate = stats["passed"] / stats["total"] * 100
        symbol = "✓" if rate >= 80 else "⚠" if rate >= 50 else "✗"
        print(f"  {symbol} {cat:20s}: {stats['passed']}/{stats['total']} ({rate:.0f}%)")
    
    # Tests fallidos
    if failed > 0:
        print("\nTests fallidos:")
        for r in results:
            if not r.get("validation", {}).get("passed", False):
                test_id = r.get("id")
                query = r.get("query", "")[:50]
                reasons = r.get("validation", {}).get("reasons", [])
                print(f"\n  Test {test_id}: {query}...")
                for reason in reasons[:3]:
                    print(f"    • {reason}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Ejecuta simulaciones contra /api/chat')
    parser.add_argument('--only-ids', type=str, help='Lista de IDs separados por coma, ej: 1,3,4,5')
    parser.add_argument('--limit', type=int, help='Limitar cantidad de casos')
    args = parser.parse_args()

    only_ids = [x.strip() for x in args.only_ids.split(',')] if args.only_ids else None
    limit = args.limit if args.limit is not None else None

    try:
        run_simulation(only_ids=only_ids, limit=limit)
    except KeyboardInterrupt:
        print("\n\nSimulación interrumpida por el usuario")
    except Exception as e:
        print(f"\nError fatal: {e}")
        import traceback
        traceback.print_exc()
