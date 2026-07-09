#!/usr/bin/env python3
"""
Script de diagnóstico del pipeline RAG
Mide métricas base antes de optimizaciones
"""

import json
import time
import sys
import os
from pathlib import Path
from datetime import datetime

# Cambiar al directorio del script para encontrar modelos y config
script_dir = Path(__file__).parent
os.chdir(script_dir)

# Asegurar que src está en el path
sys.path.insert(0, str(script_dir / 'src'))

from rag_hybrid import HybridRAG
from utils import get_console

console = get_console()

# Consultas de prueba representativas
TEST_QUERIES = [
    "¿Qué es CISSP y cuáles son sus dominios?",
    "¿Qué es un SOC y cómo opera?",
    "¿Qué certificaciones son recomendadas para un puesto SOC?",
    "Dame información sobre frameworks de seguridad",
    "¿Qué es ISO 27001?",
    "¿Cómo funciona MITRE ATT&CK?",
    "¿Qué es el GDPR y qué implica?",
    "¿Qué es pentesting?",
    "Dame información sobre ethical hacking",
    "¿Qué frameworks existen para ciberseguridad?"
]


def diagnose_query(rag, query, idx):
    """Ejecuta una consulta y mide métricas detalladas"""
    
    metrics = {
        'query': query,
        'query_index': idx,
        'timestamp': datetime.now().isoformat(),
        'errors': []
    }
    
    try:
        # Ejecutar consulta completa (search + generation)
        t0 = time.time()
        response = rag.query(
            question=query,
            top_k=20,
            length_mode='short',
            use_llm=True
        )
        t_total = time.time() - t0
        metrics['total_time_seconds'] = round(t_total, 2)
        
        # Extraer respuesta
        answer = response.get('answer', '') if isinstance(response, dict) else str(response)
        metrics['response_size_chars'] = len(answer)
        
        # Obtener resultados de búsqueda del último llamado (almacenado en el objeto)
        results = getattr(rag, '_last_results', [])
        metrics['docs_retrieved'] = len(results)
        
        # Analizar scores de resultados
        if results:
            scores = []
            for r in results:
                score = r.get('final_score', r.get('rerank_score', r.get('hybrid_score', 0)))
                try:
                    scores.append(float(score))
                except:
                    pass
            
            if scores:
                metrics['score_min'] = round(min(scores), 3)
                metrics['score_max'] = round(max(scores), 3)
                metrics['score_avg'] = round(sum(scores) / len(scores), 3)
                metrics['docs_high_quality'] = len([s for s in scores if s > 0.50])
                metrics['docs_medium_quality'] = len([s for s in scores if 0.30 <= s <= 0.50])
                metrics['docs_low_quality'] = len([s for s in scores if s < 0.30])
                
                # Contar fuentes únicas
                sources = set()
                for r in results:
                    src = r.get('source', r.get('metadata', {}).get('source', 'Unknown'))
                    sources.add(src)
                metrics['unique_sources'] = len(sources)
            else:
                metrics['score_min'] = 0
                metrics['score_max'] = 0
                metrics['score_avg'] = 0
                metrics['docs_high_quality'] = 0
                metrics['docs_medium_quality'] = 0
                metrics['docs_low_quality'] = 0
                metrics['unique_sources'] = 0
        else:
            metrics['score_min'] = 0
            metrics['score_max'] = 0
            metrics['score_avg'] = 0
            metrics['docs_high_quality'] = 0
            metrics['docs_medium_quality'] = 0
            metrics['docs_low_quality'] = 0
            metrics['unique_sources'] = 0
        
        # Detectar problemas en respuesta
        if answer:
            has_truncation = (
                answer.rstrip().endswith('**') or
                answer.rstrip().endswith('##') or
                '¿Por qué la respuesta anterior' in answer or
                '¿Por qué?' in answer[-100:] or
                (len(answer) > 100 and not any(c in answer[-20:] for c in '.!?]'))
            )
            metrics['has_truncation'] = has_truncation
            
            # Contar repeticiones de frase negativa
            negative_count = answer.lower().count('no se encontró información')
            metrics['negative_phrase_count'] = negative_count
            
            # Detectar contradicciones
            has_contradiction = (
                '¿Por qué?' in answer and 'No se encontró' in answer[:300]
            )
            metrics['has_contradiction'] = has_contradiction
        else:
            metrics['has_truncation'] = False
            metrics['negative_phrase_count'] = 0
            metrics['has_contradiction'] = False
            
    except Exception as e:
        metrics['errors'].append(f"General error: {str(e)}")
        import traceback
        metrics['errors'].append(traceback.format_exc())
    
    return metrics


def run_diagnosis():
    """Ejecuta diagnóstico completo"""
    
    console.print("[bold cyan]DIAGNÓSTICO DEL PIPELINE RAG[/bold cyan]")
    console.print("=" * 60)
    
    # Inicializar RAG
    console.print("\n[dim]Inicializando sistema RAG...[/dim]")
    try:
        config_path = str(Path(__file__).parent / "config.yaml")
        rag = HybridRAG(config_path=config_path, use_llm=True)
        console.print("[green]OK: Sistema RAG inicializado[/green]")
    except Exception as e:
        console.print(f"[red]ERROR: No se pudo inicializar RAG: {e}[/red]")
        return None
    
    # Ejecutar consultas de prueba
    all_metrics = []
    
    console.print(f"\n[bold]Ejecutando {len(TEST_QUERIES)} consultas de prueba...[/bold]\n")
    
    for idx, query in enumerate(TEST_QUERIES, 1):
        console.print(f"[cyan]{idx}/{len(TEST_QUERIES)}[/cyan] {query[:60]}...")
        
        metrics = diagnose_query(rag, query, idx)
        all_metrics.append(metrics)
        
        # Mostrar resumen rápido
        status = "[green]OK[/green]" if not metrics.get('errors') else "[yellow]WARN[/yellow]"
        if metrics.get('has_truncation') or metrics.get('has_contradiction'):
            status = "[red]ISSUE[/red]"
        
        console.print(f"  {status} Docs: {metrics.get('docs_retrieved', 0)} | "
                     f"Score avg: {metrics.get('score_avg', 0):.3f} | "
                     f"Time: {metrics.get('total_time_seconds', 0):.1f}s | "
                     f"Issues: {metrics.get('negative_phrase_count', 0)}")
        
        if metrics.get('errors'):
            for err in metrics['errors']:
                console.print(f"  [red]  - {err}[/red]")
    
    # Calcular estadísticas agregadas
    summary = {
        'timestamp': datetime.now().isoformat(),
        'total_queries': len(TEST_QUERIES),
        'successful_queries': len([m for m in all_metrics if not m.get('errors')]),
        'queries_with_truncation': len([m for m in all_metrics if m.get('has_truncation')]),
        'queries_with_contradiction': len([m for m in all_metrics if m.get('has_contradiction')]),
        'avg_docs_retrieved': round(sum(m.get('docs_retrieved', 0) for m in all_metrics) / len(all_metrics), 1),
        'avg_score': round(sum(m.get('score_avg', 0) for m in all_metrics) / len(all_metrics), 3),
        'avg_context_size': round(sum(m.get('context_size_chars', 0) for m in all_metrics) / len(all_metrics), 0),
        'avg_response_size': round(sum(m.get('response_size_chars', 0) for m in all_metrics) / len(all_metrics), 0),
        'avg_total_time': round(sum(m.get('total_time_seconds', 0) for m in all_metrics) / len(all_metrics), 2),
    }
    
    # Guardar resultados
    results = {
        'summary': summary,
        'queries': all_metrics
    }
    
    output_path = Path('pipeline_baseline.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    # Mostrar resumen final
    console.print("\n" + "=" * 60)
    console.print("[bold green]DIAGNÓSTICO COMPLETADO[/bold green]")
    console.print("=" * 60)
    console.print(f"\n[bold]Resumen:[/bold]")
    console.print(f"  Consultas ejecutadas: {summary['total_queries']}")
    console.print(f"  Exitosas: {summary['successful_queries']}")
    console.print(f"  Con truncamiento: {summary['queries_with_truncation']}")
    console.print(f"  Con contradicción: {summary['queries_with_contradiction']}")
    console.print(f"\n[bold]Métricas promedio:[/bold]")
    console.print(f"  Documentos recuperados: {summary['avg_docs_retrieved']}")
    console.print(f"  Score promedio: {summary['avg_score']}")
    console.print(f"  Tamaño de contexto: {summary['avg_context_size']:.0f} chars")
    console.print(f"  Tamaño de respuesta: {summary['avg_response_size']:.0f} chars")
    console.print(f"  Tiempo total: {summary['avg_total_time']:.2f}s")
    console.print(f"\n[dim]Resultados guardados en: {output_path.absolute()}[/dim]")
    
    return results


if __name__ == "__main__":
    results = run_diagnosis()
    if results:
        sys.exit(0)
    else:
        sys.exit(1)
