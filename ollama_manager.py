"""
Gestión del ciclo de vida del proceso Ollama: inicio, verificación, precarga y limpieza.
"""
import sys
import subprocess
import time

import requests
from rich.console import Console

console = Console()


class OllamaManager:
    """Gestiona el ciclo de vida del proceso Ollama local."""

    def __init__(self, model: str, ollama_url: str = "http://localhost:11434"):
        self.model = model
        self.ollama_url = ollama_url.rstrip("/")
        self.process: "subprocess.Popen | None" = None
        self.num_gpu_tuned: int = 99

    # ------------------------------------------------------------------
    # Verificación y arranque
    # ------------------------------------------------------------------

    def check(self) -> bool:
        """Verifica Ollama y lo inicia automáticamente si no está activo."""
        try:
            console.print("[dim]Verificando disponibilidad de Ollama...[/dim]")
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=2)
            if response.status_code == 200:
                models_data = response.json()
                available = [m['name'] for m in models_data.get('models', [])]
                if any(self.model in m for m in available):
                    console.print(f"[green]OK: Ollama activo con modelo {self.model}[/green]")
                    return True
                else:
                    console.print(f"[yellow]ADVERTENCIA: Ollama activo pero modelo {self.model} no encontrado[/yellow]")
                    if available:
                        console.print(f"[dim]   Modelos disponibles: {', '.join(available[:3])}[/dim]")
                    return False
            else:
                console.print(f"[yellow]ADVERTENCIA: Ollama respondio con codigo {response.status_code}[/yellow]")
                return False
        except requests.exceptions.ConnectionError:
            console.print("[yellow]ADVERTENCIA: Ollama no esta activo - iniciando automaticamente...[/yellow]")
            return self.start()
        except requests.exceptions.Timeout:
            console.print("[yellow]ADVERTENCIA: Ollama no responde (timeout 2s)[/yellow]")
            return False
        except Exception as e:
            console.print(f"[yellow]ADVERTENCIA: Error verificando Ollama: {str(e)[:50]}[/yellow]")
            return False

    def start(self) -> bool:
        """Inicia Ollama en background y espera a que esté disponible."""
        try:
            console.print("[dim]Iniciando Ollama serve...[/dim]")
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                self.process = subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    startupinfo=startupinfo,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                self.process = subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            console.print("[dim]Esperando que Ollama esté listo...[/dim]")
            for i in range(15):
                time.sleep(1)
                try:
                    response = requests.get(f"{self.ollama_url}/api/tags", timeout=1)
                    if response.status_code == 200:
                        available = [m['name'] for m in response.json().get('models', [])]
                        if any(self.model in m for m in available):
                            console.print(f"[green]OK: Ollama iniciado correctamente con modelo {self.model}[/green]")
                            return True
                        else:
                            console.print(f"[yellow]ADVERTENCIA: Ollama iniciado pero modelo {self.model} no encontrado[/yellow]")
                            if available:
                                console.print(f"[dim]   Modelos disponibles: {', '.join(available[:3])}[/dim]")
                            return False
                except Exception:
                    console.print(f"[dim]   Esperando... ({i+1}/15s)[/dim]", end='\r')
                    continue
            console.print("[yellow]\nADVERTENCIA: Timeout esperando a Ollama (15s)[/yellow]")
            return False
        except FileNotFoundError:
            console.print("[red]ERROR: Ollama no esta instalado en el sistema[/red]")
            console.print("[dim]   Instala desde: https://ollama.ai[/dim]")
            return False
        except Exception as e:
            console.print(f"[red]ERROR: Error iniciando Ollama: {str(e)[:80]}[/red]")
            return False

    def cleanup(self):
        """Detiene Ollama si fue iniciado por este gestor."""
        if not self.process:
            return
        console.print("\n[dim]Deteniendo Ollama...[/dim]")
        try:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
                console.print("[green]OK: Ollama detenido correctamente[/green]")
                return
            except subprocess.TimeoutExpired:
                console.print("[dim]   Proceso no respondió, buscando procesos de Ollama...[/dim]")
                self.process.kill()
            if sys.platform == 'win32':
                try:
                    subprocess.run(['taskkill', '/F', '/IM', 'ollama.exe'], capture_output=True, timeout=3)
                    subprocess.run(['taskkill', '/F', '/IM', 'ollama_llama_server.exe'], capture_output=True, timeout=3)
                    console.print("[green]OK: Ollama detenido (taskkill)[/green]")
                except Exception as e:
                    console.print(f"[yellow]ADVERTENCIA: Error con taskkill: {e}[/yellow]")
            else:
                try:
                    subprocess.run(['pkill', '-f', 'ollama'], capture_output=True, timeout=3)
                    console.print("[green]OK: Ollama detenido (pkill)[/green]")
                except Exception as e:
                    console.print(f"[yellow]ADVERTENCIA: Error con pkill: {e}[/yellow]")
        except Exception as e:
            console.print(f"[yellow]ADVERTENCIA: Error al detener Ollama: {e}[/yellow]")

    # ------------------------------------------------------------------
    # Precarga y tuning de GPU
    # ------------------------------------------------------------------

    def preload(self) -> bool:
        """Precarga el modelo en GPU con una consulta dummy."""
        try:
            start_time = time.time()
            payload = {
                "model": self.model,
                "prompt": "Test",
                "stream": False,
                "options": {
                    "num_predict": 1,
                    "temperature": 0.1,
                    "num_ctx": 2048,
                    "num_gpu": self.num_gpu_tuned,
                    "num_thread": 8,
                    "num_batch": 64
                },
                "keep_alive": "15m"
            }
            response = requests.post(f"{self.ollama_url}/api/generate", json=payload, timeout=120)
            elapsed = time.time() - start_time
            if response.status_code == 200:
                console.print(f"[dim]Modelo cargado en {elapsed:.1f}s[/dim]")
                return True
            else:
                console.print(f"[yellow]Error al precargar: HTTP {response.status_code}[/yellow]")
                return False
        except requests.exceptions.Timeout:
            console.print("[yellow]Timeout al precargar modelo (>120s)[/yellow]")
            return False
        except Exception as e:
            console.print(f"[yellow]Error al precargar: {str(e)[:100]}[/yellow]")
            return False

    def autotune_num_gpu(self) -> int:
        """Prueba valores de num_gpu para equilibrar VRAM limitada (RTX 4050 6GB)."""
        candidates = [99, 80, 60, 48, 32, 24, 16, 8]
        test_payload = {"model": self.model, "prompt": "ping", "stream": False}
        for val in candidates:
            try:
                test_payload["options"] = {"num_predict": 1, "num_ctx": 2048, "num_gpu": val}
                r = requests.post(f"{self.ollama_url}/api/generate", json=test_payload, timeout=15)
                if r.status_code == 200 and r.json().get("response") is not None:
                    self.num_gpu_tuned = val
                    return val
            except Exception:
                continue
        self.num_gpu_tuned = 8
        return 8
