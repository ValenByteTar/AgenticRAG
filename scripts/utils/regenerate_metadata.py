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

from vector_store import VectorStore
from utils import get_config, get_console
from doc_cards import _guess_role_by_name, _extract_basic_entities, _infer_attributes_presence, _estimate_centrality, save_doc_roles

console = get_console()


def build_doccards_fast(vs, sample_chars=800):
    """DocCards heuristicas rapidas: solo carga metadatas, no documentos completos."""
    console.print("[bold cyan]Construyendo DocCards (heuristicas rapidas)...[/bold cyan]")

    data = vs.collection.get(include=['metadatas'])
    metadatas = data.get('metadatas', [])

    sources_seen = {}
    for i, md in enumerate(metadatas):
        src = (md or {}).get('source', 'Unknown')
        if src in sources_seen:
            continue
        if (i + 1) % 500 == 0:
            console.print(f"  Procesados {i+1}/{len(metadatas)} chunks, {len(sources_seen)} docs unicos...")

        name = Path(src).name
        role = _guess_role_by_name(name)
        summary = name  # sin acceso al texto completo, usamos nombre
        entities_idx = []
        attributes_idx = []
        centrality = _estimate_centrality(src, name)
        quality = 0.75

        sources_seen[src] = {
            'name': name,
            'path': src,
            'role': role,
            'summary': summary,
            'entities_index': entities_idx,
            'attributes_index': attributes_idx,
            'centrality': float(centrality),
            'quality': float(quality),
        }

    console.print(f"[green]OK: {len(sources_seen)} DocCards generadas heuristicamente[/green]")
    return {'docs': sources_seen}


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

    cfg = get_config(use_cache=False)
    db_path = cfg['paths'].get('vectordb_dir_bge', 'chroma_bge_m3')
    collection_name = cfg['vectordb'].get('collection_name_bge', 'crom_protocols_bge_m3')

    vs = VectorStore(db_path=db_path, collection_name=collection_name)
    console.print(f"[dim]ChromaDB: {db_path} / {collection_name} ({vs.collection.count()} chunks)[/dim]\n")

    # 1) DocCards
    doc_roles = build_doccards_fast(vs)
    save_doc_roles(doc_roles)
    console.print(f"[green]DocCards guardadas en data/doc_roles.json[/green]\n")

    # 2) Mapa Conceptual
    build_conceptual_map_fresh(vs)

    console.print(f"\n[bold green]REGENERACION COMPLETA.[/bold green]")


if __name__ == '__main__':
    main()
