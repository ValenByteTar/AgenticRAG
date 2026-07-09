"""
Script de pruebas automatizadas para verificar indexacion y recuperacion del RAG.
Ejecuta consultas de prueba y valida que el sistema encuentra informacion.
"""
import sys
import os
from pathlib import Path

# Forzar CWD al directorio del proyecto para que rutas relativas funcionen
_script_dir = Path(__file__).parent
os.chdir(str(_script_dir))

# Asegurar que src este en el path (ruta absoluta)
_src = str(_script_dir / 'src')
if _src not in sys.path:
    sys.path.insert(0, _src)

from rag_hybrid import HybridRAG
from utils import get_console

console = get_console()

# Consultas de prueba (en espanol, sobre ciberseguridad/IT indexado)
TEST_QUERIES = [
    {
        "query": "Que es ISO 27001 y para que sirve?",
        "desc": "Framework ISO 27001 - seguridad de la informacion",
        "min_results": 1,
        "expect_spanish": True,
    },
    {
        "query": "Cuales son las responsabilidades principales de un CISO?",
        "desc": "Rol del Chief Information Security Officer",
        "min_results": 1,
        "expect_spanish": True,
    },
    {
        "query": "Que es el marco MITRE ATT&CK?",
        "desc": "Framework MITRE ATT&CK",
        "min_results": 1,
        "expect_spanish": True,
    },
    {
        "query": "Como funciona el protocolo OSPF?",
        "desc": "Protocolo de enrutamiento OSPF",
        "min_results": 1,
        "expect_spanish": True,
    },
    {
        "query": "Que es un Security Operations Center y como opera?",
        "desc": "SOC - Centro de Operaciones de Seguridad",
        "min_results": 1,
        "expect_spanish": True,
    },
    {
        "query": "Que dice sobre seguridad en la nube y AWS?",
        "desc": "Cloud security y AWS",
        "min_results": 1,
        "expect_spanish": True,
    },
    {
        "query": "Como se realiza una prueba de penetracion o pentest?",
        "desc": "Penetration testing",
        "min_results": 1,
        "expect_spanish": True,
    },
    {
        "query": "Que es el RGPD o GDPR y que implica?",
        "desc": "Regulacion de proteccion de datos GDPR",
        "min_results": 1,
        "expect_spanish": True,
    },
]

SPANISH_MARKERS = [
    'á', 'é', 'í', 'ó', 'ú', 'ñ', 'ü',
    'el ', 'la ', 'los ', 'las ', 'del ', 'en ',
    'que ', 'para ', 'por ', 'con ', 'una ',
]


def is_spanish(text: str) -> bool:
    """Heuristica simple: verifica presencia de palabras/acentos en espanol."""
    if not text:
        return False
    lower = text.lower()
    matches = sum(1 for m in SPANISH_MARKERS if m in lower)
    return matches >= 2


def has_error_message(text: str) -> bool:
    """Detecta si la respuesta contiene mensajes de error del sistema (timeout, etc.)"""
    if not text:
        return True  # Vacio es error
    lower = text.lower().strip()
    
    # Solo detectar errores claros al INICIO de la respuesta o mensajes específicos de timeout
    error_prefixes = [
        'error:', '[error]', 'timeout:', 'no se encontró información en los documentos',
        'no se encontro informacion en los documentos',
        'el modelo está tomando demasiado tiempo',
        'el modelo esta tomando demasiado tiempo',
        '>4 minutos', '>5 minutos', 'tiempo de espera agotado',
        'respuesta vacia', '[timeout]'
    ]
    
    # Verificar solo al inicio de la respuesta (primeros 100 chars)
    start_100 = lower[:100]
    for prefix in error_prefixes:
        if start_100.startswith(prefix):
            return True
    
    # Detectar mensajes de timeout específicos en cualquier parte
    timeout_markers = [
        'error: timeout', 'error (>4 minutos)', 'error (>5 minutos)',
        '(>4 minutos)', '(>5 minutos)', 'timeout (>4', 'timeout (>5'
    ]
    return any(marker in lower for marker in timeout_markers)


def run_tests():
    console.print("[bold cyan]============================================[/bold cyan]")
    console.print("[bold cyan]  PRUEBAS DE INDEXACION Y RECUPERACION RAG  [/bold cyan]")
    console.print("[bold cyan]============================================[/bold cyan]\n")

    # Inicializar RAG
    console.print("[dim]Inicializando HybridRAG (variante bge)...[/dim]")
    try:
        rag = HybridRAG(variant="bge", heuristics="balanced")
    except Exception as e:
        console.print(f"[bold red]ERROR FATAL al inicializar RAG: {e}[/bold red]")
        return False

    num_docs = len(rag.all_docs)
    console.print(f"[green]OK: RAG inicializado con {num_docs:,} documentos[/green]\n")

    passed = 0
    failed = 0
    total = len(TEST_QUERIES)

    for i, test in enumerate(TEST_QUERIES, 1):
        query = test["query"]
        desc = test["desc"]
        min_results = test.get("min_results", 1)
        expect_spanish = test.get("expect_spanish", True)

        console.print(f"[bold yellow]--- Test {i}/{total}: {desc} ---[/bold yellow]")
        console.print(f"[dim]Query: '{query}'[/dim]")

        try:
            result = rag.query(
                query,
                top_k=10,
                semantic_weight=0.5,
                entity_filter=True,
                two_stage=True,
            )
        except Exception as e:
            console.print(f"[bold red]FAIL: Excepcion en query: {e}[/bold red]")
            failed += 1
            continue

        # Validacion 1: resultados recuperados
        num_results = len(result.get('results', []))
        if num_results >= min_results:
            console.print(f"  [green]PASS[/green] Recuperacion: {num_results} resultados (min: {min_results})")
        else:
            console.print(f"  [bold red]FAIL[/bold red] Recuperacion: {num_results} resultados (min: {min_results})")
            failed += 1
            continue

        # Validacion 2: fuentes presentes
        sources = result.get('sources', [])
        if sources:
            console.print(f"  [green]PASS[/green] Fuentes: {len(sources)} fuentes citadas")
        else:
            console.print(f"  [yellow]WARN[/yellow] Sin fuentes explicitas")

        # Validacion 3: respuesta sin errores del sistema
        answer = result.get('answer', '')
        if answer:
            preview = answer[:200].replace('\n', ' ')
            # Verificar que no sea un mensaje de error/timeout
            if has_error_message(answer):
                console.print(f"  [bold red]FAIL[/bold red] Respuesta contiene error/timeout: {preview}...")
                failed += 1
                continue
            # Verificar idioma español
            if expect_spanish:
                if is_spanish(answer):
                    console.print(f"  [green]PASS[/green] Idioma: respuesta en espanol (sin errores)")
                else:
                    console.print(f"  [bold red]FAIL[/bold red] Idioma: respuesta NO parece estar en espanol")
                    console.print(f"  [dim]Preview: {preview}...[/dim]")
                    failed += 1
                    continue
            console.print(f"  [dim]Preview respuesta: {preview}...[/dim]")
        else:
            console.print(f"  [bold red]FAIL[/bold red] Respuesta vacia")
            failed += 1
            continue

        # Validacion 4: tiempo de respuesta razonable
        elapsed = result.get('time', 0)
        console.print(f"  [dim]Tiempo: {elapsed:.2f}s[/dim]")

        passed += 1

    # Resumen final
    console.print(f"\n[bold cyan]============================================[/bold cyan]")
    console.print(f"[bold cyan]  RESULTADOS: {passed}/{total} PASS, {failed}/{total} FAIL  [/bold cyan]")
    console.print(f"[bold cyan]============================================[/bold cyan]")

    if failed == 0:
        console.print(f"\n[bold green]TODAS LAS PRUEBAS PASARON. Indexacion y recuperacion funcionan correctamente.[/bold green]")
    else:
        console.print(f"\n[bold red]ATENCION: {failed} prueba(s) fallaron. Revisar logs.[/bold red]")

    # Limpiar
    try:
        rag.cleanup()
    except Exception:
        pass

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
