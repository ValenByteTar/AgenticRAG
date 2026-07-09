"""
Test crítico usando el servidor web directamente
Requiere que web_app.py esté corriendo en http://localhost:5000
"""
import json
import time
from pathlib import Path
from datetime import datetime

# Importar tests
import sys
sys.path.insert(0, '.')
exec(open('test_critical.py').read(), globals())

def query_web_api(question):
    """Hace una query al servidor web"""
    try:
        import urllib.request
        import urllib.parse
        
        url = 'http://localhost:5000/api/query'
        data = urllib.parse.urlencode({'question': question, 'length_mode': 'long'}).encode()
        
        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
        
        with urllib.request.urlopen(req, timeout=180) as response:
            result = json.loads(response.read().decode())
            return result
    except Exception as e:
        print(f"Error en query: {e}")
        return None

def run_critical_tests_web():
    """Ejecuta los tests críticos usando el API web"""
    print("\n" + "="*60)
    print("EJECUTANDO TESTS CRÍTICOS VÍA WEB API")
    print("="*60 + "\n")
    
    results = []
    passed = 0
    failed = 0
    
    for i, test_case in enumerate(CRITICAL_TESTS, 1):
        test_id = test_case['id']
        query = test_case['query']
        category = test_case['category']
        issue = test_case['issue']
        
        print(f"\n[{i}/{len(CRITICAL_TESTS)}] Test {test_id}: {query[:50]}...")
        
        # Ejecutar query
        start_time = time.time()
        result = query_web_api(query)
        elapsed = time.time() - start_time
        
        if not result:
            print(f"  X ERROR: No se pudo obtener respuesta")
            failed += 1
            continue
        
        answer = result.get('answer', '')
        sources = result.get('sources', [])
        
        # Validar respuesta
        validation = validate_response(test_case, answer)
        
        # Guardar resultado
        test_result = {
            'id': test_id,
            'query': query,
            'category': category,
            'issue': issue,
            'answer': answer,
            'answer_length': len(answer),
            'sources': sources,
            'validation': validation,
            'timestamp': datetime.now().isoformat()
        }
        results.append(test_result)
        
        # Mostrar resultado
        if validation['passed']:
            print(f"  OK PASÓ ({elapsed:.1f}s)")
            passed += 1
        else:
            print(f"  X FALLÓ ({elapsed:.1f}s)")
            if validation['missing_keywords']:
                print(f"    Faltan keywords: {', '.join(validation['missing_keywords'])}")
            if validation['unwanted_found']:
                print(f"    Contiene no deseadas: {', '.join(validation['unwanted_found'])}")
            failed += 1
        
        # Pequeña pausa entre tests
        time.sleep(0.5)
    
    # Guardar resultados
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_file = f'critical_results_{timestamp}.json'
    
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    # Resumen
    print("\n" + "="*60)
    print(f"Resultados guardados en: {results_file}")
    print(f"\nTotal: {len(CRITICAL_TESTS)} tests")
    print(f"OK Pasados: {passed} ({passed/len(CRITICAL_TESTS)*100:.1f}%)")
    print(f"X Fallidos: {failed} ({failed/len(CRITICAL_TESTS)*100:.1f}%)")
    
    # Fallos por categoría
    if failed > 0:
        print(f"\nFallos por problema:")
        failed_by_issue = {}
        for r in results:
            if not r['validation']['passed']:
                issue = r['issue']
                if issue not in failed_by_issue:
                    failed_by_issue[issue] = []
                failed_by_issue[issue].append(r['id'])
        
        for issue, test_ids in sorted(failed_by_issue.items()):
            print(f"  • {issue}: Tests {', '.join(map(str, test_ids))}")
    
    print("="*60 + "\n")
    
    return passed, failed, results

if __name__ == "__main__":
    # Verificar que el servidor esté corriendo
    try:
        import urllib.request
        urllib.request.urlopen('http://localhost:5000', timeout=2)
        print("OK Servidor web detectado en http://localhost:5000")
    except:
        print("X ERROR: El servidor web no está corriendo")
        print("  Por favor inicia web_app.py primero")
        sys.exit(1)
    
    run_critical_tests_web()
