"""
Módulo o₁: Extracción de texto de PDFs
Objetivo: Extraer texto plano de PDFs con metadata de origen
Entradas: Ruta al PDF
Salidas: Texto extraído + metadata (nombre archivo, páginas)
Restricciones: Solo PyMuPDF
"""

import fitz  # PyMuPDF
from pathlib import Path
from typing import Dict, List
from rich.console import Console
from rich.progress import track
import unicodedata

console = Console()


def remove_accents(text: str) -> str:
    """
    Elimina acentos y normaliza caracteres especiales.
    Ejemplo: "Número" -> "Numero", "eólico" -> "eolico"
    """
    # Normalizar a NFD (descomponer caracteres con acentos)
    nfd = unicodedata.normalize('NFD', text)
    # Filtrar solo caracteres que no sean marcas diacríticas
    without_accents = ''.join(char for char in nfd if unicodedata.category(char) != 'Mn')
    return without_accents


class PDFExtractor:
    """Extractor de texto desde archivos PDF"""
    
    def __init__(self, pdf_dir: str, output_dir: str = "data/extracted_texts"):
        self.pdf_dir = Path(pdf_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def extract_text_from_pdf(self, pdf_path: Path) -> Dict:
        """
        Extrae texto de un PDF página por página
        
        Returns:
            Dict con 'filename', 'total_pages', 'pages' (lista de textos por página)
        """
        try:
            doc = fitz.open(pdf_path)
            pages_text = []
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text")
                
                # Limpieza básica
                text = text.strip()
                
                # Normalizar: eliminar acentos para evitar problemas de encoding
                text = remove_accents(text)
                
                if text:
                    pages_text.append({
                        'page_num': page_num + 1,
                        'text': text
                    })
            
            total_pages = len(doc)
            doc.close()
            
            return {
                'filename': pdf_path.name,
                'filepath': str(pdf_path),
                'total_pages': total_pages,
                'pages': pages_text,
                'success': True,
                'error': None
            }
            
        except Exception as e:
            console.print(f"[red]Error procesando {pdf_path.name}: {e}[/red]")
            return {
                'filename': pdf_path.name,
                'filepath': str(pdf_path),
                'success': False,
                'error': str(e)
            }
    
    def list_pdf_files(self) -> List[Path]:
        """
        Lista los PDFs del directorio (case-insensitive) sin duplicados.
        """
        pdf_files = []
        seen_paths = set()

        for pattern in ["*.pdf", "*.PDF"]:
            for pdf_path in self.pdf_dir.glob(pattern):
                # Normalizar path para evitar duplicados en Windows
                normalized_path = pdf_path.resolve()
                if normalized_path not in seen_paths:
                    pdf_files.append(pdf_path)
                    seen_paths.add(normalized_path)

        return pdf_files

    def save_extracted_text(self, result: Dict) -> None:
        """Guarda el texto extraido de un PDF a disco (si fue exitoso)."""
        if not result.get('success'):
            return
        output_file = self.output_dir / f"{Path(result['filename']).stem}.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"=== {result['filename']} ===\n\n")
            for page in result['pages']:
                f.write(f"--- Página {page['page_num']} ---\n")
                f.write(page['text'])
                f.write("\n\n")

    def extract_all_pdfs(self) -> List[Dict]:
        """
        Procesa todos los PDFs en el directorio
        """
        # Buscar PDFs (case-insensitive) y deduplicar
        pdf_files = self.list_pdf_files()
        
        console.print(f"\n[bold cyan]Encontrados {len(pdf_files)} PDFs[/bold cyan]\n")
        
        results = []
        for pdf_path in track(pdf_files, description="Extrayendo texto..."):
            result = self.extract_text_from_pdf(pdf_path)
            results.append(result)
            
            # Guardar texto extraído
            self.save_extracted_text(result)
        
        # Estadísticas
        successful = sum(1 for r in results if r['success'])
        console.print(f"\n[bold green]OK: Procesados exitosamente: {successful}/{len(pdf_files)}[/bold green]")
        
        return results


def test_extractor():
    """Test unitario del módulo o₁"""
    console.print("\n[bold yellow]═══ TEST MÓDULO o₁: Extractor PDF ═══[/bold yellow]\n")
    
    extractor = PDFExtractor("protocolosPDF")
    results = extractor.extract_all_pdfs()
    
    # Métricas
    successful_results = [r for r in results if r['success']]
    total_pages = sum(r.get('total_pages', 0) for r in successful_results)
    avg_pages = total_pages / len(successful_results) if successful_results else 0
    
    console.print(f"\n[bold]📊 Métricas o₁:[/bold]")
    console.print(f"  • Total páginas procesadas: {total_pages}")
    console.print(f"  • Promedio páginas/PDF: {avg_pages:.1f}")
    console.print(f"  • Tasa de éxito: {len(successful_results)}/{len(results)}")
    
    # Validación
    if len(successful_results) == len(results):
        console.print(f"\n[bold green]✓ o₁ VALIDADO - Todos los PDFs procesados correctamente[/bold green]")
    else:
        console.print(f"\n[bold red]✗ o₁ PARCIAL - Algunos PDFs fallaron[/bold red]")
    
    return results


if __name__ == "__main__":
    test_extractor()
