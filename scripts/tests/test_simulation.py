"""
Script de simulación para validar el sistema RAG con 50 casos de prueba
Basado en el contexto conversacional y casos problemáticos identificados
"""

import json
import time
from datetime import datetime
from rag_hybrid import HybridRAG
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

console = Console()

# 50 casos de prueba cubriendo diferentes escenarios
TEST_CASES = [
    # Casos de entidades con variantes de nombre
    {
        "id": 1,
        "query": "Que tecnologia maneja la perla del chaco?",
        "expected_keywords": ["fotovoltaica", "huawei"],
        "should_not_contain": ["no hay información", "no se encontró", "lo siento"],
        "category": "entity_variant"
    },
    {
        "id": 2,
        "query": "Dame informacion sobre la perla de chaco",
        "expected_keywords": ["fotovoltaica", "25", "huawei"],
        "should_not_contain": ["no hay información"],
        "category": "entity_variant"
    },
    {
        "id": 3,
        "query": "Hablame sobre el parque la perla del chaco",
        "expected_keywords": ["fotovoltaica", "dqd"],
        "should_not_contain": ["no hay información"],
        "category": "entity_variant"
    },
    {
        "id": 4,
        "query": "Y no hay un Anexo D - DQD que hable de este parque?",
        "expected_keywords": ["anexo"],
        "should_not_contain": ["no aparece", "no se encontró"],
        "category": "document_reference"
    },
    
    # Casos de comparación con contexto previo
    {
        "id": 5,
        "query": "Dame toda la informacion disponible sobre parque eolico Malaspina",
        "expected_keywords": ["malaspina", "eolico", "senvion"],
        "should_not_contain": [],
        "category": "detailed_query"
    },
    {
        "id": 6,
        "query": "Que tipo de aerogeneradores tiene este parque?",
        "expected_keywords": ["senvion", "3.6m114"],
        "should_not_contain": [],
        "category": "follow_up",
        "depends_on": 5
    },
    {
        "id": 7,
        "query": "Compara estos aerogeneradores con los que tiene parque eolico Kosten",
        "expected_keywords": ["malaspina", "kosten", "senvion"],
        "should_not_contain": ["no se menciona kosten"],
        "category": "comparison",
        "depends_on": 6
    },
    
    # Casos de entidades exactas vs parciales
    {
        "id": 8,
        "query": "Dame toda la información disponible sobre Vientos del Secano",
        "expected_keywords": ["vientos del secano", "listado centrales"],
        "should_not_contain": ["envision"],
        "category": "exact_entity_match"
    },
    {
        "id": 9,
        "query": "Potencia de Vientos del Secano",
        "expected_keywords": ["mw", "vientos del secano"],
        "should_not_contain": [],
        "category": "numeric_query"
    },
    
    # Casos de documentos técnicos (PT)
    {
        "id": 10,
        "query": "Dame toda la informacion disponible sobre el PT8",
        "expected_keywords": ["pt8", "reglamento operativo", "sadi"],
        "should_not_contain": [],
        "category": "document_query"
    },
    {
        "id": 11,
        "query": "Y que significa COC?",
        "expected_keywords": ["centro", "control", "operacion"],
        "should_not_contain": [],
        "category": "follow_up",
        "depends_on": 10
    },
    {
        "id": 12,
        "query": "COC tiene que ver con CAMMESA?",
        "expected_keywords": ["cammesa", "coc"],
        "should_not_contain": [],
        "category": "follow_up",
        "depends_on": 11
    },
    
    # Casos de listados
    {
        "id": 13,
        "query": "Lista todas las centrales operadas por el CROM",
        "expected_keywords": ["central", "parque"],
        "should_not_contain": [],
        "category": "listing"
    },
    {
        "id": 14,
        "query": "Cuantas centrales opera el CROM?",
        "expected_keywords": ["total", "central"],
        "should_not_contain": [],
        "category": "count"
    },
    
    # Casos de tecnología específica
    {
        "id": 15,
        "query": "Que parques eolicos opera el CROM?",
        "expected_keywords": ["eolico", "parque"],
        "should_not_contain": [],
        "category": "tech_filter"
    },
    {
        "id": 16,
        "query": "Que parques solares opera el CROM?",
        "expected_keywords": ["solar", "fotovoltaica"],
        "should_not_contain": [],
        "category": "tech_filter"
    },
    
    # Casos de ubicación
    {
        "id": 17,
        "query": "Donde esta ubicado el parque Kosten?",
        "expected_keywords": ["kosten", "pampa del castillo", "latitud", "longitud"],
        "should_not_contain": [],
        "category": "location"
    },
    {
        "id": 18,
        "query": "Coordenadas de Malaspina",
        "expected_keywords": ["latitud", "longitud"],
        "should_not_contain": [],
        "category": "location"
    },
    
    # Casos de atributos específicos
    {
        "id": 19,
        "query": "Cuantos aerogeneradores tiene Kosten?",
        "expected_keywords": ["7", "siete", "kosten"],
        "should_not_contain": [],
        "category": "numeric_query"
    },
    {
        "id": 20,
        "query": "Potencia instalada de Malaspina",
        "expected_keywords": ["50.4", "mw", "malaspina"],
        "should_not_contain": [],
        "category": "numeric_query"
    },
    
    # Casos de procedimientos
    {
        "id": 21,
        "query": "Como se gestiona una orden de servicio en el SADI?",
        "expected_keywords": ["pt8", "orden", "servicio"],
        "should_not_contain": [],
        "category": "procedural"
    },
    {
        "id": 22,
        "query": "Que es el PT4?",
        "expected_keywords": ["pt4", "ingreso", "nuevos"],
        "should_not_contain": [],
        "category": "document_query"
    },
    
    # Casos de empresas/operadores
    {
        "id": 23,
        "query": "Que centrales opera TotalEnergies?",
        "expected_keywords": ["totalenergies", "malaspina"],
        "should_not_contain": [],
        "category": "vendor_filter"
    },
    {
        "id": 24,
        "query": "Que centrales opera GRENERGY?",
        "expected_keywords": ["grenergy", "kosten"],
        "should_not_contain": [],
        "category": "vendor_filter"
    },
    
    # Casos de protecciones
    {
        "id": 25,
        "query": "Que protecciones tiene el parque Kosten?",
        "expected_keywords": ["proteccion", "kosten"],
        "should_not_contain": [],
        "category": "protection"
    },
    
    # Casos de SCADA
    {
        "id": 26,
        "query": "Como se monitorea el parque Kosten en SCADA?",
        "expected_keywords": ["scada", "kosten"],
        "should_not_contain": [],
        "category": "scada"
    },
    
    # Casos de subestaciones
    {
        "id": 27,
        "query": "Que subestacion conecta a Kosten?",
        "expected_keywords": ["pampa del castillo", "kosten"],
        "should_not_contain": [],
        "category": "substation"
    },
    
    # Casos de celdas/circuitos
    {
        "id": 28,
        "query": "Cuantas celdas tiene la ET Pampa del Castillo?",
        "expected_keywords": ["celda", "pampa"],
        "should_not_contain": [],
        "category": "cells"
    },
    
    # Casos de potencia agregada
    {
        "id": 29,
        "query": "Cual es la potencia total de las centrales del CROM?",
        "expected_keywords": ["total", "mw"],
        "should_not_contain": [],
        "category": "aggregation"
    },
    
    # Casos de nombres con acrónimos
    {
        "id": 30,
        "query": "Que es PT8?",
        "expected_keywords": ["pt8", "reglamento"],
        "should_not_contain": [],
        "category": "acronym"
    },
    {
        "id": 31,
        "query": "Informacion sobre PT4",
        "expected_keywords": ["pt4", "ingreso"],
        "should_not_contain": [],
        "category": "acronym"
    },
    
    # Casos de variantes de nombres (Loma Blanca)
    {
        "id": 32,
        "query": "Cuantos parques Loma Blanca hay?",
        "expected_keywords": ["loma blanca"],
        "should_not_contain": [],
        "category": "multi_entity"
    },
    {
        "id": 33,
        "query": "Potencia de Loma Blanca I",
        "expected_keywords": ["loma blanca", "mw"],
        "should_not_contain": [],
        "category": "entity_variant"
    },
    
    # Casos de fechas/habilitación
    {
        "id": 34,
        "query": "Cuando fue habilitada La Perla del Chaco?",
        "expected_keywords": ["2025", "perla"],
        "should_not_contain": [],
        "category": "date_query"
    },
    
    # Casos de modelos de equipos
    {
        "id": 35,
        "query": "Que modelo de aerogeneradores tiene Malaspina?",
        "expected_keywords": ["senvion", "3.6m114"],
        "should_not_contain": [],
        "category": "equipment_model"
    },
    {
        "id": 36,
        "query": "Que inversores usa La Perla del Chaco?",
        "expected_keywords": ["huawei"],
        "should_not_contain": [],
        "category": "equipment_model"
    },
    
    # Casos de análisis conceptual
    {
        "id": 37,
        "query": "Que es una orden de servicio?",
        "expected_keywords": ["orden", "servicio"],
        "should_not_contain": [],
        "category": "conceptual"
    },
    {
        "id": 38,
        "query": "Que es el SADI?",
        "expected_keywords": ["sistema", "argentino", "interconexion"],
        "should_not_contain": [],
        "category": "conceptual"
    },
    
    # Casos de troubleshooting
    {
        "id": 39,
        "query": "Que hacer si hay una falla en un aerogenerador?",
        "expected_keywords": ["proteccion", "scada"],
        "should_not_contain": [],
        "category": "troubleshooting"
    },
    
    # Casos de múltiples documentos
    {
        "id": 40,
        "query": "Que documentos hablan sobre Kosten?",
        "expected_keywords": ["anexo d", "kosten"],
        "should_not_contain": [],
        "category": "multi_document"
    },
    
    # Casos de negación (debe rechazar correctamente)
    {
        "id": 41,
        "query": "Como se hace un asado?",
        "expected_keywords": ["consulta fuera", "alcance"],
        "should_not_contain": [],
        "category": "out_of_domain"
    },
    {
        "id": 42,
        "query": "Quien gano el mundial 2022?",
        "expected_keywords": ["consulta fuera", "alcance"],
        "should_not_contain": [],
        "category": "out_of_domain"
    },
    
    # Casos de queries ambiguas (debe pedir aclaración o usar contexto)
    {
        "id": 43,
        "query": "Cuantos tiene?",
        "expected_keywords": [],
        "should_not_contain": [],
        "category": "ambiguous",
        "depends_on": 19
    },
    
    # Casos de comparación directa
    {
        "id": 44,
        "query": "Compara Kosten y Malaspina",
        "expected_keywords": ["kosten", "malaspina"],
        "should_not_contain": ["no se menciona"],
        "category": "comparison"
    },
    
    # Casos de queries muy largas
    {
        "id": 45,
        "query": "Dame toda la informacion disponible sobre el parque eolico Kosten incluyendo ubicacion potencia aerogeneradores protecciones y conexion a la red",
        "expected_keywords": ["kosten", "mw", "aerogenerador"],
        "should_not_contain": [],
        "category": "detailed_query"
    },
    
    # Casos de queries muy cortas
    {
        "id": 46,
        "query": "Kosten",
        "expected_keywords": ["kosten"],
        "should_not_contain": [],
        "category": "short_query"
    },
    {
        "id": 47,
        "query": "PT8",
        "expected_keywords": ["pt8"],
        "should_not_contain": [],
        "category": "short_query"
    },
    
    # Casos de entidades con prefijos
    {
        "id": 48,
        "query": "Informacion sobre P.S. La Perla de Chaco",
        "expected_keywords": ["perla", "fotovoltaica"],
        "should_not_contain": [],
        "category": "entity_with_prefix"
    },
    {
        "id": 49,
        "query": "Datos de P.E. Kosten",
        "expected_keywords": ["kosten", "eolico"],
        "should_not_contain": [],
        "category": "entity_with_prefix"
    },
    
    # Caso de sticky sources
    {
        "id": 50,
        "query": "Y su potencia?",
        "expected_keywords": [],
        "should_not_contain": [],
        "category": "follow_up",
        "depends_on": 49
    }
]

def run_simulation():
    """Ejecuta las 50 simulaciones y guarda los resultados"""
    console.print("\n[bold cyan]═══════════════════════════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]  SIMULACIÓN DE 50 CASOS DE PRUEBA - SISTEMA RAG HÍBRIDO  [/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════════════════════════[/bold cyan]\n")
    
    # Inicializar RAG
    console.print("[yellow]Inicializando sistema RAG...[/yellow]")
    rag = HybridRAG()
    
    results = []
    start_time = time.time()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        
        task = progress.add_task("[cyan]Ejecutando simulaciones...", total=len(TEST_CASES))
        
        for test_case in TEST_CASES:
            test_id = test_case["id"]
            query = test_case["query"]
            category = test_case["category"]
            
            progress.update(task, description=f"[cyan]Test {test_id}/50: {category}")
            
            try:
                # Ejecutar query
                response = rag.query(query)
                answer = response.get("answer", "")
                sources = response.get("sources", [])
                time_taken = response.get("time", 0)
                
                # Validar respuesta
                validation = validate_response(test_case, answer, sources)
                
                result = {
                    "id": test_id,
                    "query": query,
                    "category": category,
                    "answer": answer[:500],  # Primeros 500 chars
                    "answer_length": len(answer),
                    "sources_count": len(sources),
                    "time_taken": time_taken,
                    "validation": validation,
                    "timestamp": datetime.now().isoformat()
                }
                
                results.append(result)
                
            except Exception as e:
                console.print(f"[red]Error en test {test_id}: {str(e)}[/red]")
                results.append({
                    "id": test_id,
                    "query": query,
                    "category": category,
                    "error": str(e),
                    "validation": {"passed": False, "reason": "exception"}
                })
            
            progress.update(task, advance=1)
            time.sleep(0.5)  # Pequeña pausa entre queries
    
    total_time = time.time() - start_time
    
    # Guardar resultados
    output_file = f"simulation_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "total_tests": len(TEST_CASES),
            "total_time": total_time,
            "results": results
        }, f, indent=2, ensure_ascii=False)
    
    console.print(f"\n[green]OK Resultados guardados en: {output_file}[/green]")
    
    return results, output_file

def validate_response(test_case, answer, sources):
    """Valida si la respuesta cumple con los criterios esperados"""
    answer_lower = answer.lower()
    
    validation = {
        "passed": True,
        "reasons": [],
        "score": 0,
        "max_score": 0
    }
    
    # Verificar keywords esperadas
    expected_keywords = test_case.get("expected_keywords", [])
    if expected_keywords:
        validation["max_score"] += len(expected_keywords)
        for keyword in expected_keywords:
            if keyword.lower() in answer_lower:
                validation["score"] += 1
            else:
                validation["passed"] = False
                validation["reasons"].append(f"Falta keyword esperada: '{keyword}'")
    
    # Verificar que NO contenga ciertas frases
    should_not_contain = test_case.get("should_not_contain", [])
    if should_not_contain:
        for phrase in should_not_contain:
            if phrase.lower() in answer_lower:
                validation["passed"] = False
                validation["reasons"].append(f"Contiene frase no deseada: '{phrase}'")
    
    # Verificar que no sea una respuesta vacía o muy corta
    if len(answer.strip()) < 20:
        validation["passed"] = False
        validation["reasons"].append("Respuesta muy corta o vacía")
    
    # Verificar que tenga fuentes
    if not sources or len(sources) == 0:
        validation["reasons"].append("Sin fuentes citadas")
    
    return validation

def analyze_results(results):
    """Analiza los resultados y genera un reporte"""
    console.print("\n[bold cyan]═══════════════════════════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]              ANÁLISIS DE RESULTADOS                       [/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════════════════════════[/bold cyan]\n")
    
    # Estadísticas generales
    total = len(results)
    passed = sum(1 for r in results if r.get("validation", {}).get("passed", False))
    failed = total - passed
    
    console.print(f"[bold]Total de pruebas:[/bold] {total}")
    console.print(f"[green]OK Pasadas:[/green] {passed} ({passed/total*100:.1f}%)")
    console.print(f"[red]X Fallidas:[/red] {failed} ({failed/total*100:.1f}%)")
    
    # Análisis por categoría
    console.print("\n[bold]Resultados por categoría:[/bold]")
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
        color = "green" if rate >= 80 else "yellow" if rate >= 50 else "red"
        console.print(f"  [{color}]{cat:20s}[/{color}]: {stats['passed']}/{stats['total']} ({rate:.0f}%)")
    
    # Tests fallidos
    if failed > 0:
        console.print("\n[bold red]Tests fallidos:[/bold red]")
        for r in results:
            if not r.get("validation", {}).get("passed", False):
                test_id = r.get("id")
                query = r.get("query", "")[:60]
                reasons = r.get("validation", {}).get("reasons", [])
                console.print(f"\n[red]Test {test_id}:[/red] {query}...")
                for reason in reasons:
                    console.print(f"  • {reason}")
    
    # Tiempos de respuesta
    times = [r.get("time_taken", 0) for r in results if "time_taken" in r]
    if times:
        avg_time = sum(times) / len(times)
        max_time = max(times)
        min_time = min(times)
        console.print(f"\n[bold]Tiempos de respuesta:[/bold]")
        console.print(f"  Promedio: {avg_time:.1f}s")
        console.print(f"  Mínimo: {min_time:.1f}s")
        console.print(f"  Máximo: {max_time:.1f}s")
    
    # Recomendaciones
    console.print("\n[bold yellow]Recomendaciones:[/bold yellow]")
    
    # Analizar patrones de fallas
    failure_patterns = {}
    for r in results:
        if not r.get("validation", {}).get("passed", False):
            reasons = r.get("validation", {}).get("reasons", [])
            for reason in reasons:
                if "keyword" in reason.lower():
                    failure_patterns["missing_keywords"] = failure_patterns.get("missing_keywords", 0) + 1
                elif "frase no deseada" in reason.lower():
                    failure_patterns["unwanted_phrases"] = failure_patterns.get("unwanted_phrases", 0) + 1
                elif "corta" in reason.lower():
                    failure_patterns["short_answers"] = failure_patterns.get("short_answers", 0) + 1
    
    if failure_patterns.get("missing_keywords", 0) > 5:
        console.print("  • [yellow]Mejorar extracción de entidades y búsqueda semántica[/yellow]")
    if failure_patterns.get("unwanted_phrases", 0) > 3:
        console.print("  • [yellow]Endurecer prompt para evitar rechazos incorrectos[/yellow]")
    if failure_patterns.get("short_answers", 0) > 3:
        console.print("  • [yellow]Mejorar construcción de contexto para respuestas más completas[/yellow]")
    
    # Categorías con bajo rendimiento
    low_perf_cats = [cat for cat, stats in categories.items() if stats["passed"] / stats["total"] < 0.7]
    if low_perf_cats:
        console.print(f"  • [yellow]Categorías con bajo rendimiento: {', '.join(low_perf_cats)}[/yellow]")

if __name__ == "__main__":
    try:
        results, output_file = run_simulation()
        analyze_results(results)
        
        console.print(f"\n[bold green]Simulación completada exitosamente[/bold green]")
        console.print(f"[dim]Resultados detallados en: {output_file}[/dim]")
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Simulación interrumpida por el usuario[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error fatal: {e}[/red]")
        import traceback
        traceback.print_exc()
