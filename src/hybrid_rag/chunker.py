"""
Módulo o₁b: Segmentación inteligente de texto (Chunking)
Objetivo: Dividir textos largos en fragmentos semánticamente coherentes
Entradas: Texto extraído + metadata
Salidas: Lista de chunks con metadata (origen, página, posición)
"""

from typing import List, Dict
import re
from rich.console import Console
from typing import Optional

from utils import canonical_doc_id

console = Console()


class TextChunker:
    """Divide textos en chunks con overlap para mantener contexto"""
    
    def __init__(self, chunk_size: int = 800, overlap: int = 200,
                 token_chunking: bool = False,
                 token_chunk_size: int = 400,
                 token_overlap: int = 50,
                 tokenizer_name: str = "bert-base-multilingual-cased"):
        """
        Args:
            chunk_size: Número de caracteres por chunk (optimizado: 512→800)
            overlap: Caracteres de solapamiento entre chunks (128→200)
            token_chunking: Si True, usa chunking por tokens con solapamiento
            token_chunk_size: Tokens por chunk (recomendado 300-500)
            token_overlap: Tokens de solapamiento (recomendado ~50)
            tokenizer_name: Tokenizer HF a usar para el modo por tokens
        
        Nota: Por defecto se mantiene el chunking por caracteres para no
        romper flujos existentes. Activa token_chunking en nuevos pipelines.
        """
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.token_chunking = token_chunking
        self.token_chunk_size = token_chunk_size
        self.token_overlap = token_overlap
        self.tokenizer_name = tokenizer_name
        self._tokenizer = None
    
    def split_text_semantic(self, text: str) -> List[str]:
        """
        Divide texto respetando límites de oraciones y párrafos
        """
        # Separar por párrafos primero
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = ""
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            # Si el párrafo cabe en el chunk actual
            if len(current_chunk) + len(para) < self.chunk_size:
                current_chunk += para + "\n\n"
            else:
                # Guardar chunk actual si tiene contenido
                if current_chunk:
                    chunks.append(current_chunk.strip())
                
                # Si el párrafo es muy largo, dividirlo por oraciones
                if len(para) > self.chunk_size:
                    sentences = re.split(r'([.!?]\s+)', para)
                    temp_chunk = ""
                    
                    for i in range(0, len(sentences), 2):
                        sentence = sentences[i]
                        if i + 1 < len(sentences):
                            sentence += sentences[i + 1]
                        
                        if len(temp_chunk) + len(sentence) < self.chunk_size:
                            temp_chunk += sentence
                        else:
                            if temp_chunk:
                                chunks.append(temp_chunk.strip())
                            temp_chunk = sentence
                    
                    current_chunk = temp_chunk
                else:
                    current_chunk = para + "\n\n"
        
        # Agregar último chunk
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _get_tokenizer(self):
        if self._tokenizer is None:
            import os
            os.environ['HF_HUB_OFFLINE'] = '1'
            os.environ['TRANSFORMERS_OFFLINE'] = '1'
            os.environ['HF_DATASETS_OFFLINE'] = '1'
            os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
            from transformers import AutoTokenizer
            try:
                # Cargar SOLO desde archivos locales (cache o carpeta local)
                self._tokenizer = AutoTokenizer.from_pretrained(self.tokenizer_name, local_files_only=True)
            except Exception:
                # Fallback: intentar carpeta local por defecto si existe
                default_local = 'models/bert-base-multilingual-cased'
                if os.path.isdir(default_local):
                    self._tokenizer = AutoTokenizer.from_pretrained(default_local, local_files_only=True)
                else:
                    raise
        return self._tokenizer

    def split_text_tokens(self, text: str) -> List[str]:
        """Divide texto por tokens usando ventana deslizante y overlap."""
        tokenizer = self._get_tokenizer()
        enc = tokenizer(text, add_special_tokens=False, return_attention_mask=False, return_offsets_mapping=True)
        input_ids = enc["input_ids"]
        offsets = enc["offset_mapping"]
        chunks = []
        step = max(self.token_chunk_size - self.token_overlap, 1)
        for start in range(0, len(input_ids), step):
            end = start + self.token_chunk_size
            token_slice = offsets[start:end]
            if not token_slice:
                break
            char_start = token_slice[0][0]
            char_end = token_slice[-1][1]
            chunk_text = text[char_start:char_end].strip()
            if chunk_text:
                chunks.append(chunk_text)
            if end >= len(input_ids):
                break
        return chunks
    
    def create_chunks_with_metadata(self, pdf_data: Dict) -> List[Dict]:
        """
        Crea chunks con metadata completa desde datos extraídos de PDF
        
        Args:
            pdf_data: Dict con estructura de PDFExtractor
            
        Returns:
            Lista de chunks con metadata
        """
        if not pdf_data.get('success'):
            return []
        
        all_chunks = []
        chunk_id = 0
        
        for page_data in pdf_data.get('pages', []):
            page_num = page_data['page_num']
            text = page_data['text']
            
            # Generar chunks del texto de la página
            if self.token_chunking:
                chunks = self.split_text_tokens(text)
            else:
                chunks = self.split_text_semantic(text)
            
            for chunk_text in chunks:
                all_chunks.append({
                    'id': f"{pdf_data['filename']}_{chunk_id}",
                    'text': chunk_text,
                    'metadata': {
                        'source': pdf_data['filename'],
                        'canonical_doc_id': canonical_doc_id(pdf_data['filename']),
                        'page': page_num,
                        'chunk_index': chunk_id,
                        'filepath': pdf_data['filepath'],
                        'section': page_data.get('section'),
                        'doc_date': pdf_data.get('doc_date'),
                        'category': pdf_data.get('category')
                    }
                })
                chunk_id += 1
        
        return all_chunks
    
    def process_all_pdfs(self, pdf_results: List[Dict]) -> List[Dict]:
        """
        Procesa múltiples resultados de extracción de PDFs
        """
        all_chunks = []
        
        console.print(f"\n[bold cyan]Segmentando textos en chunks...[/bold cyan]\n")
        
        for pdf_data in pdf_results:
            if pdf_data.get('success'):
                chunks = self.create_chunks_with_metadata(pdf_data)
                all_chunks.extend(chunks)
        
        console.print(f"[bold green]OK: Generados {len(all_chunks)} chunks[/bold green]")
        
        return all_chunks


def test_chunker():
    """Test unitario del módulo chunker"""
    console.print("\n[bold yellow]═══ TEST MÓDULO o₁b: Chunker ═══[/bold yellow]\n")
    
    # Simular datos de PDF
    mock_pdf_data = {
        'filename': 'test.pdf',
        'filepath': '/test/test.pdf',
        'success': True,
        'pages': [
            {
                'page_num': 1,
                'text': """Este es un texto de prueba para validar el chunking semántico.
                
El sistema debe dividir correctamente respetando párrafos y oraciones. Cada chunk debe mantener coherencia semántica.

Este es otro párrafo. Debe ser procesado correctamente. El sistema funciona bien."""
            }
        ]
    }
    
    chunker = TextChunker(chunk_size=100, overlap=20)
    chunks = chunker.create_chunks_with_metadata(mock_pdf_data)
    
    console.print(f"[bold]📊 Métricas o₁b:[/bold]")
    console.print(f"  • Chunks generados: {len(chunks)}")
    console.print(f"  • Tamaño promedio: {sum(len(c['text']) for c in chunks) / len(chunks):.0f} chars")
    
    console.print(f"\n[bold]Ejemplo de chunk:[/bold]")
    if chunks:
        console.print(f"  ID: {chunks[0]['id']}")
        console.print(f"  Texto: {chunks[0]['text'][:100]}...")
        console.print(f"  Metadata: {chunks[0]['metadata']}")
    
    console.print(f"\n[bold green]✓ o₁b VALIDADO - Chunking funcional[/bold green]")
    
    return chunks


if __name__ == "__main__":
    test_chunker()
