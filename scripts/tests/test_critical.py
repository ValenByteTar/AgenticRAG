"""
Tests críticos enfocados en problemas identificados
Basado en análisis de fallos: 6, 7, 8, 9, 11, 12, 15, 16, 17, 21, 25, 28, 29, 30, 40, 43, 46, 50
"""

import sys
import io
# Fix unicode encoding para Windows console
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import json
import time
from datetime import datetime
from rag_hybrid import HybridRAG
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

console = Console(force_terminal=True, legacy_windows=False)

# Tests críticos enfocados en problemas específicos
CRITICAL_TESTS = [
    # PROBLEMA: Follow-up con sticky sources (Test 6 original)
    {
        "id": 1,
        "query": "Dame toda la informacion disponible sobre parque eolico Malaspina",
        "expected_keywords": ["malaspina", "eolico", "senvion"],
        "should_not_contain": ["kosten", "loma blanca"],
        "category": "detailed_query",
        "issue": "Baseline para follow-up"
    },
    {
        "id": 2,
        "query": "Que tipo de aerogeneradores tiene este parque?",
        "expected_keywords": ["senvion", "3.6m114", "malaspina"],
        "should_not_contain": ["kosten", "goldwind", "envision"],
        "category": "follow_up",
        "depends_on": 1,
        "issue": "Sticky sources debe mantener Malaspina, no contaminar con otros parques"
    },
    
    # PROBLEMA: Comparación con contexto previo (Test 7 original)
    {
        "id": 3,
        "query": "Compara estos aerogeneradores con los que tiene parque eolico Kosten",
        "expected_keywords": ["malaspina", "kosten", "senvion"],
        "should_not_contain": ["no se menciona kosten", "no hay información"],
        "category": "comparison",
        "depends_on": 2,
        "issue": "Debe buscar info de ambos parques sin alucinar"
    },
    
    # PROBLEMA: Entidad exacta vs parcial (Test 8 original)
    {
        "id": 4,
        "query": "Dame toda la información disponible sobre Vientos del Secano",
        "expected_keywords": ["vientos del secano", "50", "mw", "envision"],
        "should_not_contain": ["garcia del rio", "loma blanca"],
        "category": "exact_entity_match",
        "issue": "No debe traer info de otros parques de Envision"
    },
    
    # PROBLEMA: Potencia numérica simple (Test 9 original)
    {
        "id": 5,
        "query": "Potencia de Vientos del Secano",
        "expected_keywords": ["50", "mw", "vientos del secano"],
        "should_not_contain": ["10 mw", "garcia"],
        "category": "numeric_query",
        "issue": "Debe responder solo potencia de Vientos del Secano, no otros parques"
    },
    
    # PROBLEMA: Follow-up con acrónimos (Test 11 original)
    {
        "id": 6,
        "query": "Dame toda la informacion disponible sobre el PT8",
        "expected_keywords": ["pt8"],
        "should_not_contain": [],
        "category": "document_query",
        "issue": "Baseline para acrónimos"
    },
    {
        "id": 7,
        "query": "Y que significa COC?",
        "expected_keywords": ["centro", "operacion"],
        "should_not_contain": [],
        "category": "follow_up",
        "depends_on": 6,
        "issue": "Debe responder sobre COC sin alucinar con PT8"
    },
    
    # PROBLEMA: Follow-up anafórico (Test 12 original)
    {
        "id": 8,
        "query": "COC tiene que ver con CAMMESA?",
        "expected_keywords": ["centro"],
        "should_not_contain": [],
        "category": "follow_up",
        "depends_on": 7,
        "issue": "Debe relacionar COC con CAMMESA correctamente"
    },
    
    # PROBLEMA: Filtro por tecnología (Test 15 original)
    {
        "id": 9,
        "query": "Que parques eolicos opera el CROM?",
        "expected_keywords": ["malaspina", "kosten"],
        "should_not_contain": ["perla del chaco", "algarrobo", "solar"],
        "category": "tech_filter",
        "issue": "Debe listar solo eólicos, no solares ni biogás"
    },
    
    # PROBLEMA: Filtro por tecnología solar (Test 16 original)
    {
        "id": 10,
        "query": "Que parques solares opera el CROM?",
        "expected_keywords": ["solar", "fotovoltaica", "perla del chaco"],
        "should_not_contain": ["malaspina", "kosten", "eolico"],
        "category": "tech_filter",
        "issue": "Debe listar solo solares, no eólicos"
    },
    
    # PROBLEMA: Ubicación con contaminación (Test 17 original)
    {
        "id": 11,
        "query": "Donde esta ubicado el parque Kosten?",
        "expected_keywords": ["kosten", "pampa del castillo", "chubut"],
        "should_not_contain": ["malaspina", "comodoro rivadavia", "totalenergies"],
        "category": "location",
        "issue": "Debe responder solo ubicación de Kosten, no otros parques"
    },
    
    # PROBLEMA: Procedimiento con alucinación (Test 21 original)
    {
        "id": 12,
        "query": "Como se gestiona una orden de servicio en el SADI?",
        "expected_keywords": ["orden", "servicio"],
        "should_not_contain": ["malaspina", "kosten", "aerogenerador"],
        "category": "procedural",
        "issue": "Debe responder sobre procedimientos, no sobre parques específicos"
    },
    
    # PROBLEMA: Protecciones con sticky sources (Test 25 original)
    {
        "id": 13,
        "query": "Que centrales opera TotalEnergies?",
        "expected_keywords": ["malaspina"],
        "should_not_contain": ["kosten", "grenergy"],
        "category": "vendor_filter",
        "issue": "Baseline para protecciones"
    },
    {
        "id": 14,
        "query": "Que protecciones tiene el parque Kosten?",
        "expected_keywords": ["proteccion", "kosten", "grenergy"],
        "should_not_contain": ["malaspina", "totalenergies", "no hay información"],
        "category": "protection",
        "depends_on": 13,
        "issue": "Debe buscar en Protecciones + Anexo D Grenergy, no mantener TotalEnergies"
    },
    
    # PROBLEMA: Celdas con alucinación (Test 28 original)
    {
        "id": 15,
        "query": "Cuantas celdas tiene la ET Pampa del Castillo?",
        "expected_keywords": ["celda", "4"],
        "should_not_contain": [],
        "category": "cells",
        "issue": "Debe responder sobre celdas o indicar falta de info, no alucinar"
    },
    
    # PROBLEMA: Agregación total (Test 29 original)
    {
        "id": 16,
        "query": "Cual es la potencia total de las centrales del CROM?",
        "expected_keywords": ["total", "mw"],
        "should_not_contain": ["malaspina: 50", "kosten: 24"],
        "category": "aggregation",
        "issue": "Debe sumar todas las centrales, no listar individualmente"
    },
    
    # PROBLEMA: Acrónimo simple (Test 30 original)
    {
        "id": 17,
        "query": "Que es PT8?",
        "expected_keywords": ["procedimiento"],
        "should_not_contain": ["pt4", "pt11"],
        "category": "acronym",
        "issue": "Debe responder solo sobre PT8, no otros PT"
    },
    
    # PROBLEMA: Multi-documento (Test 40 original)
    {
        "id": 18,
        "query": "Que documentos hablan sobre Kosten?",
        "expected_keywords": ["anexo d", "kosten", "grenergy"],
        "should_not_contain": ["malaspina", "totalenergies"],
        "category": "multi_document",
        "issue": "Debe identificar Anexo D Grenergy, no otros"
    },
    
    # PROBLEMA: Query ambigua sin contexto (Test 43 original)
    {
        "id": 19,
        "query": "Cuantos aerogeneradores tiene Kosten?",
        "expected_keywords": ["7", "kosten"],
        "should_not_contain": [],
        "category": "numeric_query",
        "issue": "Baseline para ambigua"
    },
    {
        "id": 20,
        "query": "Cuantos tiene?",
        "expected_keywords": ["aerogenerador"],
        "should_not_contain": [],
        "category": "ambiguous",
        "depends_on": 19,
        "issue": "Debe usar contexto previo (Kosten), no alucinar otros parques"
    },
    
    # PROBLEMA: Query muy corta (Test 46 original)
    {
        "id": 21,
        "query": "Kosten",
        "expected_keywords": ["kosten", "24", "mw"],
        "should_not_contain": ["malaspina", "totalenergies"],
        "category": "short_query",
        "issue": "Debe responder info de Kosten, no contaminar con otros parques"
    },
    
    # PROBLEMA: Sticky sources con follow-up (Test 50 original)
    {
        "id": 22,
        "query": "Datos de P.E. Kosten",
        "expected_keywords": ["kosten", "eolico", "24"],
        "should_not_contain": [],
        "category": "entity_with_prefix",
        "issue": "Baseline para sticky"
    },
    {
        "id": 23,
        "query": "Y su potencia?",
        "expected_keywords": ["24", "mw", "kosten"],
        "should_not_contain": ["50", "malaspina", "51"],
        "category": "follow_up",
        "depends_on": 22,
        "issue": "Debe responder potencia de Kosten, no otros parques"
    },
    
    # NUEVOS TESTS: Casos adicionales de contaminación
    {
        "id": 24,
        "query": "Cuantos aerogeneradores tiene Loma Blanca I?",
        "expected_keywords": ["16", "loma blanca"],
        "should_not_contain": ["loma blanca ii", "loma blanca iii", "14"],
        "category": "numeric_query",
        "issue": "Debe responder solo Loma Blanca I, no II o III"
    },
    {
        "id": 25,
        "query": "Informacion sobre Garcia del Rio",
        "expected_keywords": ["garcia del rio", "10", "mw", "envision"],
        "should_not_contain": ["vientos del secano", "50 mw"],
        "category": "entity_query",
        "issue": "Debe responder solo Garcia del Rio, no Vientos del Secano"
    },
    {
        "id": 26,
        "query": "Que parques opera GOLDWIND?",
        "expected_keywords": ["goldwind", "loma blanca"],
        "should_not_contain": ["envision", "senvion", "malaspina"],
        "category": "vendor_filter",
        "issue": "Debe listar solo parques de Goldwind"
    },
    {
        "id": 27,
        "query": "Potencia de Loma Blanca II",
        "expected_keywords": ["51", "mw", "loma blanca ii"],
        "should_not_contain": ["loma blanca iii"],
        "category": "numeric_query",
        "issue": "Debe responder solo Loma Blanca II"
    },
    {
        "id": 28,
        "query": "Compara Loma Blanca I y Loma Blanca II",
        "expected_keywords": ["loma blanca i", "loma blanca ii", "16", "14"],
        "should_not_contain": ["loma blanca iii"],
        "category": "comparison",
        "issue": "Debe comparar solo I y II, no incluir III"
    },
    {
        "id": 29,
        "query": "Que inversores usa Caldenes del Oeste?",
        "expected_keywords": ["caldenes", "inversor"],
        "should_not_contain": ["malaspina", "kosten", "aerogenerador"],
        "category": "equipment_model",
        "issue": "Debe responder sobre Caldenes, no otros parques"
    },
    {
        "id": 30,
        "query": "Donde esta Tinogasta?",
        "expected_keywords": ["catamarca"],
        "should_not_contain": ["chubut", "malaspina", "kosten"],
        "category": "location",
        "issue": "Debe responder ubicación de Tinogasta, no otros parques"
    }
]

def validate_response(test_case, answer):
    """Valida si la respuesta cumple con los criterios"""
    import unicodedata
    
    # Normalizar respuesta (remover tildes para comparación)
    def normalize(text):
        return ''.join(
            c for c in unicodedata.normalize('NFD', text.lower())
            if unicodedata.category(c) != 'Mn'
        )
    
    answer_normalized = normalize(answer)
    
    passed = True
    missing_keywords = []
    unwanted_found = []
    
    # Verificar keywords esperadas
    for keyword in test_case.get("expected_keywords", []):
        keyword_normalized = normalize(keyword)
        if keyword_normalized not in answer_normalized:
            missing_keywords.append(keyword)
            passed = False
    
    # Verificar que no contenga palabras no deseadas
    for unwanted in test_case.get("should_not_contain", []):
        unwanted_normalized = normalize(unwanted)
        if unwanted_normalized in answer_normalized:
            unwanted_found.append(unwanted)
            passed = False
    
    return {
        "passed": passed,
        "missing_keywords": missing_keywords,
        "unwanted_found": unwanted_found
    }

def run_critical_tests():
    """Ejecuta los tests críticos"""
    console.print("\n[bold red]===========================================================[/bold red]")
    console.print("[bold red]  TESTS CRITICOS - PROBLEMAS IDENTIFICADOS  [/bold red]")
    console.print("[bold red]===========================================================[/bold red]\n")
    
    # Inicializar RAG
    console.print("[yellow]Inicializando sistema RAG...[/yellow]")
    rag = HybridRAG()
    
    results = []
    passed_count = 0
    failed_count = 0
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        
        task = progress.add_task("[cyan]Ejecutando tests críticos...", total=len(CRITICAL_TESTS))
        
        for test_case in CRITICAL_TESTS:
            test_id = test_case["id"]
            query = test_case["query"]
            category = test_case["category"]
            issue = test_case.get("issue", "")
            
            progress.update(task, description=f"[cyan]Test {test_id}/{len(CRITICAL_TESTS)}: {category}")
            
            try:
                # Ejecutar query
                response = rag.query(query, length_mode='long', no_context=False)
                answer = response.get("answer", "")
                sources = response.get("sources", [])
                
                # Validar respuesta
                validation = validate_response(test_case, answer)
                
                if validation["passed"]:
                    passed_count += 1
                    status = "OK PASS"
                    color = "green"
                else:
                    failed_count += 1
                    status = "X FAIL"
                    color = "red"
                
                console.print(f"[{color}]{status}[/{color}] Test {test_id}: {query[:60]}...")
                if not validation["passed"]:
                    if validation["missing_keywords"]:
                        console.print(f"  [yellow]Faltan: {', '.join(validation['missing_keywords'])}[/yellow]")
                    if validation["unwanted_found"]:
                        console.print(f"  [yellow]Contaminación: {', '.join(validation['unwanted_found'])}[/yellow]")
                    console.print(f"  [dim]Issue: {issue}[/dim]")
                
                result = {
                    "id": test_id,
                    "query": query,
                    "category": category,
                    "issue": issue,
                    "answer": answer[:300],
                    "answer_length": len(answer),
                    "sources": sources,
                    "validation": validation,
                    "timestamp": datetime.now().isoformat()
                }
                
                results.append(result)
                
            except Exception as e:
                failed_count += 1
                console.print(f"[red]X EXCEPTION[/red] Test {test_id}: {str(e)}")
                results.append({
                    "id": test_id,
                    "query": query,
                    "category": category,
                    "issue": issue,
                    "error": str(e),
                    "validation": {"passed": False, "error": str(e)}
                })
            
            progress.update(task, advance=1)
            time.sleep(0.3)
    
    # Guardar resultados
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"critical_results_{timestamp}.json"
    
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    # Resumen
    console.print(f"\n[bold cyan]===========================================================[/bold cyan]")
    console.print(f"[bold]Resultados guardados en:[/bold] {results_file}")
    console.print(f"\n[bold]Total:[/bold] {len(CRITICAL_TESTS)} tests")
    console.print(f"[green]OK Pasados:[/green] {passed_count} ({passed_count/len(CRITICAL_TESTS)*100:.1f}%)")
    console.print(f"[red]X Fallidos:[/red] {failed_count} ({failed_count/len(CRITICAL_TESTS)*100:.1f}%)")
    
    # Agrupar fallos por issue
    issues = {}
    for result in results:
        if not result.get("validation", {}).get("passed", False):
            issue = result.get("issue", "Unknown")
            if issue not in issues:
                issues[issue] = []
            issues[issue].append(result["id"])
    
    if issues:
        console.print(f"\n[bold red]Fallos por problema:[/bold red]")
        for issue, test_ids in issues.items():
            console.print(f"  [yellow]• {issue}:[/yellow] Tests {', '.join(map(str, test_ids))}")
    
    return results

if __name__ == "__main__":
    run_critical_tests()
