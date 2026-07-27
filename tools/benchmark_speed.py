"""
Benchmark para identificar cuellos de botella
"""
import sys
sys.path.append('src')
import time
from rag_hybrid import HybridRAG

print("\n" + "="*80)
print("BENCHMARK: Identificando cuellos de botella")
print("="*80)

# Inicializar sistema
print("\n[1] Inicializando sistema...")
start = time.time()
rag = HybridRAG()
init_time = time.time() - start
print(f"Tiempo de inicializacion: {init_time:.2f}s")

# Test query simple
query = "Cuantos aerogeneradores tiene Kosten"
print(f"\n[2] Query de prueba: '{query}'")

# Medir búsqueda híbrida
print("\n[3] Busqueda hibrida...")
start = time.time()
results = rag.hybrid_search("Kosten", top_k=50)
search_time = time.time() - start
print(f"Tiempo de busqueda hibrida: {search_time:.2f}s")

# Medir re-ranking
print("\n[4] Re-ranking...")
start = time.time()
reranked = rag._rerank_results(query, results, top_k=50)
rerank_time = time.time() - start
print(f"Tiempo de re-ranking: {rerank_time:.2f}s")

# Saltar medición individual de LLM (está integrado en query)
llm_time = 0  # Se medirá en el total

# Query completa
print("\n[6] Query completa end-to-end...")
start = time.time()
result = rag.execute(query, top_k=20).to_query_result()
total_time = time.time() - start
print(f"Tiempo total: {total_time:.2f}s")

# Resumen
llm_time = total_time - search_time - rerank_time  # Estimar tiempo de LLM
print("\n" + "="*80)
print("RESUMEN DE TIEMPOS:")
print("="*80)
print(f"Busqueda hibrida:  {search_time:6.2f}s ({search_time/total_time*100:5.1f}%)")
print(f"Re-ranking:        {rerank_time:6.2f}s ({rerank_time/total_time*100:5.1f}%)")
print(f"LLM + otros:       {llm_time:6.2f}s ({llm_time/total_time*100:5.1f}%)")
print(f"-" * 80)
print(f"TOTAL:             {total_time:6.2f}s")

# Identificar cuello de botella
bottleneck = max([
    ("Busqueda hibrida", search_time),
    ("Re-ranking", rerank_time),
    ("LLM + otros", llm_time)
], key=lambda x: x[1])

print(f"\nCUELLO DE BOTELLA: {bottleneck[0]} ({bottleneck[1]:.2f}s)")
print("\nOPTIMIZACIONES RECOMENDADAS:")
if llm_time > 30:
    print("- LLM muy lento: Considera usar modelo mas pequeno o cuantizacion mayor")
    print("- Verifica que Ollama este usando GPU (nvidia-smi)")
if rerank_time > 1:
    print("- Re-ranking lento: Reducir top_k o mover re-ranker a GPU")
if search_time > 1:
    print("- Busqueda lenta: Optimizar ChromaDB o reducir tamano de BD")
print("="*80)
