"""
Healthcheck del Sistema
Verifica estado de componentes criticos: Ollama, ChromaDB, GPU, disco
"""

import sys
import requests
from pathlib import Path
import shutil

sys.path.append(str(Path(__file__).parent.parent / 'src'))

from rich.console import Console
from rich.table import Table

console = Console()


def check_ollama():
    """Verifica si Ollama esta activo"""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            models = response.json().get('models', [])
            model_names = [m['name'] for m in models]
            
            # Verificar si granite-3.3-8b-instruct-q5km:latest esta disponible
            granite_available = any('granite-3.3-8b-instruct-q5km:latest' in name for name in model_names)
            
            return {
                'status': 'OK',
                'models': len(models),
                'granite-3.3-8b-instruct-q5km:latest': granite_available,
                'message': f'{len(models)} modelos disponibles'
            }
        else:
            return {
                'status': 'ERROR',
                'message': f'HTTP {response.status_code}'
            }
    except requests.exceptions.ConnectionError:
        return {
            'status': 'ERROR',
            'message': 'Ollama no esta activo'
        }
    except Exception as e:
        return {
            'status': 'ERROR',
            'message': str(e)
        }


def check_chromadb():
    """Verifica si ChromaDB esta accesible"""
    try:
        chroma_path = Path("chroma_bge_m3")
        
        if not chroma_path.exists():
            return {
                'status': 'ERROR',
                'message': 'Directorio no encontrado'
            }
        
        # Verificar archivos criticos
        sqlite_files = list(chroma_path.rglob("*.sqlite3"))
        
        if not sqlite_files:
            return {
                'status': 'WARNING',
                'message': 'No se encontraron archivos .sqlite3'
            }
        
        # Calcular tamano
        total_size = sum(f.stat().st_size for f in chroma_path.rglob("*") if f.is_file())
        size_mb = total_size / 1024 / 1024
        
        return {
            'status': 'OK',
            'size_mb': round(size_mb, 1),
            'message': f'{size_mb:.1f} MB'
        }
        
    except Exception as e:
        return {
            'status': 'ERROR',
            'message': str(e)
        }


def check_gpu():
    """Verifica disponibilidad de GPU"""
    try:
        import torch
        
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            vram_total = torch.cuda.get_device_properties(0).total_memory / 1024**3
            vram_allocated = torch.cuda.memory_allocated(0) / 1024**3
            vram_free = vram_total - vram_allocated
            
            return {
                'status': 'OK',
                'name': gpu_name,
                'vram_total_gb': round(vram_total, 1),
                'vram_free_gb': round(vram_free, 1),
                'message': f'{gpu_name} ({vram_free:.1f}/{vram_total:.1f} GB libre)'
            }
        else:
            return {
                'status': 'WARNING',
                'message': 'CUDA no disponible (usando CPU)'
            }
    except ImportError:
        return {
            'status': 'WARNING',
            'message': 'PyTorch no instalado'
        }
    except Exception as e:
        return {
            'status': 'ERROR',
            'message': str(e)
        }


def check_disk_space():
    """Verifica espacio en disco"""
    try:
        disk_usage = shutil.disk_usage(".")
        
        total_gb = disk_usage.total / 1024**3
        free_gb = disk_usage.free / 1024**3
        used_gb = disk_usage.used / 1024**3
        percent_used = (used_gb / total_gb) * 100
        
        if free_gb < 10:
            status = 'ERROR'
        elif free_gb < 20:
            status = 'WARNING'
        else:
            status = 'OK'
        
        return {
            'status': status,
            'total_gb': round(total_gb, 1),
            'free_gb': round(free_gb, 1),
            'percent_used': round(percent_used, 1),
            'message': f'{free_gb:.1f} GB libres ({100-percent_used:.1f}% disponible)'
        }
        
    except Exception as e:
        return {
            'status': 'ERROR',
            'message': str(e)
        }


def check_pdfs():
    """Verifica directorio de PDFs"""
    try:
        pdf_path = Path("protocolosPDF")
        
        if not pdf_path.exists():
            return {
                'status': 'ERROR',
                'message': 'Directorio no encontrado'
            }
        
        pdf_files = list(pdf_path.rglob("*.pdf"))
        total_size = sum(f.stat().st_size for f in pdf_files)
        size_mb = total_size / 1024 / 1024
        
        return {
            'status': 'OK',
            'count': len(pdf_files),
            'size_mb': round(size_mb, 1),
            'message': f'{len(pdf_files)} PDFs ({size_mb:.1f} MB)'
        }
        
    except Exception as e:
        return {
            'status': 'ERROR',
            'message': str(e)
        }


def run_healthcheck(verbose=False):
    """
    Ejecuta healthcheck completo
    
    Returns:
        True si todo esta OK, False si hay errores criticos
    """
    console.print("\n[bold cyan]HEALTHCHECK DEL SISTEMA[/bold cyan]\n")
    
    checks = {
        'Ollama': check_ollama(),
        'ChromaDB': check_chromadb(),
        'GPU': check_gpu(),
        'Disco': check_disk_space(),
        'PDFs': check_pdfs()
    }
    
    # Crear tabla
    table = Table(show_header=True, header_style="bold")
    table.add_column("Componente", style="cyan")
    table.add_column("Estado", justify="center")
    table.add_column("Detalles")
    
    has_errors = False
    has_warnings = False
    
    for component, result in checks.items():
        status = result['status']
        message = result.get('message', '')
        
        if status == 'OK':
            status_str = "[green]OK[/green]"
        elif status == 'WARNING':
            status_str = "[yellow]WARNING[/yellow]"
            has_warnings = True
        else:
            status_str = "[red]ERROR[/red]"
            has_errors = True
        
        table.add_row(component, status_str, message)
        
        # Detalles adicionales en modo verbose
        if verbose:
            for key, value in result.items():
                if key not in ['status', 'message']:
                    console.print(f"  [dim]{key}: {value}[/dim]")
    
    console.print(table)
    console.print()
    
    # Resumen
    if has_errors:
        console.print("[bold red]ESTADO: CRITICO - Hay errores que requieren atencion[/bold red]")
        return False
    elif has_warnings:
        console.print("[bold yellow]ESTADO: ADVERTENCIA - Revisar componentes marcados[/bold yellow]")
        return True
    else:
        console.print("[bold green]ESTADO: OK - Todos los componentes funcionando correctamente[/bold green]")
        return True


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Healthcheck del sistema RAG CROM")
    parser.add_argument("-v", "--verbose", action="store_true", help="Mostrar detalles adicionales")
    
    args = parser.parse_args()
    
    try:
        success = run_healthcheck(verbose=args.verbose)
        sys.exit(0 if success else 1)
    except Exception as e:
        console.print(f"[bold red]ERROR FATAL: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)
