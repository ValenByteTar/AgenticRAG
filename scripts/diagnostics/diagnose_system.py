"""
Script de diagnóstico para identificar por qué el sistema no recupera documentos
"""

from rag_hybrid import HybridRAG
from rich.console import Console
from rich.table import Table

console = Console()

def diagnose():
    console.print("\n[bold cyan]═══════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]  DIAGNÓSTICO DEL SISTEMA RAG  [/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════[/bold cyan]\n")
    
    # Inicializar RAG
    console.print("[yellow]Inicializando sistema RAG...[/yellow]")
    rag = HybridRAG()
    
    # 1. Verificar vector store
    console.print("\n[bold]1. Verificando Vector Store[/bold]")
    try:
        stats = rag.vector_store.get_stats()
        console.print(f"  ✓ Total de chunks: {stats.get('total_chunks', 0)}")
        console.print(f"  ✓ Total de documentos: {stats.get('total_documents', 0)}")
        
        if stats.get('total_chunks', 0) == 0:
            console.print("[red]  ✗ ERROR: Vector store vacío![/red]")
            return
    except Exception as e:
        console.print(f"[red]  ✗ ERROR al acceder vector store: {e}[/red]")
        return
    
    # 2. Probar búsqueda simple
    console.print("\n[bold]2. Probando Búsqueda Simple[/bold]")
    test_queries = [
        "Malaspina",
        "Kosten",
        "Vientos del Secano",
        "parques solares",
        "PT8"
    ]
    
    for query in test_queries:
        try:
            # Búsqueda directa en vector store
            results = rag.vector_store.collection.query(
                query_texts=[query],
                n_results=5
            )
            
            num_results = len(results['documents'][0]) if results['documents'] else 0
            console.print(f"  Query: '{query}' → {num_results} resultados")
            
            if num_results > 0:
                # Mostrar primer resultado
                first_doc = results['documents'][0][0][:100]
                first_source = results['metadatas'][0][0].get('source', 'Unknown')
                console.print(f"    [dim]Fuente: {first_source}[/dim]")
                console.print(f"    [dim]Texto: {first_doc}...[/dim]")
        except Exception as e:
            console.print(f"  [red]✗ Error en '{query}': {e}[/red]")
    
    # 3. Probar query completa
    console.print("\n[bold]3. Probando Query Completa[/bold]")
    test_full_queries = [
        ("Potencia de Malaspina", ["50", "mw", "malaspina"]),
        ("Donde esta Kosten", ["kosten", "chubut"]),
        ("Que parques solares opera el CROM", ["solar", "fotovoltaica"])
    ]
    
    for query, expected_keywords in test_full_queries:
        console.print(f"\n  Query: '{query}'")
        try:
            response = rag.query(query, length_mode='long', no_context=False)
            answer = response.get("answer", "")
            sources = response.get("sources", [])
            
            console.print(f"    Respuesta: {len(answer)} chars")
            console.print(f"    Fuentes: {len(sources)}")
            
            if len(sources) == 0:
                console.print(f"    [red]✗ Sin fuentes recuperadas[/red]")
            else:
                console.print(f"    [green]✓ Fuentes: {', '.join(sources[:3])}[/green]")
            
            # Verificar keywords
            answer_lower = answer.lower()
            missing = [kw for kw in expected_keywords if kw not in answer_lower]
            
            if missing:
                console.print(f"    [yellow]⚠ Faltan keywords: {', '.join(missing)}[/yellow]")
            else:
                console.print(f"    [green]✓ Todas las keywords presentes[/green]")
            
            # Mostrar inicio de respuesta
            console.print(f"    [dim]Respuesta: {answer[:150]}...[/dim]")
            
        except Exception as e:
            console.print(f"    [red]✗ Error: {e}[/red]")
    
    # 4. Verificar documentos específicos
    console.print("\n[bold]4. Verificando Documentos Específicos[/bold]")
    critical_docs = [
        "Anexo D - TotalEnergies.pdf",
        "Anexo D - GRENERGY.pdf",
        "Anexo D - ENVISION.pdf",
        "Anexo D - DQD.pdf",
        "PT8"
    ]
    
    all_docs = rag.vector_store.collection.get()
    all_sources = set(md.get('source', '') for md in all_docs['metadatas'])
    
    for doc in critical_docs:
        found = any(doc.lower() in src.lower() for src in all_sources)
        status = "✓" if found else "✗"
        color = "green" if found else "red"
        console.print(f"  [{color}]{status}[/{color}] {doc}")
    
    # 5. Verificar entidades
    console.print("\n[bold]5. Verificando Extracción de Entidades[/bold]")
    entity_queries = [
        "Malaspina",
        "Kosten",
        "Vientos del Secano",
        "La Perla del Chaco",
        "Loma Blanca I"
    ]
    
    for query in entity_queries:
        try:
            entities = rag._extract_entities(query)
            if entities:
                console.print(f"  '{query}' → {entities}")
            else:
                console.print(f"  [yellow]'{query}' → Sin entidades detectadas[/yellow]")
        except Exception as e:
            console.print(f"  [red]'{query}' → Error: {e}[/red]")
    
    console.print("\n[bold green]Diagnóstico completado[/bold green]\n")

if __name__ == "__main__":
    diagnose()
