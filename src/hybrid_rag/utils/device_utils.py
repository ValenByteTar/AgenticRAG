"""
Utilidades para manejo de dispositivos (CPU/CUDA)
Centraliza la lógica de detección y fallback de dispositivos
"""

from typing import Literal

DeviceType = Literal['cpu', 'cuda', 'mps']


def get_available_device(preferred_device: str = 'cuda', verbose: bool = True) -> str:
    """
    Detecta y retorna el dispositivo disponible con fallback automático
    
    Args:
        preferred_device: Dispositivo preferido ('cuda', 'cpu', 'mps')
        verbose: Si True, imprime advertencias
        
    Returns:
        Dispositivo disponible ('cuda', 'cpu', o 'mps')
        
    Examples:
        >>> device = get_available_device('cuda')
        >>> # Si CUDA no disponible, retorna 'cpu' automáticamente
    """
    try:
        import torch
        
        # Verificar CUDA
        if preferred_device == 'cuda':
            if torch.cuda.is_available():
                return 'cuda'
            else:
                if verbose:
                    print("ADVERTENCIA: CUDA no disponible, usando CPU")
                return 'cpu'
        
        # Verificar MPS (Apple Silicon)
        elif preferred_device == 'mps':
            if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                return 'mps'
            else:
                if verbose:
                    print("ADVERTENCIA: MPS no disponible, usando CPU")
                return 'cpu'
        
        # CPU siempre disponible
        else:
            return 'cpu'
            
    except ImportError:
        if verbose:
            print("ADVERTENCIA: PyTorch no instalado, usando CPU por defecto")
        return 'cpu'


def get_device_info(device: str = 'cuda') -> dict:
    """
    Obtiene información detallada del dispositivo
    
    Args:
        device: Dispositivo a consultar
        
    Returns:
        Diccionario con información del dispositivo
    """
    info = {
        'device': device,
        'available': False,
        'name': None,
        'memory_total': None,
        'memory_allocated': None
    }
    
    try:
        import torch
        
        if device == 'cuda' and torch.cuda.is_available():
            info['available'] = True
            info['name'] = torch.cuda.get_device_name(0)
            info['memory_total'] = torch.cuda.get_device_properties(0).total_memory / 1e9
            info['memory_allocated'] = torch.cuda.memory_allocated(0) / 1e9
        elif device == 'cpu':
            info['available'] = True
            info['name'] = 'CPU'
        elif device == 'mps' and hasattr(torch.backends, 'mps'):
            if torch.backends.mps.is_available():
                info['available'] = True
                info['name'] = 'Apple MPS'
                
    except Exception:
        pass
    
    return info
