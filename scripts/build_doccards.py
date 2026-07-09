import sys
import os
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
os.chdir(str(BASE_DIR))
SRC_DIR = BASE_DIR / 'src'
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vector_store import VectorStore
from doc_cards import build_doc_cards_llm, save_doc_roles
from utils import get_config, get_console


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=str, default='granite-3.3-8b-instruct-q5km:latest')
    parser.add_argument('--max-docs', type=int, default=0)
    parser.add_argument('--llm-max-calls', type=int, default=0)
    parser.add_argument('--llm-ratio', type=float, default=1.0)
    parser.add_argument('--llm-timeout', type=int, default=20)
    parser.add_argument('--sample-chars', type=int, default=1200)
    args = parser.parse_args()

    console = get_console()
    cfg = get_config(use_cache=False)

    db_path = cfg['paths'].get('vectordb_dir_bge', cfg['paths'].get('vectordb_dir', 'chroma_bge_m3'))
    collection_name = cfg['vectordb'].get('collection_name_bge', cfg['vectordb'].get('collection_name', 'crom_protocols_bge_m3'))

    console.print('\n[bold cyan]Construyendo DocCards con LLM[/bold cyan]')
    console.print(f"DB: {db_path}  Coleccion: {collection_name}")
    console.print(f"Modelo: {args.model}  Presupuesto: ratio={args.llm_ratio} max_calls={args.llm_max_calls}")

    vs = VectorStore(db_path=db_path, collection_name=collection_name)

    out = build_doc_cards_llm(
        vs,
        model_name=args.model,
        max_docs=args.max_docs,
        llm_max_calls=args.llm_max_calls,
        llm_ratio=args.llm_ratio,
        llm_timeout=args.llm_timeout,
        sample_chars=args.sample_chars,
    )

    save_doc_roles(out)
    n = len((out or {}).get('docs', {}))
    console.print(f"\n[bold green]OK: DocCards generadas[/bold green]  Documentos: {n}")
    console.print("Archivo: data/doc_roles.json")


if __name__ == '__main__':
    main()
