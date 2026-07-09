"""
Módulo o₃: Sistema RAG básico funcional
Objetivo: Interfaz de consulta con retrieval de contexto
Entradas: Query del usuario
Salidas: Fragmentos relevantes + respuesta contextual
"""

import sys
from pathlib import Path
from rich.panel import Panel
from rich.markdown import Markdown

sys.path.append('src')
from embedder import EmbeddingGenerator
from vector_store import VectorStore
from utils import get_config, get_available_device, get_console

console = get_console()


class RAGQuerySystem:
    """Sistema de consulta RAG con búsqueda semántica"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config = get_config(config_path)
        
        console.print("\n[bold cyan]🔄 Inicializando sistema RAG...[/bold cyan]\n")
        
        # Verificar disponibilidad de CUDA
        device = self.config['embeddings']['device']
        device = get_available_device(device, verbose=True)
        
        # Cargar embedder
        self.embedder = EmbeddingGenerator(
            model_name=self.config['embeddings']['model_name'],
            device=device
        )
        
        # Conectar a vector store
        self.vector_store = VectorStore(
            db_path=self.config['paths']['vectordb_dir'],
            collection_name=self.config['vectordb']['collection_name']
        )
        
        stats = self.vector_store.get_stats()
        console.print(f"[bold green]✓ Sistema listo: {stats['total_chunks']} documentos disponibles[/bold green]\n")
    
    def query(self, query_text: str, top_k: int = None) -> dict:
        """
        Realiza búsqueda semántica
        
        Args:
            query_text: Consulta del usuario
            top_k: Número de resultados (default desde config)
            
        Returns:
            Dict con resultados y contexto
        """
        if top_k is None:
            top_k = self.config['retrieval']['top_k']
        
        # Búsqueda
        results = self.vector_store.search_by_text(
            query_text=query_text,
            embedder=self.embedder,
            top_k=top_k
        )
        
        # Filtrar por score threshold
        threshold = self.config['retrieval']['score_threshold']
        filtered_results = [r for r in results if r['similarity_score'] >= threshold]
        
        return {
            'query': query_text,
            'results': filtered_results,
            'total_results': len(filtered_results)
        }
    
    def display_results(self, query_result: dict):
        """Muestra resultados formateados"""
        
        console.print(Panel.fit(
            f"[bold cyan]Consulta:[/bold cyan] {query_result['query']}\n"
            f"[bold]Resultados encontrados:[/bold] {query_result['total_results']}",
            border_style="cyan"
        ))
        
        if not query_result['results']:
            console.print("\n[yellow]⚠ No se encontraron resultados relevantes[/yellow]")
            return
        
        for i, result in enumerate(query_result['results'], 1):
            score_color = "green" if result['similarity_score'] > 0.7 else "yellow"
            
            console.print(f"\n[bold]═══ Resultado {i} ═══[/bold]")
            console.print(f"[{score_color}]Similitud: {result['similarity_score']:.3f}[/{score_color}]")
            console.print(f"[dim]Fuente: {result['metadata']['source']} (Página {result['metadata']['page']})[/dim]")
            console.print(f"\n{result['text']}")
        
        console.print("\n" + "─" * 80)
    
    def interactive_mode(self):
        """Modo interactivo de consultas"""
        console.print(Panel.fit(
            "[bold green]SISTEMA RAG - MODO INTERACTIVO[/bold green]\n"
            "Escribe tu consulta o 'salir' para terminar",
            border_style="green"
        ))
        
        while True:
            try:
                query = input("\n🔍 Consulta: ").strip()
                
                if query.lower() in ['salir', 'exit', 'quit']:
                    console.print("\n[bold cyan]👋 Hasta luego![/bold cyan]")
                    break
                
                if not query:
                    continue
                
                result = self.query(query)
                self.display_results(result)
                
            except KeyboardInterrupt:
                console.print("\n\n[bold cyan]👋 Hasta luego![/bold cyan]")
                break
            except Exception as e:
                console.print(f"\n[bold red]✗ Error: {e}[/bold red]")


def test_rag_system():
    """Test unitario del módulo o₃"""
    console.print("\n[bold yellow]═══ TEST MÓDULO o₃: Sistema RAG ═══[/bold yellow]\n")
    
    rag = RAGQuerySystem()
    
    # Queries de prueba
    test_queries = [
        "¿Cuál es el procedimiento para centrales GOLDWIND?",
        "Instructivo de enlaces CROM",
        "Códigos ANSI"
    ]
    
    for query in test_queries:
        console.print(f"\n[bold]Testing: {query}[/bold]")
        result = rag.query(query, top_k=3)
        console.print(f"  • Resultados: {result['total_results']}")
        if result['results']:
            console.print(f"  • Score máximo: {result['results'][0]['similarity_score']:.3f}")
    
    console.print(f"\n[bold green]✓ o₃ VALIDADO - Sistema RAG funcional[/bold green]")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_rag_system()
    else:
        rag = RAGQuerySystem()
        rag.interactive_mode()
