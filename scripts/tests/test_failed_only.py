"""
Script para ejecutar SOLO los tests que fallaron en la ultima ejecucion
Tests fallidos: 2, 4, 9, 10, 11, 14, 19, 20, 23, 25, 28, 29
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

# SOLO tests que fallaron (12 tests)
FAILED_TESTS = [
    {
        "id": 2,
        "query": "Que tipo de aerogeneradores tiene este parque?",
        "expected_keywords": ["senvion", "3.6m114", "malaspina"],
        "should_not_contain": ["kosten", "goldwind", "envision"],
        "category": "follow_up",
        "depends_on": 1,
        "issue": "Sticky sources debe mantener Malaspina, no contaminar con otros parques"
    },
    {
        "id": 4,
        "query": "Dame toda la información disponible sobre Vientos del Secano",
        "expected_keywords": ["vientos del secano", "50", "mw", "envision"],
        "should_not_contain": ["malaspina", "kosten", "loma blanca"],
        "category": "exact_entity_match",
        "issue": "No debe traer info de otros parques de Envision"
    },
    {
        "id": 9,
        "query": "Que parques eolicos opera el CROM?",
        "expected_keywords": ["eolico", "kosten", "malaspina"],
        "should_not_contain": ["fotovoltaica", "solar", "biogas"],
        "category": "tech_filter",
        "issue": "Debe listar solo eólicos, no solares ni biogás"
    },
    {
        "id": 10,
        "query": "Que parques solares opera el CROM?",
        "expected_keywords": ["fotovoltaica", "solar", "perla del chaco"],
        "should_not_contain": ["eolico", "aerogenerador"],
        "category": "tech_filter",
        "issue": "Debe listar solo solares, no eólicos"
    },
    {
        "id": 11,
        "query": "Donde esta ubicado el parque Kosten?",
        "expected_keywords": ["chubut", "kosten"],
        "should_not_contain": ["malaspina", "totalenergies"],
        "category": "location",
        "issue": "Debe responder solo ubicación de Kosten, no otros parques"
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
    {
        "id": 23,
        "query": "Y su potencia?",
        "expected_keywords": ["24", "mw", "kosten"],
        "should_not_contain": [],
        "category": "follow_up",
        "depends_on": 22,
        "issue": "Debe responder potencia de Kosten, no otros parques"
    },
    {
        "id": 25,
        "query": "Informacion sobre Garcia del Rio",
        "expected_keywords": ["garcia del rio", "10", "envision"],
        "should_not_contain": ["vientos del secano"],
        "category": "entity_query",
        "issue": "Debe responder solo Garcia del Rio, no Vientos del Secano"
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
        "expected_keywords": ["inversor", "caldenes", "abb"],
        "should_not_contain": ["aerogenerador", "eolico"],
        "category": "equipment_model",
        "issue": "Debe responder sobre Caldenes, no otros parques"
    }
]

def normalize_text(text):
    """Normaliza texto removiendo tildes y convirtiendo a minúsculas"""
    if not text:
        return ""
    
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'a', 'É': 'e', 'Í': 'i', 'Ó': 'o', 'Ú': 'u',
        'ñ': 'n', 'Ñ': 'n'
    }
    
    normalized = text.lower()
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    
    return normalized

def validate_answer(answer, sources, expected_keywords, should_not_contain):
    """Valida la respuesta contra keywords esperadas"""
    answer_normalized = normalize_text(answer)
    sources_normalized = ' '.join([normalize_text(s) for s in sources])
    
    missing_keywords = []
    for keyword in expected_keywords:
        keyword_normalized = normalize_text(keyword)
        if keyword_normalized not in answer_normalized and keyword_normalized not in sources_normalized:
            missing_keywords.append(keyword)
    
    unwanted_found = []
    for unwanted in should_not_contain:
        unwanted_normalized = normalize_text(unwanted)
        if unwanted_normalized in answer_normalized:
            unwanted_found.append(unwanted)
    
    passed = len(missing_keywords) == 0 and len(unwanted_found) == 0
    
    return {
        "passed": passed,
        "missing_keywords": missing_keywords,
        "unwanted_found": unwanted_found
    }

def run_failed_tests():
    """Ejecuta SOLO los tests que fallaron"""
    console.print("\n[bold cyan]============================================================[/bold cyan]")
    console.print("[bold cyan]  TESTS FALLIDOS - EJECUCION SELECTIVA (12 tests)  [/bold cyan]")
    console.print("[bold cyan]============================================================[/bold cyan]\n")
    
    # Inicializar RAG
    console.print("[dim]Inicializando sistema RAG...[/dim]")
    rag = HybridRAG()
    
    results = []
    passed_count = 0
    failed_count = 0
    
    # Tests que requieren contexto previo (ejecutar test base primero)
    base_tests = {
        1: {"query": "Dame toda la informacion disponible sobre parque eolico Malaspina"},
        13: {"query": "Que centrales opera TotalEnergies?"},
        22: {"query": "Datos de P.E. Kosten"}
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        
        task = progress.add_task(
            f"[cyan]Ejecutando tests fallidos...",
            total=len(FAILED_TESTS)
        )
        
        for test in FAILED_TESTS:
            test_id = test["id"]
            query = test["query"]
            category = test.get("category", "unknown")
            
            progress.update(task, description=f"Test {test_id}/{len(FAILED_TESTS)}: {category}")
            
            try:
                # Si depende de otro test, ejecutar el base primero
                if "depends_on" in test:
                    dep_id = test["depends_on"]
                    if dep_id in base_tests:
                        console.print(f"[dim]Ejecutando test base {dep_id} para contexto...[/dim]")
                        rag.query(base_tests[dep_id]["query"])
                
                # Ejecutar test
                start_time = time.time()
                result = rag.query(query)
                elapsed = time.time() - start_time
                
                answer = result.get("answer", "")
                sources = result.get("sources", [])
                
                # Validar respuesta
                validation = validate_answer(
                    answer,
                    sources,
                    test["expected_keywords"],
                    test["should_not_contain"]
                )
                
                # Guardar resultado
                results.append({
                    "id": test_id,
                    "query": query,
                    "category": category,
                    "issue": test.get("issue", ""),
                    "answer": answer[:300] if answer else "",
                    "answer_length": len(answer),
                    "sources": sources,
                    "validation": validation,
                    "elapsed": elapsed,
                    "timestamp": datetime.now().isoformat()
                })
                
                # Mostrar resultado
                if validation["passed"]:
                    passed_count += 1
                    status = "OK PASS"
                    color = "green"
                else:
                    failed_count += 1
                    status = "X FAIL"
                    color = "red"
                
                console.print(f"[{color}]{status}[/{color}] Test {test_id}: {test.get('issue', query[:50])}...")
                
                if not validation["passed"]:
                    if validation["missing_keywords"]:
                        console.print(f"  [yellow]Faltan: {', '.join(validation['missing_keywords'])}[/yellow]")
                    if validation["unwanted_found"]:
                        console.print(f"  [yellow]Contaminación: {', '.join(validation['unwanted_found'])}[/yellow]")
                    console.print(f"  [dim]Issue: {test.get('issue', '')}[/dim]")
                
            except Exception as e:
                failed_count += 1
                console.print(f"[red]X EXCEPTION[/red] Test {test_id}: {str(e)}")
                results.append({
                    "id": test_id,
                    "query": query,
                    "category": category,
                    "issue": test.get("issue", ""),
                    "error": str(e),
                    "validation": {
                        "passed": False,
                        "error": str(e)
                    }
                })
            
            progress.update(task, advance=1)
    
    # Guardar resultados
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"failed_results_{timestamp}.json"
    
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    # Resumen
    console.print(f"\n[bold cyan]============================================================[/bold cyan]")
    console.print(f"[bold]Resultados guardados en:[/bold] {results_file}")
    console.print(f"\n[bold]Total:[/bold] {len(FAILED_TESTS)} tests fallidos")
    console.print(f"[green]OK Pasados:[/green] {passed_count} ({passed_count/len(FAILED_TESTS)*100:.1f}%)")
    console.print(f"[red]X Fallidos:[/red] {failed_count} ({failed_count/len(FAILED_TESTS)*100:.1f}%)")
    
    # Fallos por categoría
    if failed_count > 0:
        console.print(f"\n[bold red]Fallos por problema:[/bold red]")
        for result in results:
            if not result.get("validation", {}).get("passed", False):
                console.print(f"  - {result.get('issue', 'Unknown')}: Tests {result['id']}")
    
    console.print(f"[bold cyan]============================================================[/bold cyan]\n")
    
    return results

if __name__ == "__main__":
    run_failed_tests()
