"""
Singleton de Rich Console
Evita crear múltiples instancias de Console en diferentes módulos
"""

from rich.console import Console
from typing import Optional

_console_instance: Optional[Console] = None


def get_console() -> Console:
    """
    Obtiene la instancia singleton de Rich Console
    
    Returns:
        Instancia compartida de Console
        
    Examples:
        >>> from src.utils import get_console
        >>> console = get_console()
        >>> console.print("[green]Hola mundo[/green]")
    """
    global _console_instance
    
    if _console_instance is None:
        _console_instance = Console()
    
    return _console_instance


def reset_console():
    """Resetea la instancia de console (útil para testing)"""
    global _console_instance
    _console_instance = None
