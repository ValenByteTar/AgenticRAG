"""
Script para limpiar y reconstruir ambas bases de datos ChromaDB
con textos normalizados (sin acentos)
"""
import shutil
from pathlib import Path
from rich.console import Console
from rich.prompt import Confirm
from rich.panel import Panel

console = Console()

def main():
    console.print("\n" + "="*80)
    console.print("[bold red]LIMPIEZA Y RECONSTRUCCION DE BASES DE DATOS[/bold red]")
    console.print("\nEste proceso:")
    console.print("1. Eliminara las bases de datos existentes (chroma_bge_m3 y vectordb)")
    console.print("2. Re-extraera texto de PDFs (ahora SIN acentos)")
    console.print("3. Reconstruira ambas bases de datos con texto normalizado")
    console.print("\n[yellow]ADVERTENCIA: Esto tomara ~10-15 minutos[/yellow]")
    console.print("="*80 + "\n")
    
    # Ejecutar directamente (usuario ya confirmo al ejecutar el script)
    console.print("[green]Iniciando proceso...[/green]\n")
    
    # Rutas de las bases de datos
    db_paths = [
        Path("chroma_bge_m3"),
        Path("vectordb"),
        Path("data/extracted_texts")  # También limpiar textos extraídos
    ]
    
    # PASO 1: Eliminar bases de datos existentes
    console.print("\n[bold yellow]PASO 1/3: Limpiando bases de datos existentes...[/bold yellow]")
    for db_path in db_paths:
        if db_path.exists():
            console.print(f"  • Eliminando {db_path}...")
            try:
                shutil.rmtree(db_path)
                console.print(f"    [green]OK - Eliminado[/green]")
            except Exception as e:
                console.print(f"    [red]ERROR: {e}[/red]")
        else:
            console.print(f"  • {db_path} no existe (omitiendo)")
    
    # PASO 2: Re-extraer textos de PDFs (ahora con normalización)
    console.print("\n[bold yellow]PASO 2/3: Re-extrayendo textos de PDFs (sin acentos)...[/bold yellow]")
    try:
        from src.pdf_extractor import PDFExtractor
        extractor = PDFExtractor("protocolosPDF")
        results = extractor.extract_all_pdfs()
        successful = sum(1 for r in results if r['success'])
        console.print(f"[green]OK - Extraidos {successful}/{len(results)} PDFs[/green]")
    except Exception as e:
        console.print(f"[red]ERROR en extraccion: {e}[/red]")
        return
    
    # PASO 3: Reconstruir bases de datos
    console.print("\n[bold yellow]PASO 3/3: Reconstruyendo bases de datos...[/bold yellow]")
    console.print("[dim]Esto tomará varios minutos...[/dim]\n")
    
    try:
        from build_rag_system import build_rag_database
        
        # Reconstruir BGE-M3 (principal)
        console.print("[cyan]Reconstruyendo chroma_bge_m3...[/cyan]")
        build_rag_database(config_path='config.yaml', variant_override='bge', rebuild_override=True)
        console.print("[green]OK - chroma_bge_m3 reconstruida[/green]\n")
        
        # Reconstruir legacy (backup)
        console.print("[cyan]Reconstruyendo vectordb (legacy)...[/cyan]")
        build_rag_database(config_path='config.yaml', variant_override='legacy', rebuild_override=True)
        console.print("[green]OK - vectordb reconstruida[/green]")
        
    except Exception as e:
        console.print(f"[red]ERROR en reconstruccion: {e}[/red]")
        import traceback
        traceback.print_exc()
        return
    
    # Resumen final
    console.print("\n" + "="*80)
    console.print("[bold green]RECONSTRUCCION COMPLETADA[/bold green]")
    console.print("\nCambios aplicados:")
    console.print("- Textos extraidos SIN acentos (Numero -> Numero)")
    console.print("- Bases de datos reconstruidas con texto normalizado")
    console.print("- El LLM corregira automaticamente la ortografia en las respuestas")
    console.print("\n[cyan]Proximo paso: Reinicia el servidor web (python chat.py --web)[/cyan]")
    console.print("="*80)

if __name__ == "__main__":
    main()
