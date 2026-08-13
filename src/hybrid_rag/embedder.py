"""
Módulo o₂: Generación de embeddings vectoriales
Objetivo: Convertir chunks de texto a vectores densos para búsqueda semántica
Entradas: Lista de chunks con texto
Salidas: Embeddings vectoriales (numpy arrays)
Restricciones: Soporte para sentence-transformers y Ollama
"""

import numpy as np
from typing import List, Dict
from rich.console import Console
from rich.progress import track
import yaml
import requests
import hashlib
from functools import lru_cache

console = Console()


class EmbeddingGenerator:
    """Genera embeddings usando sentence-transformers o Ollama"""
    
    def __init__(self, model_name: str = "nomic-embed-text", device: str = "cpu", provider: str = "ollama", use_cache: bool = True):
        """
        Args:
            model_name: Nombre del modelo (nomic-embed-text para Ollama, o hiiamsid/... para sentence-transformers)
            device: 'cuda' o 'cpu' (solo para sentence-transformers)
            provider: 'ollama' o 'sentence-transformers'
            use_cache: Si True, usa caché LRU para embeddings (recomendado para sesiones largas)
        """
        self.provider = provider
        self.model_name = model_name
        self.device = device
        self.use_cache = use_cache
        
        # Estadísticas de caché
        self._cache_hits = 0
        self._cache_misses = 0
        
        console.print(f"\n[bold cyan]Cargando modelo de embeddings: {model_name} ({provider})...[/bold cyan]")
        
        if provider == "ollama":
            # Verificar que Ollama esté corriendo
            try:
                response = requests.get("http://localhost:11434/api/tags", timeout=5)
                if response.status_code == 200:
                    models = response.json().get('models', [])
                    model_names = [m['name'] for m in models]
                    if not any(model_name in name for name in model_names):
                        raise ValueError(f"Modelo {model_name} no encontrado en Ollama. Modelos disponibles: {model_names}")
                    console.print(f"[bold green]OK: Ollama activo con {model_name}[/bold green]")
                    self.ollama_url = "http://localhost:11434/api/embeddings"
                    self.embedding_dim = 768  # nomic-embed-text dimension
                else:
                    raise ConnectionError("Ollama no responde correctamente")
            except Exception as e:
                console.print(f"[bold red]ERROR conectando con Ollama: {e}[/bold red]")
                raise
        else:
            import os
            import warnings
            os.environ['HF_HUB_OFFLINE'] = '1'
            os.environ['TRANSFORMERS_OFFLINE'] = '1'
            os.environ['HF_DATASETS_OFFLINE'] = '1'
            os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
            # Reducir fragmentacion de memoria CUDA (clave en GPUs de baja VRAM)
            os.environ.setdefault('PYTORCH_CUDA_ALLOC_CONF', 'expandable_segments:True')
            warnings.filterwarnings('ignore', category=FutureWarning, module='huggingface_hub')
            try:
                from sentence_transformers import SentenceTransformer
                self.model = SentenceTransformer(model_name, device=device)
                # Acotar longitud de secuencia: BGE-m3 trae max_seq_length=8192 por
                # defecto, lo que dispara la memoria de atencion (O(seq^2)) y causa
                # OOM en GPUs pequenas. Los chunks rondan <=400 tokens, por lo que
                # 512 es suficiente y limita el consumo de VRAM.
                try:
                    if device == "cuda" and getattr(self.model, 'max_seq_length', 0) and self.model.max_seq_length > 512:
                        self.model.max_seq_length = 512
                        console.print("[dim]max_seq_length acotado a 512 (control de VRAM)[/dim]")
                except Exception:
                    pass
                console.print(f"[bold green]OK: Modelo cargado en {device} (modo offline)[/bold green]")
                try:
                    self.embedding_dim = int(self.model.get_sentence_embedding_dimension())
                except Exception:
                    self.embedding_dim = 1024
            except Exception as e:
                console.print(f"[bold yellow]FALLBACK OFFLINE:[/bold yellow] {e}")
                try:
                    response = requests.get("http://localhost:11434/api/tags", timeout=5)
                    if response.status_code == 200:
                        models = response.json().get('models', [])
                        names = [m['name'] for m in models]
                        fallback_model = 'nomic-embed-text'
                        if not any(fallback_model in n for n in names):
                            raise ValueError("Modelo nomic-embed-text no disponible en Ollama")
                        self.provider = 'ollama'
                        self.model_name = fallback_model
                        self.ollama_url = "http://localhost:11434/api/embeddings"
                        self.embedding_dim = 768
                        console.print(f"[bold green]OK: Fallback a Ollama embeddings ({fallback_model})[/bold green]")
                    else:
                        raise ConnectionError("Ollama no responde correctamente para fallback")
                except Exception as e2:
                    console.print(f"[bold red]ERROR: No se pudo cargar embeddings offline ni fallback Ollama: {e2}[/bold red]")
                    raise
        
        # Inicializar caché si está habilitado
        if self.use_cache:
            console.print(f"[dim]Caché de embeddings habilitado (LRU maxsize=1000)[/dim]")
    
    def _normalize_text_for_cache(self, text: str) -> str:
        """Normaliza texto para caché (lowercase, sin espacios extra)"""
        return ' '.join(text.lower().strip().split())
    
    def _compute_text_hash(self, text: str) -> str:
        """Computa hash MD5 del texto normalizado"""
        normalized = self._normalize_text_for_cache(text)
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()
    
    @lru_cache(maxsize=1000)
    def _generate_embedding_cached(self, text_hash: str, text: str) -> tuple:
        """Genera embedding con caché LRU (retorna tuple para ser hasheable)"""
        embedding = self._generate_embedding_uncached(text)
        return tuple(embedding.tolist())
    
    def _generate_embedding_uncached(self, text: str) -> np.ndarray:
        """Genera embedding sin caché (método interno)"""
        if self.provider == "ollama":
            try:
                response = requests.post(
                    self.ollama_url,
                    json={"model": self.model_name, "prompt": text},
                    timeout=30
                )
                if response.status_code == 200:
                    embedding = np.array(response.json()['embedding'], dtype=np.float32)
                    norm = np.linalg.norm(embedding)
                    if norm > 0:
                        embedding = embedding / norm
                    return embedding
                else:
                    raise ValueError(f"Error en Ollama API: {response.status_code}")
            except Exception as e:
                console.print(f"[red]Error generando embedding: {e}[/red]")
                raise
        else:
            # sentence-transformers: normalización L2 y float32
            embedding = self.model.encode(
                text,
                convert_to_numpy=True,
                normalize_embeddings=True
            )
            if embedding.dtype != np.float32:
                embedding = embedding.astype(np.float32, copy=False)
            return embedding
    
    def generate_embedding(self, text: str) -> np.ndarray:
        """
        Genera embedding para un texto individual (con caché opcional)
        
        Args:
            text: Texto a embedir
        
        Returns:
            Vector numpy de dimensión [embedding_dim]
        """
        if not self.use_cache:
            self._cache_misses += 1
            return self._generate_embedding_uncached(text)
        
        # Usar caché
        try:
            text_hash = self._compute_text_hash(text)
            embedding_tuple = self._generate_embedding_cached(text_hash, text)
            self._cache_hits += 1
            return np.array(embedding_tuple, dtype=np.float32)
        except Exception:
            # Fallback sin caché si hay error
            self._cache_misses += 1
            return self._generate_embedding_uncached(text)
    
    def generate_embeddings_batch(self, texts: List[str], batch_size: int = 8) -> np.ndarray:
        """
        Genera embeddings en batch para eficiencia.

        En GPUs de baja VRAM, ante un OOM se reduce el batch_size a la mitad y se
        reintenta (liberando cache CUDA), hasta llegar a batch_size=1.

        Returns:
            Matriz numpy [num_texts, embedding_dim]
        """
        if self.provider == "ollama":
            # Ollama procesa uno por uno (no tiene batch nativo)
            embeddings = []
            for text in track(texts, description="Generando embeddings"):
                emb = self.generate_embedding(text)
                embeddings.append(emb)
            return np.array(embeddings, dtype=np.float32)
        else:
            try:
                import torch
            except Exception:
                torch = None

            current_bs = max(1, int(batch_size))
            while True:
                try:
                    embeddings = self.model.encode(
                        texts,
                        batch_size=current_bs,
                        show_progress_bar=True,
                        convert_to_numpy=True,
                        normalize_embeddings=True
                    )
                    if embeddings.dtype != np.float32:
                        embeddings = embeddings.astype(np.float32, copy=False)
                    return embeddings
                except RuntimeError as e:
                    is_oom = 'out of memory' in str(e).lower()
                    if is_oom and torch is not None and current_bs > 1:
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                        new_bs = max(1, current_bs // 2)
                        console.print(
                            f"[yellow]OOM con batch_size={current_bs}; reintentando con batch_size={new_bs}[/yellow]"
                        )
                        current_bs = new_bs
                        continue
                    raise
    
    def process_chunks(self, chunks: List[Dict]) -> List[Dict]:
        """
        Agrega embeddings a chunks con metadata
        
        Args:
            chunks: Lista de dicts con 'text' y 'metadata'
            
        Returns:
            Chunks con campo 'embedding' agregado
        """
        console.print(f"\n[bold cyan]Generando embeddings para {len(chunks)} chunks...[/bold cyan]")
        
        # Extraer textos
        texts = [chunk['text'] for chunk in chunks]
        
        # Generar embeddings
        embeddings = self.generate_embeddings_batch(texts)
        
        # Agregar embeddings a chunks
        for chunk, embedding in zip(chunks, embeddings):
            chunk['embedding'] = embedding
        
        console.print(f"[bold green]OK: Embeddings generados - dimension {embeddings.shape[1]}[/bold green]")
        
        return chunks
    
    def get_embedding_dim(self) -> int:
        """Retorna dimensión de embeddings"""
        return self.embedding_dim
    
    def get_cache_stats(self) -> dict:
        """Retorna estadísticas de caché"""
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total * 100) if total > 0 else 0
        
        cache_info = None
        if self.use_cache:
            try:
                cache_info = self._generate_embedding_cached.cache_info()
            except Exception:
                pass
        
        return {
            'enabled': self.use_cache,
            'hits': self._cache_hits,
            'misses': self._cache_misses,
            'total': total,
            'hit_rate': hit_rate,
            'cache_info': cache_info._asdict() if cache_info else None
        }
    
    def clear_cache(self):
        """Limpia el caché de embeddings"""
        if self.use_cache:
            self._generate_embedding_cached.cache_clear()
            self._cache_hits = 0
            self._cache_misses = 0
            console.print("[dim]Caché de embeddings limpiado[/dim]")


def test_embedder():
    """Test unitario del módulo o₂"""
    console.print("\n[bold yellow]═══ TEST MÓDULO o₂: Embeddings ═══[/bold yellow]\n")
    
    # Cargar configuración
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    model_name = config['embeddings']['model_name']
    device = config['embeddings']['device']
    provider = config['embeddings'].get('provider', 'sentence-transformers')
    
    # Verificar disponibilidad de CUDA (solo para sentence-transformers)
    if provider == 'sentence-transformers':
        import torch
        if device == "cuda" and not torch.cuda.is_available():
            console.print("[yellow]ADVERTENCIA: CUDA no disponible, usando CPU[/yellow]")
            device = "cpu"
    
    embedder = EmbeddingGenerator(model_name=model_name, device=device, provider=provider)
    
    # Test con textos de ejemplo
    test_chunks = [
        {
            'id': 'test_1',
            'text': 'Procedimiento de operación de centrales eléctricas del CROM',
            'metadata': {'source': 'test.pdf', 'page': 1}
        },
        {
            'id': 'test_2',
            'text': 'Instructivo para manejo de enlaces de comunicación',
            'metadata': {'source': 'test.pdf', 'page': 2}
        }
    ]
    
    chunks_with_embeddings = embedder.process_chunks(test_chunks)
    
    # Métricas
    console.print(f"\n[bold]Metricas embedder:[/bold]")
    console.print(f"  • Dimensión embeddings: {embedder.get_embedding_dim()}")
    console.print(f"  • Chunks procesados: {len(chunks_with_embeddings)}")
    console.print(f"  • Shape embedding[0]: {chunks_with_embeddings[0]['embedding'].shape}")
    
    # Validar similitud (los textos similares deben tener alta similitud)
    emb1 = chunks_with_embeddings[0]['embedding']
    emb2 = chunks_with_embeddings[1]['embedding']
    
    # Similitud coseno
    similarity = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
    console.print(f"  • Similitud entre textos: {similarity:.3f}")
    
    if similarity > 0.3:
        console.print(f"\n[bold green]OK: embedder VALIDADO - Embeddings generados correctamente[/bold green]")
    else:
        console.print(f"\n[bold yellow]ADVERTENCIA: embedder PARCIAL - Verificar calidad de embeddings[/bold yellow]")
    
    return chunks_with_embeddings


if __name__ == "__main__":
    test_embedder()
