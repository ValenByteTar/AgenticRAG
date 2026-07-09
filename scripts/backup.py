"""
Script de Backup Automatizado
Realiza snapshot de ChromaDB, PDFs y configuracion con verificacion de integridad
"""

import shutil
import hashlib
from pathlib import Path
from datetime import datetime
import json
import zipfile
import sys

# Agregar src al path
sys.path.append(str(Path(__file__).parent.parent / 'src'))

from rich.console import Console
from rich.progress import track

console = Console()


def compute_hash(file_path):
    """Calcula hash MD5 de un archivo"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def create_backup(backup_dir="backups", keep_last=7):
    """
    Crea backup completo del sistema
    
    Args:
        backup_dir: Directorio donde guardar backups
        keep_last: Numero de backups a mantener (rotacion)
    """
    console.print("\n[bold cyan]Iniciando backup del sistema...[/bold cyan]\n")
    
    # Crear directorio de backups
    backup_root = Path(backup_dir)
    backup_root.mkdir(exist_ok=True)
    
    # Timestamp para este backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_{timestamp}"
    backup_path = backup_root / backup_name
    backup_path.mkdir(exist_ok=True)
    
    console.print(f"[dim]Directorio de backup: {backup_path}[/dim]\n")
    
    # Manifest para verificacion
    manifest = {
        'timestamp': timestamp,
        'datetime': datetime.now().isoformat(),
        'files': {}
    }
    
    # 1. Backup de ChromaDB
    console.print("[yellow]1/4: Backup de ChromaDB...[/yellow]")
    chroma_src = Path("chroma_bge_m3")
    if chroma_src.exists():
        chroma_dst = backup_path / "chroma_bge_m3"
        shutil.copytree(chroma_src, chroma_dst)
        
        # Calcular hash de archivos criticos
        for db_file in chroma_dst.rglob("*.sqlite3"):
            file_hash = compute_hash(db_file)
            manifest['files'][str(db_file.relative_to(backup_path))] = file_hash
        
        console.print(f"[green]OK: ChromaDB copiado ({chroma_dst})[/green]")
    else:
        console.print("[yellow]ADVERTENCIA: chroma_bge_m3 no encontrado[/yellow]")
    
    # 2. Backup de PDFs
    console.print("\n[yellow]2/4: Backup de PDFs...[/yellow]")
    pdf_src = Path("protocolosPDF")
    if pdf_src.exists():
        pdf_dst = backup_path / "protocolosPDF"
        
        # Comprimir PDFs para ahorrar espacio
        zip_path = backup_path / "protocolosPDF.zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            pdf_files = list(pdf_src.rglob("*.pdf"))
            for pdf_file in track(pdf_files, description="Comprimiendo PDFs"):
                zipf.write(pdf_file, pdf_file.relative_to(pdf_src.parent))
        
        # Hash del ZIP
        zip_hash = compute_hash(zip_path)
        manifest['files']['protocolosPDF.zip'] = zip_hash
        
        console.print(f"[green]OK: {len(pdf_files)} PDFs comprimidos ({zip_path.stat().st_size / 1024 / 1024:.1f} MB)[/green]")
    else:
        console.print("[yellow]ADVERTENCIA: protocolosPDF no encontrado[/yellow]")
    
    # 3. Backup de configuracion
    console.print("\n[yellow]3/4: Backup de configuracion...[/yellow]")
    config_files = [
        "config.yaml",
        "data/chats.json",
        "data/conceptual_map.json",
        "data/memory.db"
    ]
    
    for config_file in config_files:
        src_file = Path(config_file)
        if src_file.exists():
            dst_file = backup_path / config_file
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            
            file_hash = compute_hash(dst_file)
            manifest['files'][config_file] = file_hash
            
            console.print(f"[dim]  - {config_file}[/dim]")
    
    console.print("[green]OK: Configuracion respaldada[/green]")
    
    # 4. Guardar manifest
    console.print("\n[yellow]4/4: Generando manifest...[/yellow]")
    manifest_path = backup_path / "manifest.json"
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    console.print(f"[green]OK: Manifest guardado ({len(manifest['files'])} archivos)[/green]")
    
    # 5. Rotacion de backups antiguos
    console.print(f"\n[yellow]Rotacion de backups (mantener ultimos {keep_last})...[/yellow]")
    all_backups = sorted(backup_root.glob("backup_*"), key=lambda p: p.name)
    
    if len(all_backups) > keep_last:
        to_delete = all_backups[:-keep_last]
        for old_backup in to_delete:
            shutil.rmtree(old_backup)
            console.print(f"[dim]  - Eliminado: {old_backup.name}[/dim]")
        console.print(f"[green]OK: {len(to_delete)} backups antiguos eliminados[/green]")
    else:
        console.print(f"[dim]No hay backups antiguos para eliminar ({len(all_backups)}/{keep_last})[/dim]")
    
    # Resumen final
    backup_size = sum(f.stat().st_size for f in backup_path.rglob("*") if f.is_file())
    console.print(f"\n[bold green]BACKUP COMPLETADO[/bold green]")
    console.print(f"[bold]Ubicacion:[/bold] {backup_path}")
    console.print(f"[bold]Tamano:[/bold] {backup_size / 1024 / 1024:.1f} MB")
    console.print(f"[bold]Archivos:[/bold] {len(manifest['files'])}")
    console.print(f"[bold]Timestamp:[/bold] {timestamp}\n")
    
    return backup_path


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Backup del sistema RAG CROM")
    parser.add_argument("--dir", default="backups", help="Directorio de backups")
    parser.add_argument("--keep", type=int, default=7, help="Numero de backups a mantener")
    
    args = parser.parse_args()
    
    try:
        backup_path = create_backup(backup_dir=args.dir, keep_last=args.keep)
        console.print("[bold green]Backup exitoso[/bold green]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[bold red]ERROR: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)
