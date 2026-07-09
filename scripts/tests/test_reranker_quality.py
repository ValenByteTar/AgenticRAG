"""
Test controlado de calidad del reranker.
Objetivo: tomar fragmentos REALES de un PDF, hacer consultas exactas,
y verificar que los scores son coherentes en cada etapa.
"""
import sys, os, json, time, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, r'C:\Users\Valen\Desktop\Proyectos\Asunto RAG\SistemaGraniteEXP')
sys.path.insert(0, r'C:\Users\Valen\Desktop\Proyectos\Asunto RAG\SistemaGraniteEXP\src')
os.chdir(r'C:\Users\Valen\Desktop\Proyectos\Asunto RAG\SistemaGraniteEXP')

# Tee output a archivo
class Tee:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, data):
        for s in self.streams:
            s.write(data)
            s.flush()
    def flush(self):
        for s in self.streams:
            s.flush()

log_file = open('reranker_quality_test.log', 'w', encoding='utf-8')
sys.stdout = Tee(sys.stdout, log_file)

import yaml
from src.vector_store import VectorStore
from sentence_transformers import CrossEncoder
import torch
import numpy as np

# ==========================================
# PASO 1: Cargar ChromaDB y extraer chunks reales
# ==========================================
print("=" * 80)
print("TEST CONTROLADO DE CALIDAD DEL RERANKER")
print("=" * 80)

with open('config.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

vs = VectorStore(db_path=config['paths']['vectordb_dir'], collection_name=config['vectordb']['collection_name'])

# Elegir documento target
TARGET_DOC = "Firewall Checklist.pdf"
print(f"\n[PASO 1] Extrayendo chunks de: {TARGET_DOC}")

target_chunks = vs.collection.get(
    where={"source": TARGET_DOC}, 
    limit=50, 
    include=["documents", "metadatas"]
)

n_target = len(target_chunks["documents"])
print(f"  Chunks encontrados: {n_target}")

if n_target == 0:
    # Intentar variantes
    print("  Intentando variantes del nombre...")
    all_meta = vs.collection.get(limit=100, include=["metadatas"])
    sources = set()
    for m in all_meta["metadatas"]:
        s = m.get("source", "")
        if "firewall" in s.lower() or "checklist" in s.lower():
            sources.add(s)
    print(f"  Documentos similares: {sources}")
    if sources:
        TARGET_DOC = list(sources)[0]
        target_chunks = vs.collection.get(
            where={"source": TARGET_DOC},
            limit=50,
            include=["documents", "metadatas"]
        )
        n_target = len(target_chunks["documents"])
        print(f"  Usando: {TARGET_DOC} ({n_target} chunks)")

# Mostrar contenido de los chunks
print(f"\n  Contenido de los primeros 5 chunks:")
for i in range(min(5, n_target)):
    doc = target_chunks["documents"][i]
    meta = target_chunks["metadatas"][i]
    print(f"\n  --- CHUNK {i} | page={meta.get('page','?')} ---")
    print(f"  {doc[:250]}")
    print(f"  [len={len(doc)} chars]")

# ==========================================
# PASO 2: Extraer chunks de OTRO documento (ruido)
# ==========================================
NOISE_DOC = "100 Excel Functions you should know in one handy PDF.pdf"
print(f"\n[PASO 2] Extrayendo chunks de ruido: {NOISE_DOC}")

noise_chunks = vs.collection.get(
    where={"source": NOISE_DOC},
    limit=20,
    include=["documents", "metadatas"]
)
n_noise = len(noise_chunks["documents"])
print(f"  Chunks de ruido encontrados: {n_noise}")

if n_noise == 0:
    # Buscar cualquier doc que no sea firewall
    all_meta = vs.collection.get(limit=200, include=["metadatas"])
    noise_sources = set()
    for m in all_meta["metadatas"]:
        s = m.get("source", "")
        if "firewall" not in s.lower() and s != TARGET_DOC and len(s) > 5:
            noise_sources.add(s)
    if noise_sources:
        NOISE_DOC = list(noise_sources)[0]
        noise_chunks = vs.collection.get(
            where={"source": NOISE_DOC},
            limit=20,
            include=["documents", "metadatas"]
        )
        n_noise = len(noise_chunks["documents"])
        print(f"  Usando ruido de: {NOISE_DOC} ({n_noise} chunks)")

# ==========================================
# PASO 3: Construir consultas controladas
# ==========================================
print(f"\n[PASO 3] Construyendo consultas controladas")

# Tomar el chunk mas sustancial del target
best_chunk_idx = 0
best_chunk_len = 0
for i, doc in enumerate(target_chunks["documents"]):
    if len(doc) > best_chunk_len:
        best_chunk_len = len(doc)
        best_chunk_idx = i

target_text = target_chunks["documents"][best_chunk_idx]
target_meta = target_chunks["metadatas"][best_chunk_idx]

print(f"\n  Chunk objetivo (idx={best_chunk_idx}, page={target_meta.get('page','?')}):")
print(f"  {target_text[:400]}")
print(f"  [len={len(target_text)} chars]")

# Crear 3 tipos de consulta:
# A) Consulta EXACTA: copiar una frase literal del chunk
# B) Consulta PARAFRASEADA: reformular el contenido
# C) Consulta IRRELEVANTE: algo que no tiene nada que ver

# Extraer una frase del chunk para consulta exacta
sentences = [s.strip() for s in target_text.split('.') if len(s.strip()) > 30]
exact_query = sentences[0] + "." if sentences else target_text[:100]

queries = {
    "EXACTA": exact_query,
    "SEMANTICA": "What are the best practices for configuring and auditing firewall rules and policies?",
    "IRRELEVANTE": "How to make chocolate cake with vanilla frosting recipe step by step"
}

print(f"\n  Consultas:")
for qtype, q in queries.items():
    print(f"    [{qtype}]: {q[:120]}...")

# ==========================================
# PASO 4: Cargar reranker y embedder
# ==========================================
print(f"\n[PASO 4] Cargando modelos")

reranker = CrossEncoder(
    "models/BAAI-bge-reranker-v2-m3",
    max_length=512,
    device="cuda" if torch.cuda.is_available() else "cpu"
)
print(f"  Reranker cargado en {'GPU' if torch.cuda.is_available() else 'CPU'}")

# Cargar embedder para scores semanticos
from sentence_transformers import SentenceTransformer
emb_model = config['embeddings']['model_name']
embedder = SentenceTransformer(emb_model, device='cuda' if torch.cuda.is_available() else 'cpu')
embedder.max_seq_length = 512
print(f"  Embedder cargado: {emb_model}")

# ==========================================
# PASO 5: Construir pool de documentos (target + ruido)
# ==========================================
print(f"\n[PASO 5] Construyendo pool de documentos")

# Tomar hasta 5 chunks del target y 5 de ruido
pool = []
for i in range(min(5, n_target)):
    pool.append({
        "text": target_chunks["documents"][i],
        "source": TARGET_DOC,
        "page": target_chunks["metadatas"][i].get("page", "?"),
        "is_relevant": True,
        "label": f"TARGET_{i}"
    })

for i in range(min(5, n_noise)):
    pool.append({
        "text": noise_chunks["documents"][i],
        "source": NOISE_DOC,
        "page": noise_chunks["metadatas"][i].get("page", "?"),
        "is_relevant": False,
        "label": f"NOISE_{i}"
    })

print(f"  Pool: {len(pool)} documentos ({sum(1 for p in pool if p['is_relevant'])} target, {sum(1 for p in pool if not p['is_relevant'])} ruido)")

# ==========================================
# PASO 6: Evaluar scores en cada etapa
# ==========================================
print(f"\n[PASO 6] Evaluando scores por etapa")

for qtype, query in queries.items():
    print(f"\n{'='*80}")
    print(f"CONSULTA [{qtype}]: {query[:100]}...")
    print(f"{'='*80}")
    
    # --- 6a. Scores semanticos (cosine similarity via embedder) ---
    query_emb = embedder.encode(query, show_progress_bar=False)
    semantic_scores = []
    for doc in pool:
        doc_emb = embedder.encode(doc["text"][:512], show_progress_bar=False)
        # Cosine similarity
        cos_sim = np.dot(query_emb, doc_emb) / (np.linalg.norm(query_emb) * np.linalg.norm(doc_emb))
        semantic_scores.append(float(cos_sim))
    
    # --- 6b. Scores del reranker (CrossEncoder) ---
    pairs = [[query, doc["text"][:512]] for doc in pool]
    rerank_raw = reranker.predict(pairs, batch_size=12, show_progress_bar=False, convert_to_numpy=True)
    rerank_scores = [float(s) for s in rerank_raw]
    
    # --- 6c. Normalizacion min-max del reranker (como hace rag_hybrid.py) ---
    s_min = min(rerank_scores)
    s_max = max(rerank_scores)
    if s_max - s_min < 1e-9:
        import math
        rerank_norm = [1.0 / (1.0 + math.exp(-s)) for s in rerank_scores]
    else:
        rerank_norm = [(s - s_min) / (s_max - s_min) for s in rerank_scores]
    
    # --- 6d. Hybrid score simulado (60% semantic + 40% keyword, simplificado) ---
    # En el sistema real: hybrid = 0.6*semantic + 0.4*bm25_norm
    # Aquí simulamos sin BM25 para aislar el efecto
    hybrid_scores = [sem * 0.6 for sem in semantic_scores]  # Solo componente semántico
    
    # --- 6e. Final score (como lo calcula rag_hybrid.py: 50/50) ---
    final_scores = [(h * 0.5) + (rn * 0.5) for h, rn in zip(hybrid_scores, rerank_norm)]
    
    # --- Mostrar resultados ---
    print(f"\n  {'Label':<12} {'Source':<20} {'Relevant':<8} {'Semantic':<10} {'Rerank Raw':<12} {'Rerank Norm':<12} {'Hybrid':<10} {'Final':<10}")
    print(f"  {'-'*94}")
    
    # Ordenar por final_score para ver el ranking
    indices = list(range(len(pool)))
    indices.sort(key=lambda i: final_scores[i], reverse=True)
    
    for rank, i in enumerate(indices, 1):
        doc = pool[i]
        marker = ">>>" if doc["is_relevant"] else "   "
        print(f"{marker} #{rank:<2} {doc['label']:<12} {doc['source'][:18]:<20} {'SI' if doc['is_relevant'] else 'NO':<8} {semantic_scores[i]:<10.4f} {rerank_scores[i]:<12.4f} {rerank_norm[i]:<12.4f} {hybrid_scores[i]:<10.4f} {final_scores[i]:<10.4f}")
    
    # --- Diagnostico ---
    target_ranks = [rank for rank, i in enumerate(indices, 1) if pool[i]["is_relevant"]]
    noise_ranks = [rank for rank, i in enumerate(indices, 1) if not pool[i]["is_relevant"]]
    
    avg_target_rerank = np.mean([rerank_scores[i] for i in range(len(pool)) if pool[i]["is_relevant"]])
    avg_noise_rerank = np.mean([rerank_scores[i] for i in range(len(pool)) if not pool[i]["is_relevant"]])
    avg_target_final = np.mean([final_scores[i] for i in range(len(pool)) if pool[i]["is_relevant"]])
    avg_noise_final = np.mean([final_scores[i] for i in range(len(pool)) if not pool[i]["is_relevant"]])
    
    print(f"\n  DIAGNOSTICO:")
    print(f"    Posiciones TARGET: {target_ranks}")
    print(f"    Posiciones RUIDO:  {noise_ranks}")
    print(f"    Avg rerank raw  - TARGET: {avg_target_rerank:.4f} vs RUIDO: {avg_noise_rerank:.4f} (separacion: {avg_target_rerank - avg_noise_rerank:.4f})")
    print(f"    Avg final_score - TARGET: {avg_target_final:.4f} vs RUIDO: {avg_noise_final:.4f} (separacion: {avg_target_final - avg_noise_final:.4f})")
    
    # Verificar si la normalizacion destruye la separacion
    sep_raw = avg_target_rerank - avg_noise_rerank
    sep_final = avg_target_final - avg_noise_final
    if sep_raw > 0 and sep_final < sep_raw * 0.5:
        print(f"    !! ALERTA: La normalizacion/mezcla REDUCE la separacion en {((1 - sep_final/sep_raw)*100):.0f}%")
    
    # Verificar si algun doc de ruido supera a un target
    max_noise_final = max(final_scores[i] for i in range(len(pool)) if not pool[i]["is_relevant"])
    min_target_final = min(final_scores[i] for i in range(len(pool)) if pool[i]["is_relevant"])
    if max_noise_final > min_target_final:
        print(f"    !! ALERTA: Documento de RUIDO (final={max_noise_final:.4f}) SUPERA a un TARGET (final={min_target_final:.4f})")

print(f"\n{'='*80}")
print("TEST COMPLETADO")
print(f"{'='*80}")
