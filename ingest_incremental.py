"""
Ingesta incremental de PDFs a ChromaDB con hashing SHA256 y chunking por tokens.
- Evita duplicados usando un registro persistente en JSON.
- No toca ni reindexa embeddings anteriores.
- Enriquecimiento de metadata básico (filename, page, filepath, fecha de archivo).
"""

import sys
from pathlib import Path
from datetime import datetime
from rich.panel import Panel

sys.path.append('src')
from pdf_extractor import PDFExtractor
from chunker import TextChunker
from embedder import EmbeddingGenerator
from vector_store import VectorStore
from hash_registry import HashRegistry
from utils import get_config, get_available_device, get_console
from doc_cards import load_doc_roles, save_doc_roles, build_doc_cards_llm_incremental

console = get_console()


def ingest_incremental(retry_incomplete: bool = False, update_doccards: bool = False):
    cfg = get_config(use_cache=False)

    console.print(Panel.fit(
        "[bold cyan]INGESTA INCREMENTAL[/bold cyan]\n"
        "PDF → Extracción → Chunking (tokens) → Embeddings → ChromaDB",
        border_style="cyan"
    ))

    # 1) Inicializar componentes
    extractor = PDFExtractor(
        pdf_dir=cfg['paths']['pdf_dir'],
        output_dir=cfg['paths']['extracted_dir']
    )
    chunker = TextChunker(
        chunk_size=cfg['chunking']['chunk_size'],
        overlap=cfg['chunking']['overlap'],
        token_chunking=cfg['chunking'].get('token_chunking', False),
        token_chunk_size=cfg['chunking'].get('token_chunk_size', 400),
        token_overlap=cfg['chunking'].get('token_overlap', 50)
    )

    # Verificar dispositivo embeddings
    device = cfg['embeddings']['device']
    device = get_available_device(device, verbose=True)

    embedder = EmbeddingGenerator(
        model_name=cfg['embeddings']['model_name'],
        device=device,
        provider=cfg['embeddings'].get('provider', 'sentence-transformers')
    )

    bge_db_path = cfg['paths'].get('vectordb_dir_bge', cfg['paths'].get('vectordb_dir', 'chroma_bge_m3'))
    bge_collection = cfg['vectordb'].get('collection_name_bge', cfg['vectordb'].get('collection_name', 'crom_protocols_bge_m3'))
    vectordb = VectorStore(
        db_path=bge_db_path,
        collection_name=bge_collection
    )

    registry = HashRegistry(store_path='data/ingest_registry.json')
    retry_hashes = set()
    if retry_incomplete:
        for e in registry._data.get("entries", []):
            attempted = e.get('attempted_chunks')
            indexed = e.get('chunks_indexed')
            if attempted is not None and indexed is not None and indexed < attempted:
                retry_hashes.add(e['hash'])

    # 2) Extraer PDFs
    results = extractor.extract_all_pdfs()
    successes = [r for r in results if r.get('success')]

    if not successes:
        console.print("[red]✗ No hay PDFs exitosos para procesar[/red]")
        return False

    # 3) Procesar incrementalmente
    total_new = 0
    for r in successes:
        # Construir texto completo del PDF para hashing
        pages = r.get('pages', [])
        full_text = "\n\n".join(p.get('text', '') for p in pages)
        from hash_registry import HashRegistry as _HR
        content_hash = _HR.compute_hash(full_text)

        if registry.exists(content_hash) and (content_hash not in retry_hashes):
            console.print(f"[dim]Saltando {r['filename']} (hash ya procesado)[/dim]")
            continue

        # Enriquecer metadata base en pdf_data (fecha de archivo)
        try:
            mtime = Path(r['filepath']).stat().st_mtime
            file_date = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
        except Exception:
            file_date = None
        r['doc_date'] = file_date

        # Chunking (tokens)
        chunks = chunker.create_chunks_with_metadata(r)
        if not chunks:
            console.print(f"[yellow]ADVERTENCIA: Sin chunks para {r['filename']}[/yellow]")
            continue

        # Asegurar IDs únicos agregando prefijo del hash
        prefix = content_hash[:8]
        for ch in chunks:
            ch['id'] = f"{r['filename']}_{prefix}_{ch['metadata']['chunk_index']}"

        # Embeddings normalizados (embedder ya normaliza)
        chunks = embedder.process_chunks(chunks)

        # Insertar en base vectorial (incremental)
        added = vectordb.add_chunks(chunks)
        total_new += added

        # Registrar hash procesado
        registry.add(
            content_hash=content_hash,
            filename=r['filename'],
            filepath=r['filepath'],
            extra={
                'total_pages': r.get('total_pages', 0),
                'attempted_chunks': len(chunks),
                'chunks_indexed': added
            }
        )

    console.print(Panel.fit(
        f"[bold green]✓ Ingesta incremental completada[/bold green]\n\n"
        f"Nuevos chunks: {total_new}\n"
        f"DB: {cfg['paths']['vectordb_dir']} / Colección: {cfg['vectordb']['collection_name']}",
        border_style="green"
    ))

    # 4) (Opcional) Actualizar DocCards de forma incremental
    try:
        if update_doccards and total_new > 0:
            console.print("\n[bold cyan]Actualizando DocCards (incremental)...[/bold cyan]")
            # Cargar existentes
            existing_roles = load_doc_roles()
            before = len((existing_roles or {}).get('docs', {}))

            # Parámetros desde config.yaml
            dcfg = cfg.get('doccards', {}) if isinstance(cfg, dict) else {}
            model = dcfg.get('model_name', 'granite33-8b-q4')
            llm_max_calls = dcfg.get('llm_max_calls', 0)
            llm_ratio = dcfg.get('llm_ratio', 0.2)
            llm_timeout = dcfg.get('llm_timeout', 8)
            sample_chars = dcfg.get('sample_chars', 600)

            out = build_doc_cards_llm_incremental(
                vectordb,
                existing=existing_roles,
                model_name=model,
                max_docs=0,
                llm_max_calls=llm_max_calls,
                llm_ratio=llm_ratio,
                llm_timeout=llm_timeout,
                sample_chars=sample_chars,
            )
            save_doc_roles(out)
            after = len((out or {}).get('docs', {}))
            added = after - before
            console.print(f"[bold green]DocCards actualizadas[/bold green]  Total: {after}  Nuevas: {added}")
            console.print("Archivo: data/doc_roles.json")
        elif update_doccards:
            console.print("[dim]No hay nuevos chunks, DocCards no requieren actualización[/dim]")
    except Exception as e:
        console.print(f"[yellow]ADVERTENCIA: Falló actualización incremental de DocCards: {e}[/yellow]")
    return True


if __name__ == '__main__':
    try:
        import sys as _sys
        retry_flag = '--retry-incomplete' in _sys.argv
        update_dc_flag = '--update-doccards' in _sys.argv
        ingest_incremental(retry_incomplete=retry_flag, update_doccards=update_dc_flag)
    except Exception as e:
        console.print(f"\n[bold red]✗ ERROR CRÍTICO: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)
