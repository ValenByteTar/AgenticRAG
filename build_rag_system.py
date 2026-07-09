"""
Script principal para construir el sistema RAG completo
Ejecuta módulos o₁ y o₂: Extracción + Chunking + Embeddings + Indexación
"""

from pathlib import Path
from rich.panel import Panel
import sys
import argparse

# Importar módulos (ruta absoluta para funcionar desde cualquier CWD)
_src_dir = str(Path(__file__).parent / 'src')
if _src_dir not in sys.path:
    sys.path.append(_src_dir)
from pdf_extractor import PDFExtractor
from chunker import TextChunker
from embedder import EmbeddingGenerator
from vector_store import VectorStore
from utils import get_config, get_available_device, get_console

console = get_console()


def build_rag_database(config_path: str = 'config.yaml', variant_override: str = None,
                       rebuild_override: bool = None, batch_pdfs: int = 25):
    """
    Pipeline en streaming por lotes: por cada lote de PDFs se ejecuta
    Extraccion -> Chunking -> Embeddings -> Indexacion, liberando memoria
    entre lotes. Esto evita acumular todos los chunks/embeddings en RAM y
    permite escalar a cientos de PDFs.

    Args:
        batch_pdfs: cantidad de PDFs por lote antes de generar embeddings/indexar.
    """
    # Resolver config.yaml y rutas relativas al directorio del script
    script_dir = Path(__file__).parent
    config_file = script_dir / config_path
    if config_file.exists():
        config = get_config(str(config_file), use_cache=False)
    else:
        config = get_config(config_path, use_cache=False)
    # Convertir rutas relativas del config a absolutas (basadas en el directorio del script)
    if 'paths' in config:
        for key, val in config['paths'].items():
            if isinstance(val, str):
                p = Path(val)
                if not p.is_absolute():
                    abs_p = script_dir / p
                    abs_p.mkdir(parents=True, exist_ok=True)
                    config['paths'][key] = str(abs_p)
    # Selección de variante
    variant = variant_override or (config.get('rag', {}) or {}).get('index_variant', 'bge')
    variant = str(variant).lower()
    
    console.print(Panel.fit(
        "[bold cyan]CONSTRUCCION DEL SISTEMA RAG (streaming por lotes)[/bold cyan]\n"
        "Pipeline: PDF -> Extraccion -> Chunking -> Embeddings -> VectorDB",
        border_style="cyan"
    ))

    # ═══ PREPARACIÓN: módulos y lista de PDFs ═══
    extractor = PDFExtractor(
        pdf_dir=config['paths']['pdf_dir'],
        output_dir=config['paths']['extracted_dir']
    )
    pdf_files = extractor.list_pdf_files()
    total_pdfs = len(pdf_files)
    if total_pdfs == 0:
        console.print("[bold red]ERROR: No se encontraron PDFs en el directorio[/bold red]")
        return False
    console.print(f"\n[bold cyan]Encontrados {total_pdfs} PDFs en '{config['paths']['pdf_dir']}'[/bold cyan]")

    chunker = TextChunker(
        chunk_size=config['chunking']['chunk_size'],
        overlap=config['chunking']['overlap'],
        token_chunking=config['chunking'].get('token_chunking', False),
        token_chunk_size=config['chunking'].get('token_chunk_size', 400),
        token_overlap=config['chunking'].get('token_overlap', 50)
    )

    # Elegir configuración de embeddings por variante
    if variant == 'legacy':
        emb_cfg = (config.get('embeddings_legacy') or config['embeddings'])
    else:
        emb_cfg = (config.get('embeddings_bge') or config['embeddings'])
    device = emb_cfg.get('device', config['embeddings']['device'])
    device = get_available_device(device, verbose=True)
    # Resolver ruta del modelo a absoluta (SentenceTransformer la evalúa desde CWD)
    model_name = emb_cfg['model_name']
    model_path = Path(model_name)
    if not model_path.is_absolute():
        abs_model = script_dir / model_path
        if abs_model.exists():
            model_name = str(abs_model)
    embedder = EmbeddingGenerator(
        model_name=model_name,
        device=device,
        provider=emb_cfg.get('provider', 'sentence-transformers'),
        use_cache=False  # En build masivo el caché LRU no aporta y consume RAM
    )

    # Rutas y colección por variante
    if variant == 'legacy':
        db_path = config['paths']['vectordb_dir']
        collection_name = config['vectordb']['collection_name']
    else:
        db_path = config['paths'].get('vectordb_dir_bge', config['paths']['vectordb_dir'])
        collection_name = config['vectordb'].get('collection_name_bge', config['vectordb']['collection_name'])
    vector_store = VectorStore(
        db_path=db_path,
        collection_name=collection_name,
        search_ef=config.get('vectordb', {}).get('search_ef', 100)
    )

    # Limpieza automática opcional (antes de indexar)
    rebuild_flag = config.get('vectordb', {}).get('rebuild_on_build', False)
    if rebuild_override is not None:
        rebuild_flag = bool(rebuild_override)
    if rebuild_flag:
        console.print(f"\n[yellow]ADVERTENCIA: Limpieza automatica habilitada (rebuild_on_build=true)[/yellow]")
        vector_store.clear_collection()
    else:
        if vector_store.collection.count() > 0:
            console.print(f"\n[yellow]ADVERTENCIA: La base de datos ya contiene {vector_store.collection.count()} documentos[/yellow]")
            try:
                response = input("¿Desea reemplazarlos? (s/n): ")
                if response.lower() == 's':
                    vector_store.clear_collection()
            except Exception:
                pass

    # ═══ PROCESAMIENTO POR LOTES ═══
    total_chunks = 0
    total_indexed = 0
    ok_pdfs = 0
    failed_pdfs = []
    empty_pdfs = []  # PDFs sin texto extraible (probables escaneos/imagenes)
    num_batches = (total_pdfs + batch_pdfs - 1) // batch_pdfs

    for b in range(num_batches):
        batch_paths = pdf_files[b * batch_pdfs:(b + 1) * batch_pdfs]
        console.print(
            f"\n[bold yellow]LOTE {b + 1}/{num_batches}[/bold yellow] "
            f"[dim]({len(batch_paths)} PDFs)[/dim]"
        )

        # o1: Extraccion + o1b: Chunking del lote
        batch_chunks = []
        for pdf_path in batch_paths:
            result = extractor.extract_text_from_pdf(pdf_path)
            if not result.get('success'):
                failed_pdfs.append(result.get('filename', str(pdf_path)))
                continue
            extractor.save_extracted_text(result)
            ok_pdfs += 1
            chunks = chunker.create_chunks_with_metadata(result)
            if not chunks:
                empty_pdfs.append(result['filename'])
                continue
            batch_chunks.extend(chunks)

        if not batch_chunks:
            console.print("[dim]  Lote sin chunks indexables, se omite.[/dim]")
            continue

        # o2: Embeddings del lote
        batch_chunks = embedder.process_chunks(batch_chunks)
        total_chunks += len(batch_chunks)

        # o2b: Indexacion del lote
        indexed = vector_store.add_chunks(batch_chunks)
        total_indexed += (indexed or 0)

        # Liberar memoria del lote (RAM y VRAM)
        del batch_chunks
        import gc
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    if total_indexed == 0:
        console.print("[bold red]ERROR: No se indexo ningun chunk[/bold red]")
        return False

    # ═══ RESUMEN FINAL ═══
    stats = vector_store.get_stats()

    resumen = (
        f"[bold green]OK: SISTEMA RAG CONSTRUIDO EXITOSAMENTE[/bold green]\n\n"
        f"Estadisticas:\n"
        f"  - PDFs encontrados: {total_pdfs}\n"
        f"  - PDFs extraidos OK: {ok_pdfs}\n"
        f"  - PDFs fallidos: {len(failed_pdfs)}\n"
        f"  - PDFs sin texto (probable imagen/escaneo): {len(empty_pdfs)}\n"
        f"  - Chunks generados: {total_chunks}\n"
        f"  - Embeddings indexados: {stats['total_chunks']}\n"
        f"  - Dimension vectores: {embedder.get_embedding_dim()}\n"
        f"  - Base de datos: {stats['db_path']}\n"
        f"  - Variante: {variant}\n"
        f"  - Lotes procesados: {num_batches} (tam. lote = {batch_pdfs})"
    )
    console.print(Panel.fit(resumen, border_style="green"))

    if empty_pdfs:
        console.print(f"\n[dim]PDFs sin texto extraible ({len(empty_pdfs)}):[/dim]")
        for name in empty_pdfs[:30]:
            console.print(f"[dim]  - {name}[/dim]")
        if len(empty_pdfs) > 30:
            console.print(f"[dim]  ... y {len(empty_pdfs) - 30} mas[/dim]")
    if failed_pdfs:
        console.print(f"\n[yellow]PDFs fallidos ({len(failed_pdfs)}):[/yellow]")
        for name in failed_pdfs[:30]:
            console.print(f"[yellow]  - {name}[/yellow]")

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Construye la base Chroma para el sistema RAG")
    parser.add_argument("--config", default="config.yaml", help="Ruta al archivo de configuración")
    parser.add_argument("--variant", choices=["bge", "legacy"], default=None, help="Selecciona índice/embeddings a construir")
    parser.add_argument("--rebuild", action="store_true", help="Forzar limpieza de la colección antes de indexar")
    parser.add_argument("--batch-pdfs", type=int, default=25, help="Cantidad de PDFs por lote (control de memoria)")
    args = parser.parse_args()

    try:
        success = build_rag_database(config_path=args.config, variant_override=args.variant,
                                     rebuild_override=args.rebuild, batch_pdfs=args.batch_pdfs)
        if success:
            console.print("\n[bold cyan]Siguiente paso: Ejecutar busquedas con 'python query_rag.py'[/bold cyan]")
        else:
            console.print("\n[bold red]Construccion fallida. Revisar logs.[/bold red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]ERROR CRITICO: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)
