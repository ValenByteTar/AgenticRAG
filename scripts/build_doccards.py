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

    console.print('\n[bold cyan]Construyendo DocCards con LLM (desde corpus)[/bold cyan]')
    console.print(f"Modelo: {args.model}  Presupuesto: ratio={args.llm_ratio} max_calls={args.llm_max_calls}")

    out = build_doc_cards_llm(
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
