"""
Módulo o₂b: Base de datos vectorial con ChromaDB
Objetivo: Almacenar y buscar embeddings eficientemente
Entradas: Chunks con embeddings
Salidas: Sistema de búsqueda por similitud
"""

import chromadb
from chromadb.config import Settings
from typing import List, Dict
from pathlib import Path
from rich.console import Console
import yaml

console = Console()


class VectorStore:
    """Gestiona almacenamiento y búsqueda en ChromaDB"""
    
    def __init__(self, db_path: str = "vectordb", collection_name: str = "cybersec_docs", search_ef: int = 100):
        """
        Args:
            db_path: Directorio para persistencia de ChromaDB
            collection_name: Nombre de la colección
        """
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)
        try:
            self.search_ef = int(search_ef) if search_ef else 100
        except Exception:
            self.search_ef = 100
        
        # Inicializar cliente ChromaDB persistente
        self.client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Crear o recuperar colección con parámetros HNSW optimizados
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={
                "hnsw:space": "cosine",              # Métrica de similitud
                "hnsw:construction_ef": 200,         # Calidad construcción (default 100)
                "hnsw:search_ef": int(self.search_ef),               # Calidad búsqueda (default 10→100) +recall
                "hnsw:M": 32                         # Conexiones por nodo (16→32) +precisión
            }
        )
        
        console.print(f"[bold green]OK: ChromaDB inicializado con {self.collection.count()} documentos[/bold green]")
    
    def add_chunks(self, chunks: List[Dict], batch_size: int = 100):
        """
        Agrega chunks con embeddings a la base de datos
        
        Args:
            chunks: Lista de dicts con 'id', 'text', 'embedding', 'metadata'
        """
        console.print(f"\n[bold cyan]Indexando {len(chunks)} chunks en ChromaDB...[/bold cyan]")
        
        added_count = 0
        
        def _sanitize_metadata(meta: Dict) -> Dict:
            allowed = {}
            for k, v in (meta or {}).items():
                if v is None:
                    continue
                if isinstance(v, (bool, int, float, str)):
                    allowed[k] = v
                else:
                    # Convert other types to str as a last resort
                    try:
                        allowed[k] = str(v)
                    except Exception:
                        continue
            return allowed
        # Procesar en batches para eficiencia
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            
            ids = [chunk['id'] for chunk in batch]
            embeddings = [chunk['embedding'].tolist() for chunk in batch]
            documents = [chunk['text'] for chunk in batch]
            metadatas = [_sanitize_metadata(chunk.get('metadata', {})) for chunk in batch]
            
            try:
                self.collection.add(
                    ids=ids,
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas
                )
                added_count += len(batch)
            except Exception as e:
                console.print(f"[yellow]ADVERTENCIA: Error en batch {i//batch_size + 1}: {e}[/yellow]")
                # Intentar agregar uno por uno para identificar el problema
                for j, chunk in enumerate(batch):
                    try:
                        self.collection.add(
                            ids=[ids[j]],
                            embeddings=[embeddings[j]],
                            documents=[documents[j]],
                            metadatas=[_sanitize_metadata(chunk.get('metadata', {}))]
                        )
                        added_count += 1
                    except Exception as e2:
                        console.print(f"[dim]  • Chunk {ids[j]}: {str(e2)[:50]}...[/dim]")
        
        console.print(f"[bold green]OK: {added_count} chunks indexados exitosamente[/bold green]")
        console.print(f"[bold]Total en base de datos: {self.collection.count()}[/bold]")
        return added_count
    
    def search(self, query_embedding: List[float], top_k: int = 5, where: Dict | None = None, include: List[str] | None = None) -> Dict:
        """
        Busca los chunks más similares al query
        
        Args:
            query_embedding: Vector de embedding de la consulta
            top_k: Número de resultados a retornar
            
        Returns:
            Dict con 'documents', 'metadatas', 'distances'
        """
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=(include or ["documents","metadatas","distances"])  # 'ids' no es válido en include; Chroma los devuelve por defecto
        )
        
        return {
            'documents': results.get('documents', [[]])[0] if results.get('documents') else [],
            'metadatas': results.get('metadatas', [[]])[0] if results.get('metadatas') else [],
            'distances': results.get('distances', [[]])[0] if results.get('distances') else [],
            'ids': results.get('ids', [[]])[0] if results.get('ids') else []
        }
    
    def search_by_text(self, query_text: str, embedder, top_k: int = 5) -> List[Dict]:
        """
        Búsqueda conveniente con texto directo
        
        Args:
            query_text: Texto de consulta
            embedder: Instancia de EmbeddingGenerator
            top_k: Número de resultados
            
        Returns:
            Lista de resultados con score
        """
        # Generar embedding del query
        query_embedding = embedder.generate_embedding(query_text)
        
        # Buscar
        results = self.search(query_embedding.tolist(), top_k=top_k)
        
        # Formatear resultados
        formatted_results = []
        for doc, meta, dist in zip(results['documents'], results['metadatas'], results['distances']):
            formatted_results.append({
                'text': doc,
                'metadata': meta,
                'similarity_score': 1 - dist,  # Convertir distancia a score
                'distance': dist
            })
        
        return formatted_results
    
    def clear_collection(self):
        """Limpia todos los documentos de la colección"""
        collection_name = self.collection.name
        self.client.delete_collection(collection_name)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={
                "hnsw:space": "cosine",
                "hnsw:construction_ef": 200,
                "hnsw:search_ef": int(self.search_ef) if self.search_ef else 100,
                "hnsw:M": 32
            }
        )
        console.print("[yellow]ADVERTENCIA: Coleccion limpiada (con parametros optimizados)[/yellow]")
    
    def get_stats(self) -> Dict:
        """Retorna estadísticas de la base de datos"""
        return {
            'total_chunks': self.collection.count(),
            'collection_name': self.collection.name,
            'db_path': str(self.db_path)
        }


def test_vector_store():
    """Test unitario del módulo vector store"""
    console.print("\n[bold yellow]═══ TEST MÓDULO o₂b: Vector Store ═══[/bold yellow]\n")
    
    # Cargar configuración
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # Crear instancia
    vector_store = VectorStore(
        db_path=config['paths']['vectordb_dir'],
        collection_name=config['vectordb']['collection_name'] + "_test"
    )
    
    # Limpiar colección de test
    vector_store.clear_collection()
    
    # Simular chunks con embeddings
    import numpy as np
    test_chunks = [
        {
            'id': 'test_chunk_1',
            'text': 'Procedimiento de operación CROM para centrales GOLDWIND',
            'embedding': np.random.rand(384),  # Dimensión típica
            'metadata': {'source': 'GOLDWIND.pdf', 'page': 1}
        },
        {
            'id': 'test_chunk_2',
            'text': 'Instructivo de enlaces de comunicación para operadores',
            'embedding': np.random.rand(384),
            'metadata': {'source': 'enlaces.pdf', 'page': 3}
        }
    ]
    
    # Agregar chunks
    vector_store.add_chunks(test_chunks)
    
    # Buscar
    query_emb = np.random.rand(384)
    results = vector_store.search(query_emb.tolist(), top_k=2)
    
    # Métricas
    stats = vector_store.get_stats()
    console.print(f"\n[bold]Metricas vector_store:[/bold]")
    console.print(f"  • Total chunks indexados: {stats['total_chunks']}")
    console.print(f"  • Resultados de búsqueda: {len(results['documents'])}")
    console.print(f"  • Distancia mínima: {min(results['distances']):.3f}")
    
    if stats['total_chunks'] == len(test_chunks):
        console.print(f"\n[bold green]OK: vector_store VALIDADO - Vector Store funcional[/bold green]")
    else:
        console.print(f"\n[bold red]ERROR: vector_store FALLO - Error en indexacion[/bold red]")
    
    # Limpiar test
    vector_store.clear_collection()
    
    return vector_store


if __name__ == "__main__":
    test_vector_store()
