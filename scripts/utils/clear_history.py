"""
Script para limpiar el historial de chats
Útil antes de ejecutar tests para evitar contaminación
"""

import json
from pathlib import Path

try:
    from rich.console import Console
    console = Console()
except:
    import re
    class Console:
        def print(self, msg):
            # Remover tags de rich y caracteres unicode problemáticos
            clean_msg = re.sub(r'\[.*?\]', '', str(msg))
            clean_msg = clean_msg.encode('ascii', 'ignore').decode('ascii')
            print(clean_msg)
    console = Console()

def clear_web_history():
    """Limpia el historial a través del API"""
    try:
        import requests
        response = requests.delete('http://localhost:5000/api/chats/clear')
        if response.status_code == 200:
            console.print("[green]OK: Historial web limpiado exitosamente[/green]")
            return True
        else:
            console.print(f"[red]ERROR: Error al limpiar historial web: {response.status_code}[/red]")
            return False
    except Exception as e:
        console.print(f"[yellow]ADVERTENCIA: No se pudo conectar al servidor web[/yellow]")
        return False

def clear_local_files():
    """Limpia archivos locales de chats"""
    chats_file = Path("data/chats.json")
    
    if chats_file.exists():
        try:
            with open(chats_file, 'w', encoding='utf-8') as f:
                json.dump([], f)
            console.print("[green]OK: Archivo local de chats limpiado[/green]")
            return True
        except Exception as e:
            console.print(f"[red]ERROR: Error al limpiar archivo local: {e}[/red]")
            return False
    else:
        console.print("[dim]Archivo de chats no existe (ya esta limpio)[/dim]")
        return True

def main():
    console.print("\n[bold cyan]=======================================[/bold cyan]")
    console.print("[bold cyan]  LIMPIEZA DE HISTORIAL DE CHATS  [/bold cyan]")
    console.print("[bold cyan]=======================================[/bold cyan]\n")
    
    # Intentar limpiar vía API
    web_cleared = clear_web_history()
    
    # Limpiar archivo local
    local_cleared = clear_local_files()
    
    if web_cleared or local_cleared:
        console.print("\n[bold green]OK: Historial limpiado correctamente[/bold green]")
        console.print("[dim]Puedes ejecutar los tests ahora con contexto limpio[/dim]\n")
    else:
        console.print("\n[bold red]ERROR: No se pudo limpiar el historial completamente[/bold red]\n")

if __name__ == "__main__":
    main()
