import sys
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = BASE_DIR / 'src'
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from utils import get_config, get_console
from vector_store import VectorStore
from doc_cards import (
    load_doc_roles,
    save_doc_roles,
    build_doc_cards_llm_incremental,
)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=str, default=None, help='Modelo Ollama (por defecto usa config.yaml)')
    parser.add_argument('--max-docs', type=int, default=0, help='Máximo de documentos nuevos a procesar (0 = todos)')
    parser.add_argument('--llm-max-calls', type=int, default=None, help='Máximo de llamados al LLM (prioritario sobre ratio)')
    parser.add_argument('--llm-ratio', type=float, default=None, help='Proporción de docs nuevos a refinar con LLM (0-1)')
    parser.add_argument('--llm-timeout', type=int, default=None, help='Timeout por documento (s)')
    parser.add_argument('--sample-chars', type=int, default=None, help='Cantidad de caracteres de muestra por doc al LLM')
    args = parser.parse_args()

    console = get_console()
    cfg = get_config(use_cache=False)

    db_path = cfg['paths'].get('vectordb_dir_bge', cfg['paths'].get('vectordb_dir', 'chroma_bge_m3'))
    collection_name = cfg['vectordb'].get('collection_name_bge', cfg['vectordb'].get('collection_name', 'crom_protocols_bge_m3'))

    # Defaults desde config.yaml
    dcfg = cfg.get('doccards', {})
    model = args.model or dcfg.get('model_name', 'granite-3.3-8b-instruct-q5km:latest')
    llm_max_calls = args.llm_max_calls if args.llm_max_calls is not None else dcfg.get('llm_max_calls', 0)
    llm_ratio = args.llm_ratio if args.llm_ratio is not None else dcfg.get('llm_ratio', 0.2)
    llm_timeout = args.llm_timeout if args.llm_timeout is not None else dcfg.get('llm_timeout', 8)
    sample_chars = args.sample_chars if args.sample_chars is not None else dcfg.get('sample_chars', 600)

    console.print('\n[bold cyan]DocCards incremental[/bold cyan]')
    console.print(f"DB: {db_path}  Coleccion: {collection_name}")
    console.print(f"Modelo: {model}  Presupuesto: ratio={llm_ratio} max_calls={llm_max_calls}")

    vs = VectorStore(db_path=db_path, collection_name=collection_name)

    existing = load_doc_roles()
    before = len((existing or {}).get('docs', {}))

    out = build_doc_cards_llm_incremental(
        vs,
        existing=existing,
        model_name=model,
        max_docs=args.max_docs,
        llm_max_calls=llm_max_calls,
        llm_ratio=llm_ratio,
        llm_timeout=llm_timeout,
        sample_chars=sample_chars,
    )

    save_doc_roles(out)

    after = len((out or {}).get('docs', {}))
    added = after - before
    console.print(f"\n[bold green]OK: DocCards actualizadas[/bold green]  Total: {after}  Nuevas: {added}")
    console.print("Archivo: data/doc_roles.json")

if __name__ == '__main__':
    main()
