"""
Interfaz de Chat Interactiva para RAG Híbrido
Sistema de consultas sobre documentos de ciberseguridad

USO:
    python chat.py            → Abre la interfaz de consola
    python chat.py --console  → Abre la interfaz de consola

Nota: La ejecucion por interfaz web/Microsoft Edge fue desacoplada de este
modulo. Si se requiere la interfaz web, ejecutar 'python web_app.py' de forma
independiente.
"""

import sys
sys.path.append('src')
from rag_hybrid import HybridRAG
from utils import get_console

from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.table import Table
import time

console = get_console()


def print_welcome(num_docs=None):
    """Pantalla de bienvenida con información del sistema"""
    console.clear()

    docs_info = f"{num_docs:,} documentos indexados" if num_docs else "Cargando..."
    
    welcome_text = f"""
==============================================================
        ASISTENTE IA - SISTEMA DE CONOCIMIENTO
==============================================================
 
Base de conocimiento:
   - {docs_info}
   - Búsqueda semántica + keyword + re-ranking

Capacidades:
   • Responder preguntas técnicas
   • Buscar información específica
   • Citar fuentes y páginas
   • Generar resúmenes

Ejemplos de consultas:
   • "¿Qué es MITRE ATT&CK y para qué sirve?"
   • "Dame información sobre CISSP"
   • "¿Qué dice sobre pentesting?"
   • "¿Qué es ISO 27001?"

COMANDOS:
   /ayuda       - Mostrar ayuda
   /detalles    - Toggle detalles de búsqueda
   /fuentes     - Toggle mostrar fuentes
   /config      - Configurar búsqueda
   /limpiar     - Limpiar pantalla
   /contexto    - Limpiar contexto conversacional
   /salir       - Salir del chat

"""
    console.print(welcome_text, style="bold cyan")
    console.print("[dim]Presiona ENTER para comenzar...[/dim]")
    try:
        input()
    except (EOFError, OSError):
        # Si no hay stdin disponible (ej: ejecutado desde bat sin consola interactiva), continuar
        import time
        time.sleep(1)

def show_help():
    """Mostrar ayuda"""
    help_text = """
[bold cyan]GUIA DE USO[/bold cyan]

[bold green]MEJORAS ACTIVAS:[/bold green]
  • Re-ranking: Ordena resultados por relevancia real (+25% precisión)
  • LLM Qwen 3: Mejor comprensión de listas y contexto largo
  • Temperatura optimizada: Respuestas más determinísticas y precisas
  • Contexto ampliado: 800 chars (tablas completas sin cortar)
  • Modo corto optimizado: fast-path por snippets cercanos a keywords y conteos determinísticos
  • Anti-tablas por defecto: sólo se permiten tablas si pides "lista", "listado", "tabla" o "tablilla"
  • Celdas: extracción determinística por entidad, con anclaje y citas por línea
  • Pista explícita de páginas: prioriza páginas indicadas en la consulta (ej. "página 3 y 4")
  • Auditor visible: el veredicto del auditor se muestra completo en consola

[bold yellow]Hacer Preguntas:[/bold yellow]
Simplemente escribe tu pregunta y presiona ENTER.
Ejemplos:
  • "¿Qué certificaciones de ciberseguridad existen?"
  • "¿Qué es un SOC y cómo opera?"
  • "Información sobre frameworks de seguridad"
  • "¿Qué es el GDPR y qué implica?"

[bold yellow]Comandos Disponibles:[/bold yellow]
  /ayuda       - Mostrar esta ayuda
  /detalles    - Activar/desactivar detalles de búsqueda (incluye re-rank scores)
  /fuentes     - Activar/desactivar lista de fuentes
  /config      - Ajustar parámetros de búsqueda
  /limpiar     - Limpiar pantalla
  /contexto    - Limpiar historial de conversación
  /salir       - Salir del chat

[bold yellow]Configuración de Búsqueda:[/bold yellow]
  • Balance semántica/keyword (30-70% por defecto)
  • Número de resultados (20 por defecto)
  • Re-ranking automático (siempre activo)
  • Estos se pueden ajustar con /config

[bold yellow]Tips:[/bold yellow]
  • Sé específico en tus preguntas
  • Usa nombres propios (ej: "CISSP", "MITRE ATT&CK")
  • El sistema cita las fuentes automáticamente. En modo corto se exige al menos una cita.
  • Listas/tablas sólo si dices explícitamente: "lista", "listado", "tabla" o "tablilla".
  • Celdas: extracción determinística por entidad con citas por línea.
  • Puedes guiar al sistema a páginas específicas: ej. "en la página 3 y 4 del documento".
"""
    console.print(Panel(help_text, border_style="cyan"))


def show_config(current_settings):
    """Mostrar configuración actual"""
    table = Table(title="Configuracion Actual", show_header=True)
    table.add_column("Parámetro", style="cyan")
    table.add_column("Valor", style="yellow")
    table.add_column("Descripción", style="dim")
    
    table.add_row(
        "Búsqueda Semántica",
        f"{current_settings['semantic_weight']*100:.0f}%",
        "Basada en significado"
    )
    table.add_row(
        "Búsqueda Keyword",
        f"{(1-current_settings['semantic_weight'])*100:.0f}%",
        "Basada en palabras exactas"
    )
    table.add_row(
        "Resultados",
        str(current_settings['top_k']),
        "Fragmentos a recuperar"
    )
    table.add_row(
        "Mostrar Detalles",
        "Sí" if current_settings['show_details'] else "No",
        "Scores y fragmentos"
    )
    table.add_row(
        "Mostrar Fuentes",
        "Sí" if current_settings['show_sources'] else "No",
        "Lista de documentos"
    )
    
    console.print(table)


def configure_search():
    """Configurar parámetros de búsqueda"""
    console.print("\n[bold cyan]CONFIGURACION DE BUSQUEDA[/bold cyan]\n")
    
    console.print("[yellow]Balance Semántica/Keyword:[/yellow]")
    console.print("  30% = Más peso a keywords (mejor para nombres propios)")
    console.print("  50% = Balanceado")
    console.print("  70% = Más peso semántico (mejor para conceptos)")
    
    semantic = Prompt.ask(
        "\nPorcentaje semántico",
        default="30",
        choices=["20", "30", "40", "50", "60", "70", "80"]
    )
    
    top_k = Prompt.ask(
        "Número de resultados a recuperar",
        default="20"
    )
    
    return {
        'semantic_weight': int(semantic) / 100,
        'top_k': int(top_k)
    }


def display_result_chat(result, settings, already_streamed=False):
    """Mostrar resultado en formato chat"""
    
    # Respuesta del asistente
    if result['answer']:
        if not already_streamed:
            console.print("\n[bold green]Asistente:[/bold green]\n")
            console.print(result['answer'])
        else:
            # Añadir un salto de línea al final de la respuesta que ya se transmitió
            console.print()
    else:
        console.print("\n[bold yellow]ADVERTENCIA: No se pudo generar respuesta[/bold yellow]")
    
    # Fuentes consultadas
    if settings['show_sources'] and result['results']:
        console.print(f"\n[bold blue]Fuentes consultadas:[/bold blue]")
        
        sources_shown = set()
        for r in result['results'][:5]:
            source_key = f"{r['metadata']['source']}_{r['metadata']['page']}"
            if source_key not in sources_shown:
                source = r['metadata']['source'][:50]
                page = r['metadata']['page']
                # Usar final_score si está disponible (con re-ranking), sino hybrid_score
                score = r.get('final_score', r.get('hybrid_score', 0))
                console.print(f"  • {source}... (pág. {page}) - Score: {score:.2f}")
                sources_shown.add(source_key)
    
    # Detalles de búsqueda
    if settings['show_details'] and result['results']:
        console.print(f"\n[bold yellow]Detalles de Busqueda:[/bold yellow]")
        
        for i, r in enumerate(result['results'][:3], 1):
            console.print(f"\n[bold]Resultado {i}:[/bold]")
            
            # Mostrar scores (incluir re-rank si está disponible)
            scores_text = f"  Híbrido: {r['hybrid_score']:.3f} | Semántico: {r['semantic_score']:.3f} | Keyword: {r['keyword_score']:.3f}"
            
            if 'rerank_score' in r:
                scores_text += f" | Re-rank: {r['rerank_score']:.3f}"
            
            if 'final_score' in r:
                scores_text += f"\n  [bold cyan]Final: {r['final_score']:.3f}[/bold cyan]"
            
            console.print(scores_text)
            console.print(f"  [dim]{r['text'][:150]}...[/dim]")


def chat_interface():
    """Interfaz principal de chat"""
    
    # Mostrar welcome inicial (sin números)
    print_welcome()
    
    console.clear()
    console.print("[bold cyan]Iniciando sistema...[/bold cyan]\n")
    
    # Inicializar RAG (forzar variante BGE y heurísticas balanceadas)
    rag = HybridRAG(variant="bge", heuristics="balanced")
    
    # Obtener número real de documentos
    num_docs = len(rag.all_docs)
    
    # Configuración por defecto (optimizada para BGE)
    settings = {
        'semantic_weight': 0.5,  # balance 50/50
        'top_k': 10,
        'show_details': False,
        'show_sources': True
    }
    
    console.clear()
    console.print(Panel.fit(
        f"[bold green]SISTEMA RAG HÍBRIDO[/bold green]\n"
        f"Búsqueda Semántica + Keyword + Re-ranking + Qwen3\n\n"
        f"Base de Conocimiento:\n"
        f"  • {num_docs:,} documentos indexados\n\n"
        f"MEJORAS ACTIVAS:\n"
        f"  • Re-ranking con CrossEncoder (precisión +25%)\n"
        f"  • LLM Qwen3 (mejor comprensión de listas)\n"
        f"  • Temperatura optimizada (respuestas determinísticas)\n\n"
        f"Comandos principales:\n"
        f"  • Escribe tu pregunta para consultar\n"
        f"  • /ayuda - Ver todos los comandos\n"
        f"  • /salir - Terminar",
        
        border_style="green"
    ))
    
    # Loop principal
    try:
        while True:
            try:
                # Prompt para el usuario
                console.print()
                user_input = Prompt.ask("[bold cyan]Tú[/bold cyan]").strip()
                
                if not user_input:
                    continue
                
                # Comandos
                if user_input.startswith('/'):
                    command = user_input.lower()
                    
                    if command == '/salir' or command == '/exit':
                        console.print("\n[bold cyan]Hasta luego![/bold cyan]")
                        break
                    
                    elif command == '/ayuda' or command == '/help':
                        show_help()
                    
                    elif command == '/detalles':
                        settings['show_details'] = not settings['show_details']
                        status = "activados" if settings['show_details'] else "desactivados"
                        console.print(f"[yellow]Detalles de búsqueda {status}[/yellow]")
                    
                    elif command == '/fuentes':
                        settings['show_sources'] = not settings['show_sources']
                        status = "activadas" if settings['show_sources'] else "desactivadas"
                        console.print(f"[yellow]Fuentes {status}[/yellow]")
                    
                    elif command == '/config':
                        show_config(settings)
                        if Prompt.ask("\n¿Modificar configuración?", choices=["s", "n"], default="n") == "s":
                            new_config = configure_search()
                            settings.update(new_config)
                            console.print("[green]OK: Configuración actualizada[/green]")
                    
                    elif command == '/limpiar' or command == '/clear':
                        console_interface_line = "-" * 80
                        console.print(console_interface_line)
                        console.print("[green]OK: Pantalla limpiada[/green]")
                    
                    elif command == '/contexto':
                        rag.conversation.clear()
                        console.print("[green]OK: Contexto conversacional limpiado[/green]")
                        console.print("[dim]El asistente no recordará la conversación anterior[/dim]")
                    
                    else:
                        console.print(f"[red]Comando desconocido: {user_input}[/red]")
                        console.print("[dim]Usa /ayuda para ver comandos disponibles[/dim]")
                    
                    continue
                
                # Procesar consulta
                console.print("\n[dim]Buscando...[/dim]")
                
                start_time = time.time()
                
                has_printed_header = [False]
                def token_cb(chunk: str):
                    if not has_printed_header[0]:
                        console.print("\n[bold green]Asistente:[/bold green]\n", end='', flush=True)
                        has_printed_header[0] = True
                    sys.stdout.write(chunk)
                    sys.stdout.flush()
                
                result = rag.query(
                    user_input,
                    top_k=settings['top_k'],
                    semantic_weight=settings['semantic_weight'],
                    entity_filter=True,  # Filtro de entidades activado
                    two_stage=True,      # Búsqueda en dos etapas para mayor precisión
                    stream=True,
                    token_callback=token_cb
                )
                
                elapsed = time.time() - start_time
                
                # Mostrar resultado
                display_result_chat(result, settings, already_streamed=has_printed_header[0])
                
                console.print(f"\n[dim]Tiempo de respuesta: {elapsed:.2f}s[/dim]")
                console.print("─" * 80)
                
            except KeyboardInterrupt:
                console.print("\n\n[bold cyan]Hasta luego![/bold cyan]")
                break
            
            except Exception as e:
                console.print(f"\n[bold red]ERROR: {e}[/bold red]")
                console.print("[dim]Puedes continuar con otra pregunta[/dim]")
    
    finally:
        # Siempre detener Ollama al salir
        console.print("\n[dim]Limpiando recursos...[/dim]")
        rag.cleanup()
        console.print("[dim]Sistema cerrado correctamente[/dim]")



if __name__ == "__main__":
    # Ejecucion exclusiva por consola. La interfaz web/Edge fue desacoplada
    # de este modulo; para usarla, ejecutar 'python web_app.py' por separado.
    if len(sys.argv) > 1 and sys.argv[1] == '--web':
        console.print(
            "\n[bold yellow]La interfaz web fue desacoplada de chat.py.[/bold yellow]"
        )
        console.print(
            "[dim]Para iniciar la interfaz web, ejecuta: python web_app.py[/dim]"
        )
        sys.exit(2)

    try:
        chat_interface()
    except Exception as e:
        console.print(f"\n[bold red]ERROR FATAL: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)
