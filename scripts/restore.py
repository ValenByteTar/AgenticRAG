"""
Script de Restauracion de Backup
Restaura el sistema desde un backup verificando integridad
"""

import shutil
import hashlib
from pathlib import Path
import json
import zipfile
import sys

sys.path.append(str(Path(__file__).parent.parent / 'src'))

from rich.console import Console
from rich.prompt import Confirm

console = Console()


def compute_hash(file_path):
    """Calcula hash MD5 de un archivo"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def list_backups(backup_dir="backups"):
    """Lista backups disponibles"""
    backup_root = Path(backup_dir)
    if not backup_root.exists():
        console.print(f"[red]ERROR: Directorio de backups no encontrado: {backup_dir}[/red]")
        return []
    
    backups = sorted(backup_root.glob("backup_*"), key=lambda p: p.name, reverse=True)
    return backups


def restore_backup(backup_path, verify=True, force=False):
    """
    Restaura sistema desde un backup
    
    Args:
        backup_path: Path al directorio de backup
        verify: Verificar integridad con manifest
        force: No pedir confirmacion
    """
    backup_path = Path(backup_path)
    
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup no encontrado: {backup_path}")
    
    console.print(f"\n[bold cyan]Restaurando desde: {backup_path.name}[/bold cyan]\n")
    
    # Leer manifest
    manifest_path = backup_path / "manifest.json"
    if not manifest_path.exists():
        console.print("[yellow]ADVERTENCIA: manifest.json no encontrado[/yellow]")
        manifest = None
    else:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        console.print(f"[dim]Backup creado: {manifest.get('datetime', 'desconocido')}[/dim]")
        console.print(f"[dim]Archivos en manifest: {len(manifest.get('files', {}))}[/dim]\n")
    
    # Verificar integridad si se solicita
    if verify and manifest:
        console.print("[yellow]Verificando integridad...[/yellow]")
        errors = []
        
        for file_rel, expected_hash in manifest['files'].items():
            file_path = backup_path / file_rel
            if not file_path.exists():
                errors.append(f"Archivo faltante: {file_rel}")
                continue
            
            actual_hash = compute_hash(file_path)
            if actual_hash != expected_hash:
                errors.append(f"Hash incorrecto: {file_rel}")
        
        if errors:
            console.print("[red]ERRORES DE INTEGRIDAD:[/red]")
            for error in errors:
                console.print(f"  - {error}")
            
            if not force:
                if not Confirm.ask("\nContinuar con la restauracion?"):
                    console.print("[yellow]Restauracion cancelada[/yellow]")
                    return False
        else:
            console.print("[green]OK: Integridad verificada[/green]\n")
    
    # Confirmacion final
    if not force:
        console.print("[bold yellow]ADVERTENCIA: Esto sobrescribira los datos actuales[/bold yellow]")
        if not Confirm.ask("Continuar con la restauracion?"):
            console.print("[yellow]Restauracion cancelada[/yellow]")
            return False
    
    console.print()
    
    # 1. Restaurar ChromaDB
    console.print("[yellow]1/4: Restaurando ChromaDB...[/yellow]")
    chroma_src = backup_path / "chroma_bge_m3"
    chroma_dst = Path("chroma_bge_m3")
    
    if chroma_src.exists():
        if chroma_dst.exists():
            shutil.rmtree(chroma_dst)
        shutil.copytree(chroma_src, chroma_dst)
        console.print(f"[green]OK: ChromaDB restaurado[/green]")
    else:
        console.print("[yellow]ADVERTENCIA: ChromaDB no encontrado en backup[/yellow]")
    
    # 2. Restaurar PDFs
    console.print("\n[yellow]2/4: Restaurando PDFs...[/yellow]")
    pdf_zip = backup_path / "protocolosPDF.zip"
    pdf_dst = Path("protocolosPDF")
    
    if pdf_zip.exists():
        if pdf_dst.exists():
            shutil.rmtree(pdf_dst)
        pdf_dst.mkdir(exist_ok=True)
        
        with zipfile.ZipFile(pdf_zip, 'r') as zipf:
            zipf.extractall(".")
        
        pdf_count = len(list(pdf_dst.rglob("*.pdf")))
        console.print(f"[green]OK: {pdf_count} PDFs restaurados[/green]")
    else:
        console.print("[yellow]ADVERTENCIA: protocolosPDF.zip no encontrado en backup[/yellow]")
    
    # 3. Restaurar configuracion
    console.print("\n[yellow]3/4: Restaurando configuracion...[/yellow]")
    config_files = [
        "config.yaml",
        "data/chats.json",
        "data/conceptual_map.json",
        "data/memory.db"
    ]
    
    restored_count = 0
    for config_file in config_files:
        src_file = backup_path / config_file
        dst_file = Path(config_file)
        
        if src_file.exists():
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            console.print(f"[dim]  - {config_file}[/dim]")
            restored_count += 1
    
    console.print(f"[green]OK: {restored_count} archivos de configuracion restaurados[/green]")
    
    # 4. Resumen
    console.print(f"\n[bold green]RESTAURACION COMPLETADA[/bold green]")
    console.print(f"[bold]Backup:[/bold] {backup_path.name}")
    console.print(f"[bold]Origen:[/bold] {manifest.get('datetime', 'desconocido') if manifest else 'desconocido'}\n")
    
    return True


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Restaurar backup del sistema RAG CROM")
    parser.add_argument("--dir", default="backups", help="Directorio de backups")
    parser.add_argument("--backup", help="Nombre especifico del backup (ej: backup_20241102_120000)")
    parser.add_argument("--latest", action="store_true", help="Usar el backup mas reciente")
    parser.add_argument("--no-verify", action="store_true", help="No verificar integridad")
    parser.add_argument("--force", action="store_true", help="No pedir confirmacion")
    
    args = parser.parse_args()
    
    try:
        # Listar backups disponibles
        backups = list_backups(args.dir)
        
        if not backups:
            console.print("[red]No se encontraron backups[/red]")
            sys.exit(1)
        
        # Seleccionar backup
        if args.backup:
            backup_path = Path(args.dir) / args.backup
            if not backup_path.exists():
                console.print(f"[red]ERROR: Backup no encontrado: {args.backup}[/red]")
                sys.exit(1)
        elif args.latest:
            backup_path = backups[0]
            console.print(f"[dim]Usando backup mas reciente: {backup_path.name}[/dim]")
        else:
            console.print("[bold]Backups disponibles:[/bold]")
            for i, backup in enumerate(backups, 1):
                console.print(f"  {i}. {backup.name}")
            
            choice = input("\nSelecciona numero de backup (o Enter para cancelar): ").strip()
            if not choice:
                console.print("[yellow]Cancelado[/yellow]")
                sys.exit(0)
            
            try:
                idx = int(choice) - 1
                backup_path = backups[idx]
            except (ValueError, IndexError):
                console.print("[red]Seleccion invalida[/red]")
                sys.exit(1)
        
        # Restaurar
        success = restore_backup(
            backup_path,
            verify=not args.no_verify,
            force=args.force
        )
        
        if success:
            console.print("[bold green]Restauracion exitosa[/bold green]")
            sys.exit(0)
        else:
            sys.exit(1)
            
    except Exception as e:
        console.print(f"[bold red]ERROR: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)
