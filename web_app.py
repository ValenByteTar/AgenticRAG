"""
Frontend Web para Sistema RAG - Estilo Ollama
Interfaz minimalista con sidebar y chat
"""
from flask import Flask, render_template, request, jsonify, session, send_file, Response, stream_with_context
from flask_cors import CORS
import secrets
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from chromadb.config import Settings
from rag_hybrid import HybridRAG
import time
import threading
import queue
import re
import sys

# Agregar src al path para imports
sys.path.append('src')
from metrics_analyzer import MetricsAnalyzer

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
CORS(app)

# Deshabilitar logging de Flask para reducir ruido en consola
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)  # Solo mostrar errores, no requests normales

# Validacion de hardware al inicio
def validate_hardware():
    """Valida hardware disponible y muestra warnings si es necesario"""
    print("\n" + "="*60)
    print("VALIDACION DE HARDWARE")
    print("="*60)
    
    # Verificar GPU
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            vram_total_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
            
            print(f"GPU: {gpu_name}")
            print(f"VRAM: {vram_total_gb:.1f} GB")
            
            if vram_total_gb < 6:
                print("WARNING: VRAM < 6 GB - Rendimiento puede ser limitado")
            elif vram_total_gb < 12:
                print("INFO: VRAM suficiente para operacion basica")
            else:
                print("OK: VRAM adecuada para operacion optima")
        else:
            print("WARNING: GPU CUDA no disponible - Usando CPU")
            print("INFO: Embeddings se procesaran en CPU (mas lento)")
    except ImportError:
        print("WARNING: PyTorch no instalado - No se puede verificar GPU")
    
    # Verificar espacio en disco
    import shutil
    disk_usage = shutil.disk_usage(".")
    free_gb = disk_usage.free / 1024**3
    
    print(f"Disco libre: {free_gb:.1f} GB")
    
    if free_gb < 10:
        print("ERROR: Espacio en disco critico (< 10 GB)")
    elif free_gb < 20:
        print("WARNING: Espacio en disco bajo (< 20 GB)")
    else:
        print("OK: Espacio en disco suficiente")
    
    # Verificar ChromaDB
    chroma_path = Path("chroma_bge_m3")
    if chroma_path.exists():
        chunk_count = "desconocido"
        try:
            # Intentar contar documentos (aproximado)
            import chromadb
            client = chromadb.PersistentClient(path=str(chroma_path), settings=Settings(anonymized_telemetry=False))
            collection = client.get_collection("cybersec_docs_bge_m3")
            chunk_count = collection.count()
        except Exception:
            pass
        
        print(f"ChromaDB: OK ({chunk_count} documentos)")
    else:
        print("WARNING: ChromaDB no encontrado - Ejecutar build_rag_system.py")
    
    print("="*60 + "\n")

validate_hardware()

# Inicializar RAG (forzar BGE con heurísticas balanceadas)
print("Inicializando sistema RAG (BGE, heuristicas balanced)...")
rag = HybridRAG(variant="bge", heuristics="balanced")

# Sistema de cola de peticiones
class QueryQueue:
    """Cola de peticiones para procesamiento secuencial con feedback"""
    def __init__(self):
        self.queue = queue.Queue()
        self.active_queries = {}
        self.query_counter = 0
        self.lock = threading.Lock()
        
    def add_query(self, query_data):
        """Agrega consulta a la cola y retorna ID"""
        with self.lock:
            self.query_counter += 1
            query_id = f"q_{self.query_counter}_{secrets.token_hex(4)}"
            query_data['id'] = query_id
            query_data['status'] = 'queued'
            query_data['position'] = self.queue.qsize() + 1
            query_data['queued_at'] = time.time()
            self.active_queries[query_id] = query_data
            self.queue.put(query_data)
            return query_id
    
    def get_status(self, query_id):
        """Obtiene estado de una consulta"""
        with self.lock:
            if query_id in self.active_queries:
                return self.active_queries[query_id]
            return None
    
    def update_status(self, query_id, status, **kwargs):
        """Actualiza estado de una consulta"""
        with self.lock:
            if query_id in self.active_queries:
                self.active_queries[query_id]['status'] = status
                self.active_queries[query_id].update(kwargs)
    
    def complete_query(self, query_id, result):
        """Marca consulta como completada"""
        with self.lock:
            if query_id in self.active_queries:
                self.active_queries[query_id]['status'] = 'completed'
                self.active_queries[query_id]['result'] = result
                self.active_queries[query_id]['completed_at'] = time.time()
    
    def get_queue_size(self):
        """Retorna tamaño actual de la cola"""
        return self.queue.qsize()

# Inicializar cola global
query_queue = QueryQueue()

# Inicializar analizador de metricas
metrics_analyzer = MetricsAnalyzer()

# Almacenar historial de chats
chats_file = Path("data/chats.json")
chats_file.parent.mkdir(exist_ok=True)

def load_chats():
    """Cargar chats guardados"""
    if chats_file.exists():
        with open(chats_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_chats(chats):
    """Guardar chats"""
    with open(chats_file, 'w', encoding='utf-8') as f:
        json.dump(chats, f, ensure_ascii=False, indent=2)

# Registro de streams activos para cancelación cooperativa
active_streams = {}

@app.route('/')
def index():
    """Página principal"""
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    """Endpoint para procesar consultas"""
    try:
        data = request.json
        query = data.get('query', '')
        chat_id = data.get('chat_id', None)
        length_mode = data.get('length_mode', 'short')
        no_context = bool(data.get('no_context', False))
        
        if not query:
            return jsonify({'error': 'Query vacío'}), 400
        
        # Procesar consulta con RAG (ADR-0020)
        t0 = time.time()
        # Forzar long si no_context está activo, para tu experimento
        if no_context:
            length_mode = 'long'
        sw = float(rag.config.get('retrieval', {}).get('semantic_weight', 0.6))
        exec_res = rag.execute(
            query,
            top_k=10,
            semantic_weight=sw,
            length_mode=length_mode,
            no_context=no_context
        )
        result = exec_res.to_query_result()
        elapsed_s = max(0.0, time.time() - t0)
        response = result.get('answer', 'No se pudo generar respuesta')
        # Sanear respuesta: remover duplicación de citas "(según [Doc ...])" y variantes en línea,
        # y eliminar marcas entre corchetes tipo "[Doc ...]" dentro del cuerpo (las fuentes se muestran aparte).
        def _sanitize_answer(text: str) -> str:
            if not isinstance(text, str) or not text:
                return text
            txt = text
            # 1) Remover paréntesis que contengan la palabra 'según/segun' (cualquier contenido adentro)
            txt = re.sub(r"\s*\((?=[^)]*(según|segun))[^)]*\)", "", txt, flags=re.IGNORECASE)
            # 2) Remover frases en línea: ", según [Doc ...]" o " según [Doc ...] y [Doc ...]"
            txt = re.sub(r"[,;]?\s*(según|segun)\s+\[Doc[^\]\n]+\](?:\s*(?:y|,)\s*\[Doc[^\]\n]+\])*", "", txt, flags=re.IGNORECASE)
            # 3) Remover marcas de cita internas entre corchetes: "[Doc ...]" (case-insensitive)
            txt = re.sub(r"\s*\[\s*Doc[^\]]+\]", "", txt, flags=re.IGNORECASE)
            # 3b) Evitar expansiones inventadas de siglas críticas de ciberseguridad
            #    Cualquier expansión entre paréntesis luego de estas siglas se elimina.
            txt = re.sub(r"\b(CVE|CVSS|MITRE|NIST|CISA)\s*\([^)]*\)", r"\1", txt, flags=re.IGNORECASE)
            # 4) Normalizar espacios y saltos de línea repetidos
            txt = re.sub(r"\s+\n", "\n", txt)
            txt = re.sub(r"\n{3,}", "\n\n", txt)
            txt = re.sub(r"[ \t]{2,}", " ", txt)
            return txt.strip()
        response = _sanitize_answer(response)
        sources = result.get('results', [])[:5]  # Top 5 fuentes
        
        # Formatear fuentes como links clicables
        sources_formatted = []
        for src in sources:
            metadata = src.get('metadata', {})
            source_name = metadata.get('source', 'Unknown')
            
            # Extraer solo el nombre del archivo (sin ruta)
            if source_name != 'Unknown':
                source_name = Path(source_name).name
            
            page = metadata.get('page', 1)
            # Mostrar score final si existe (re-rank + híbrido), sino híbrido
            score = src.get('final_score', src.get('hybrid_score', 0))
            sources_formatted.append({
                'name': source_name,
                'page': page,
                'score': round(score, 2),
                'text_preview': src.get('text', '')[:150] + '...'
            })
        
        # Guardar en historial
        chats = load_chats()
        
        if chat_id:
            # Actualizar chat existente
            for chat in chats:
                if chat['id'] == chat_id:
                    chat['messages'].append({
                        'role': 'user',
                        'content': query,
                        'timestamp': datetime.now().isoformat()
                    })
                    chat['messages'].append({
                        'role': 'assistant',
                        'content': response,
                        'timestamp': datetime.now().isoformat()
                    })
                    chat['updated_at'] = datetime.now().isoformat()
                    break
        else:
            # Crear nuevo chat
            chat_id = secrets.token_hex(8)
            new_chat = {
                'id': chat_id,
                'title': query[:50] + ('...' if len(query) > 50 else ''),
                'messages': [
                    {
                        'role': 'user',
                        'content': query,
                        'timestamp': datetime.now().isoformat()
                    },
                    {
                        'role': 'assistant',
                        'content': response,
                        'timestamp': datetime.now().isoformat()
                    }
                ],
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            chats.insert(0, new_chat)
        
        save_chats(chats)
        
        return jsonify({
            'response': response,
            'chat_id': chat_id,
            'sources': sources_formatted,
            'length_mode': length_mode,
            'no_context': no_context,
            'latency_ms': int(elapsed_s * 1000),
            'latency_s': round(elapsed_s, 2)
        })
        
    except Exception as e:
        import traceback
        print(f"\n[ERROR] Error en /api/chat:")
        print(f"Query: {query}")
        print(f"Error: {str(e)}")
        print(f"Traceback:")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat/stream', methods=['POST'])
def chat_stream():
    try:
        data = request.json or {}
        query = data.get('query', '')
        chat_id = data.get('chat_id', None)
        length_mode = data.get('length_mode', 'short')
        no_context = bool(data.get('no_context', False))

        if not query:
            return jsonify({'error': 'Query vacío'}), 400

        q = queue.Queue()
        done = threading.Event()
        # ID único del stream y evento de cancelación
        stream_id = secrets.token_hex(8)
        cancel_event = threading.Event()
        active_streams[stream_id] = cancel_event
        start_ts = time.time()

        # Sanitizador igual al endpoint normal
        def _sanitize_answer(text: str) -> str:
            if not isinstance(text, str) or not text:
                return text
            txt = text
            txt = re.sub(r"\s*\((?=[^)]*(según|segun))[^)]*\)", "", txt, flags=re.IGNORECASE)
            txt = re.sub(r"[,;]?\s*(según|segun)\s+\[Doc[^\]\n]+\](?:\s*(?:y|,)\s*\[Doc[^\]\n]+\])*", "", txt, flags=re.IGNORECASE)
            txt = re.sub(r"\s*\[\s*Doc[^\]]+\]", "", txt, flags=re.IGNORECASE)
            # Evitar expansiones inventadas de siglas críticas de ciberseguridad
            txt = re.sub(r"\b(CVE|CVSS|MITRE|NIST|CISA)\s*\([^)]*\)", r"\1", txt, flags=re.IGNORECASE)
            txt = re.sub(r"\s+\n", "\n", txt)
            txt = re.sub(r"\n{3,}", "\n\n", txt)
            txt = re.sub(r"[ \t]{2,}", " ", txt)
            return txt.strip()

        def token_cb(tok: str):
            try:
                # Si se canceló, no encolar más tokens
                if cancel_event.is_set():
                    return
                q.put_nowait(json.dumps({'event': 'token', 'token': tok}))
            except Exception:
                pass

        def docs_cb(docs_list):
            try:
                if cancel_event.is_set():
                    return
                q.put_nowait(json.dumps({'event': 'docs', 'docs': docs_list}))
            except Exception:
                pass

        result_holder = {'result': None}

        def worker():
            try:
                sw = float(rag.config.get('retrieval', {}).get('semantic_weight', 0.6))
                exec_res = rag.execute(
                    query,
                    top_k=10,
                    semantic_weight=sw,
                    length_mode=length_mode,
                    no_context=no_context,
                    stream=True,
                    token_callback=token_cb,
                    docs_callback=docs_cb,
                    cancel_checker=lambda: cancel_event.is_set()
                )
                res = exec_res.to_query_result()
                result_holder['result'] = res

                # Formatear fuentes como en /api/chat
                sources = (res or {}).get('results', [])[:5]
                sources_formatted = []
                for src in sources:
                    metadata = src.get('metadata', {})
                    source_name = metadata.get('source', 'Unknown')
                    if source_name != 'Unknown':
                        source_name = Path(source_name).name
                    page = metadata.get('page', 1)
                    score = src.get('final_score', src.get('hybrid_score', 0))
                    sources_formatted.append({
                        'name': source_name,
                        'page': page,
                        'score': round(score, 2),
                        'text_preview': src.get('text', '')[:150] + '...'
                    })

                answer = _sanitize_answer((res or {}).get('answer', '') or '')

                # Guardar en historial igual que /api/chat
                chats = load_chats()
                out_chat_id = chat_id
                if out_chat_id:
                    for chat in chats:
                        if chat['id'] == out_chat_id:
                            chat['messages'].append({'role': 'user', 'content': query, 'timestamp': datetime.now().isoformat()})
                            chat['messages'].append({'role': 'assistant', 'content': answer, 'timestamp': datetime.now().isoformat()})
                            chat['updated_at'] = datetime.now().isoformat()
                            break
                else:
                    out_chat_id = secrets.token_hex(8)
                    new_chat = {
                        'id': out_chat_id,
                        'title': query[:50] + ('...' if len(query) > 50 else ''),
                        'messages': [
                            {'role': 'user', 'content': query, 'timestamp': datetime.now().isoformat()},
                            {'role': 'assistant', 'content': answer, 'timestamp': datetime.now().isoformat()},
                        ],
                        'created_at': datetime.now().isoformat(),
                        'updated_at': datetime.now().isoformat()
                    }
                    chats.insert(0, new_chat)
                save_chats(chats)

                if not cancel_event.is_set():
                    q.put(json.dumps({
                        'event': 'done',
                        'response': answer,
                        'chat_id': out_chat_id,
                        'sources': sources_formatted,
                        'length_mode': length_mode,
                        'no_context': no_context,
                        'latency_s': round(max(0.0, time.time() - start_ts), 2)
                    }))
            except Exception as e:
                if not cancel_event.is_set():
                    q.put(json.dumps({'event': 'error', 'message': str(e)}))
            finally:
                done.set()

        threading.Thread(target=worker, daemon=True).start()

        def stream_gen():
            # Anunciar inicio incluyendo stream_id para cancelación
            yield json.dumps({'event': 'start', 'stream_id': stream_id}) + '\n'
            while not done.is_set() or not q.empty():
                try:
                    item = q.get(timeout=0.2)
                    yield item + '\n'
                except queue.Empty:
                    continue
            # Limpieza al finalizar
            try:
                active_streams.pop(stream_id, None)
            except Exception:
                pass

        return Response(stream_with_context(stream_gen()), mimetype='application/x-ndjson')
    except Exception as e:
        import traceback
        print(f"\n[ERROR] Error en /api/chat/stream: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat/cancel/<stream_id>', methods=['POST'])
def cancel_stream(stream_id):
    try:
        ev = active_streams.get(stream_id)
        if ev:
            ev.set()
            return jsonify({'ok': True, 'cancelled': True})
        return jsonify({'ok': True, 'cancelled': False}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chats', methods=['GET'])
def get_chats():
    """Obtener lista de chats"""
    chats = load_chats()
    return jsonify(chats)

@app.route('/api/chats/<chat_id>', methods=['GET'])
def get_chat(chat_id):
    """Obtener un chat específico"""
    chats = load_chats()
    for chat in chats:
        if chat['id'] == chat_id:
            return jsonify(chat)
    return jsonify({'error': 'Chat no encontrado'}), 404

@app.route('/api/chats/<chat_id>', methods=['DELETE'])
def delete_chat(chat_id):
    """Eliminar un chat"""
    chats = load_chats()
    chats = [c for c in chats if c['id'] != chat_id]
    save_chats(chats)
    return jsonify({'success': True})

@app.route('/api/chats/<chat_id>/rename', methods=['PUT'])
def rename_chat(chat_id):
    """Renombrar un chat"""
    try:
        data = request.get_json()
        new_title = data.get('title', '').strip()
        
        if not new_title:
            return jsonify({'error': 'Título vacío'}), 400
        
        chats = load_chats()
        for chat in chats:
            if chat['id'] == chat_id:
                chat['title'] = new_title
                save_chats(chats)
                return jsonify({'success': True})
        
        return jsonify({'error': 'Chat no encontrado'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chats/clear', methods=['DELETE'])
def clear_all_chats():
    """Eliminar todos los chats (útil para testing)"""
    try:
        save_chats([])
        return jsonify({'success': True, 'message': 'Historial limpiado'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/vector-stats', methods=['GET'])
def vector_stats():
    """Estadísticas de la base vectorial y top fuentes"""
    try:
        stats = rag.vector_store.get_stats()
        # Contar top fuentes
        data = rag.vector_store.collection.get()
        sources = [md.get('source', 'Unknown') for md in data.get('metadatas', [])]
        counts = {}
        for s in sources:
            counts[s] = counts.get(s, 0) + 1
        top_sources = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10]
        dim = 0
        try:
            dim = rag.embedder.get_embedding_dim()
        except Exception:
            pass
        return jsonify({
            'total_chunks': stats.get('total_chunks', 0),
            'collection_name': stats.get('collection_name'),
            'db_path': stats.get('db_path'),
            'embedding_dim': dim,
            'top_sources': [{'source': k, 'count': v} for k, v in top_sources]
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/open-pdf', methods=['POST'])
def open_pdf():
    """Abrir PDF en página específica"""
    try:
        data = request.json
        pdf_name = data.get('pdf_name', '')
        page = data.get('page', 1)
        
        if not pdf_name:
            return jsonify({'error': 'Nombre de PDF requerido'}), 400
        
        # Buscar PDF en directorio de protocolos
        pdf_path = Path('protocolosPDF') / pdf_name
        
        if not pdf_path.exists():
            return jsonify({'error': f'PDF no encontrado: {pdf_name}'}), 404
        
        # Abrir PDF en página específica
        pdf_path_abs = pdf_path.absolute()
        
        try:
            # Construir URL de archivo con cache-busting y página: ?v=ts#page=N
            ts = int(time.time())
            pdf_url = f'file:///{str(pdf_path_abs).replace(chr(92), "/")}?v={ts}#page={page}'
            
            # Preferir Microsoft Edge para respetar #page y forzar nueva ventana
            possible_edge_paths = [
                r"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
                r"C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
            ]
            edge_opened = False
            for edge_path in possible_edge_paths:
                if os.path.exists(edge_path):
                    # Abrir en nueva ventana para evitar reutilizar pestaña con otra página
                    subprocess.Popen([edge_path, "--new-window", pdf_url])
                    edge_opened = True
                    break
            if not edge_opened:
                # Fallback 1: protocolo de Edge (puede reutilizar pestaña)
                try:
                    subprocess.Popen(['powershell', '-Command', f'Start-Process microsoft-edge:"{pdf_url}"'])
                    edge_opened = True
                except Exception:
                    pass
            if not edge_opened:
                # Fallback 2: navegador por defecto
                import webbrowser
                webbrowser.open(pdf_url)
            
            return jsonify({
                'success': True, 
                'message': f'Abriendo {pdf_name} en página {page}'
            })
        except Exception as e:
            # Fallback: abrir con aplicación predeterminada (sin página específica)
            try:
                os.startfile(str(pdf_path_abs))
                return jsonify({
                    'success': True,
                    'message': f'PDF abierto (navega manualmente a pág. {page})',
                    'warning': 'No se pudo abrir en página específica'
                })
            except Exception as e2:
                raise Exception(f'Error abriendo PDF: {str(e2)}')
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/queue/status/<query_id>', methods=['GET'])
def queue_status(query_id):
    """Obtener estado de una consulta en la cola"""
    try:
        status = query_queue.get_status(query_id)
        if status:
            return jsonify(status)
        else:
            return jsonify({'error': 'Query ID no encontrado'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/queue/info', methods=['GET'])
def queue_info():
    """Obtener información general de la cola"""
    try:
        return jsonify({
            'queue_size': query_queue.get_queue_size(),
            'timestamp': time.time()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/metrics/summary', methods=['GET'])
def metrics_summary():
    """Obtener resumen de metricas del sistema"""
    try:
        hours = int(request.args.get('hours', 24))
        summary = metrics_analyzer.get_summary(hours=hours)
        return jsonify(summary)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/metrics/health', methods=['GET'])
def metrics_health():
    """Obtener estado de salud del sistema"""
    try:
        import shutil
        
        # Espacio en disco
        disk_usage = shutil.disk_usage(".")
        free_gb = disk_usage.free / 1024**3
        total_gb = disk_usage.total / 1024**3
        
        # GPU (si esta disponible)
        gpu_info = {'available': False}
        try:
            import torch
            if torch.cuda.is_available():
                gpu_info = {
                    'available': True,
                    'name': torch.cuda.get_device_name(0),
                    'vram_total_gb': round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 1),
                    'vram_allocated_gb': round(torch.cuda.memory_allocated(0) / 1024**3, 1)
                }
        except Exception:
            pass
        
        # ChromaDB
        chroma_path = Path("chroma_bge_m3")
        chroma_size_mb = 0
        if chroma_path.exists():
            chroma_size_mb = sum(f.stat().st_size for f in chroma_path.rglob("*") if f.is_file()) / 1024 / 1024
        
        return jsonify({
            'disk': {
                'free_gb': round(free_gb, 1),
                'total_gb': round(total_gb, 1),
                'percent_free': round((free_gb / total_gb) * 100, 1)
            },
            'gpu': gpu_info,
            'chromadb': {
                'exists': chroma_path.exists(),
                'size_mb': round(chroma_size_mb, 1)
            },
            'queue': {
                'size': query_queue.get_queue_size()
            },
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/shutdown', methods=['POST'])
def shutdown():
    """Cerrar servidor"""
    import os
    import signal
    
    print("\n[INFO] Cerrando servidor...")
    os.kill(os.getpid(), signal.SIGINT)
    return jsonify({'message': 'Servidor cerrándose...'})

# Servir sonido de notificación listo desde raíz del proyecto
@app.route('/ReadySound')
def ready_sound():
    try:
        path = Path('ReadySound.mp3')
        if not path.exists():
            return jsonify({'error': 'ReadySound.mp3 no encontrado'}), 404
        return send_file(str(path), mimetype='audio/mpeg')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    import webbrowser
    import threading
    
    # Abrir navegador automáticamente (Microsoft Edge)
    def open_browser():
        import time
        import os
        import subprocess
        time.sleep(1.5)
        
        url = 'http://localhost:5000'
        edge_opened = False
        
        try:
            # Intentar abrir en Microsoft Edge - buscar en ubicaciones comunes
            possible_edge_paths = [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            ]
            
            for edge_path in possible_edge_paths:
                if os.path.exists(edge_path):
                    # Abrir SIEMPRE en NUEVA ventana
                    subprocess.Popen([edge_path, "--new-window", url])
                    edge_opened = True
                    break
            
            # Si no se encontró Edge en las rutas comunes, usar PowerShell
            if not edge_opened:
                # Intentar abrir Edge con nueva ventana usando PowerShell
                try:
                    subprocess.Popen(['powershell', '-Command', f'Start-Process msedge "--new-window {url}"'])
                    edge_opened = True
                except Exception:
                    # Fallback al protocolo (puede reutilizar ventana)
                    subprocess.Popen(['powershell', '-Command', f'Start-Process microsoft-edge:"{url}"'])
                    edge_opened = True
                
        except Exception as e:
            print(f"[WARN] No se pudo abrir Edge: {e}")
            # Fallback: navegador por defecto
            try:
                webbrowser.open(url)
            except:
                print("[ERROR] No se pudo abrir ningún navegador automáticamente")
                print(f"Por favor, abre manualmente: {url}")
    
    # Permitir desactivar la auto-apertura desde variable de entorno
    import os as _os
    _no_auto = str(_os.environ.get('NO_AUTO_BROWSER', '0')).strip() == '1'
    if not _no_auto:
        threading.Thread(target=open_browser).start()
    else:
        print("[INFO] NO_AUTO_BROWSER=1 -> No se abrirá el navegador automáticamente")
    
    print("\n" + "="*60)
    print("SERVIDOR WEB INICIADO")
    print("="*60)
    print(f"URL: http://localhost:5000")
    print(f"Abriendo Microsoft Edge automaticamente...")
    print(f"\nPara CERRAR el servidor:")
    print(f"   • Presiona Ctrl+C en esta terminal")
    print(f"   • O usa el botón 'Settings' > 'Cerrar Servidor' en la web")
    print("="*60 + "\n")
    
    try:
        app.run(debug=True, use_reloader=False, port=5000)
    except KeyboardInterrupt:
        print("\n\n[INFO] Servidor detenido correctamente")
        print("Hasta luego!\n")
