#!/usr/bin/env python3
"""
Diagnóstico exhaustivo del reranker BAAI-bge-reranker-v2-m3
Mide tiempos, batch sizes, uso de GPU/CPU, y VRAM.
"""

import sys
import os
import time
import torch
from pathlib import Path

# Configurar paths
script_dir = Path(__file__).parent
os.chdir(script_dir)
sys.path.insert(0, str(script_dir / 'src'))

from sentence_transformers import CrossEncoder


def diagnose_reranker():
    print("="*70)
    print("DIAGNÓSTICO DEL RERANKER BAAI-bge-reranker-v2-m3")
    print("="*70)
    
    # Info del sistema
    print("\n[1] INFORMACIÓN DEL SISTEMA")
    print("-"*40)
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA disponible: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA version: {torch.version.cuda}")
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"VRAM total: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")
        print(f"VRAM reservada: {torch.cuda.memory_reserved(0) / 1024**3:.2f} GB")
        print(f"VRAM asignada: {torch.cuda.memory_allocated(0) / 1024**3:.2f} GB")
    else:
        print("WARNING: CUDA no disponible - el modelo correrá en CPU (muy lento)")
    
    # Cargar modelo
    print("\n[2] CARGA DEL MODELO")
    print("-"*40)
    model_path = "models/BAAI-bge-reranker-v2-m3"
    print(f"Ruta: {model_path}")
    
    t0 = time.time()
    try:
        # Cargar igual que en el sistema
        model = CrossEncoder(
            model_path, 
            max_length=512,
            device="cuda" if torch.cuda.is_available() else "cpu"
        )
        load_time = time.time() - t0
        print(f"Tiempo de carga: {load_time:.2f}s")
        # CrossEncoder no expone device directamente, verificamos mediante torch
        if torch.cuda.is_available():
            print(f"CUDA disponible: Sí (modelo debería estar en GPU)")
        else:
            print(f"CUDA disponible: No (modelo en CPU)")
    except Exception as e:
        print(f"ERROR al cargar: {e}")
        return
    
    # Preparar datos de prueba
    print("\n[3] PREPARANDO DATOS DE PRUEBA")
    print("-"*40)
    
    # Simular pares (query, doc) típicos del sistema
    query = "¿Qué es CISSP y cuáles son sus dominios?"
    docs = [
        "CISSP (Certified Information Systems Security Professional) es una certificación de seguridad de la información.",
        "El CISSP cubre 8 dominios: Seguridad y Gestión de Riesgos, Seguridad de Activos, etc.",
        "Para obtener CISSP se necesitan 5 años de experiencia en 2 o más dominios.",
        "El examen CISSP tiene 250 preguntas y dura 6 horas.",
        "(ISC)² es la organización que administra la certificación CISSP.",
        "CISSP es reconocida mundialmente como estándar de oro en seguridad.",
        "Los dominios de CISSP incluyen: Seguridad de Redes, Desarrollo Seguro, etc.",
        "CISM es otra certificación relacionada pero con enfoque en gestión.",
        "CEH es más técnico y ofensivo comparado con CISSP que es gestión.",
        "La recertificación CISSP requiere CPEs continuos.",
    ]
    
    pairs = [[query, doc] for doc in docs]
    print(f"Query: {query}")
    print(f"Documentos: {len(docs)}")
    print(f"Longitudes: {[len(d) for d in docs]}")
    
    # Test con diferentes batch sizes
    print("\n[4] TEST DE BATCH SIZES")
    print("-"*40)
    
    results = []
    batch_sizes = [4, 8, 12, 16]
    
    for bs in batch_sizes:
        print(f"\nBatch size: {bs}")
        try:
            # Warm up
            _ = model.predict(pairs[:2], batch_size=bs, show_progress_bar=False)
            if torch.cuda.is_available():
                torch.cuda.synchronize()
            
            # Medir
            t0 = time.time()
            scores = model.predict(pairs, batch_size=bs, show_progress_bar=False, convert_to_numpy=True)
            if torch.cuda.is_available():
                torch.cuda.synchronize()
            elapsed = time.time() - t0
            
            vram_used = torch.cuda.memory_allocated(0) / 1024**3 if torch.cuda.is_available() else 0
            
            print(f"  Tiempo: {elapsed:.3f}s")
            print(f"  Scores: {scores.tolist()}")
            print(f"  VRAM usada: {vram_used:.2f} GB")
            
            results.append({
                'batch_size': bs,
                'time': elapsed,
                'vram': vram_used,
                'success': True
            })
            
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({
                'batch_size': bs,
                'time': None,
                'vram': None,
                'success': False,
                'error': str(e)
            })
    
    # Test con truncamiento de texto
    print("\n[5] TEST DE LONGITUD DE TEXTO (batch_size=8)")
    print("-"*40)
    
    max_lengths = [128, 256, 512]
    
    for max_len in max_lengths:
        print(f"\nMax length: {max_len}")
        try:
            # Truncar documentos
            truncated_docs = [d[:max_len] for d in docs]
            truncated_pairs = [[query, doc] for doc in truncated_docs]
            
            t0 = time.time()
            scores = model.predict(truncated_pairs, batch_size=8, show_progress_bar=False)
            if torch.cuda.is_available():
                torch.cuda.synchronize()
            elapsed = time.time() - t0
            
            print(f"  Tiempo: {elapsed:.3f}s")
            print(f"  Scores sample: {scores[:3].tolist()}")
            
        except Exception as e:
            print(f"  ERROR: {e}")
    
    # Resumen
    print("\n" + "="*70)
    print("RESUMEN")
    print("="*70)
    
    successful = [r for r in results if r['success']]
    if successful:
        fastest = min(successful, key=lambda x: x['time'])
        print(f"\nConfiguración más rápida: batch_size={fastest['batch_size']}")
        print(f"Tiempo: {fastest['time']:.3f}s")
        print(f"VRAM: {fastest['vram']:.2f} GB")
        
        # Recomendación
        if fastest['time'] > 10.0:
            print("\n⚠️  RECOMENDACIÓN: El reranker tarda más de 10s.")
            print("    Opciones:")
            print("    1. Reducir candidatos a rankear (top-5 en vez de top-10)")
            print("    2. Truncar textos a 256 tokens")
            print("    3. Subir timeout a 20s")
            print("    4. Considerar modelo más liviano (bge-reranker-base)")
        elif fastest['time'] > 5.0:
            print("\n⚠️  ADVERTENCIA: Tiempo marginal (5-10s). Considerar optimizaciones.")
        else:
            print("\n✅ OK: Tiempo aceptable (<5s). El timeout actual de 10s es suficiente.")
            print("    Posible causa del timeout: otros procesos o carga del sistema.")
    
    print("\n" + "="*70)


if __name__ == "__main__":
    diagnose_reranker()
