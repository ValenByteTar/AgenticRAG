"""
Cargador centralizado de configuración
Evita duplicación de código de carga de config.yaml en múltiples archivos
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional

_config_cache: Optional[Dict[str, Any]] = None


def load_config(config_path: str = 'config.yaml') -> Dict[str, Any]:
    """
    Carga configuración desde archivo YAML
    
    Args:
        config_path: Ruta al archivo de configuración
        
    Returns:
        Diccionario con la configuración
        
    Raises:
        FileNotFoundError: Si el archivo no existe
        yaml.YAMLError: Si hay error al parsear el YAML
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Archivo de configuración no encontrado: {config_path}")
    
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_config(config_path: str = 'config.yaml', use_cache: bool = True) -> Dict[str, Any]:
    """
    Obtiene configuración con caché opcional
    
    Args:
        config_path: Ruta al archivo de configuración
        use_cache: Si True, usa caché en memoria (más rápido)
        
    Returns:
        Diccionario con la configuración
    """
    global _config_cache
    
    if use_cache and _config_cache is not None:
        return _config_cache
    
    config = load_config(config_path)
    
    if use_cache:
        _config_cache = config
    
    return config


def clear_config_cache():
    """Limpia el caché de configuración"""
    global _config_cache
    _config_cache = None
