"""
Utilidades compartidas del sistema RAG
Centraliza funciones comunes para evitar duplicación
"""

from .config_loader import load_config, get_config
from .device_utils import get_available_device
from .console import get_console

__all__ = [
    'load_config',
    'get_config',
    'get_available_device',
    'get_console'
]
