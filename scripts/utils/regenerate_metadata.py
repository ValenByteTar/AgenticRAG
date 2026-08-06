"""
Script rapido de regeneracion de DocCards y Mapa Conceptual.
Usa solo heuristicas (sin LLM) para evitar cargar 100K chunks en memoria.
"""
import sys
import os
import json
from pathlib import Path
from collections import Counter

# Forzar CWD al proyecto
SCRIPT_DIR = Path(__file__).parent
os.chdir(str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / 'src'))

from utils import get_config, get_console
from doc_cards import build_doc_cards, save_doc_roles

console = get_console()


def build_doccards_fast():
    """DocCards heuristicas rapidas desde el corpus (sin Chroma)."""
    console.print("[bold cyan]Construyendo DocCards (heuristicas desde corpus)...[/bold cyan]")
    doc_roles = build_doc_cards()
    n = len(doc_roles.get("docs", {}))
    console.print(f"[green]OK: {n} DocCards generadas heuristicamente[/green]")
    return doc_roles


def build_conceptual_map_fresh(vs):
    """Mapa conceptual fresco desde cero basado en los documentos indexados."""
    console.print("[bold cyan]Construyendo Mapa Conceptual fresco...[/bold cyan]")

    data = vs.collection.get(include=['metadatas'])
    metadatas = data.get('metadatas', [])

    # Extraer nombres unicos de documentos
    doc_names = sorted(set(
        Path((m or {}).get('source', 'Unknown')).name
        for m in metadatas
    ))

    # Crear estructura fresca
    cmap = {
        'entity_facts': {},
        'query_shortcuts': {},
        'entity_aliases': {},
        'metadata': {
            'total_documents': len(doc_names),
            'generated_from': 'build_rag_system.py',
            'document_sample': doc_names[:30],
        }
    }

    # Guardar
    cmap_path = SCRIPT_DIR / 'data' / 'conceptual_map.json'
    cmap_path.parent.mkdir(parents=True, exist_ok=True)
    cmap_path.write_text(json.dumps(cmap, ensure_ascii=False, indent=2), encoding='utf-8')

    console.print(f"[green]OK: Mapa conceptual fresco creado ({len(doc_names)} documentos)[/green]")
    return cmap


def main():
    console.print("[bold cyan]============================================[/bold cyan]")
    console.print("[bold cyan]  REGENERACION DE DOCCARDS Y MAPA CONCEPTUAL [/bold cyan]")
    console.print("[bold cyan]============================================[/bold cyan]\n")

    # 1) DocCards (from corpus, no Chroma needed)
    doc_roles = build_doccards_fast()
    save_doc_roles(doc_roles)
    console.print(f"[green]DocCards guardadas en data/doc_roles.json[/green]\n")

    # 2) Mapa Conceptual (still uses Chroma for document list)
    try:
        from vector_store import VectorStore
        cfg = get_config(use_cache=False)
        db_path = cfg['paths'].get('vectordb_dir_bge', 'chroma_bge_m3')
        collection_name = cfg['vectordb'].get('collection_name_bge', 'crom_protocols_bge_m3')
        vs = VectorStore(db_path=db_path, collection_name=collection_name)
        console.print(f"[dim]ChromaDB: {db_path} / {collection_name} ({vs.collection.count()} chunks)[/dim]\n")
        build_conceptual_map_fresh(vs)
    except Exception as e:
        console.print(f"[yellow]Mapa conceptual omitido (Chroma no disponible): {e}[/yellow]")

    console.print(f"\n[bold green]REGENERACION COMPLETA.[/bold green]")


if __name__ == '__main__':
    main()
