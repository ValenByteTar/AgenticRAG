"""
Sistema RAG Híbrido de Alta Calidad
Combina búsqueda semántica (embeddings) + keyword (BM25) + LLM (Ollama)
"""

import sys
import os
import re
import unicodedata

import yaml
import json
import subprocess
import requests
import numpy as np
from typing import List, Dict, Tuple
import time
import heapq
from pathlib import Path
from rank_bm25 import BM25Okapi
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from sentence_transformers import CrossEncoder

# Controlar hilos/parallelismo
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'

sys.path.append('src')
from metrics_logger import log_event
from embedder import EmbeddingGenerator
from vector_store import VectorStore
from memory_system import MemorySystem, ConversationHistory, parse_memory_command
from conceptual_map import ConceptualMap
from doc_cards import load_doc_roles, save_doc_roles, build_doc_cards, build_doc_cards_llm, select_docs_by_roles
from learning_queue import LearningQueue
from rag.entity_extractor import EntityExtractor
from ollama_manager import OllamaManager
from query_classifier import QueryClassifier
from equivalences_manager import EquivalencesManager
from answer_postprocessor import AnswerPostprocessor
from retrieval_engine import RetrievalEngine
from context_builder import ContextBuilder

console = Console()

EQUIVALENCES_EMBEDDED_TEXT = """Tabla de equivalencias

CISO = Chief Information Security Officer
CISSP = Certified Information Systems Security Professional
CISM = Certified Information Security Manager
CEH = Certified Ethical Hacker
CCSP = Certified Cloud Security Professional
CISA = Certified Information Systems Auditor
SOC = Security Operations Center = Centro de Operaciones de Seguridad
SIEM = Security Information and Event Management
ISO 27001 = ISO/IEC 27001 = Information Security Management System = ISMS = SGSI
NIST = National Institute of Standards and Technology
MITRE ATT&CK = ATT&CK = Adversarial Tactics Techniques and Common Knowledge
GDPR = General Data Protection Regulation = RGPD = Reglamento General de Proteccion de Datos
DORA = Digital Operational Resilience Act
NIS2 = NIS 2 = Network and Information Security Directive 2
IAM = Identity and Access Management = Gestion de Identidades y Accesos
MFA = Multi-Factor Authentication = 2FA = Autenticacion Multifactor
DLP = Data Loss Prevention = Prevencion de Perdida de Datos
IDS = Intrusion Detection System = Sistema de Deteccion de Intrusiones
IPS = Intrusion Prevention System = Sistema de Prevencion de Intrusiones
WAF = Web Application Firewall
EDR = Endpoint Detection and Response
XDR = Extended Detection and Response
VM = Vulnerability Management = Gestion de Vulnerabilidades
PT = Penetration Test = Pentest = Pentesting = Test de Penetracion
BCP = Business Continuity Plan = Plan de Continuidad de Negocio
DRP = Disaster Recovery Plan = Plan de Recuperacion ante Desastres
CIA = Confidentiality Integrity Availability = Confidencialidad Integridad Disponibilidad
APT = Advanced Persistent Threat = Amenaza Persistente Avanzada
IR = Incident Response = Respuesta a Incidentes
OSINT = Open Source Intelligence
CTI = Cyber Threat Intelligence = Inteligencia de Amenazas Ciberneticas
TTP = Tactics Techniques and Procedures = Tacticas Tecnicas y Procedimientos
IoC = Indicator of Compromise = Indicador de Compromiso
IoA = Indicator of Attack = Indicador de Ataque
SAST = Static Application Security Testing
DAST = Dynamic Application Security Testing
SDLC = Software Development Life Cycle = Ciclo de Vida de Desarrollo de Software
DevSecOps = Development Security Operations
CSPM = Cloud Security Posture Management
CWPP = Cloud Workload Protection Platform
SASE = Secure Access Service Edge
ZTNA = Zero Trust Network Access
VPN = Virtual Private Network = Red Privada Virtual
FW = Firewall = Cortafuegos
PAM = Privileged Access Management = Gestion de Acceso Privilegiado
RBAC = Role Based Access Control = Control de Acceso Basado en Roles
SSO = Single Sign On = Inicio de Sesion Unico
PKI = Public Key Infrastructure = Infraestructura de Clave Publica
TLS = Transport Layer Security
SSL = Secure Sockets Layer
DNS = Domain Name System = Sistema de Nombres de Dominio
DDoS = Distributed Denial of Service = Denegacion de Servicio Distribuida
RCE = Remote Code Execution = Ejecucion Remota de Codigo
XSS = Cross Site Scripting
SQLi = SQL Injection = Inyeccion SQL
CSRF = Cross Site Request Forgery
SSRF = Server Side Request Forgery
OWASP = Open Web Application Security Project
OSI = Open Systems Interconnection
TCP/IP = Transmission Control Protocol/Internet Protocol
LAN = Local Area Network = Red de Area Local
WAN = Wide Area Network = Red de Area Amplia
SD-WAN = Software Defined Wide Area Network
OSPF = Open Shortest Path First
ISIS = Intermediate System to Intermediate System
BGP = Border Gateway Protocol
MPLS = Multiprotocol Label Switching
VLAN = Virtual Local Area Network
NAC = Network Access Control = Control de Acceso a la Red
BYOD = Bring Your Own Device
AI = Artificial Intelligence = Inteligencia Artificial = IA
ML = Machine Learning = Aprendizaje Automatico
LLM = Large Language Model = Modelo de Lenguaje Grande
RAG = Retrieval Augmented Generation = Generacion Aumentada por Recuperacion
COBIT = Control Objectives for Information and Related Technologies
ITIL = Information Technology Infrastructure Library
GRC = Governance Risk and Compliance = Gobierno Riesgo y Cumplimiento
ERM = Enterprise Risk Management = Gestion de Riesgos Empresariales
BIA = Business Impact Analysis = Analisis de Impacto al Negocio
RTO = Recovery Time Objective = Objetivo de Tiempo de Recuperacion
RPO = Recovery Point Objective = Objetivo de Punto de Recuperacion
SLA = Service Level Agreement = Acuerdo de Nivel de Servicio
KPI = Key Performance Indicator = Indicador Clave de Rendimiento
KRI = Key Risk Indicator = Indicador Clave de Riesgo
Active Directory = AD = Directorio Activo
Azure = Microsoft Azure
AWS = Amazon Web Services
GCP = Google Cloud Platform
SaaS = Software as a Service
PaaS = Platform as a Service
IaaS = Infrastructure as a Service
API = Application Programming Interface = Interfaz de Programacion de Aplicaciones
"""


class HybridRAG:
    """RAG de alta calidad con búsqueda híbrida y LLM"""
    
    def __init__(self, config_path: str = "config.yaml", use_llm: bool = True, variant: str = None, heuristics: str = None):
        console.print("\n[bold cyan]Sistema RAG Hibrido de Alta Calidad[/bold cyan]")
        console.print("[dim]Búsqueda Semántica + Keyword + Llama3 + Memoria[/dim]\n")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        # Flags de comportamiento
        self.flags = self.config.get('rag', {}).get('flags', {})
        # Defaults para modo LLM-first y desactivar heurísticas determinísticas
        try:
            self.flags.setdefault('mode_llm_first', False)
            self.flags.setdefault('enable_deterministic_count', False)
            self.flags.setdefault('enable_cells_extractor', False)
            self.flags.setdefault('enable_salvage', False)
            self.flags.setdefault('enable_self_review_in_detailed', False)
            # Modo de prompts simples sin plantillas estructuradas
            self.flags.setdefault('plain_prompts', True)
            # Deshabilitar secciones estructuradas (p.ej., "Requisitos del Control", "Procedimientos de Seguridad")
            self.flags.setdefault('disable_structured_sections', True)
            # Modo de seguimiento conversacional (follow-up) con ancla
            self.flags.setdefault('follow_up_mode', True)
            # TTL para fuentes pegajosas (sticky) en follow-ups
            self.flags.setdefault('sticky_sources_ttl', 2)
            # Rechazo estricto fuera de dominio
            self.flags.setdefault('strict_ood', True)
            # Glosario: requerir mención explícita del acrónimo en la consulta
            self.flags.setdefault('glossary_require_explicit', True)
            # Glosario: listas de control (pueden venir desde config.yaml)
            self.flags.setdefault('glossary_allowlist', [])
            # Por defecto, negar 'ES' para evitar colisiones con el verbo 'es'
            self.flags.setdefault('glossary_denylist', ['ES'])
        except Exception:
            pass
        # Modo de heurísticas y variante de índice
        try:
            self.heuristics_mode = (self.config.get('rag', {}) or {}).get('heuristics_mode', 'legacy')
        except Exception:
            self.heuristics_mode = 'legacy'
        # Override de heurísticas por parámetro
        if isinstance(heuristics, str) and heuristics:
            self.heuristics_mode = heuristics
        try:
            self.index_variant = (self.config.get('rag', {}) or {}).get('index_variant', 'bge')
        except Exception:
            self.index_variant = 'bge'
        # Override de variante por parámetro
        if isinstance(variant, str) and variant:
            self.index_variant = variant
        # Equivalencias: colaborador independiente
        self._eq_mgr = EquivalencesManager(EQUIVALENCES_EMBEDDED_TEXT, flags=self.flags)
        # Mantener atributos de compatibilidad
        self.equivalences = self._eq_mgr.equivalences
        self.equivalences_map = self._eq_mgr.equivalences_map
        self.definitions_map = self._eq_mgr.definitions_map
        console.print(f"[dim]Equivalencias cargadas: {len(self.equivalences)} grupos[/dim]")

        # LLM: Ollama con modelo optimizado para GPU 6GB
        self.use_llm = use_llm
        self.ollama_model = "mistral:7b"
        self._ollama_mgr = OllamaManager(model=self.ollama_model)
        self.ollama_process = None  # compatibilidad: apunta al proceso del manager
        self.num_gpu_tuned = 99  # valor por defecto (auto)
        
        # Inicializar sistema de memoria
        self.memory = MemorySystem()
        self.conversation = ConversationHistory(max_history=10)
        # Recordar entidades del turno anterior para continuidad del tema
        self.last_entities = []
        # Configuración de razonamiento automático (HABILITADO - sin restricciones de RAM)
        self.enable_auto_reasoning = self.config.get('enable_auto_reasoning', True)
        self.centrales_map: dict = {}
        self.centrales_loaded: bool = False
        
        # MEJORA: Gazetteer de alias de entidades para mejorar búsqueda (ciberseguridad)
        self.entity_aliases = {
            'iso 27001': ['iso 27001', 'iso27001', 'iso 27k', 'isms'],
            'nist csf': ['nist csf', 'nist cybersecurity framework', 'cybersecurity framework', 'nist framework'],
            'cissp': ['cissp', 'certified information systems security professional', '(isc)2'],
            'ceh': ['ceh', 'certified ethical hacker', 'ethical hacker'],
            'mitre att&ck': ['mitre att&ck', 'mitre attack', 'mitre attck', 'attack framework'],
            'owasp': ['owasp', 'open web application security project'],
            'splunk': ['splunk', 'splunk siem', 'splunk enterprise security'],
        }
        # Mapa conceptual: conocimiento aprendido de consultas previas
        self.conceptual_map = ConceptualMap()
        # Cola de aprendizaje diferido con validación automática (DESHABILITADO por usuario)
        self.enable_auto_learning = False
        self.learning_queue = LearningQueue(
            ollama_url=f"http://localhost:{self.config.get('ollama_port', 11434)}",
            ollama_model=self.ollama_model,
            conceptual_map=self.conceptual_map
        ) if self.enable_auto_learning else None
        # Doc roles/cards: metadata enriquecida por documento (hubs, perfiles, etc.)
        self.doc_roles = {}
        
        # Verificar y arrancar Ollama si es necesario
        if not self._ollama_mgr.check():
            console.print("[yellow]ADVERTENCIA: Ollama no disponible, modo solo-retrieval[/yellow]")
            self.use_llm = False
        else:
            self.use_llm = True
            try:
                tuned = self._ollama_mgr.autotune_num_gpu()
                if isinstance(tuned, int) and tuned > 0:
                    self.num_gpu_tuned = tuned
                    self._ollama_mgr.num_gpu_tuned = tuned
            except Exception:
                pass
        self.ollama_process = self._ollama_mgr.process

        # Cargar sistema de búsqueda semántica
        console.print("[yellow]1/4 Cargando búsqueda semántica...[/yellow]")
        
        # Selección de embeddings y base vectorial por variante
        try:
            variant = self.index_variant
        except Exception:
            variant = 'bge'
        embeddings_cfg = (
            (self.config.get('embeddings_bge') or self.config['embeddings'])
            if str(variant).lower() == 'bge' else
            (self.config.get('embeddings_legacy') or self.config['embeddings'])
        )
        self.embedder = EmbeddingGenerator(
            model_name=embeddings_cfg['model_name'],
            device=embeddings_cfg['device'],
            provider=embeddings_cfg.get('provider', 'sentence-transformers')
        )
        # Paths/colección para Chroma según variante
        db_path = (
            self.config['paths'].get('vectordb_dir_bge', self.config['paths']['vectordb_dir'])
            if str(variant).lower() == 'bge' else
            self.config['paths']['vectordb_dir']
        )
        collection_name = (
            self.config['vectordb'].get('collection_name_bge', self.config['vectordb']['collection_name'])
            if str(variant).lower() == 'bge' else
            self.config['vectordb']['collection_name']
        )
        self.vector_store = VectorStore(
            db_path=db_path,
            collection_name=collection_name,
            search_ef=int((self.config.get('vectordb', {}) or {}).get('search_ef', 100))
        )
        
        # Cargar todos los documentos para BM25
        console.print("[yellow]2/4 Indexando búsqueda por keywords (BM25)...[/yellow]")
        self._load_bm25_index()
        
        console.print(f"[green]OK: {len(self.all_docs)} documentos indexados[/green]")
        
        # Cargar modelo de re-ranking (multilingüe)
        console.print("[yellow]3/4 Cargando modelo de re-ranking...[/yellow]")
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ['HF_DATASETS_OFFLINE'] = '1'
        os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
        os.environ['TOKENIZERS_PARALLELISM'] = 'false'
        # Reducir riesgo de deadlock con BLAS en Windows
        os.environ.setdefault('OMP_NUM_THREADS', '1')
        os.environ.setdefault('MKL_NUM_THREADS', '1')
        # Resolver rutas locales primero
        cfg_rr = (self.config.get('reranker', {}) or {})
        local_path = cfg_rr.get('local_path')
        reranker_name = cfg_rr.get('model_name') or 'BAAI/bge-reranker-v2-m3'
        self.reranker = None
        try:
            candidate_path = None
            if isinstance(local_path, str) and local_path:
                candidate_path = local_path
            elif isinstance(reranker_name, str) and (reranker_name.startswith('models/') or os.path.isdir(reranker_name)):
                candidate_path = reranker_name
            if candidate_path:
                # Usar CUDA si está disponible; fallback a CPU con todos los hilos
                try:
                    import torch as _torch
                    _rr_device = 'cuda' if _torch.cuda.is_available() else 'cpu'
                except Exception:
                    _rr_device = 'cpu'
                self.reranker = CrossEncoder(candidate_path, device=_rr_device, max_length=128)
                console.print(f"[green]OK: Re-ranker cargado (local: {candidate_path}, device={_rr_device}, max_length=128)[/green]")
            else:
                # No hay ruta local: desactivar sin intentar remoto
                console.print("[yellow]Re-ranking desactivado (sin ruta local configurada)\n[/yellow]")
        except Exception as e:
            console.print(f"[yellow]ADVERTENCIA: No se pudo cargar re-ranker local: {str(e)[:80]}[/yellow]")
            self.reranker = None
            console.print("[yellow]Re-ranking desactivado (modo 100% offline)\n[/yellow]")
        
        # Cargar DocCards/Roles (si no existen, construir por heurística o LLM)
        try:
            self.doc_roles = load_doc_roles()
            if self.config.get('use_doc_roles', True):
                if not isinstance(self.doc_roles, dict) or not self.doc_roles.get('docs'):
                    doccards_cfg = self.config.get('doccards', {}) if isinstance(self.config, dict) else {}
                    llm_enabled = bool(doccards_cfg.get('llm_enabled', False))
                    model_name = doccards_cfg.get('model_name', 'granite-3.3-8b-instruct-q5km:latest')
                    max_docs = int(doccards_cfg.get('max_docs', 0) or 0)
                    if llm_enabled:
                        console.print(f"[yellow]Construyendo DocCards con LLM ({model_name}) ...[/yellow]")
                        try:
                            self.doc_roles = build_doc_cards_llm(self.vector_store, model_name=model_name, max_docs=max_docs)
                        except Exception as e:
                            console.print(f"[yellow]ADVERTENCIA: Fallo DocCards LLM: {str(e)[:80]} - usando heurística[/yellow]")
                            self.doc_roles = build_doc_cards(self.vector_store)
                    else:
                        console.print("[yellow]Construyendo DocCards (heurística) ...[/yellow]")
                        self.doc_roles = build_doc_cards(self.vector_store)
                    save_doc_roles(self.doc_roles)
                console.print(f"[dim]DocCards cargados: {len(self.doc_roles.get('docs', {}))} documentos[/dim]")
                # ELIMINADO: Ampliación de centrales eléctricas desde DocCards
                # El sistema ahora usa domain_map genérico en entity_extractor
                pass
        except Exception as e:
            console.print(f"[yellow]ADVERTENCIA: No se pudieron cargar DocCards: {e}[/yellow]")
        # Instanciar extractor unificado y construir gazetteer de dominio
        try:
            self.entity_extractor = EntityExtractor(domain_map=self.centrales_map)
            try:
                col_data = self.vector_store.collection.get(include=["metadatas","documents","ids"])  # puede ser pesado; necesario una vez
            except Exception:
                col_data = self.vector_store.collection.get()
            self.entity_extractor.update_domain_from_collection(col_data, doc_roles=self.doc_roles, domain_map=self.centrales_map)
            console.print("[dim]Extractor de entidades inicializado con gazetteer de dominio[/dim]")
        except Exception as _e:
            console.print(f"[yellow]ADVERTENCIA: No se pudo inicializar EntityExtractor: {str(_e)[:80]}[/yellow]")
        
        # Clasificador de consultas: colaborador independiente
        self._query_clf = QueryClassifier(flags=self.flags, extract_entities_fn=self._extract_entities)
        # Post-procesador de respuestas: colaborador con back-reference
        self._postproc = AnswerPostprocessor(rag=self)
        # Motor de recuperación: colaborador con back-reference
        self._retrieval = RetrievalEngine(rag=self)
        # Constructor de contexto: colaborador con back-reference
        self._ctx_builder = ContextBuilder(rag=self)

        # Modo solo-retrieval o con LLM
        console.print("[yellow]4/4 Modo solo-retrieval (sin LLM)[/yellow]" if not self.use_llm else f"[yellow]4/4 Precargando modelo LLM en GPU: {self.ollama_model}[/yellow]")
        if self.use_llm:
            if self._ollama_mgr.preload():
                console.print(f"[green]OK: Modelo {self.ollama_model} cargado en GPU y listo[/green]\n")
            else:
                console.print(f"[yellow]ADVERTENCIA: No se pudo precargar el modelo[/yellow]\n")
        else:
            console.print(f"[yellow]4/4 Modo solo-retrieval (sin LLM)[/yellow]\n")

    def _autotune_num_gpu(self) -> int:
        """Delegado a OllamaManager.autotune_num_gpu()."""
        return self._ollama_mgr.autotune_num_gpu()
        
    def _check_ollama(self) -> bool:
        """Delegado a OllamaManager.check()."""
        return self._ollama_mgr.check()
    
    def _start_ollama(self) -> bool:
        """Delegado a OllamaManager.start()."""
        return self._ollama_mgr.start()
    
    def _preload_model(self) -> bool:
        """Delegado a OllamaManager.preload()."""
        return self._ollama_mgr.preload()

    def cleanup(self):
        """Delegado a OllamaManager.cleanup()."""
        self._ollama_mgr.cleanup()
        
    def _load_bm25_index(self):
        """Carga índice BM25 desde ChromaDB"""
        collection = self.vector_store.collection
        all_data = collection.get(include=['documents', 'metadatas'])
        self.all_docs = all_data['documents']
        self.all_metadatas = all_data['metadatas']
        self.all_ids = all_data.get('ids', [])
        try:
            self.id_to_index = {self.all_ids[i]: i for i in range(len(self.all_ids))}
        except Exception:
            self.id_to_index = {}
        try:
            src_map = {}
            for i, md in enumerate(self.all_metadatas):
                src = (md or {}).get('source', '')
                if src:
                    k = src.lower()
                    arr = src_map.get(k)
                    if arr is None:
                        arr = []
                        src_map[k] = arr
                    arr.append(i)
            self.source_to_indices = src_map
        except Exception:
            self.source_to_indices = {}
        tokenized_docs = [self._tokenize_for_bm25(doc) for doc in self.all_docs]
        self.bm25 = BM25Okapi(tokenized_docs)

    def _tokenize_for_bm25(self, text: str) -> List[str]:
        try:
            s = (text or '').lower()
            tokens = re.findall(r"[a-zñáéíóúü]+(?:[./-]?[a-z0-9]+)*|\d+(?:[.,]\d+)?", s)
            stop = {
                'de','la','el','los','las','y','o','a','en','del','al','un','una','con','por','para','que','se','es','su','sus','lo','como','sobre','sin','entre','desde','hasta'
            }
            return [t for t in tokens if t not in stop]
        except Exception:
            return (text or '').lower().split()

    def _normalize_query(self, query: str) -> str:
        """Delegado a EquivalencesManager.normalize_query()."""
        return self._eq_mgr.normalize_query(query)

    def _load_equivalences(self, txt_path: str):
        """Delegado a EquivalencesManager (usa texto embebido, txt_path ignorado)."""
        self.equivalences = self._eq_mgr.equivalences
        self.equivalences_map = self._eq_mgr.equivalences_map
        self.definitions_map = self._eq_mgr.definitions_map

    def _build_equivalences_maps(self):
        """Delegado a EquivalencesManager._build_maps()."""
        self._eq_mgr._build_maps()
        self.equivalences_map = self._eq_mgr.equivalences_map
        self.definitions_map = self._eq_mgr.definitions_map

    def _expand_with_equivalences(self, query: str) -> str:
        """Delegado a EquivalencesManager.expand()."""
        return self._eq_mgr.expand(query)

    def _build_glossary_for_query(self, query: str) -> str:
        """Delegado a EquivalencesManager.build_glossary()."""
        return self._eq_mgr.build_glossary(query)

    def _filter_results_by_technology(self, question: str, results: list) -> list:
        """Filtra o prioriza resultados según el tipo de documento de ciberseguridad mencionado.
        Si se pide 'framework ISO', se priorizan documentos de frameworks y se penalizan otros tipos.
        """
        try:
            if not results:
                return results
            q = (question or '').lower()
            want_framework = any(w in q for w in ['framework', 'estandar', 'estándar', 'iso', 'nist', 'control'])
            want_certification = any(w in q for w in ['certificacion', 'certificación', 'certified', 'cissp', 'ceh', 'oscp'])
            want_threat = any(w in q for w in ['threat', 'amenaza', 'apt', 'malware', 'ransomware'])
            want_procedure = any(w in q for w in ['procedimiento', 'procedure', 'protocolo', 'playbook', 'runbook'])
            if not (want_framework or want_certification or want_threat or want_procedure):
                return results
            def tech_score(src: str, txt: str) -> int:
                s = (src or '').lower()
                t = (txt or '').lower()
                # Heurísticas de dominio por nombre de documento o texto (ciberseguridad)
                is_framework = any(k in s for k in ['framework', 'standard', 'iso', 'nist', 'pci']) or any(k in t for k in ['framework', 'standard', 'control', 'requisito'])
                is_certification = any(k in s for k in ['certification', 'certified', 'cissp', 'ceh', 'oscp']) or any(k in t for k in ['certification', 'certified', 'credential', 'exam'])
                is_threat_intel = any(k in s for k in ['threat', 'intel', 'apt', 'ioc', 'ttp']) or any(k in t for k in ['threat', 'amenaza', 'actor', 'campaign'])
                is_procedural = any(k in s for k in ['procedure', 'protocol', 'playbook', 'runbook']) or any(k in t for k in ['procedure', 'protocolo', 'paso', 'step'])
                score = 0
                if want_framework:
                    score += 2 if is_framework else (-1 if (is_certification or is_threat_intel) else 0)
                if want_certification:
                    score += 2 if is_certification else (-1 if (is_framework or is_threat_intel) else 0)
                if want_threat:
                    score += 2 if is_threat_intel else (-1 if (is_framework or is_certification) else 0)
                if want_procedure:
                    score += 2 if is_procedural else (-1 if (is_framework or is_certification) else 0)
                return score
            # Reordenar por tecnología preferida con estabilidad por rerank_score
            sorted_results = sorted(results, key=lambda r: (tech_score(r.get('metadata',{}).get('source',''), r.get('text','')), r.get('rerank_score', r.get('hybrid_score', 0))), reverse=True)
            # También filtrar duros los casos opuestos si hay suficientes del tipo pedido
            top = sorted_results[:10]
            pos = sum(1 for r in top if tech_score(r.get('metadata',{}).get('source',''), r.get('text','')) > 0)
            if pos >= 3:
                # Mantener los positivos y neutrales, eliminar negativos
                filtered = [r for r in sorted_results if tech_score(r.get('metadata',{}).get('source',''), r.get('text','')) >= 0]
                return filtered or sorted_results
            return sorted_results
        except Exception:
            return results


    def _augment_with_page_neighbors(self, results: list, per_source_limit: int = 4) -> list:
        """Añade páginas vecinas (±1) para cada (source,page) presente en results, sin duplicar.
        Limita la cantidad total añadida por documento para evitar contexto inflado.
        """
        try:
            if not results:
                return results
            seen = set()
            for r in results:
                key = (r.get('metadata',{}).get('source',''), r.get('metadata',{}).get('page',0), (r.get('text','') or '')[:120])
                seen.add(key)
            added = []
            added_per_src = {}
            for r in results[:10]:
                meta = r.get('metadata', {})
                src = meta.get('source', '')
                page = meta.get('page', 0)
                if not src:
                    continue
                if added_per_src.get(src, 0) >= per_source_limit:
                    continue
                for pg in [page-1, page+1]:
                    if pg <= 0:
                        continue
                    try:
                        neighbors = self._search_in_specific_doc(src, page=pg, top_k=2)
                    except Exception:
                        neighbors = []
                    for nr in neighbors:
                        key = (nr.get('metadata',{}).get('source',''), nr.get('metadata',{}).get('page',0), (nr.get('text','') or '')[:120])
                        if key in seen:
                            continue
                        added.append(nr)
                        seen.add(key)
                        added_per_src[src] = added_per_src.get(src, 0) + 1
                        if added_per_src[src] >= per_source_limit:
                            break
            if added:
                return results + added
            return results
        except Exception:
            return results
    
    def _condense_text(self, text: str, max_chars: int = 600) -> str:
        """Delegado a AnswerPostprocessor.condense_text()."""
        return self._postproc.condense_text(text, max_chars)
    
    def _spanish_number_variants(self, answer: str) -> str:
        """Delegado a AnswerPostprocessor.spanish_number_variants()."""
        return self._postproc.spanish_number_variants(answer)

    def _has_numeric_evidence(self, entity: str, results: list, max_chunks: int = 5) -> bool:
        """Delegado a AnswerPostprocessor.has_numeric_evidence()."""
        return self._postproc.has_numeric_evidence(entity, results, max_chunks)

    def _numbers_match_context(self, answer: str, context: str, query: str) -> bool:
        """Delegado a AnswerPostprocessor.numbers_match_context()."""
        return self._postproc.numbers_match_context(answer, context, query)

    def _self_review_answer(self, query: str, answer: str, context: str) -> str:
        """Delegado a AnswerPostprocessor.self_review_answer()."""
        return self._postproc.self_review_answer(query, answer, context)

    def _audit_auto_review_decision(self, query: str, context: str, original_answer: str, corrected_answer: 'Optional[str]' = None, system_decision: str = '', length_mode: str = 'short') -> None:
        """Delegado a AnswerPostprocessor.audit_auto_review_decision()."""
        self._postproc.audit_auto_review_decision(query, context, original_answer, corrected_answer, system_decision, length_mode)

    def _post_process_answer(self, answer: str) -> str:
        """Delegado a AnswerPostprocessor.post_process_answer()."""
        return self._postproc.post_process_answer(answer)

    def _truncate_safe_short(self, text: str, limit: int = 1000) -> str:
        """Delegado a AnswerPostprocessor.truncate_safe_short()."""
        return self._postproc.truncate_safe_short(text, limit)

    def _postprocess_answer(self, question: str, answer: str, context: str) -> str:
        """Delegado a AnswerPostprocessor.postprocess_answer()."""
        return self._postproc.postprocess_answer(question, answer, context)

    def hybrid_search(self, query: str, top_k: int = 20, semantic_weight: float = 0.6, allowed_sources: List[str] = None) -> list:
        """Delegado a RetrievalEngine.hybrid_search()."""
        return self._retrieval.hybrid_search(query, top_k, semantic_weight, allowed_sources)

    def _search_in_specific_doc(self, doc_name: str, page: int = None, top_k: int = 10) -> list:
        """Delegado a RetrievalEngine.search_in_specific_doc()."""
        return self._retrieval.search_in_specific_doc(doc_name, page, top_k)

    def _search_for_comparison(self, entities: list, top_k: int = 20) -> list:
        """Delegado a RetrievalEngine.search_for_comparison()."""
        return self._retrieval.search_for_comparison(entities, top_k)

    def _filter_by_entity(self, results: list, entities: list, min_matches: int = 1, strict: bool = False) -> list:
        """Delegado a RetrievalEngine.filter_by_entity()."""
        return self._retrieval.filter_by_entity(results, entities, min_matches, strict)

    def _rerank_results(self, query: str, results: list, top_k: int = 10) -> list:
        """Delegado a RetrievalEngine.rerank_results()."""
        return self._retrieval.rerank_results(query, results, top_k)

    def _diversify_by_source(self, results: list, per_source_limit: int = 1, max_results: int = 50) -> list:
        """Delegado a RetrievalEngine.diversify_by_source()."""
        return self._retrieval.diversify_by_source(results, per_source_limit, max_results)

    def _ensure_source_for_entity(self, results: list, source_substr: str, entity_substr: str, limit: int = 1) -> list:
        """Delegado a RetrievalEngine.ensure_source_for_entity()."""
        return self._retrieval.ensure_source_for_entity(results, source_substr, entity_substr, limit)

    def _ensure_sources(self, results: list, source_substrings: list, per_source_limit: int = 1) -> list:
        """Delegado a RetrievalEngine.ensure_sources()."""
        return self._retrieval.ensure_sources(results, source_substrings, per_source_limit)

    def _plan_retrieval(self, question: str, entities: list, is_conceptual: bool, is_procedural: bool, is_direct_comparison: bool = False, is_simple_numeric: bool = False, is_troubleshooting: bool = False) -> dict:
        """Delegado a RetrievalEngine.plan_retrieval()."""
        return self._retrieval.plan_retrieval(question, entities, is_conceptual, is_procedural, is_direct_comparison, is_simple_numeric, is_troubleshooting)

    def _filter_to_candidates(self, results: list, allowed_sources: list) -> list:
        """Delegado a RetrievalEngine.filter_to_candidates()."""
        return self._retrieval.filter_to_candidates(results, allowed_sources)

    def _deduplicate_results(self, results: list, similarity_threshold: float = 0.85) -> list:
        """Delegado a RetrievalEngine.deduplicate_results()."""
        return self._retrieval.deduplicate_results(results, similarity_threshold)

    def _adaptive_quality_filter(self, results: list, question: str) -> list:
        """Delegado a RetrievalEngine.adaptive_quality_filter()."""
        return self._retrieval.adaptive_quality_filter(results, question)

    def _limit_results_per_source(self, results: list, max_per_source: int = 2) -> list:
        """Delegado a RetrievalEngine.limit_results_per_source()."""
        return self._retrieval.limit_results_per_source(results, max_per_source)

    def _categorize_results(self, results: list) -> list:
        """Delegado a RetrievalEngine.categorize_results()."""
        return self._retrieval.categorize_results(results)

    def _detect_detailed_query(self, query: str) -> bool:
        """Delegado a QueryClassifier.is_detailed()."""
        return self._query_clf.is_detailed(query)
    
    def _is_multi_document_query(self, query: str) -> bool:
        """Delegado a QueryClassifier.is_multi_document()."""
        return self._query_clf.is_multi_document(query)
    
    def _is_comparison_query(self, query: str) -> bool:
        """Delegado a QueryClassifier.is_comparison()."""
        return self._query_clf.is_comparison(query)
    
    def _is_aggregation_query(self, query: str) -> bool:
        """Delegado a QueryClassifier.is_aggregation()."""
        return self._query_clf.is_aggregation(query)

    def _is_listing_query(self, query: str) -> bool:
        """Delegado a QueryClassifier.is_listing()."""
        return self._query_clf.is_listing(query)
    
    def _is_direct_comparison_query(self, query: str) -> bool:
        """Delegado a QueryClassifier.is_direct_comparison()."""
        return self._query_clf.is_direct_comparison(query)
    
    def _is_simple_numeric_query(self, query: str) -> bool:
        """Delegado a QueryClassifier.is_simple_numeric()."""
        return self._query_clf.is_simple_numeric(query)
    
    def _is_troubleshooting_query(self, query: str) -> bool:
        """Delegado a QueryClassifier.is_troubleshooting()."""
        return self._query_clf.is_troubleshooting(query)
    
    def _is_follow_up_query(self, query: str) -> bool:
        """Delegado a QueryClassifier.is_follow_up()."""
        return self._query_clf.is_follow_up(query)


    def _format_listing_answer(self, items: list) -> str:
        """Formatea la lista de frameworks/políticas enumerada con versión y categoría."""
        lines = []
        for idx, it in enumerate(items, 1):
            name = it.get('name', '')
            version = (str(it.get('version', '')).strip())
            category = (it.get('category') or '').strip()
            cat_part = f" — {category}" if category else ''
            ver_part = f" (v{version})" if version else ''
            lines.append(f"{idx}. {name}{ver_part}{cat_part}")
        return "\n".join(lines)

    def _is_sum_query(self, query: str) -> bool:
        """Delegado a QueryClassifier.is_sum()."""
        return self._query_clf.is_sum(query)

    def _extract_tech_filter(self, query: str) -> str:
        """Delegado a QueryClassifier.extract_tech_filter()."""
        return self._query_clf.extract_tech_filter(query)

    def _extract_vendor_filter(self, query: str) -> str:
        """Delegado a QueryClassifier.extract_vendor_filter()."""
        return self._query_clf.extract_vendor_filter(query)

    def _norm_name(self, s: str) -> str:
        t = ''.join(c for c in unicodedata.normalize('NFD', s or '') if unicodedata.category(c) != 'Mn').lower()
        # ELIMINADO: Referencias a p.e./p.s. (Parque Eólico/Solar) - ahora es genérico
        t = re.sub(r"[^a-z0-9]+", " ", t).strip()
        return t

    def _get_vendor_project_names(self, vendor: str) -> list:
        """Extrae nombres de documentos relacionados al vendor (p.ej., 'CROWDSTRIKE') usando el vector_store."""
        names = set()
        try:
            all_docs = self.vector_store.collection.get()
            for i, md in enumerate(all_docs.get('metadatas', [])):
                src = (md or {}).get('source', '')
                if src and vendor.lower() in src.lower():
                    txt = all_docs['documents'][i]
                    if not txt:
                        continue
                    # Buscar nombres propios capitalizados como candidatos de proyectos/entidades
                    for m in re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b", txt):
                        if len(m) > 3 and m.lower() not in {'this', 'the', 'that', 'with', 'from', 'para', 'para'}:
                            names.add(m.title())
        except Exception:
            pass
        return list(sorted(names))



    def _boost_results_for_exact_entity(self, results: list, entity_name: str) -> list:
        """Aumenta score si el texto contiene la entidad exacta y penaliza si contiene variantes conflictivas (p.ej., VI vs II)."""
        if not results or not entity_name:
            return results
        ent = entity_name.lower()
        # Detectar posible conflicto por sufijo romano (I, II, III, IV, V, VI)
        conflict_map = {
            ' i': [' ii', ' iii', ' iv', ' v', ' vi'],
            ' ii': [' i', ' iii', ' iv', ' v', ' vi'],
            ' iii': [' i', ' ii', ' iv', ' v', ' vi'],
            ' iv': [' i', ' ii', ' iii', ' v', ' vi'],
            ' v': [' i', ' ii', ' iii', ' iv', ' vi'],
            ' vi': [' i', ' ii', ' iii', ' iv', ' v'],
        }
        suf = ''
        m = re.search(r"loma\s+blanca\s+(i{1,3}|iv|v|vi)$", ent)
        if m:
            suf = f" {m.group(1)}"
        boosted = []
        for r in results:
            txt = (r.get('text') or '').lower()
            boost = r.get('priority_boost', 0.0)
            # Boost por match exacto de entidad
            if ent in txt:
                boost += 0.6
            # Penalización por conflictos de sufijo
            if suf and any((f"loma blanca{c}" in txt) for c in conflict_map.get(suf, [])):
                boost -= 0.5
            r['priority_boost'] = boost
            # Recalcular final_score si existe
            fs = r.get('final_score', r.get('hybrid_score', 0.0))
            r['final_score'] = fs + boost
            boosted.append(r)
        # Reordenar por final_score descendente
        boosted.sort(key=lambda x: x.get('final_score', x.get('hybrid_score', 0.0)), reverse=True)
        return boosted

    def _looks_like_procedural_steps(self, text: str) -> bool:
        """Delegado a AnswerPostprocessor.looks_like_procedural_steps()."""
        return self._postproc.looks_like_procedural_steps(text)

    def _has_procedural_evidence(self, context: str, min_sources: int = 2) -> bool:
        """Delegado a AnswerPostprocessor.has_procedural_evidence()."""
        return self._postproc.has_procedural_evidence(context, min_sources)


    def _extract_doc_scope(self, query: str) -> str:
        """Intenta extraer un nombre de documento para limitar la búsqueda (e.g., "buscar en 'Anexo D - Listado Centrales.pdf'").
        Devuelve string del documento a buscar o cadena vacía si no hay scope.
        """
        q = query.strip()
        # 1) Documento entre comillas
        m = re.search(r'"([^"]+\.pdf)"', q, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
        # 2) Patrones comunes: buscar en / apunta tu búsqueda a / solo en / en ... .pdf
        m2 = re.search(r'(?:buscar en|busca en|apunta(?: tu)?\s+b(?:ú|u)squeda a|solo en|solamente en|en\s+(?:el\s+documento|documento|el\s+anexo|anexo|archivo))\s+([^\n\r]+?\.pdf)\b', q, flags=re.IGNORECASE)
        if m2:
            return m2.group(2 if m2.lastindex and m2.lastindex >= 2 else 1).strip()
        # 3) Detectar "Anexo X - <Nombre>" sin .pdf (ej: "Anexo A - Políticas")
        ql = q.lower()
        m3 = re.search(r'anexo\s+[a-z]\s*-\s*([a-z0-9áéíóúñ\s]+)', ql, flags=re.IGNORECASE)
        if m3:
            anexo_name = m3.group(1).strip()
            # Validar que no sea una frase larga (max 3 palabras)
            if len(anexo_name.split()) <= 3:
                return f"Anexo - {anexo_name.title()}.pdf"
        # 4) Buscar documento que contenga el número/código mencionado (ej: "ISO 27001", "NSE4")
        m4 = re.search(r'\b(?:ISO|NIST|NSE|SC|AZ|CCNA|CISSP|CEH|OSCP)\s*[-]?\s*([0-9]{1,4}[a-z]?)\b', ql, flags=re.IGNORECASE)
        if m4:
            try:
                prefix = (m4.group(0) or '').strip().replace(' ', '').replace('-', '')
                col = self.vector_store.collection.get()
                metas = col.get('metadatas', []) or []
                sources = [(md or {}).get('source', '') for md in metas]
                target = None
                needle = prefix.lower()
                for s in sources:
                    if s and needle in s.lower().replace(' ', ''):
                        target = s
                        break
                if target:
                    return target
            except Exception:
                pass
        return ''

    def _requires_full_anexos_coverage(self, query: str) -> bool:
        """Detecta si el usuario pide revisar TODOS los documentos/controles/frameworks.
        Dispara modo de cobertura completa (sin truncar a top 10).
        """
        q = query.lower()
        if ('cada control' in q) or ('cada framework' in q) or ('todos los controles' in q) or ('todos los frameworks' in q):
            return True
        if ('cada documento' in q) or ('todos los documentos' in q):
            return True
        return False
    
    def _extract_doc_reference(self, query: str) -> dict:
        """
        Extrae referencia a un documento citado en formato [Doc N - nombre p.X]
        
        Args:
            query: Query del usuario
        
        Returns:
            dict con 'doc_name' y 'page' si encuentra referencia, None si no
        """
        
        # Patrones para detectar referencias a documentos
        patterns = [
            r'\[Doc \d+ - ([^\]]+) p\.(\d+)\]',  # [Doc 3 - nombre p.11]
            r'\[Doc \d+ - ([^\]]+) pág\.(\d+)\]',  # [Doc 3 - nombre pág.11]
            r'documento \[Doc \d+ - ([^\]]+) p\.(\d+)\]',  # documento [Doc...]
            r'el \[Doc \d+ - ([^\]]+) p\.(\d+)\]',  # el [Doc...]
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query)
            if match:
                doc_name = match.group(1).strip()
                page = int(match.group(2))
                return {'doc_name': doc_name, 'page': page}
        
        return None
    
    def _is_doc_explanation_query(self, query: str) -> bool:
        """Delegado a QueryClassifier.is_doc_explanation()."""
        return self._query_clf.is_doc_explanation(query)
    
    def _is_conceptual_question(self, query: str) -> bool:
        """Delegado a QueryClassifier.is_conceptual()."""
        return self._query_clf.is_conceptual(query)

    def _is_specific_count_query(self, query: str) -> bool:
        """Delegado a QueryClassifier.is_specific_count()."""
        return self._query_clf.is_specific_count(query)

    def _is_wtg_power_query(self, query: str) -> bool:
        """Detecta si piden detalle por unidad/control (antes potencia por WTG)."""
        q = (query or '').lower()
        has_detail = any(k in q for k in ['versión', 'version', 'cvss', 'severidad', 'detalle', 'detalle de'])
        has_control = any(k in q for k in ['control', 'controles', 'requisito', 'requisitos'])
        # Refuerzos semánticos
        per_unit_hints = any(k in q for k in ['cada', 'c/u', 'por control', 'por requisito'])
        return (has_detail and has_control) or per_unit_hints



    def _is_centrales_list_request(self, query: str) -> bool:
        """Intención explícita de listar frameworks/políticas/controles (adaptado de centrales/parques).
        Requiere palabras de listado + término de frameworks; excluye consultas procedimentales.
        """
        q = (query or '').lower()
        # Excluir consultas procedimentales específicas
        if any(k in q for k in ['procedimiento', 'paso', 'step', 'celda', 'incidente']):
            return False
        # Modo extremadamente estricto: solo estas palabras habilitan el listado/tablas
        explicit_tokens = ['listado', 'lista', 'tabla', 'tablilla', 'catalogo', 'catálogo']
        return any(tok in q for tok in explicit_tokens)

    def _extract_doc_pages_hint(self, query: str):
        """Extrae pista explícita de documento y páginas de la query.
        Ejemplos soportados:
        - "pagina 3 y 4 del documento 'ISO 27001.pdf'"
        - "páginas 3-4 de NIST CSF.pdf"
        - "p. 3 y 12 del Manual de Seguridad.pdf"
        Devuelve dict {'doc': str, 'pages': [int,...]} o None.
        """
        try:
            q = (query or '')
            # Buscar nombre de doc entre comillas o con .pdf
            doc_match = re.search(r"['\"]([^'\"]+?\.pdf)['\"]|([A-Za-zÁÉÍÓÚÑáéíóúñ0-9 \-]+?\.pdf)", q)
            if not doc_match:
                return None
            doc = (doc_match.group(1) or doc_match.group(2) or '').strip()
            # Buscar páginas: "página(s) X y Y", "X-Y", "p. X, Y"
            pages = []
            for pat in [
                r"p[aá]g(?:ina|inas)?\s*(\d{1,3})\s*(?:y|e|,|-)\s*(\d{1,3})",
                r"p\.?\s*(\d{1,3})\s*(?:y|e|,|-)\s*(\d{1,3})",
                r"p[aá]g(?:ina|inas)?\s*(\d{1,3})",
                r"\b(\d{1,3})\s*[-–]\s*(\d{1,3})\b",
            ]:
                m = re.search(pat, q, flags=re.IGNORECASE)
                if m:
                    if m.lastindex and m.lastindex >= 2 and m.group(2):
                        a = int(m.group(1)); b = int(m.group(2))
                        if a <= b:
                            pages = list(range(a, b+1))
                        else:
                            pages = [a, b]
                    else:
                        pages = [int(m.group(1))]
                    break
            if not pages:
                return None
            return {'doc': doc, 'pages': pages}
        except Exception:
            return None

    def _try_fast_snippet_answer(self, question: str, results: list, entities: list, length_mode: str = 'short'):
        try:
            if not results or not isinstance(length_mode, str) or length_mode.strip().lower() != 'short':
                return None
            q = (question or '').lower()
            kw = ['wtg','aerogenerador','aerogeneradores','turbina','turbinas','panel','paneles','mw','megawatt']
            kw = [k for k in kw if k in q] or ['wtg','aerogeneradores','paneles','mw']
            snippets = []
            top = results[:5]
            for i, r in enumerate(top, 1):
                txt = r.get('text','') or ''
                meta = r.get('metadata',{}) or {}
                src = meta.get('source','')
                pg = meta.get('page',0)
                label = f"[Doc {i} - {src.split('.pdf')[0]} p.{pg}]"
                # Anclaje por entidad (si hay entidades detectadas)
                if entities:
                    tlow = txt.lower()
                    if not any(e for e in entities if e and e.lower() in tlow):
                        continue
                for m in re.finditer(r"(" + r"|".join(re.escape(k) for k in kw) + r")", txt, flags=re.IGNORECASE):
                    s, e = m.start(), m.end()
                    a = max(0, s-40)
                    b = min(len(txt), e+40)
                    snip = txt[a:b].replace('\n',' ')
                    # Requerir dígitos cercanos (para consultas de conteo o numéricas)
                    if not re.search(r"\d", snip):
                        continue
                    if snip and len(snip.strip())>0:
                        snippets.append(f"{label} {snip}")
                    if len(snippets) >= 8:
                        break
                if len(snippets) >= 8:
                    break
            if not snippets:
                return None
            prompt = (
                "Responde de forma CORTA, PRECISA y COMPLETA usando SOLO estos fragmentos.\n"
                "Incluye al menos una cita [Doc i - fuente p.X]. Sin preámbulos.\n"
                "Si no puedes responder estrictamente con esta información, responde EXACTAMENTE: INSUFICIENTE.\n\n"
                f"Pregunta: {question}\n\n"
                + "\n".join(snippets) + "\n\nRespuesta:"
            )
            # Si está activado el modo de prompts simples, usa un formato mínimo sin plantillas
            try:
                if self.flags.get('plain_prompts', False):
                    prompt = (
                        "Contexto (usa SOLO esta evidencia, no inventes ni asumas nada):\n" + "\n".join(snippets) +
                        f"\n\nInstrucciones estrictas:\n"
                        f"- Responde únicamente con información explícitamente contenida en el contexto.\n"
                        f"- Si la información clave no aparece en el contexto, responde exactamente: Insuficiente evidencia.\n"
                        f"- Si usas cifras, nombres de tecnologías, ubicaciones o fabricantes, deben aparecer literalmente en el contexto.\n"
                        f"- Responde SIEMPRE en español.\n"
                        f"- Incluye, cuando corresponda, citas breves [doc:pag].\n\n"
                        f"Pregunta: {question}\n\nRespuesta:" 
                    )
            except Exception:
                pass
            payload = {
                "model": getattr(self, 'ollama_model', 'granite-3.3-8b-instruct-q5km:latest'),
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": 220,
                    "temperature": 0.2,
                    "top_k": 30,
                    "top_p": 0.85,
                    "num_ctx": 1024,
                    "num_gpu": getattr(self, 'num_gpu_tuned', 99),
                    "stop": ["```"]
                },
                "keep_alive": "10m"
            }
            r = requests.post("http://localhost:11434/api/generate", json=payload, timeout=25)
            if r.status_code == 200:
                ans = (r.json().get('response','') or '').strip()
                if ans.upper().startswith('INSUFICIENTE') or len(ans) < 3:
                    return None
                try:
                    ctx_text = "\n".join(snippets).lower()
                    nums = re.findall(r"\d+(?:[\.,]\d+)?", ans)
                    if nums:
                        for n in set(nums):
                            if n.lower() not in ctx_text:
                                return "Insuficiente evidencia"
                except Exception:
                    pass
                return ans
            return None
        except Exception:
            return None

    def _infer_entity_from_conv_context(self, conv_context: str) -> 'Optional[str]':
        try:
            if not conv_context:
                return None
            m = re.search(r"ENTIDAD OBJETIVO:\s*(.+)\s*$", conv_context, flags=re.MULTILINE)
            if m:
                name = m.group(1).strip()
                if name:
                    return name
            return None
        except Exception:
            return None


    def _try_deterministic_count_answer(self, question: str, results: list, entities: list, length_mode: str = 'short'):
        """Extrae determinísticamente un conteo cercano a keywords con anclaje por entidad.
        Devuelve una respuesta breve con cita si encuentra un único valor consistente.
        """
        try:
            if not results or not isinstance(length_mode, str) or length_mode.strip().lower() != 'short':
                return None
            t0 = time.time()
            q = (question or '').lower()
            # Palabras clave por dominio
            dom = [
                ('WTG', [r'wtg', r'aerogenerador(?:es)?', r'turbina(?:s)?']),
                ('paneles', [r'panel(?:es)?', r'm[óo]dulo(?:s)?']),
            ]
            candidates = []
            top = results[:8]
            for i, r in enumerate(top, 1):
                txt = r.get('text','') or ''
                tlow = txt.lower()
                meta = r.get('metadata',{}) or {}
                src = meta.get('source','')
                pg = meta.get('page',0)
                label = f"[Doc {i} - {src.split('.pdf')[0]} p.{pg}]"
                # Anclaje por entidad
                if entities:
                    if not any(e for e in entities if e and e.lower() in tlow):
                        continue
                for unit_label, kws in dom:
                    # número +/- 40 chars alrededor de keyword
                    pat = r"(\d{1,3}(?:[\.,\s]\d{3})+|\d+(?:[\.,]\d+)?)"
                    for kw in kws:
                        regex = re.compile(rf"{pat}.{{0,40}}{kw}|{kw}.{{0,40}}{pat}", re.IGNORECASE)
                        for m in regex.finditer(txt):
                            g = [g for g in m.groups() if g and re.search(r"\d", g)]
                            if g:
                                val = g[0]
                                candidates.append((val, unit_label, label))
            if not candidates:
                return None
            # Normalizar valores (quitar separadores)
            norm = lambda s: re.sub(r"[\.,\s]", "", s)
            vals = [norm(v) for v,_,_ in candidates]
            unique = set(vals)
            if len(unique) == 1:
                # usar la primera cita encontrada
                v_raw, unit, lab = candidates[0]
                ans = f"{v_raw} {unit} {lab}"
                console.print(f"[dim]Conteo determinístico usado en {time.time()-t0:.1f}s: {ans}[/dim]")
                return ans
            # Si hay 2 valores pero uno domina
            from collections import Counter
            cc = Counter(vals)
            most, cnt = cc.most_common(1)[0]
            if cnt >= 2:
                # tomar la primera coincidencia del valor dominante
                for v_raw, unit, lab in candidates:
                    if norm(v_raw) == most:
                        ans = f"{v_raw} {unit} {lab}"
                        console.print(f"[dim]Conteo determinístico (mayoría) usado: {ans}[/dim]")
                        return ans
            return None
        except Exception:
            return None

    
    def _is_procedural_question(self, query: str) -> bool:
        """Delegado a QueryClassifier.is_procedural()."""
        return self._query_clf.is_procedural(query)
    
    def _reason_and_retry_search(self, original_query: str, failed_results: list, attempt: int = 1) -> dict:
        """
        Usa el LLM para RAZONAR sobre por qué la búsqueda falló y proponer nuevos términos.
        OPTIMIZADO: Uso mínimo de RAM.
        
        Args:
            original_query: Query original del usuario
            failed_results: Resultados con baja relevancia
            attempt: Número de intento (máximo 2)
        
        Returns:
            Dict con 'retry': bool, 'new_terms': list, 'reasoning': str
        """
        if attempt > 2:
            console.print("[yellow]ADVERTENCIA: Limite de re-intentos alcanzado[/yellow]")
            return {'retry': False, 'new_terms': [], 'reasoning': 'Máximo de intentos alcanzado'}
        
        console.print(f"[bold yellow]Razonamiento automatico (intento {attempt}/2)...[/bold yellow]")
        
        # OPTIMIZACIÓN: Solo tomar 2 resultados más relevantes, texto corto
        sample_results = failed_results[:2]
        results_preview = '\n'.join([
            f"- {r.get('metadata', {}).get('source', 'Unknown')}: {r.get('text', '')[:80]}..."
            for r in sample_results
        ])
        
        # PROMPT COMPACTO para minimizar tokens
        reasoning_prompt = f"""Búsqueda NO encontró resultados relevantes.

QUERY: {original_query}

RESULTADOS (baja relevancia):
{results_preview}

TAREA: Propón 3-4 términos de búsqueda ALTERNATIVOS.

EJEMPLOS:
- "nombre parque" -> "potencia MW", "inversores", "ubicación"
- "Pampetrol" -> "Victorica", "7.2 MW"

FORMATO:
NUEVOS_TERMINOS: término1, término2, término3

Respuesta:"""
        
        try:
            
            response = requests.post(
                'http://localhost:11434/api/generate',
                json={
                    'model': self.ollama_model,
                    'prompt': reasoning_prompt,
                    'stream': False,
                    'options': {
                        'temperature': 0.6,
                        'num_predict': 220,  # un poco más para permitir mejor propuesta
                        'top_k': 40,
                        'top_p': 0.9,
                        'num_ctx': 4096,     # mayor contexto para razonar mejor
                        'num_thread': 12,
                        'num_gpu': 99,
                        'num_batch': 256     # Reducido para velocidad
                    },
                    'keep_alive': '5m'  # Mantener modelo 5 minutos
                },
                timeout=45  # Reducido para velocidad
            )
            
            if response.status_code == 200:
                result = response.json()
                reasoning_text = result.get('response', '').strip()
                
                console.print(f"[dim cyan]{reasoning_text}[/dim cyan]")
                
                # Extraer nuevos términos
                match = re.search(r'NUEVOS_TERMINOS:\s*(.+)', reasoning_text, re.IGNORECASE)
                if match:
                    terms_str = match.group(1).strip()
                    new_terms = [t.strip() for t in terms_str.split(',') if t.strip()]
                    
                    # Extraer razonamiento
                    reasoning_match = re.search(r'RAZONAMIENTO:\s*(.+?)(?:\n|NUEVOS_TERMINOS)', reasoning_text, re.IGNORECASE | re.DOTALL)
                    reasoning = reasoning_match.group(1).strip() if reasoning_match else "Sin razonamiento explícito"
                    
                    if new_terms:
                        console.print(f"[green]OK: Nuevos terminos propuestos:[/green] {', '.join(new_terms)}")
                        return {
                            'retry': True,
                            'new_terms': new_terms,
                            'reasoning': reasoning
                        }
            
            return {'retry': False, 'new_terms': [], 'reasoning': 'No se pudieron generar términos alternativos'}
            
        except Exception as e:
            console.print(f"[red]Error en razonamiento: {e}[/red]")
            return {'retry': False, 'new_terms': [], 'reasoning': str(e)}
    
    def _enrich_query_with_context(self, query: str) -> tuple[str, list]:
        """
        Enriquece la consulta con contexto de la entidad anterior si detecta referencias.
        
        Ejemplo:
        - Respuesta anterior: "...Transformadores BLC..." (sobre Cura Brochero)
        - Query actual: "Explica el punto de Transformadores BLC"
        - Query enriquecida: "Explica Transformadores BLC de Cura Brochero"
        
        Returns:
            (query_enriquecida, entidades_contextuales)
        """
        query_lower = query.lower()
        
        # Detectar patrones de referencia a información previa
        reference_patterns = [
            'explica el punto', 'explica ese punto', 'explica eso',
            'qué significa', 'que significa', 'a qué se refiere', 'a que se refiere',
            'detalla', 'amplia', 'más sobre', 'mas sobre',
            'qué es', 'que es', 'cómo funciona', 'como funciona',
            # Follow-ups típicos sin repetir entidad
            'potencia total', 'de cuanta potencia', 'de cuánta potencia', 'cuanta potencia', 'cuánta potencia',
            'y de cuanta potencia', 'y de cuánta potencia'
        ]
        
        has_reference = any(pattern in query_lower for pattern in reference_patterns)
        
        if has_reference and self.last_entities:
            prev_entity = self.last_entities[0] if self.last_entities else None
            
            if prev_entity:
                words = re.findall(r"\b[\wáéíóúñÁÉÍÓÚÑ-]+\b", query_lower)
                stopwords = {
                    'el','la','los','las','un','una','de','del','en','es','por','para','con','que','qué','como','cómo','sobre','tiene','dame',
                    'dime','cuál','cuáles','cuántos','hay','son','está','información','detalles','datos','explicame','hablame','ahora'
                }
                tokens = set(w for w in words if len(w) > 3 and w not in stopwords)
                prev_tok = set(prev_entity.lower().split())
                new_tokens = [t for t in tokens if t not in prev_tok]
                if new_tokens and prev_entity.lower() not in query_lower:
                    return query, []
                if prev_entity.lower() not in query_lower:
                    enriched_query = f"{query} de {prev_entity}"
                    console.print(f"[cyan]Query enriquecida con contexto: '{prev_entity}'[/cyan]")
                    return enriched_query, self.last_entities
        
        return query, []
    
    def _should_use_conversation_context(self, current_query: str, last_query: str = None) -> bool:
        """
        Determina INTELIGENTEMENTE si debe usar el contexto conversacional previo.
        Evita contaminación cuando el tema cambia completamente.
        
        Args:
            current_query: Pregunta actual
            last_query: Última pregunta del historial
        
        Returns:
            True si debe mantener contexto, False si es tema nuevo
        """
        if not last_query:
            return False
        
        current_lower = current_query.lower()
        last_lower = last_query.lower()
        
        # 1. Palabras que indican continuación explícita del tema
        continuation_indicators = [
            'y ', 'también', 'además', 'otro', 'otra',
            'ese', 'esa', 'eso', 'este', 'esta', 'esto',
            'el mismo', 'la misma', 'lo mismo',
            'ahí', 'allí', 'esa información',
            'más sobre', 'más info', 'más detalles',
            'explicame', 'detalla', 'amplia',
            'qué más', 'qué otras', 'qué otro',
            'ahora', 'de sus', 'del parque', 'de ese', 'de esa', 'sobre eso', 'sus ', ' sus', 'solo ',
            # Deixis específicas de activos
            'esta central', 'esta planta', 'este parque', 'este proyecto', 'esta et', 'esa central', 'la central', 'la planta', 'el parque',
            # Referencias a información previa
            'explica el punto', 'explica ese punto', 'qué significa', 'que significa',
            # Referencias temporales/causales (seguimiento de eventos)
            'acabo de', 'acaba de', 'acaban de', 'si tengo', 'si tuve', 'si ocurre', 'si ocurrió', 'cuando ocurre', 'cuando tengo',
            'en ese caso', 'en este caso', 'si pasa', 'si pasó', 'después de',
            # Conectores causales y conclusivos (NUEVO)
            'entonces', 'por lo tanto', 'por eso', 'así que', 'de modo que', 'en consecuencia',
            # Preguntas de seguimiento sobre el mismo tema
            'eso significa', 'eso quiere decir', 'a qué se refiere', 'qué implica', 'qué pasa si', 'qué sucede si',
            # Continuación con condicionales
            'si sale', 'si entra', 'si actúa', 'si se activa', 'cuando sale', 'cuando entra'
        ]
        
        # Si la pregunta actual tiene indicadores de continuación
        has_continuation = any(ind in current_lower for ind in continuation_indicators)
        
        if has_continuation:
            words_c = re.findall(r"\b[\wáéíóúñÁÉÍÓÚÑ-]+\b", current_lower)
            words_l = re.findall(r"\b[\wáéíóúñÁÉÍÓÚÑ-]+\b", last_lower)
            stopwords = {
                'el','la','los','las','un','una','de','del','en','es','por','para','con','que','qué','como','cómo','sobre','tiene','dame',
                'dime','cuál','cuáles','cuántos','hay','son','está','información','detalles','datos','explicame','hablame','ahora'
            }
            ents_c = set(w for w in words_c if len(w) > 3 and w not in stopwords)
            ents_l = set(w for w in words_l if len(w) > 3 and w not in stopwords)
            if ents_c and ents_l and len(ents_c - ents_l) >= 1:
                return False
            return True
        
        # 2. Extraer entidades técnicas clave de ambas preguntas
        def extract_technical_entities(text):
            """Extrae entidades técnicas (nombres propios, códigos, modelos)"""
            
            stopwords = {
                'el', 'la', 'los', 'las', 'un', 'una', 'de', 'del', 'en', 'es', 'por', 
                'para', 'con', 'que', 'qué', 'como', 'cómo', 'sobre', 'tiene', 'dame', 
                'dime', 'cuál', 'cuáles', 'cuántos', 'hay', 'son', 'está', 'información',
                'detalles', 'datos', 'explicame', 'hablame'
            }
            
            # Extraer palabras significativas (>3 letras, no stopwords)
            words = re.findall(r'\b[a-záéíóúñA-ZÁÉÍÓÚÑ][a-záéíóúñA-ZÁÉÍÓÚÑ0-9-]+\b', text)
            entities = set()
            
            for word in words:
                word_lower = word.lower()
                # Incluir si:
                # - Tiene mayúsculas (nombre propio)
                # - Tiene números (modelo/código)
                # - Es palabra larga y no stopword
                if (word[0].isupper() or 
                    any(c.isdigit() for c in word) or 
                    (len(word) > 4 and word_lower not in stopwords)):
                    entities.add(word_lower)
            
            return entities
        
        current_entities = extract_technical_entities(current_query)
        last_entities = extract_technical_entities(last_query)
        
        # Si alguna pregunta no tiene entidades claras, no usar contexto
        if not current_entities or not last_entities:
            return False
        
        # 3. Calcular similitud entre entidades
        common_entities = current_entities & last_entities
        
        # Similitud = entidades comunes / total de entidades únicas
        total_unique = len(current_entities | last_entities)
        similarity = len(common_entities) / total_unique if total_unique > 0 else 0
        
        # 4. Decisión basada en similitud
        # Si comparten >15% de entidades técnicas, probablemente es el mismo tema (umbral reducido para mejor continuidad)
        if similarity > 0.15:
            return True
        
        # 5. Verificar si hay entidades clave idénticas (nombres específicos o acrónimos críticos)
        # Ej: "Kosten", "SUN2000", "ANSI", "DAG", "ET", "WTG", etc.
        # Acrónimos cortos (3+ letras) son críticos en contexto técnico
        key_entities_match = len(common_entities) >= 1 and any(
            len(e) >= 3  # Cualquier entidad compartida de 3+ letras es suficiente
            for e in common_entities
        )
        
        if key_entities_match:
            return True
        
        # Si no hay similitud suficiente, es tema nuevo
        return False
    
    def _extract_follow_up_anchor(self, user_query: str, last_answer: str) -> str:
        """Extrae una 'ancla' de seguimiento desde la consulta actual y la última respuesta del asistente.
        Regla:
        - Si el usuario incluye una frase entre comillas de ≥5 palabras, usarla como ancla.
        - Si no hay comillas, buscar una secuencia contigua de ≥5 palabras del usuario que aparezca en la última respuesta.
        Devuelve la frase ancla o None.
        """
        try:
            if not self.flags.get('follow_up_mode', True):
                return None
            uq = (user_query or '').strip()
            la = (last_answer or '').strip()
            if not uq:
                return None
            # 1) Frases entre comillas
            quotes = re.findall(r'"([^"]{10,})"|“([^”]{10,})”', uq)
            candidates = []
            for q1, q2 in quotes:
                q = q1 or q2
                if q and len(q.split()) >= 5:
                    candidates.append(q.strip())
            if candidates:
                # Elegir la más larga
                return max(candidates, key=lambda s: len(s))
            # 2) Coincidencia contigua de ≥5 palabras con la última respuesta
            if la:
                words = re.findall(r'\b\w[\wáéíóúñÁÉÍÓÚÑ-]*\b', uq)
                n = len(words)
                # Ventanas de 7 a 5 palabras, priorizando más largas
                for win in (12, 10, 8, 7, 6, 5):
                    if n < win:
                        continue
                    for i in range(0, n - win + 1):
                        phrase = " ".join(words[i:i+win])
                        if phrase and phrase.lower() in la.lower():
                            return phrase
            return None
        except Exception:
            return None
    
    def generate_with_ollama(self, query: str, context: str, conv_context: str = "", detailed: bool = False, is_aggregation: bool = False, num_centrales: int = 0, is_conceptual: bool = False, is_procedural: bool = False, is_direct_comparison: bool = False, is_simple_numeric: bool = False, is_troubleshooting: bool = False, is_summary: bool = False, length_mode: str = None, stream: bool = False, token_callback=None, cancel_checker=None) -> str:
        """Genera respuesta con Ollama incluyendo contexto conversacional"""
        
        # Construir prompt (REVERTIDO a versión completa)
        context_section = ""
        
        # RESTRICCIÓN GLOBAL: Solo documentos, no conocimiento previo
        domain_restriction = """RESTRICCIÓN CRÍTICA: Eres un asistente técnico especializado en ciberseguridad.
- SOLO puedes usar información de los documentos proporcionados.
- PROHIBIDO usar conocimiento previo o entrenamiento general.
- REGLA DE ORO: Si los documentos contienen CUALQUIER información relevante (aunque sea parcial), SIEMPRE responde basándote en ellos. NUNCA digas "no hay información" si los documentos mencionan el tema.
- IMPORTANTE: Los nombres de certificaciones/frameworks pueden aparecer con variantes (ej: "CISSP" = "C I S S P", "MITRE ATT&CK" = "ATTACK framework"). Busca variantes del nombre antes de rechazar.
- Las preguntas pueden hacer referencia a información previa. Usa el contexto conversacional para identificar la entidad.
- PROHIBIDO rechazar con "Lo siento, pero no hay información" si los documentos contienen datos relevantes. Extrae y presenta la información disponible.
- Solo responde "Consulta fuera de mi alcance técnico" si la pregunta es claramente ajena a ciberseguridad/IT Y no hay documentos relevantes.
- Si NO hay ningún documento relevante en el contexto, responde: "No se encontró información en los documentos para esa consulta."
- PROHIBIDO cambiar el nombre de la entidad consultada por otra.
- SOLO menciona entidades (certificaciones/frameworks/términos) que aparezcan en los DOCUMENTOS del contexto.
- Si el nombre consultado no aparece en los documentos, responde: 'No se encontró información en los documentos para esa entidad.'
- IDIOMA OBLIGATORIO: La pregunta del usuario está en español. Los documentos recuperados pueden estar en inglés. DEBES traducir y presentar la información al español en tu respuesta. NUNCA respondas en inglés.
- SI los documentos contienen información parcial o indirectamente relacionada con la pregunta, USA esa información y aclara que es lo que encontraste. No rechaces la pregunta si hay contenido relevante.


"""
        context_section = domain_restriction
        
        if conv_context:
            context_section = f"{context_section}\n{conv_context}\n\n---\n\n"
        # Agregar glosario de acrónimos/definiciones desde equivalencias
        try:
            glossary = self._build_glossary_for_query(query)
        except Exception:
            glossary = ''
        if glossary:
            context_section = f"{context_section}DEFINICIONES OFICIALES (usar exactamente estas):\n{glossary}\n\n---\n\n"
        
        prompt, is_listing = self._build_ollama_prompt(
            query, context, context_section, conv_context,
            detailed, is_aggregation, is_conceptual, is_procedural,
            is_direct_comparison, is_simple_numeric, is_troubleshooting,
            is_summary, length_mode)

        try:
            # Usar API de Ollama con parámetros optimizados
            
            options = self._build_ollama_options(detailed, length_mode, query, is_listing)

            payload = {
                "model": self.ollama_model,
                "prompt": prompt,
                "stream": bool(stream),
                "options": options,
                "keep_alive": "15m"
            }
            
            try:
                approx_prompt_tokens = int(len(prompt) / 4)
                opts = options or {}
                log_event('llm_request', {
                    'model': self.ollama_model,
                    'stream': False,
                    'num_ctx': opts.get('num_ctx'),
                    'num_gpu': opts.get('num_gpu'),
                    'num_batch': opts.get('num_batch'),
                    'num_thread': opts.get('num_thread'),
                    'temperature': opts.get('temperature'),
                    'top_k': opts.get('top_k'),
                    'top_p': opts.get('top_p'),
                    'num_predict': opts.get('num_predict'),
                    'length_mode': length_mode,
                    'detailed': bool(detailed),
                    'is_aggregation': bool(is_aggregation),
                    'is_conceptual': bool(is_conceptual),
                    'is_procedural': bool(is_procedural),
                    'is_direct_comparison': bool(is_direct_comparison),
                    'is_simple_numeric': bool(is_simple_numeric),
                    'is_troubleshooting': bool(is_troubleshooting),
                    'approx_prompt_tokens': approx_prompt_tokens,
                    'prompt_len_chars': len(prompt),
                    'context_len_chars': len(context or ''),
                    'conv_len_chars': len(conv_context or '')
                })
            except Exception:
                pass
            
            # Timeout generoso para evitar fallos (aumentar si long)
            timeout = 240 if detailed else 150
            if isinstance(length_mode, str) and length_mode.strip().lower() == 'long':
                timeout = max(timeout, 300)
            
            console.print(f"[dim]Enviando request a Ollama (timeout: {timeout}s)...[/dim]")
            start_time = time.time()
            
            try:
                response = requests.post(
                    "http://localhost:11434/api/generate",
                    json=payload,
                    timeout=timeout,
                    stream=bool(stream)
                )
                
                elapsed = time.time() - start_time
                console.print(f"[green]Ollama respondió en {elapsed:.1f}s[/green]")
                
            except requests.exceptions.Timeout:
                elapsed = time.time() - start_time
                console.print(f"[red]ERROR: Timeout después de {elapsed:.1f}s[/red]")
                console.print(f"[yellow]El modelo tardó más de {timeout}s en responder[/yellow]")
                raise
            except requests.exceptions.ConnectionError as e:
                console.print(f"[red]ERROR: No se pudo conectar a Ollama[/red]")
                console.print(f"[yellow]¿Está Ollama corriendo? Error: {str(e)[:100]}[/yellow]")
                raise
            
            if response.status_code == 200:
                result_json = None
                answer = ""
                if not stream:
                    result_json = response.json()
                    try:
                        ld = resultjson.get('load_duration')
                        pd = resultjson.get('prompt_eval_duration')
                        ttft = None
                        try:
                            if (ld is not None) and (pd is not None):
                                s_ld = (ld / 1e9) if ld and ld > 1e6 else float(ld or 0)
                                s_pd = (pd / 1e9) if pd and pd > 1e6 else float(pd or 0)
                                ttft = s_ld + s_pd
                        except Exception:
                            ttft = None
                        log_event('llm_infer', {
                            'model': self.ollama_model,
                            'latency_s': round(elapsed, 3),
                            'eval_count': resultjson.get('eval_count'),
                            'prompt_eval_count': resultjson.get('prompt_eval_count'),
                            'total_duration': resultjson.get('total_duration'),
                            'load_duration': resultjson.get('load_duration'),
                            'prompt_eval_duration': resultjson.get('prompt_eval_duration'),
                            'eval_duration': resultjson.get('eval_duration'),
                            'ttft_est_s': ttft
                        })
                    except Exception:
                        pass
                    answer = resultjson.get('response', '').strip()
                else:
                    got_first = False
                    for line in response.iter_lines(decode_unicode=True):
                        try:
                            if callable(cancel_checker) and cancel_checker():
                                try:
                                    response.close()
                                except Exception:
                                    pass
                                break
                        except Exception:
                            pass
                        # Cancelación cooperativa
                        try:
                            if callable(cancel_checker) and cancel_checker():
                                try:
                                    response.close()
                                except Exception:
                                    pass
                                break
                        except Exception:
                            pass
                        if not line:
                            continue
                        try:
                            ev = json.loads(line)
                        except Exception:
                            continue
                        if (not got_first) and ev.get('response'):
                            try:
                                ttft = time.time() - start_time
                                log_event('llm_first_token', {'model': self.ollama_model, 'ttft_s': round(ttft, 3)})
                            except Exception:
                                pass
                            got_first = True
                        # Si se canceló antes de procesar chunk, salir
                        try:
                            if callable(cancel_checker) and cancel_checker():
                                try:
                                    response.close()
                                except Exception:
                                    pass
                                break
                        except Exception:
                            pass
                        chunk = ev.get('response', '') or ''
                        if chunk:
                            try:
                                if callable(token_callback):
                                    token_callback(chunk)
                            except Exception:
                                pass
                            answer += chunk
                        if ev.get('done'):
                            result_json = ev
                            try:
                                ld = resultjson.get('load_duration')
                                pd = resultjson.get('prompt_eval_duration')
                                ttft = None
                                try:
                                    if (ld is not None) and (pd is not None):
                                        s_ld = (ld / 1e9) if ld and ld > 1e6 else float(ld or 0)
                                        s_pd = (pd / 1e9) if pd and pd > 1e6 else float(pd or 0)
                                        ttft = s_ld + s_pd
                                except Exception:
                                    ttft = None
                                log_event('llm_infer', {
                                    'model': self.ollama_model,
                                    'latency_s': round(time.time() - start_time, 3),
                                    'eval_count': resultjson.get('eval_count'),
                                    'prompt_eval_count': resultjson.get('prompt_eval_count'),
                                    'total_duration': resultjson.get('total_duration'),
                                    'load_duration': resultjson.get('load_duration'),
                                    'prompt_eval_duration': resultjson.get('prompt_eval_duration'),
                                    'eval_duration': resultjson.get('eval_duration'),
                                    'ttft_est_s': ttft
                                })
                            except Exception:
                                pass
                            break
                
                answer = self._clean_ollama_response(answer, query, context)
                
                if "no puedo proporcionar" in answer.lower() or "lo siento" in answer.lower()[:50]:
                    console.print(f"[yellow]ADVERTENCIA: LLM generó respuesta de rechazo[/yellow]")
                    console.print(f"[dim]Primeros 200 chars del prompt: {prompt[:200]}...[/dim]")
                    console.print(f"[dim]Respuesta: {answer[:200]}...[/dim]")
                    # Fallback seguro para consultas procedimentales: entregar guía general no operativa
                    try:
                        if is_procedural:
                            al = answer.lower()
                            if ("no puedo" in al and ("proporcionar" in al or "ayudar" in al or "brindar" in al or "ofrecer" in al)) or ("lo siento" in al):
                                fallback = (
                                    "Guia general ante un incidente de seguridad (sin acciones operativas):\n"
                                    "1. Verificar el estado del sistema en logs y registros: eventos, alertas y tendencias.\n"
                                    "2. Confirmar el alcance del incidente (activos, usuarios y sistemas afectados).\n"
                                    "3. Revisar los controles involucrados (por ejemplo firewall, EDR/XDR, SIEM) y su cronologia.\n"
                                    "4. Validar informacion con el equipo de seguridad correspondiente y consignas vigentes.\n"
                                    "5. Consultar procedimientos internos aplicables (playbooks, politicas de respuesta a incidentes) y seguir el flujo de escalamiento.\n"
                                    "6. Notificar al equipo de seguridad; registrar el incidente (hora, señales, evidencias) y abrir ticket.\n"
                                    "7. Si se requiere intervencion, actuar solo segun procedimientos aprobados y con autorizacion correspondiente.\n"
                                    "Nota: Pasos orientativos basados en documentacion disponible. Adaptar segun procedimientos especificos de la organizacion."
                                )
                                answer = fallback
                    except Exception:
                        pass
                
                # AUTO-REVISIÓN: desactivada por defecto para evitar contradicciones
                # Solo activar si enable_self_review está EXPLÍCITAMENTE en True
                if (not is_aggregation) and (not is_conceptual) and \
                   (((not detailed) or self.flags.get('enable_self_review_in_detailed', False))) and \
                   (not (isinstance(length_mode, str) and length_mode.strip().lower() == 'long')) and \
                   (not is_procedural) and \
                   self.config.get('enable_self_review', False):
                    answer = self._self_review_answer(query, answer, context)

                # Enforce longitud según preferencia de UI (short con overflow hasta 20%)
                try:
                    if isinstance(length_mode, str) and length_mode.strip().lower() == 'short':
                        limit = 1200  # 1000 con tolerancia del 20%
                        if len(answer) > limit:
                            answer = self._truncate_safe_short(answer, limit)
                except Exception:
                    pass
                
                # FASE 5: Post-procesamiento de la respuesta
                try:
                    answer = self._post_process_answer(answer)
                    console.print(f"[dim]Post-procesamiento aplicado[/dim]")
                except Exception as e:
                    console.print(f"[dim]Post-procesamiento no aplicado: {e}[/dim]")
                
                console.print(f"[dim]Longitud final antes de retornar: {len(answer)} chars[/dim]")
                return answer
            else:
                console.print(f"[red]ERROR: Ollama HTTP {response.status_code}[/red]")
                return f"Error: HTTP {response.status_code}"
        
        except requests.exceptions.Timeout:
            timeout_msg = "5 minutos" if detailed else "4 minutos"
            return f"Error: Timeout (>{timeout_msg}). El modelo está tomando demasiado tiempo. Verifica que Ollama esté corriendo correctamente."
        except Exception as e:
            return f"Error: {str(e)}"

    def _build_ollama_prompt(self, query, context, context_section, conv_context,
                              detailed, is_aggregation, is_conceptual, is_procedural,
                              is_direct_comparison, is_simple_numeric, is_troubleshooting,
                              is_summary, length_mode):
        is_listing = False
        # Detección de pedido de longitud explícita (exhaustividad sin disclaimers)
        has_length_req = re.search(r'\b(minimo|mínimo|al menos|como minimo|como mínimo)\s+\d+\s+(palabra|palabras|caracteres)\b', (query or '').lower()) or re.search(r'\b\d+\s+(palabra|palabras|caracteres)\b', (query or '').lower())
        
        if has_length_req:
            prompt = f"""Eres un asistente técnico. Proporciona una respuesta EXHAUSTIVA usando SOLO los documentos.

{context_section}
DOCUMENTOS:
{context}

PREGUNTA: {query}

INSTRUCCIONES:
1. Extrae TODA la información disponible de los documentos sobre el tema solicitado.
2. Organiza en secciones claras con encabezados.
3. Incluye citas [Doc N - nombre p.X] para cada dato.
4. Sé exhaustivo: cubre todos los aspectos mencionados en los documentos.
5. NO uses disclaimers de longitud o falta de información si los documentos tienen contenido relevante.

Respuesta:"""
        elif is_summary:
            # Detección de modo resumen
            prompt = f"""Eres un asistente técnico. Resume el contenido solicitado usando SOLO los documentos.

{context_section}
DOCUMENTOS:
{context}

PREGUNTA: {query}

INSTRUCCIONES:
1. Entrega un resumen estructurado: Objetivo -> Alcance -> Responsables -> Requisitos -> Secciones/Pasos.
2. Incluye citas como [Doc N - nombre p.X] cuando corresponda.
3. Sé conciso, directo y no inventes información.

Respuesta:"""
        elif is_conceptual:
            # MODO CONCEPTUAL: Explicación general con base documental
            prompt = f"""Eres un asistente técnico experto. Explica el concepto solicitado usando SOLO los documentos proporcionados.

{context_section}
DOCUMENTOS:
{context}

PREGUNTA: {query}

INSTRUCCIONES:
1. Proporciona una explicación CLARA Y DIRECTA del concepto.
2. Usa información SOLO de los documentos proporcionados.
3. Estructura: definición breve -> componentes/funcionamiento -> ejemplos concretos de los docs.
4. Cita las fuentes como [Doc N - nombre p.X] cuando uses información específica.
5. Si la pregunta es general pero los docs solo tienen casos específicos, indícalo: "Según los documentos disponibles..." y explica con ejemplos.

PROHIBIDO:
- Inventar información no presente en los documentos.
- Autocorregirte o añadir una sección de "errores" al final.
- Usar tablas o formato tabular salvo que se soliciten.
- Introducir temas no relacionados con ciberseguridad/IT.

Respuesta:"""
        elif is_direct_comparison:
            # MODO COMPARACIÓN DIRECTA: Comparar dos entidades específicas uno-a-uno
            prompt = f"""Eres un asistente técnico. Compara las entidades solicitadas usando SOLO los documentos.

{context_section}
DOCUMENTOS:
{context}

PREGUNTA: {query}

INSTRUCCIONES CRÍTICAS:
1. Si los documentos contienen información sobre AMBAS entidades, extrae y compara.
2. NUNCA digas "no se menciona X" si X aparece en los documentos.
3. **IMPORTANTE: Extrae TODOS los datos relevantes** (requisitos, estructura, aplicabilidad, etc.)
4. Presenta en formato claro:
   **[Entidad A]**:
   - Definición/propósito: X [Doc N - nombre p.X]
   - Requisitos: Y [Doc N - nombre p.X]
   - Estructura/componentes: Z [Doc N - nombre p.X]
   
   **[Entidad B]**:
   - Definición/propósito: X [Doc N - nombre p.X]
   - Requisitos: Y [Doc N - nombre p.X]
   - Estructura/componentes: Z [Doc N - nombre p.X]
   
   **Diferencias principales**: Menciona las diferencias clave.

PROHIBIDO:
- Decir "no se menciona" si la entidad aparece en los documentos.
- Inventar datos.
- Omitir información clave disponible en los documentos.
- Mencionar entidades no solicitadas.
- Usar tablas salvo que el usuario las pida.
- Introducir temas no solicitados.
- Usar referencias como "(Doc 22)" sin el formato completo [Doc N - nombre p.X].

Respuesta:"""
        elif is_simple_numeric:
            # MODO NUMÉRICO SIMPLE: Respuesta ultra-concisa con un dato numérico
            prompt = f"""Responde con el dato numérico solicitado de forma DIRECTA y CONCISA.

{context_section}
DOCUMENTOS:
{context}

PREGUNTA: {query}

INSTRUCCIONES:
1. Busca el dato numérico exacto en los documentos.
2. **IMPORTANTE: Menciona el nombre de la certificación/framework en tu respuesta.**
3. Responde en UNA línea: "[Entidad]: [Valor] [unidad] [Doc N - nombre p.X]"
4. Si no encuentras el dato: "No se encontró información"

PROHIBIDO:
- Explicaciones adicionales salvo que sean críticas.
- Aproximar o inventar números.
- Omitir el nombre de la entidad/certificación.

Respuesta:"""
        elif is_troubleshooting:
            # MODO TROUBLESHOOTING/DIAGNÓSTICO: Guía de diagnóstico basada en docs
            prompt = f"""Eres un asistente técnico. Proporciona un diagnóstico basado en los documentos.

{context_section}
DOCUMENTOS:
{context}

PREGUNTA: {query}

INSTRUCCIONES:
1. Identifica el problema o síntoma descrito.
2. Estructura tu respuesta:
   **Posibles causas** (según documentos):
   - Causa 1 [Doc N - nombre p.X]
   - Causa 2 [Doc N - nombre p.X]
   
   **Verificaciones recomendadas**:
   - Paso 1
   - Paso 2
   
   **Referencias documentales**: [Doc N - nombre p.X]

3. Si no hay información suficiente, indícalo claramente.

PROHIBIDO:
- Instrucciones operativas sin respaldo documental.
- Inventar causas o soluciones.
- Introducir temas no solicitados (ej: Entrada en Servicio).

Respuesta:"""
        elif is_aggregation:
            # MODO AGREGACIÓN: Extraer tabla de centrales línea por línea
            
            # Buscar TOTAL en el contexto
            total_match = re.search(r'TOTAL\s*\n\s*([\d,\.]+)', context, re.IGNORECASE)
            total_value = total_match.group(1) if total_match else "No encontrado"
            
            # Extraer centrales línea por línea (mejorado para nombres multi-línea)
            lines = context.split('\n')
            centrales = []
            i = 0
            while i < len(lines) - 2:
                line1 = lines[i].strip()
                line2 = lines[i+1].strip()
                line3 = lines[i+2].strip()
                
                # Verificar si line2 es un número y line3 es una tecnología
                if re.match(r'^[\d,\.]+$', line2) and line3 in ['Eólica', 'Fotovoltaica', 'Biogás', 'Biomasa']:
                    # line1 es el nombre de la central
                    if line1 and not line1.startswith('CENTRAL') and not line1.startswith('POTENCIA'):
                        nombre = line1
                        
                        # Verificar si el nombre continúa en la línea anterior (nombres multi-línea)
                        if i > 0:
                            line_prev = lines[i-1].strip()
                            # Si la línea anterior no es un número ni tecnología, es parte del nombre
                            if line_prev and not re.match(r'^[\d,\.]+$', line_prev) and line_prev not in ['Eólica', 'Fotovoltaica', 'Biogás', 'Biomasa', 'CENTRAL', 'POTENCIA', 'MW', 'TECNOLOGIA', 'BLC', 'Inv. Kehua', 'Inv. Huawei']:
                                # Casos especiales: nombres que están en 2 líneas
                                if 'Río Seco' in nombre and 'Villa María' in line_prev:
                                    nombre = f"P.S. Villa María del Río Seco"
                                elif 'CHACO' in nombre and 'PERLA' in line_prev:
                                    nombre = f"P.S. LA PERLA DE CHACO"
                                elif 'Ventura' in nombre and 'Buena' in line_prev:
                                    nombre = f"P.E. de la Buena Ventura"
                                elif not any(x in line_prev for x in ['Supervisor', 'Responsable', 'Instructivo', 'Anexo']):
                                    # Otros casos: concatenar si no es encabezado
                                    nombre = f"{line_prev} {nombre}"
                        
                        centrales.append((nombre, line2, line3))
                i += 1
            
            # Formatear tabla de centrales
            tabla_centrales = ""
            if centrales:
                tabla_centrales = "\n**TABLA DE CENTRALES EXTRAÍDA:**\n"
                for i, (nombre, potencia, tecnologia) in enumerate(centrales, 1):
                    tabla_centrales += f"{i}. {nombre}: {potencia} MW ({tecnologia})\n"
                tabla_centrales += f"\n**TOTAL OFICIAL: {total_value} MW**\n"
                tabla_centrales += f"**Total de centrales: {len(centrales)}**\n"
            
            # MODO AGREGACIÓN: Usar SOLO la tabla extraída
            # Evitar este modo si el usuario pide TECNOLOGÍA o COBERTURA COMPLETA de Anexos D
            tech_sig = any(k in (query.lower()) for k in ['tecnologia', 'tecnología', 'tecnologias', 'tecnologías'])
            if tabla_centrales and not (tech_sig or self._requires_full_anexos_coverage(query)):
                # Si tenemos tabla extraída, NO enviar el contexto completo
                prompt = f"""Eres un asistente técnico especializado en ciberseguridad. Tienes una tabla con TODOS los elementos extraídos de los documentos.

{context_section}
{tabla_centrales}

PREGUNTA: {query}

INSTRUCCIONES:
1. La tabla tiene TODOS los elementos con valores EXACTOS.
2. NO inventes ni modifiques NADA.
3. Usa el TOTAL OFICIAL al final de la tabla.
4. Cita como [Doc N - nombre p.X] si es relevante.

PROHIBIDO:
- Preámbulos ("Entendido", "Análisis:").
- Código o JSON.
- Encabezados Markdown (###) o emojis.
- Introducir temas no solicitados.

Formato:
- Si piden total: "[TOTAL OFICIAL]".
- Si piden listado: copiar tabla exactamente.

Respuesta:"""
        elif is_procedural:
            # MODO PROCEDIMENTAL: Guía general segura y no operativa basada en documentos
            prompt = f"""Eres un asistente técnico. Proporciona una guía GENERAL, SEGURA y NO OPERATIVA basada EXCLUSIVAMENTE en los documentos.

{context_section}
DOCUMENTOS:
{context}

PREGUNTA: {query}

INSTRUCCIONES:
1. Entrega PASOS de verificación y comunicación (NO operativos).
2. Usa los documentos solo como referencia informativa.
3. Si describe un evento, incluye: verificación de estados, alertas, controles, registros de logs/eventos, comunicación con el responsable.
4. Indica consultar procedimientos internos aplicables y notificar al equipo de seguridad correspondiente.
5. Si no hay evidencia documental para un paso, decláralo explícitamente.
6. Cita las fuentes como [Doc N - nombre p.X].

FORMATO:
- Título breve.
- Lista numerada de pasos de verificación y comunicación.
- Nota final de seguridad y referencia a documentación.

PROHIBIDO:
- Maniobras o cambios de estado.
- Operaciones específicas sin respaldo documental claro.
- Introducir temas no solicitados (ej: Entrada en Servicio, habilitación comercial).

Respuesta con pasos:"""
        elif detailed:
            # Respuesta DETALLADA
            prompt = f"""Extrae TODA la información disponible del tema solicitado usando SOLO los documentos.

{context_section}
DOCUMENTOS:
{context}

PREGUNTA: {query}

INSTRUCCIONES CRÍTICAS:
1. Proporciona una respuesta COMPLETA Y EXHAUSTIVA - NO te detengas en la primera línea o párrafo.
2. Incluye TODOS los datos relevantes encontrados en los documentos:
   - Definiciones y conceptos clave
   - Nombres de certificaciones, frameworks, estándares
   - Requisitos, prerequisitos, criterios de elegibilidad
   - Estructura de exámenes (dominios, número de preguntas, duración)
   - Roles y responsabilidades profesionales
   - Procedimientos y mejores prácticas
   - Cualquier dato numérico relevante (costos, duración, etc.)
3. Si encuentras información parcial en un documento, CONTINÚA buscando en otros fragmentos.
4. Organiza claramente: usa títulos, listas numeradas si aplica.
5. Cita las fuentes como [Doc N - nombre p.X] para cada dato importante.
6. Si varios documentos aportan información, COMBINA toda la información disponible.

PROHIBIDO:
- Detenerte después de extraer solo el primer dato.
- Inventar o extrapolar datos no presentes en los documentos.
- Autocorregirte o añadir una sección de "errores" al final de tu respuesta.
- Usar tablas salvo que el usuario las pida explícitamente.

Respuesta detallada y completa:"""
        else:
            # Respuesta NORMAL
            # Detectar si pide explicación de un documento específico
            is_doc_explanation = self._is_doc_explanation_query(query)
            doc_ref = self._extract_doc_reference(query)
            
            # Detectar si requiere información de múltiples documentos
            is_multi_doc = self._is_multi_document_query(query)
            # Detectar si es una petición de LISTADO (enumeración de centrales)
            is_listing = self._is_listing_query(query)
            
            if is_doc_explanation and doc_ref:
                # MODO EXPLICACIÓN DE DOCUMENTO: Explicar en profundidad un documento citado
                prompt = f"""Eres un asistente técnico. Explica en profundidad el documento [{doc_ref['doc_name']} p.{doc_ref['page']}].

{context_section}
DOCUMENTO:
{context}

PREGUNTA: {query}

INSTRUCCIONES:
- Proporciona una explicación COMPLETA y DETALLADA.
- Incluye TODOS los procedimientos, pasos, códigos y valores técnicos.
- Organiza claramente (títulos, listas numeradas si aplica).
- Cita la fuente como [Doc N - nombre p.X].

PROHIBIDO:
- Inventar información no presente.
- Introducir temas no solicitados (ej: Entrada en Servicio, habilitación comercial).
- Usar tablas salvo que el usuario las pida.

Explicación detallada:"""
            elif is_listing:
                # MODO LISTADO: Enumerar TODOS los frameworks/controles/políticas (solo nombres)
                # Detectar filtro de categoría de ciberseguridad
                tech_filter = ""
                if 'network' in query.lower() or 'red' in query.lower():
                    tech_filter = "\n- **IMPORTANTE: Lista SOLO elementos de categoría NETWORK. NO incluyas otras categorías.**"
                elif 'cloud' in query.lower() or 'nube' in query.lower():
                    tech_filter = "\n- **IMPORTANTE: Lista SOLO elementos de categoría CLOUD. NO incluyas otras categorías.**"

                prompt = f"""Eres un asistente técnico especializado en ciberseguridad. Enumera TODOS los elementos solicitados usando SOLO los documentos.

{context_section}
DOCUMENTOS:
{context}

PREGUNTA: {query}

INSTRUCCIONES:
- Lista SOLO los NOMBRES de los elementos solicitados (sin detalles adicionales, sin comentarios).{tech_filter}
- Un ítem por línea, numerado.
- No repitas nombres ni incluyas líneas vacías.
- Si falta información para completar la lista total, indica claramente cuántos elementos encontraste.
 - Si no encuentras info: "No se encontró información" (exacto, sin explicaciones adicionales).
 - No incluyas fuentes ni comentarios.

 PROHIBIDO:
 - Preambulos o metacomentarios ("Entendido", "Análisis:", "Respuesta final:").
 - Razonamiento visible o explicación del proceso.
 - Bloques de código o JSON.
 - Encabezados Markdown (###) o emojis.

Respuesta (solo la lista):"""
            elif is_multi_doc:
                # MODO MULTI-DOCUMENTO: Agregar información de múltiples fuentes
                prompt = f"""Eres un asistente técnico experto. Analiza TODOS los documentos y responde.

{context_section}
DOCUMENTOS (sin acentos - corrígelos en tu respuesta):
{context}

PREGUNTA: {query}

INSTRUCCIONES:
1. **LEE TODOS LOS DOCUMENTOS**: Revisa CADA fragmento [Doc 1], [Doc 2]... hasta el último.
2. **COMBINA INFORMACIÓN**: Si varios documentos contienen datos relevantes, combínalos.
3. **BUSCA PATRONES NUMÉRICOS**: Tablas, frases con números ("El framework tiene X controles"), números en texto ("diez y seis").
4. **CORRIGE ORTOGRAFÍA**: Agrega acentos correctos ("Numero" -> "Número").
5. **Cita fuentes**: Usa formato [Doc N - nombre p.X].

PROHIBIDO:
- Inventar o aproximar números.
- Agregar secciones extra o preguntas de seguimiento.
- Repetir información.
- Introducir temas no solicitados (ej: Entrada en Servicio, habilitación comercial).
- Usar tablas salvo que el usuario las pida.

Respuesta:"""
            elif is_simple_numeric:
                # MODO NUMÉRICO SIMPLE: Extraer un dato específico (potencia, cantidad, etc.)
                prompt = f"""Eres un asistente técnico. Extrae el dato numérico solicitado usando SOLO los documentos.

{context_section}
DOCUMENTOS:
{context}

PREGUNTA: {query}

INSTRUCCIONES CRÍTICAS:
1. **BUSCA EL DATO ESPECÍFICO**: Versión, cantidad, número, puntaje CVSS, etc.
2. **EXTRAE TODOS LOS VALORES RELEVANTES**: Si hay múltiples menciones del dato, inclúyelas todas.
3. **FORMATO CLARO**: Responde directamente con el valor y la unidad (ej: "versión 4.2", "7 controles", "CVSS 9.8").
4. **INCLUYE CONTEXTO MÍNIMO**: Menciona la entidad a la que pertenece el dato.
5. **CITA LA FUENTE**: Usa formato [Doc N - nombre p.X].

PROHIBIDO:
- Detenerte en el primer dato parcial (ej: solo nombre cuando se pregunta versión).
- Inventar valores no presentes en los documentos.
- Agregar información no solicitada.

Respuesta directa:"""
            else:
                # MODO GENERAL: Responder con datos precisos y concisos
                prompt = f"""Eres un asistente técnico especializado en ciberseguridad. Debes responder de forma
precisa y sustentada SOLO con la información de los documentos provistos. Si no hay
suficiente evidencia, admite que no se encontró en los documentos.
Primero, responde con el dato principal en una sola línea, claro y conciso. Luego (si aplica) agrega detalles breves. No incluyas fuentes en el texto, el sistema las mostrará aparte.
No introduzcas temas no consultados a menos que el usuario lo pida explícitamente.
No declares propietarios/empresas si no está explícitamente indicado en el CONTEXTO.
{context_section}
CONTEXTO RELEVANTE:
{context}

PREGUNTA: {query}

INSTRUCCIONES CRÍTICAS:
1. **LEE TODOS LOS DOCUMENTOS**: Revisa CADA fragmento [Doc 1], [Doc 2], [Doc 3]... hasta el último. NO te detengas en los primeros.
2. **USA EL CONTEXTO ESTRUCTURADO**: El contexto está organizado por categorías:
   - === DEFINICIONES Y CONCEPTOS ===: Usa para explicar qué es algo
   - === PROCEDIMIENTOS Y MEJORES PRÁCTICAS ===: Usa para responder cómo hacer algo
   - === EJEMPLOS Y CASOS ===: Usa para ilustrar con casos concretos
   - === MENCIONES ADICIONALES ===: Información complementaria
3. **EXTRAE TODA LA INFORMACIÓN RELEVANTE**: Si varios documentos contienen datos sobre la pregunta, COMBINA toda la información.
4. **NO OMITAS DATOS**: Si encontraste información en [Doc 5] pero no la mencionaste, VUELVE y agrégala a la respuesta.

Restricciones:
- No agregues secciones extra, ni preguntas de seguimiento.
- No repitas la misma información.
- Si la pregunta es sobre una entidad específica, responde SOLO sobre esa entidad; ignora otras.
- Verifica consistencia numérica con los datos del contexto; no inventes totales ni dupliques sumas.
- NO HAGAS CÁLCULOS ni operaciones matemáticas a menos que el usuario lo solicite explícitamente. Reporta los números tal como aparecen en los documentos.
- No incluyas notas, correcciones, revisiones ni metacomentarios (ej.: "Nota:", "Corrección final", "Revisión final").
- Si no encuentras info: "No se encontró información" (exacto, sin explicaciones adicionales).
 
REGLAS DE RAZONAMIENTO HÍBRIDO (FASE 5):
- Prioridad 1: Usar información de los DOCUMENTOS proporcionados siempre que sea posible.
- Prioridad 2: Si los documentos son insuficientes o no contienen la respuesta completa, PUEDES complementar con conocimiento general del dominio de ciberseguridad/IT.
- CUANDO uses conocimiento general, marca claramente con prefijo: "[Conocimiento general]" antes de esa parte de la respuesta.
- NUNCA inventes información específica (nombres, fechas, versiones) que no estén en los documentos ni en tu conocimiento verificable.
- Si una pregunta requiere datos exactos y estos no están en los documentos, indica: "[Conocimiento general] Según conocimiento del dominio, [tu respuesta basada en conocimiento general]."

PROHIBIDO ABSOLUTO:
- Responder preguntas fuera del dominio de ciberseguridad e IT. Si la pregunta no es sobre seguridad informática, frameworks de seguridad, tecnologías IT, o temas relacionados, responde: "Consulta fuera de mi alcance técnico."
- Inventar información específica (números de versión, fechas exactas, nombres de personas) que no esté en los documentos ni sea de dominio público verificable.
- Contradecirte: nunca digas "No se encontró información" y luego proporciones la información.
- Preambulos o metacomentarios ("Entendido", "Análisis:", "Respuesta final:").
- Razonamiento visible o explicación del proceso.
- Bloques de código o JSON.
- Encabezados Markdown (###) o emojis.

Respuesta:"""

        # Si está activado el modo de prompts simples, sobreescribe el prompt con un formato mínimo
        try:
            if self.flags.get('plain_prompts', False):
                prompt = (
                    f"Contexto relevante:\n{context_section}\n{context}\n\n"
                    f"Pregunta: {query}\n\nRespuesta:"
                )
        except Exception:
            pass

        # Añadir pista de estilo para modo corto (respuestas concisas)
        short_hint = ""
        if (not self.flags.get('plain_prompts', False)) and isinstance(length_mode, str) and length_mode.strip().lower() == 'short':
            short_hint = "\n\nESTILO: Responde de forma lo más CORTA, PRECISA y COMPLETA posible. Sin preámbulos. Incluye al menos una cita [Doc i - fuente p.X]."
        if short_hint:
            try:
                prompt = prompt + short_hint
            except Exception:
                pass

        try:
            if not self._is_centrales_list_request(query):
                if not self.flags.get('plain_prompts', False):
                    prompt = prompt + "\n\nRESTRICCION: No uses tablas ni formato tabular (|, columnas) salvo que el usuario pida 'lista', 'listado', 'tabla' o 'tablilla'."
        except Exception:
            pass
        return prompt, is_listing

    def _build_ollama_options(self, detailed, length_mode, query, is_listing):
        # Parámetros OPTIMIZADOS para RTX 4050 (6GB) + Ryzen 5 7535HS (12 threads)
        # BALANCE entre velocidad y calidad
        full_cov = self._requires_full_anexos_coverage(query)
        if detailed:
            # Parámetros para RESPUESTA DETALLADA (optimizados para consistencia)
            options = {
                "num_predict": 900,
                "temperature": 0.2,
                "top_k": 30,
                "top_p": 0.85,
                "num_ctx": 2048,
                "num_thread": 8,
                "num_gpu": getattr(self, 'num_gpu_tuned', 99),
                "num_batch": 64,
                "repeat_penalty": 1.2,
                "seed": 42,
                "stop": ["```"]
            }
        else:
            # Parámetros para RESPUESTA NORMAL (optimizados para consistencia)
            options = {
                "num_predict": 500,
                "temperature": 0.2,
                "top_k": 30,
                "top_p": 0.85,
                "num_ctx": 2048,
                "num_thread": 8,
                "num_gpu": getattr(self, 'num_gpu_tuned', 99),
                "num_batch": 64,
                "seed": 42,
                "stop": ["```"]
            }
        # Ajuste por length_mode explícito
        try:
            if isinstance(length_mode, str):
                lm = length_mode.strip().lower()
                if lm == 'long':
                    # Permitir salida amplia para superar 3000 chars (aprox.)
                    options["num_predict"] = max(options.get("num_predict", 600), 1200)
                elif lm == 'short':
                    # Salida compacta para facilitar <1000 chars
                    options["num_predict"] = min(options.get("num_predict", 350), 256)
        except Exception:
            pass
        # Ajuste para LISTADO: permitir salida más larga si enumera muchos nombres
        if 'is_listing' in locals() and is_listing:
            try:
                options["num_predict"] = max(options.get("num_predict", 350), 800)
            except Exception:
                pass
        # MEJORA: Ajuste para queries de herramientas/equipos de ciberseguridad
        query_lower = query.lower()
        if any(kw in query_lower for kw in ['firewall', 'sensor', 'agente', 'equipo', 'modelo', 'appliance', 'herramienta']):
            try:
                options["num_predict"] = max(options.get("num_predict", 500), 600)
            except Exception:
                pass
        # Si el usuario pide cobertura completa, ampliar ligeramente el límite de salida
        if full_cov:
            try:
                options["num_predict"] = min(options.get("num_predict", 450) + 200, 800)
            except Exception:
                pass
        return options

    def _clean_ollama_response(self, answer, query, context):
        # FILTRAR THINKING DE QWEN: Extraer solo la respuesta final
                
        # DEBUG: Mostrar primeros 300 chars de la respuesta cruda
        console.print(f"[dim]Respuesta cruda (primeros 300 chars): {answer[:300]}...[/dim]")
        console.print(f"[dim]Longitud respuesta cruda: {len(answer)} chars[/dim]")
                
        original_answer = answer  # Guardar original por si acaso
                
        # ESTRATEGIA 1: Si empieza con thinking en inglés, buscar la respuesta real después
        if answer.startswith(('Okay,', 'Let me', 'First,', 'The user', 'Looking at')):
            # Buscar patrones que indican el inicio de la respuesta real
            patterns = [
                r'(?:Respuesta|Answer|Response):\s*(.+)',  # "Respuesta: ..."
                r'(?:La respuesta es|The answer is):\s*(.+)',  # "La respuesta es: ..."
                r'\n\n([A-Z][^\.]+\.)',  # Párrafo que empieza con mayúscula después de doble salto
            ]
                    
            for pattern in patterns:
                match = re.search(pattern, answer, re.DOTALL | re.IGNORECASE)
                if match:
                    answer = match.group(1).strip()
                    console.print(f"[green]Respuesta extraída con patrón: {pattern[:30]}...[/green]")
                    break
            else:
                # Si no encuentra patrones, tomar todo después del primer párrafo de thinking
                lines = answer.split('\n')
                # Saltar las primeras líneas que parecen thinking
                for i, line in enumerate(lines):
                    if line.strip() and not line.startswith(('Okay', 'Let', 'First', 'The', 'Looking')):
                        answer = '\n'.join(lines[i:])
                        break
                
        # ESTRATEGIA 2: Remover etiquetas de thinking si existen
        while '<thinking>' in answer or '</thinking>' in answer:
            answer = re.sub(r'<thinking>.*?</thinking>', '', answer, flags=re.DOTALL)
                
        # Remover marcadores y artefactos
        answer = re.sub(r'\[Escribe tu respuesta aquí\]', '', answer)
        answer = re.sub(r'\(en español\)', '', answer)
        # Quitar fences y separadores comunes
        answer = answer.replace('```', '')
        answer = re.sub(r'^---.*$', '', answer, flags=re.MULTILINE)
        # Eliminar encabezados Markdown
        answer = re.sub(r'^\s*#{1,6}\s+.*$', '', answer, flags=re.MULTILINE)
        # Eliminar líneas de metacomentarios frecuentes
        meta_patterns = [
            r'^\s*RESPUESTA FINAL.*$', r'^\s*Respuesta final.*$', r'^\s*An(á|a)lisis.*$',
            r'^\s*Analizando.*$', r'^\s*Entendido.*$', r'^\s*Cumple todas las instrucciones.*$',
            r'^\s*Nota t(é|e)cnica.*$', r'^\s*Nota:.*$'
        ]
        for pat in meta_patterns:
            answer = re.sub(pat, '', answer, flags=re.MULTILINE)
        answer = re.sub(r'\n\s*\n\s*\n+', '\n\n', answer)
        answer = answer.strip()
        console.print(f"[dim]Longitud tras limpieza básica: {len(answer)} chars[/dim]")
                
        # Si es listado, evitar JSON/bloques
        try:
            if self._is_listing_query(query):
                # Remover líneas que empiecen con llaves o corchetes
                answer = re.sub(r'^[\[\{].*$', '', answer, flags=re.MULTILINE).strip()
                console.print(f"[dim]Longitud tras limpieza de listado: {len(answer)} chars[/dim]")
        except Exception:
            pass
                
        # Guardia final: si la respuesta está vacía tras posprocesado, sintetizar desde contexto
        if not answer or len(answer.strip()) == 0 or not any(ch.isalnum() for ch in answer):
            console.print(f"[yellow]ADVERTENCIA: Respuesta vacía tras posprocesado; usando síntesis del contexto[/yellow]")
            try:
                # Tomar el primer párrafo no vacío del contexto como fallback breve
                paras = [p.strip() for p in (context or '').split('\n\n') if p and any(ch.isalnum() for ch in p)]
                if paras:
                    answer = paras[0][:600].strip()
                    console.print(f"[dim]Respuesta sintetizada desde contexto: {len(answer)} chars[/dim]")
            except Exception:
                pass
            if not answer or len(answer.strip()) == 0:
                answer = "No se encontró información en los documentos para esa consulta."
                console.print(f"[yellow]Usando mensaje determinístico por falta de síntesis[/yellow]")
        return answer

    def _handle_system_command(self, command: str) -> dict:
        """
        Maneja comandos del sistema (/comando)
        
        Args:
            command: Comando completo (ej: "/reset", "/ayuda")
        
        Returns:
            Diccionario con respuesta del comando
        """
        cmd = command.lower().strip()
        console.print(f"[bold yellow]Comando del sistema: {cmd}[/bold yellow]")
        
        # /reset - Limpiar historial
        if cmd == '/reset':
            self.conversation.clear()
            response = "OK: **Historial de conversación limpiado**\n\nPuedes empezar una nueva conversación desde cero."
            console.print("[green]OK: Historial limpiado[/green]")
            
            return {
                'question': command,
                'results': [],
                'context': '',
                'answer': response,
                'method': 'system_command',
                'memory_hits': 0
            }
        
        # /mapa_borrar - Borrar hecho o entidad del mapa conceptual
        elif cmd.startswith('/mapa_borrar') or cmd.startswith('/mapa_eliminar'):
            # Formatos soportados:
            #   /mapa_borrar <entidad>.<atributo>
            #   /mapa_borrar <entidad>.*
            #   /mapa_borrar <entidad>
            try:
                parts = command.split(maxsplit=1)
                if len(parts) < 2:
                    response = (
                        "Uso: /mapa_borrar <entidad>[.<atributo>|.*]\n\n"
                        "Ejemplos:\n"
                        "• /mapa_borrar 'eolico vientos del secano'.tecnologia\n"
                        "• /mapa_borrar 'eolico vientos del secano'.*\n"
                        "• /mapa_borrar 'eolico vientos del secano'"
                    )
                    return {
                        'question': command,
                        'results': [],
                        'context': '',
                        'answer': response,
                        'method': 'system_command',
                        'memory_hits': 0
                    }
                target = parts[1].strip()
                # Remover comillas si vienen
                if (target.startswith("'") and target.endswith("'")) or (target.startswith('"') and target.endswith('"')):
                    target = target[1:-1]
                entity = target
                attribute = None
                if '.' in target:
                    entity, attribute = target.split('.', 1)
                    entity = entity.strip()
                    attribute = attribute.strip()
                removed = False
                if attribute and attribute != '*':
                    removed = self.conceptual_map.remove_fact(entity, attribute)
                else:
                    removed = self.conceptual_map.remove_entity(entity)
                if removed:
                    response = f"OK: Eliminado del mapa conceptual: {entity}{'.'+attribute if attribute and attribute!='*' else ''}"
                else:
                    response = f"No se encontró entrada para eliminar: {entity}{'.'+attribute if attribute and attribute!='*' else ''}"
            except Exception as e:
                response = f"Error al borrar del mapa: {e}"
            return {
                'question': command,
                'results': [],
                'context': '',
                'answer': response,
                'method': 'system_command',
                'memory_hits': 0
            }
        
        # /ayuda - Mostrar ayuda
        elif cmd == '/ayuda' or cmd == '/help':
            response = """# 📚 Guía de Uso - CROM RAG Assistant

## 🔍 Comandos Disponibles

- `/ayuda` - Muestra esta guía
- `/reset` - Limpia el historial de conversación
- `/centrales` - Listar centrales
- `/documentos` - Muestra documentos indexados
- `/memoria` - Ver sinónimos guardados en memoria
- `/mapa` - Ver mapa conceptual aprendido (atajos y hechos)

## 🧠 Memoria de Sinónimos

Puedes enseñarme equivalencias de términos:

**Ejemplos:**
- "Guarda que molino eólico = WTG = aerogenerador"
- "Recuerda que inversor es lo mismo que convertidor"

## 💡 Ejemplos de Consultas

**Información general:**
- "¿Cuántas centrales opera el CROM?"
- "Dame información sobre Kosten"

**Procedimientos:**
- "¿Cómo se opera una central eólica?"
- "Procedimiento ante falla de sistema"

**Comparaciones:**
- "Compara Kosten y Algarrobo"

**Agregaciones:**
- "¿Cuál es la potencia total del CROM?"
"""
            
            return {
                'question': command,
                'results': [],
                'context': '',
                'answer': response,
                'method': 'system_command',
                'memory_hits': 0
            }
        
        # /centrales - Listar centrales
        elif cmd == '/centrales':
            # Buscar en el documento de listado de centrales
            results = self._search_in_specific_doc("anexo d", top_k=30)
            
            response = "# 🏭 Centrales del CROM\n\n"
            if results:
                # Extraer nombres de centrales de los resultados
                centrales_found = set()
                for r in results:
                    text = r['text']
                    # Buscar patrones de centrales
                    matches = re.findall(r'(?:P\.?E\.?|P\.?S\.?|Parque|Central)\s+[A-Za-záéíóúñÁÉÍÓÚÑ\s]+', text)
                    centrales_found.update([m.strip() for m in matches])
                
                if centrales_found:
                    response += "**Centrales encontradas:**\n\n"
                    for central in sorted(centrales_found):
                        response += f"• {central}\n"
                else:
                    response += "Consulta el documento 'Anexo D - Listado de Centrales' para información completa."
            else:
                response += "No se encontró información del listado de centrales."
            
            return {
                'question': command,
                'results': results[:5] if results else [],
                'context': '',
                'answer': response,
                'method': 'system_command',
                'memory_hits': 0
            }
        
        # /documentos - Listar documentos
        elif cmd == '/documentos' or cmd == '/docs':
            # Obtener lista de documentos únicos
            all_docs = set()
            
            # Iterar sobre algunos chunks para ver qué documentos hay
            try:
                sample_results = self.hybrid_search("central parque", top_k=100)
                for r in sample_results:
                    doc_name = r['metadata'].get('source', 'Unknown')
                    all_docs.add(doc_name)
            except:
                pass
            
            response = "# 📄 Documentos Indexados\n\n"
            if all_docs:
                response += f"**Total de documentos:** {len(all_docs)}\n\n"
                for doc in sorted(all_docs):
                    response += f"• {doc}\n"
            else:
                response += "No se pudo obtener la lista de documentos."
            
            return {
                'question': command,
                'results': [],
                'context': '',
                'answer': response,
                'method': 'system_command',
                'memory_hits': 0
            }
        
        # /memoria - Ver sinónimos guardados
        elif cmd == '/memoria' or cmd == '/sinonimos':
            all_synonyms = self.memory.get_all_synonyms()
            
            response = "# 🧠 Memoria de Sinónimos\n\n"
            if all_synonyms:
                response += f"**Total de términos:** {len(all_synonyms)}\n\n"
                for canonical, syns in sorted(all_synonyms.items()):
                    response += f"• **{canonical}** = {', '.join(syns)}\n"
            else:
                response += "No hay sinónimos guardados.\n\n"
                response += "**Uso:** `Guarda que X es igual a Y y Z`"
            
            return {
                'question': command,
                'results': [],
                'context': '',
                'answer': response,
                'method': 'system_command',
                'memory_hits': 0
            }
        
        # /mapa - Ver mapa conceptual aprendido
        elif cmd == '/mapa' or cmd == '/conceptual':
            stats = self.conceptual_map.stats()
            
            response = "# 📚 Mapa Conceptual Aprendido\n\n"
            response += f"**Entidades:** {stats['entities']}\n"
            response += f"**Hechos totales:** {stats['total_facts']}\n"
            response += f"**Atajos de consulta:** {stats['query_shortcuts']}\n"
            response += f"**Aliases:** {stats['aliases']}\n\n"
            
            if stats['total_facts'] > 0:
                response += "**Conocimiento por entidad:**\n\n"
                for entity, facts in sorted(self.conceptual_map.entity_facts.items())[:10]:
                    response += f"### {entity.title()}\n"
                    for attr, data in facts.items():
                        conf = data.get('confidence', 1.0)
                        ans = data.get('answer', '')[:80]
                        response += f"- **{attr}**: {ans}... (confianza: {conf:.0%})\n"
                    response += "\n"
            
            return {
                'question': command,
                'results': [],
                'context': '',
                'answer': response,
                'method': 'system_command',
                'memory_hits': 0
            }
        
        # Comando desconocido
        else:
            response = f"❌ Comando desconocido: `{command}`\n\n"
            response += "**Comandos disponibles:**\n"
            response += "• `/ayuda` - Mostrar ayuda\n"
            response += "• `/reset` - Limpiar historial\n"
            response += "• `/centrales` - Listar centrales\n"
            response += "• `/documentos` - Listar documentos\n"
            response += "• `/memoria` - Ver sinónimos guardados\n"
            response += "• `/mapa` - Ver mapa conceptual aprendido\n"
            
            return {
                'question': command,
                'results': [],
                'context': '',
                'answer': response,
                'method': 'system_command',
                'memory_hits': 0
            }
    
    def _extract_entities(self, question: str) -> list:
        """Extrae nombres propios y términos técnicos de la pregunta (parques, empresas, tecnologías, etc)"""
        entities = []
        try:
            if hasattr(self, 'entity_extractor') and self.entity_extractor is not None:
                entities = self.entity_extractor.extract_entities(question)
        except Exception:
            pass
        
        # FALLBACK: Si no detectó entidades, buscar manualmente nombres conocidos en centrales_map
        if not entities:
            try:
                q_lower = question.lower()
                # Buscar en centrales_map (acrónimos y variantes)
                if hasattr(self, 'centrales_map') and self.centrales_map:
                    for variant, (canonical, _) in self.centrales_map.items():
                        if variant.lower() in q_lower:
                            entities.append(canonical.lower())
                            break
                # Buscar patrones comunes de nombres de centrales
                if not entities:
                    # Patrones: "parque X", "central X", "P.S. X", "P.E. X", "la perla del chaco"
                    patterns = [
                        # Nombres compuestos específicos (prioridad alta)
                        r'(?:parque|central|planta|p\.?s\.?|p\.?e\.?)\s+(?:la\s+)?perla\s+de(?:l)?\s+chaco',
                        r'(?:la\s+)?perla\s+de(?:l)?\s+chaco',
                        # Patrones genéricos
                        r'(?:parque|central|planta)\s+(?:eolico|eólico|solar|fotovoltaico|fotovoltaica)?\s*(?:la\s+)?([a-záéíóúñ\s]+?)(?:\s+(?:tiene|maneja|opera|ubicado|ubicada|cuenta|posee|dispone)|\?|$)',
                        r'(?:p\.?s\.?|p\.?e\.?)\s+([a-záéíóúñ\s]+?)(?:\s+(?:tiene|maneja|opera|ubicado|ubicada|cuenta|posee|dispone)|\?|$)',
                        r'(?:sobre|de|del)\s+(?:parque|central|planta|p\.?s\.?|p\.?e\.?)?\s*(?:la\s+)?([a-záéíóúñ\s]+?)(?:\?|$)',
                        r'(?:la|el)\s+([a-záéíóúñ\s]+?)\s+(?:tiene|maneja|opera|ubicado|ubicada|cuenta|posee|dispone)'
                    ]
                    for pat in patterns:
                        m = re.search(pat, q_lower, re.IGNORECASE)
                        if m:
                            # Si el patrón no tiene grupo, usar todo el match
                            if m.lastindex is None or m.lastindex == 0:
                                name = m.group(0).strip()
                                # Limpiar prefijos
                                name = re.sub(r'^(?:parque|central|planta|p\.?s\.?|p\.?e\.?|sobre|de|del|la|el)\s+', '', name, flags=re.IGNORECASE).strip()
                            else:
                                name = m.group(1).strip()
                            # Limpiar stopwords finales pero preservar "del chaco" y "de chaco"
                            if 'del chaco' not in name and 'de chaco' not in name:
                                name = re.sub(r'\s+(de|del|la|el|los|las|y|o|en|a|con)$', '', name).strip()
                            # Normalizar "del chaco" -> "de chaco" para consistencia
                            name = name.replace('del chaco', 'de chaco')
                            if len(name) > 3:  # Evitar nombres muy cortos
                                entities.append(name)
                                break
            except Exception:
                pass
        
        # Normalizar variantes comunes de nombres (preservando el original y agregando de/del)
        if entities:
            try:
                out = []
                seen = set()
                for ent in entities:
                    ent_lower = (ent if isinstance(ent, str) else str(ent)).lower().strip()
                    if ent_lower and ent_lower not in seen:
                        out.append(ent_lower); seen.add(ent_lower)
                    # Variantes de/de l
                    v1 = ent_lower.replace(' del ', ' de ')
                    v2 = ent_lower.replace(' de ', ' del ')
                    for v in (v1, v2):
                        if v and v not in seen:
                            out.append(v); seen.add(v)
                entities = out
            except Exception:
                pass
        
        return entities
    
    
    
    
    def _synthesize_fallback_answer(self, question: str, results: list, is_aggregation: bool, is_conceptual: bool, is_procedural: bool) -> str:
        try:
            if not results:
                return "No se encontró información en los documentos para esa consulta."
            max_lines = int(self.flags.get('max_answer_lines', 4) or 4)
            max_lines = max(2, min(max_lines, 6))
            pieces = []
            if is_aggregation:
                docs = {}
                for r in results[:8]:
                    src = r.get('metadata', {}).get('source', '')
                    if src not in docs:
                        docs[src] = r
                for r in list(docs.values())[:max_lines]:
                    txt = r.get('text', '')
                    if len(txt) > 280:
                        txt = self._condense_text(txt, 280)
                    pieces.append(txt.strip())
            else:
                ordered = results[:max_lines]
                for r in ordered:
                    txt = r.get('text', '')
                    if len(txt) > 280:
                        txt = self._condense_text(txt, 280)
                    pieces.append(txt.strip())
            ans = "\n".join([p for p in pieces if p])
            if not ans.strip():
                return "No se encontró información en los documentos para esa consulta."
            ans = re.sub(r"\n\s*\n+", "\n", ans).strip()
            lines = [l.strip() for l in ans.splitlines() if l.strip()]
            if len(lines) > max_lines:
                lines = lines[:max_lines]
            return "\n".join(lines)
        except Exception:
            return "No se encontró información en los documentos para esa consulta."

    def _has_entity_evidence(self, entities: list, results: list, context: str) -> bool:
        """Verifica si al menos una entidad aparece explícitamente en resultados o contexto.
        Normaliza tolerando 'de/del' y espacios. Incluye busqueda de formas canonicas y aliases.
        """
        try:
            if not entities:
                return True
            ctx = (context or '').lower()
            
            def normalize(s: str) -> str:
                """Minúsculas sin acentos, espacios normalizados"""
                if not s:
                    return ''
                s = s.strip().lower()
                s = ''.join(c for c in unicodedata.normalize('NFD', s) 
                           if unicodedata.category(c) != 'Mn')
                return re.sub(r"\s+", " ", s)
            
            def variants(e_raw: str):
                e = (e_raw or '').strip().lower()
                e = re.sub(r"\s+", " ", e)
                if not e:
                    return []
                outs = set()
                outs.add(e)
                # Variantes de/de l
                outs.add(e.replace(" de ", " del "))
                outs.add(e.replace(" del ", " de "))
                # Si tiene 3+ tokens, construir patrón tolerante a de/del entre primero y último
                toks = [t for t in e.split() if t]
                if len(toks) >= 3:
                    first = toks[0]
                    last = toks[-1]
                    outs.add(f"{first} del {last}")
                    outs.add(f"{first} de {last}")
                return [s for s in outs if len(s) >= 3]
            
            def has_match(blob: str, ent: str) -> bool:
                b = (blob or '').lower()
                # 1) Intento exacto por variantes
                for v in variants(ent):
                    try:
                        pat = r"\b" + re.escape(v) + r"\b"
                        if re.search(pat, b):
                            return True
                    except Exception:
                        continue
                # 2) Proximidad: primer y último token presentes cercanos (< 50 chars)
                try:
                    toks = [t for t in ent.split() if t not in {"de","del"}]
                    if len(toks) >= 2:
                        i1 = b.find(toks[0])
                        i2 = b.find(toks[-1], max(i1, 0))
                        if i1 >= 0 and i2 >= 0 and (i2 - i1) <= 50:
                            return True
                except Exception:
                    pass
                return False
            
            # Expandir entidades con aliases del gazetteer
            ents_expanded = set()
            for e in entities:
                if isinstance(e, str) and len(e.strip()) >= 3:
                    ents_expanded.add(e.lower().strip())
                    # Buscar forma canónica y todos sus aliases
                    if hasattr(self, 'entity_extractor') and self.entity_extractor:
                        norm = normalize(e)
                        # Buscar si esta entidad es un alias conocido
                        if norm in self.entity_extractor.domain_entities:
                            canonical = self.entity_extractor.domain_entities[norm][0]
                            ents_expanded.add(canonical)
                            # Agregar también variaciones del canónico
                            for v in variants(canonical):
                                ents_expanded.add(v)
                            # Agregar TODOS los aliases que mapean a esta forma canónica
                            for alias_key, (canon_val, _) in self.entity_extractor.domain_entities.items():
                                if canon_val == canonical:
                                    ents_expanded.add(alias_key)
                                    for v in variants(alias_key):
                                        ents_expanded.add(v)
            
            ents = list(ents_expanded)
            
            # revisar contexto completo
            for e in ents:
                if has_match(ctx, e):
                    return True
            # revisar resultados
            for r in results or []:
                src = (r.get('metadata', {}) or {}).get('source', '')
                txt = r.get('text', '')
                blob = (str(src) + "\n" + str(txt))
                for e in ents:
                    if has_match(blob, e):
                        return True
            return False
        except Exception:
            return True

    def _ensure_results_for_entities(self, results: list, entities: list, per_entity: int = 1) -> list:
        """Asegura que exista al menos un resultado por entidad buscada.
        Busca tanto en 'source' como en el texto dentro de toda la colección.
        """
        if not results or not entities:
            return results
        try:
            col = self.vector_store.collection.get()
        except Exception:
            return results
        present = list(results)
        def _blob(md, doc) -> str:
            try:
                return (str((md or {}).get('source', '')) + "\n" + str(doc)).lower()
            except Exception:
                return ''
        def _in_blob_variants(blob: str, ent: str) -> bool:
            b = (blob or '').lower()
            e = (ent or '').lower().strip()
            if not e:
                return False
            variants = {e, e.replace(' de ', ' del '), e.replace(' del ', ' de ')}
            if any(v in b for v in variants):
                return True
            toks = [t for t in e.split() if t not in {'de','del'}]
            if len(toks) >= 2:
                i1 = b.find(toks[0])
                i2 = b.find(toks[-1], max(i1, 0)) if i1 >= 0 else -1
                if i1 >= 0 and i2 >= 0 and (i2 - i1) <= 50:
                    return True
            return False
        # ya presente en resultados actuales con tolerancia
        def _exists(ent: str) -> bool:
            for r in present[:20]:
                md = r.get('metadata', {})
                txt = r.get('text', '')
                if _in_blob_variants(str(md.get('source','')) + "\n" + str(txt), ent):
                    return True
            return False
        for ent in entities:
            if _exists(ent):
                continue
            added = 0
            metadatas = col.get('metadatas', []) or []
            documents = col.get('documents', []) or []
            ids = col.get('ids', []) or []
            for i in range(min(len(metadatas), len(documents))):
                if _in_blob_variants(_blob(metadatas[i], documents[i]), ent):
                    present.insert(0, {
                        'text': documents[i],
                        'metadata': metadatas[i],
                        'hybrid_score': 0.9,
                        'rerank_score': 0.0,
                        'final_score': 0.88,
                        'id': ids[i] if i < len(ids) else ''
                    })
                    added += 1
                    if added >= per_entity:
                        break
        return present
    
    
    def _resolve_entity_to_anexo(self, entity: str) -> tuple:
        """Resuelve una entidad a su nombre canónico y documento fuente.
        Returns: (nombre_canonico, archivo) o (None, None) si no encuentra.
        """
        entity_lower = entity.lower().strip()
        
        # Buscar en doc_roles.entities_index
        try:
            if hasattr(self, 'doc_roles') and self.doc_roles:
                # Normalizar entidad para búsqueda flexible
                entity_tokens = set(entity_lower.split())
                best_match = None
                best_score = 0
                
                for doc_name, doc_info in self.doc_roles.items():
                    if not doc_name.lower().startswith('anexo d'):
                        continue
                    entities_idx = doc_info.get('entities_index', [])
                    for ent_variant in entities_idx:
                        ent_variant_lower = ent_variant.lower().strip()
                        variant_tokens = set(ent_variant_lower.split())
                        # Calcular overlap de tokens
                        common = entity_tokens & variant_tokens
                        if common:
                            score = len(common) / max(len(entity_tokens), len(variant_tokens))
                            if score > best_score and score >= 0.4:  # Al menos 40% de overlap
                                best_score = score
                                # Extraer nombre canónico limpio
                                canonical = ent_variant.strip()
                                best_match = (canonical, doc_name)
                
                if best_match:
                    return best_match
        except Exception:
            pass
        
        return (None, None)
    

    
    
    
    
    def _is_out_of_domain(self, query: str) -> bool:
        """Delegado a QueryClassifier.is_out_of_domain()."""
        return self._query_clf.is_out_of_domain(query)
    
    def _calculate_semantic_similarity(self, text1: str, text2: str) -> float:
        """Calcula similitud semántica entre dos textos usando embeddings si están disponibles."""
        try:
            # Si hay embeddings disponibles, usar similitud coseno
            if hasattr(self, 'embedding_model') and self.embedding_model:
                emb1 = self.embedding_model.encode(text1[:500], show_progress_bar=False)
                emb2 = self.embedding_model.encode(text2[:500], show_progress_bar=False)
                # Similitud coseno
                dot = sum(a * b for a, b in zip(emb1, emb2))
                norm1 = sum(a * a for a in emb1) ** 0.5
                norm2 = sum(b * b for b in emb2) ** 0.5
                if norm1 == 0 or norm2 == 0:
                    return 0.0
                return dot / (norm1 * norm2)
        except Exception:
            pass
        
        # Fallback: similitud de Jaccard basada en palabras
        try:
            words1 = set(text1.lower().split())
            words2 = set(text2.lower().split())
            if not words1 or not words2:
                return 0.0
            intersection = words1 & words2
            union = words1 | words2
            return len(intersection) / len(union)
        except Exception:
            return 0.0
    
    
    
    
    
    
    def query(self, question: str, top_k: int = 50, 
              semantic_weight: float = 0.6, use_llm: bool = None,
              entity_filter: bool = True, two_stage: bool = True,
              length_mode: str = None, no_context: bool = False,
              stream: bool = False, token_callback=None, docs_callback=None, cancel_checker=None) -> dict:
        """
        Consulta completa con búsqueda híbrida
        
        Args:
            question: Pregunta
            top_k: Resultados a recuperar
            semantic_weight: Balance semántica/keyword (0.5 = 50/50)
            use_llm: Usar LLM para generar respuesta
            entity_filter: Filtrar por entidades encontradas en pregunta
            two_stage: Usar búsqueda en dos etapas para entidades específicas
            length_mode: 'short' para respuestas breves (<1000 chars), 'long' para respuestas extensas (>3000 chars)
        """
        
        if use_llm is None:
            use_llm = self.use_llm
        
        # BLOQUEO TEMPRANO (estricto) fuera de dominio antes de cualquier impresión o búsqueda
        try:
            if self.flags.get('strict_ood', True) and self._is_out_of_domain(question):
                brief = (
                    "Lo siento, esta consulta está fuera del alcance de mi especialidad.\n\n"
                    "Puedo responder consultas relacionadas con ciberseguridad, tecnologías de la información y frameworks de seguridad:\n\n"
                    "• Certificaciones (CISSP, CEH, CISM, OSCP, etc.)\n"
                    "• Frameworks (NIST CSF, ISO 27001, PCI DSS, MITRE ATT&CK)\n"
                    "• Tecnologías (firewalls, SIEM, EDR, cloud security)\n"
                    "• Metodologías (pentesting, red team, blue team, DevSecOps)\n"
                    "• Cumplimiento y gobernanza (GDPR, SOC 2, gobierno de riesgos)\n\n"
                    "Por favor, reformula tu consulta dentro de estos temas."
                )
                console.print(f"[yellow]Consulta fuera de dominio bloqueada[/yellow]")
                try:
                    log_event('out_of_domain', {'question': question[:200]})
                except Exception:
                    pass
                return {
                    'question': question,
                    'results': [],
                    'context': '',
                    'answer': brief,
                    'sources': [],
                    'method': 'out_of_domain',
                    'memory_hits': 0,
                    'time': 0
                }
        except Exception:
            pass
        
        console.print(f"\n[bold cyan]Procesando consulta hibrida...[/bold cyan]")
        _t0 = time.time()
        
        # Limpiar flag de warning de páginas para esta nueva consulta
        if hasattr(self, '_page_warning_shown'):
            delattr(self, '_page_warning_shown')
        
        # DETECTAR COMANDOS DEL SISTEMA (/comando)
        if question.strip().startswith('/'):
            return self._handle_system_command(question.strip())
        
        # DETECTAR COMANDOS DE MEMORIA (guarda que X = Y = Z)
        memory_cmd = parse_memory_command(question)
        if memory_cmd:
            console.print(f"[bold green]Comando de memoria detectado[/bold green]")
            canonical = memory_cmd['canonical']
            synonyms = memory_cmd['synonyms']
            
            # Guardar sinónimos
            added = self.memory.add_synonyms(canonical, synonyms, category='user_defined')
            
            synonyms_formatted = ', '.join([f"[cyan]'{s}'[/cyan]" for s in synonyms])
            console.print(f"[green]OK: Guardado:[/green] [cyan]'{canonical}'[/cyan] = {synonyms_formatted}")
            console.print(f"[dim]Total: {added} nuevo(s) sinónimo(s) agregado(s)[/dim]")
            
            # Devolver confirmación
            response = f"OK: Entendido y guardado en mi memoria:\n\n"
            response += f"**{canonical}** es equivalente a:\n"
            for syn in synonyms:
                response += f"• {syn}\n"
            response += f"\nAhora cuando busques cualquiera de estos términos, expandiré la búsqueda a todos sus sinónimos automáticamente."
            
            return {
                'question': question,
                'results': [],
                'context': '',
                'answer': response,
                'sources': [],
                'method': 'memory_command',
                'memory_hits': 0,
                'time': time.time() - _t0
            }
        
        # ENRIQUECER QUERY CON CONTEXTO si detecta referencias a información previa
        if not no_context:
            enriched_question, contextual_entities = self._enrich_query_with_context(question)
            if enriched_question != question:
                question = enriched_question  # Usar query enriquecida
        else:
            contextual_entities = []
        # Expandir con equivalencias (sinónimos/acrónimos) para mejorar recuperación
        try:
            q2 = self._expand_with_equivalences(question)
            if q2 and q2 != question:
                question = q2
        except Exception:
            pass
        
        # DETECTAR SI PIDE EXPLICACIÓN DE UN DOCUMENTO CITADO
        is_doc_explanation = self._is_doc_explanation_query(question)
        doc_ref = self._extract_doc_reference(question) if is_doc_explanation else None
        
        # Inicializar flag conceptual
        is_conceptual = False
        
        if is_doc_explanation and doc_ref:
            console.print(f"[dim]📄 Explicación de documento detectada: {doc_ref['doc_name']} (página {doc_ref['page']})[/dim]")
            results = self._search_in_specific_doc(
                doc_ref['doc_name'], 
                page=doc_ref['page'], 
                top_k=top_k
            )
            console.print(f"[dim]OK: {len(results)} fragmentos del documento recuperados[/dim]")
        
        else:
            cls = self._classify_query(question, length_mode, top_k)
            is_conceptual = cls["is_conceptual"]
            is_procedural = cls["is_procedural"]
            is_count_query = cls["is_count_query"]
            is_comparison = cls["is_comparison"]
            is_aggregation = cls["is_aggregation"]
            is_direct_comparison = cls["is_direct_comparison"]
            is_simple_numeric = cls["is_simple_numeric"]
            is_troubleshooting = cls["is_troubleshooting"]
            is_summary = cls["is_summary"]
            is_detailed = cls["is_detailed"]
            is_listing_ctx = cls["is_listing_ctx"]
            length_mode = cls["length_mode"]
            top_k = cls["top_k"]
            
            if is_conceptual:
                console.print(f"[dim]Pregunta CONCEPTUAL/GENERAL detectada - busqueda amplia[/dim]")
            
            entities = self._extract_and_clean_entities(question, entity_filter, is_conceptual, contextual_entities)
            
            # Detectar continuidad conversacional ANTES de buscar, para poder arrastrar entidad previa
            last_query = self.conversation.get_last_user_message()
            use_prev_topic = False if no_context else self._should_use_conversation_context(question, last_query)
            # Extraer ancla desde la última respuesta del asistente
            followup_anchor_active = False
            anchor_phrase = None
            try:
                last_answer = self.conversation.get_last_assistant_message()
            except Exception:
                pass
            # Detectar si hay ancla conversacional (frase citada de la última respuesta)
            follow_up_anchor = None
            try:
                last_answer = self.conversation.get_last_assistant_message()
                follow_up_anchor = self._extract_follow_up_anchor(question, last_answer)
                if follow_up_anchor:
                    console.print(f"[cyan]Ancla conversacional detectada[/cyan]")
                    followup_anchor_active = True
                    # Si hay ancla, forzar uso de sticky sources (documentos del turno anterior)
                    if hasattr(self, '_sticky_sources') and self._sticky_sources:
                        console.print(f"[dim]Priorizando documentos del turno anterior (sticky sources)[/dim]")
                        # No limpiar sticky sources en este caso
                        try:
                            if hasattr(self, '_sticky_entity'):
                                delattr(self, '_sticky_entity')
                        except Exception:
                            pass
            except Exception:
                pass
            if entities:
                # Normalizar entidades (remover términos genéricos: parque, eolico, central, planta)
                try:
                    entities = self._normalize_entities(entities, question)
                except Exception:
                    pass
                console.print(f"[dim]Entidades detectadas: {', '.join(entities)}[/dim]")
                try:
                    # Guardar entidades actuales y activar sticky por 3 turnos
                    setattr(self, 'last_entities', list(entities))
                    if len(entities) >= 1:
                        try:
                            # EXCEPCIÓN 1: Si es comparación, NO limpiar sticky sources (necesitamos ambas entidades)
                            is_comparison_query = self._is_comparison_query(question) or self._is_direct_comparison_query(question)
                            
                            # EXCEPCIÓN 2: Si es follow-up, NO limpiar sticky sources (necesitamos contexto previo)
                            is_follow_up = self._is_follow_up_query(question)
                            
                            # Detectar cambio de entidad comparando con la anterior
                            current_entity = entities[0].lower().strip()
                            prev_sticky = getattr(self, '_sticky_entity', None)
                            prev_entity = prev_sticky.get('name', '').lower().strip() if prev_sticky else ''
                            
                            entity_changed = False
                            if prev_entity and current_entity != prev_entity:
                                # Verificar que no sea una variante del mismo nombre
                                if current_entity not in prev_entity and prev_entity not in current_entity:
                                    entity_changed = True
                            
                            # Limpiar sticky sources SOLO si cambió la entidad Y NO es comparación NI follow-up
                            if entity_changed and not is_comparison_query and not is_follow_up:
                                if hasattr(self, '_sticky_entity'):
                                    delattr(self, '_sticky_entity')
                                if hasattr(self, '_sticky_sources'):
                                    delattr(self, '_sticky_sources')
                                    console.print(f"[cyan]Sticky sources limpiadas: {prev_entity} -> {current_entity}[/cyan]")
                            elif is_comparison_query:
                                console.print(f"[dim]Comparación detectada: preservando sticky sources para contexto dual[/dim]")
                            elif is_follow_up:
                                console.print(f"[dim]Follow-up detectado: preservando sticky sources para contexto previo[/dim]")
                        except Exception:
                            pass
                        setattr(self, '_sticky_entity', {'name': entities[0], 'ttl': 3})
                except Exception:
                    pass
            else:
                # Si no hay entidades, intentar usar entidad persistente (TTL)
                try:
                    # MEJORA: Detectar follow-up incluso sin entidades explícitas
                    is_follow_up_detected = self._is_follow_up_query(question)
                    
                    if (not no_context) and (use_prev_topic or is_follow_up_detected):
                        sticky = getattr(self, '_sticky_entity', None)
                        if (not is_conceptual) and sticky and sticky.get('name') and int(sticky.get('ttl', 0)) > 0:
                            entities = [sticky['name']]
                            # Aumentar TTL si es follow-up explícito
                            if is_follow_up_detected:
                                sticky['ttl'] = 3  # Resetear TTL para follow-ups
                            else:
                                sticky['ttl'] = int(sticky['ttl']) - 1
                            setattr(self, '_sticky_entity', sticky)
                            console.print(f"[dim]Entidad persistente aplicada: {sticky['name']} (ttl={sticky['ttl']})[/dim]")
                    else:
                        if not use_prev_topic and not is_follow_up_detected and hasattr(self, '_sticky_entity'):
                            delattr(self, '_sticky_entity')
                except Exception:
                    pass
                # Si no hay entidades explícitas y hay señales de anáfora o continuidad, reusar entidad previa
                if entity_filter and (not no_context):
                    ql_local = question.lower()
                    pronoun_hints = [' sus', 'su ', 'ahora', 'del parque', 'de ese', 'de esa', 'de ello', 'de eso']
                    # Detectar preguntas de follow-up que implican continuidad (sin mencionar entidad explícita)
                    followup_patterns = [
                        'que centrales', 'qué centrales', 'cuales centrales', 'cuáles centrales',
                        'que parques', 'qué parques', 'cuales parques', 'cuáles parques',
                        'donde esta', 'dónde está', 'donde están', 'dónde están',
                        'cuantos', 'cuántos', 'cuanta', 'cuánta'
                    ]
                    is_followup = any(pattern in ql_local for pattern in followup_patterns)
                    
                    if use_prev_topic or any(h in ql_local for h in pronoun_hints) or is_followup:
                        prev_ents = getattr(self, 'last_entities', [])
                        if prev_ents and len(prev_ents) <= 2:
                            entities = list(prev_ents)
                            console.print(f"[dim]Usando entidad del turno anterior: {', '.join(entities)}[/dim]")
                    # Además: si la pregunta es sobre ET/subestación, asumir continuidad si hay entidad previa
                    et_words = [' et ', 'estación transformadora', 'estacion transformadora', 'pampa del castillo', '132 kv', '33 kv', '4tr08', '33/132']
                    if (not entities) and any(w in ql_local for w in et_words):
                        prev_ents = getattr(self, 'last_entities', [])
                        if prev_ents and len(prev_ents) <= 2:
                            entities = list(prev_ents)
                            console.print(f"[dim]Follow-up de ET detectado - usando entidad previa: {', '.join(entities)}[/dim]")
            
            # CONSULTAR MAPA CONCEPTUAL antes de búsqueda completa
            conceptual_answer = None
            full_cov_flag = self._requires_full_anexos_coverage(question)
            listing_flag = False
            try:
                listing_flag = self._is_listing_query(question)
            except Exception:
                listing_flag = False
            if self.use_llm and entities and self.config.get('use_conceptual_map', True) and not (is_aggregation or full_cov_flag or listing_flag):
                conceptual_answer = self.conceptual_map.query_shortcut(question, entities)
                if conceptual_answer and conceptual_answer.get('confidence', 0) >= 0.8:
                    # Responder directo desde el mapa conceptual
                    ans = conceptual_answer['answer']
                    src = conceptual_answer.get('source', 'Conocimiento previo')
                    pg = conceptual_answer.get('page', 0)
                    console.print(f"[bold green]Respuesta desde mapa conceptual (confianza: {conceptual_answer.get('confidence', 1.0):.0%})[/bold green]")
                    # Crear resultado mock para devolver
                    mock_result = {
                        'text': ans,
                        'metadata': {'source': src, 'page': pg},
                        'hybrid_score': 1.0,
                        'final_score': 1.0
                    }
                    return {
                        'question': question,
                        'answer': ans,
                        'results': [mock_result],
                        'context': f"[Conocimiento previo verificado]\n{ans}",
                        'method': 'conceptual_map',
                        'source': src,
                        'elapsed_ms': int((time.time() - _t0) * 1000)
                    }
            
            # EXPANSIÓN DE ACRÓNIMOS usando mapa pre-cargado
            # NO expandir entidades que ya son específicas (contienen números romanos)
            acr_expansions = {}
            for ent in list(entities):
                # Evitar expandir "loma blanca i" -> "loma blanca" (pérdida de especificidad)
                if re.search(r'\b(i|ii|iii|iv|v|vi|vii|viii|ix|x)\b', ent.lower()):
                    continue  # Ya es específico, no expandir
                
                canonical, anexo = self._resolve_entity_to_anexo(ent)
                if canonical and canonical.lower() != ent.lower():
                    acr_expansions[ent] = canonical
            
            if acr_expansions:
                # Reemplazar entidades por sus expansiones
                new_entities = []
                for ent in entities:
                    if ent in acr_expansions:
                        new_entities.append(acr_expansions[ent])
                    else:
                        new_entities.append(ent)
                entities = new_entities
                try:
                    for acr, full in acr_expansions.items():
                        self.memory.add_synonyms(full, [acr], category='auto_acronym')
                        console.print(f"[dim]Acrónimo expandido: {acr} -> {full}[/dim]")
                except Exception:
                    pass

            # EXPANDIR ENTIDADES CON SINÓNIMOS (memoria del usuario)
            # NO expandir si hay múltiples entidades específicas (>= 3) para evitar ruido
            num_specific_entities = sum(1 for e in entities if re.search(r'\b(i|ii|iii|iv|v|vi|vii|viii|ix|x)\b', e.lower()))
            should_expand_synonyms = num_specific_entities < 3
            
            if should_expand_synonyms:
                expanded_entities = set(entities)
                for entity in entities:
                    # MEJORA: Usar gazetteer de alias primero
                    entity_lower = entity.lower()
                    if entity_lower in self.entity_aliases:
                        aliases = self.entity_aliases[entity_lower]
                        expanded_entities.update(aliases)
                        console.print(f"[dim green]Expandiendo '{entity}' -> {', '.join(aliases)}[/dim green]")
                    else:
                        # Fallback: usar sinónimos de memoria
                        synonyms = self.memory.get_synonyms(entity)
                        if len(synonyms) > 1:  # Si tiene sinónimos (además del término original)
                            expanded_entities.update(synonyms)
                            console.print(f"[dim green]Expandiendo '{entity}' -> {', '.join(synonyms)}[/dim green]")
                
                # Convertir a lista para usar en búsquedas
                entities = list(expanded_entities)
            else:
                console.print(f"[yellow]Consulta multi-entidad específica ({num_specific_entities} entidades) - omitiendo expansión de sinónimos[/yellow]")

            # Heurística: si NO se detectaron entidades y la consulta parece nombre propio en minúsculas (2+ palabras),
            # intentar inferir entidad buscando en Anexos D que contengan la frase literal (case-insensitive)
            if not entities and not is_conceptual:
                tokens = [t for t in question.strip().split() if len(t) > 2]
                if len(tokens) >= 2:
                    candidate = ' '.join(tokens).lower()
                    try:
                        col = self.vector_store.collection.get()
                        found = False
                        for i, md in enumerate(col.get('metadatas', [])):
                            src = (md or {}).get('source', '')
                            if 'anexo d' in src.lower():
                                txt = col.get('documents', [''])[i] if i < len(col.get('documents', [])) else ''
                                if candidate in (txt + ' ' + src).lower():
                                    entities = [candidate]
                                    console.print(f"[dim]Entidad inferida: {candidate}[/dim]")
                                    found = True
                                    break
                    except Exception:
                        pass
            
            # EXPANSION LIGERA DE QUERY para términos técnicos comunes
            ql = question.lower()
            extra_terms = []
            if 'cuant' in ql or 'número' in ql or 'numero' in ql or 'cuantos' in ql or 'cuántos' in ql:
                extra_terms += ['cantidad', 'número', 'numero', 'total']
            if 'version' in ql or 'versión' in ql:
                extra_terms += ['versión', 'version', 'actualización', 'release']
            # Incidente de seguridad / respuesta a incidentes: ampliar términos de búsqueda relevantes
            ir_triggers = ['incidente', 'respuesta', 'contencion', 'contención', 'eradicacion', 'erradicación', 'forense', 'ir']
            if any(t in ql for t in ir_triggers):
                extra_terms += [
                    'incidente', 'respuesta a incidentes', 'contención', 'erradicación', 'forense',
                    'playbook', 'procedimiento', 'instructivo', 'manual', 'estado', 'alerta', 'alertas'
                ]
            # Controles específicos de ciberseguridad
            control_triggers = ['control', 'controles', 'seguridad', 'proteccion', 'protección']
            if any(t in ql for t in control_triggers):
                extra_terms += [
                    'control', 'controles', 'seguridad', 'política', 'politica', 'protección',
                    'firewall', 'siem', 'edr', 'xdr', 'ids', 'ips', 'mfa', 'acceso'
                ]
            # Troubleshooting/diagnóstico: ampliar términos de búsqueda relevantes a eventos/fallas
            if 'is_troubleshooting' in locals() and is_troubleshooting:
                extra_terms += [
                    'alerta', 'alertas', 'evento', 'eventos', 'incidente', 'fallo', 'fault',
                    'registro', 'log', 'auditoría', 'control', 'estado', 'bloqueo'
                ]
            # Construir consulta de búsqueda ampliada
            search_query = question if not extra_terms else (question + ' ' + ' '.join(sorted(set(extra_terms))))

            # Ajuste dinámico de pesos para consultas numéricas (contar, versión, CVSS)
            numeric_q = any(k in ql for k in ['cuant', 'número', 'numero', 'versión', 'version', 'cvss', 'severidad'])
            semantic_weight_run = (0.4 if numeric_q else semantic_weight)
            
            # PLANNER: definir roles preferidos y candidatos de documentos
            plan = {'doc_roles_preferred': [], 'attribute': None, 'candidate_docs': []}
            try:
                if self.config.get('use_planner', True):
                    plan = self._plan_retrieval(
                        question,
                        entities,
                        is_conceptual,
                        is_procedural,
                        is_direct_comparison=is_direct_comparison,
                        is_simple_numeric=is_simple_numeric,
                        is_troubleshooting=is_troubleshooting
                    )
                    if plan.get('doc_roles_preferred'):
                        console.print(f"[dim]Planner: roles preferidos = {', '.join(plan['doc_roles_preferred'])}[/dim]")
                    if plan.get('candidate_docs'):
                        console.print(f"[dim]Planner: {len(plan['candidate_docs'])} candidatos preseleccionados[/dim]")
            except Exception:
                pass
            
            # DOC SCOPE: si el usuario indica un documento específico, limitar la búsqueda a ese documento
            # EXCEPCIÓN: si hay ancla conversacional, priorizar sticky sources (documentos del turno anterior)
            results = None
            try:
                doc_scope = self._extract_doc_scope(question)
            except Exception:
                doc_scope = ''
            
            # Si hay ancla conversacional y sticky sources, forzar búsqueda en esos documentos
            if follow_up_anchor and hasattr(self, '_sticky_sources') and self._sticky_sources:
                console.print(f"[dim]Ancla conversacional: forzando búsqueda en documentos del turno anterior[/dim]")
                try:
                    # Buscar en los documentos sticky
                    sticky_dict = self._sticky_sources if isinstance(self._sticky_sources, dict) else {'sources': list(self._sticky_sources), 'ttl': 1}
                    sticky_docs = list(set(sticky_dict.get('sources', []) or []))
                    results = []
                    for doc_name in sticky_docs[:3]:  # Limitar a top 3 docs sticky
                        doc_results = self._search_in_specific_doc(doc_name, top_k=top_k)
                        results.extend(doc_results)
                    if results:
                        console.print(f"[dim]OK: {len(results)} fragmentos de documentos sticky[/dim]")
                        # Reducir TTL
                        try:
                            ttl = int(sticky_dict.get('ttl', 1)) - 1
                            if ttl <= 0:
                                delattr(self, '_sticky_sources')
                            else:
                                sticky_dict['ttl'] = ttl
                                setattr(self, '_sticky_sources', sticky_dict)
                        except Exception:
                            pass
                except Exception:
                    results = None
            elif doc_scope:
                console.print(f"[dim]Scope de documento detectado: {doc_scope}[/dim]")
                try:
                    results = self._search_in_specific_doc(doc_scope, top_k=max(top_k * 4, 100))
                    console.print(f"[dim]OK: {len(results)} fragmentos del documento scoped[/dim]")
                except Exception:
                    results = None
            
            
            # BÚSQUEDA ESPECIALIZADA PARA COMPARACIONES
            elif (results is None) and is_comparison and entities:
                # Si es comparación y solo hay 1 entidad, agregar la entidad previa (sticky)
                if len(entities) == 1:
                    try:
                        prev_ents = getattr(self, 'last_entities', [])
                        if prev_ents and prev_ents[0].lower() != entities[0].lower():
                            entities.insert(0, prev_ents[0])
                            console.print(f"[dim]Comparación con contexto previo: agregando entidad {prev_ents[0]}[/dim]")
                    except Exception:
                        pass
                if len(entities) >= 2:
                    console.print(f"[dim]Comparacion detectada - busqueda balanceada entre entidades[/dim]")
                    results = self._search_for_comparison(entities, top_k=top_k)
                else:
                    console.print(f"[yellow]Comparación detectada pero falta segunda entidad - búsqueda normal[/yellow]")
            
            # Para preguntas procedimentales, NO filtrar agresivamente por entidades
            # porque los procedimientos pueden no mencionar la entidad en cada chunk
            elif (results is None) and is_procedural:
                console.print(f"[dim]Pregunta procedural detectada - busqueda amplia[/dim]")
                entity_filter_strict = False
                results = None  # Se buscará en el flujo normal
            else:
                hard_trigger = (
                    is_count_query or (entities and len(entities) == 1)
                )
                entity_filter_strict = True if (entity_filter and hard_trigger) else entity_filter
                results = None  # Se buscará en el flujo normal
        
        
        # BÚSQUEDA EN DOS ETAPAS (solo si no es comparación o explicación de doc)
        # Evitar forzar Anexo D cuando la consulta es de tipo PT (p.ej., "PT 11", "PT_11", "Protocolo tecnico")
        try:
            _q = (question or '')
            _ents = [e.lower() for e in (entities or []) if e]
            pt_like = bool(re.search(r"\bpt\s*_?\d+\b", _q.lower())) or any(('pt' in e and any(ch.isdigit() for ch in e)) for e in _ents) or ('protocolo tecnico' in _q.lower()) or ('protocolo de cammesa' in _q.lower())
        except Exception:
            pt_like = False
        if results is None and two_stage and entities and len(entities) <= 2 and not is_procedural and not locals().get('is_listing_ctx', False) and not self._is_sum_query(question) and not self._extract_tech_filter(question) and not self._extract_vendor_filter(question) and not pt_like:
            # Etapa 1: Buscar primero en Anexo D específico si existe
            entity_name = entities[0]
            console.print(f"[dim]Etapa 1: Buscando documentos específicos para entidad: {entity_name}[/dim]")
            
            # RAZONAMIENTO: Resolver entidad a archivo Anexo D correcto
            canonical_name, target_anexo = self._resolve_entity_to_anexo(entity_name)
            
            if target_anexo:
                console.print(f"[dim cyan]Razonamiento: '{entity_name}' -> '{canonical_name}' en documento específico[/dim cyan]")
                # Guardar target_anexo para priorizar en modo detallado
                setattr(self, '_target_anexo_etapa1', target_anexo)
                # Buscar directamente en el archivo correcto
                anexo_query = target_anexo.replace('.pdf', '').replace('.PDF', '')
                entity_results = self.hybrid_search(f"{anexo_query} {canonical_name}", top_k=30, semantic_weight=0.3)
                # Filtrar solo chunks de ese archivo
                anexo_results = [r for r in entity_results if target_anexo.lower() in r.get('metadata', {}).get('source', '').lower()]
                
                if anexo_results:
                    console.print(f"[green]OK: Encontrado documento específico con {len(anexo_results)} fragmentos[/green]")
                    entity_results = anexo_results
                else:
                    # Fallback: buscar en ese archivo sin filtro estricto
                    console.print(f"[yellow]Buscando en documento específico sin filtro estricto...[/yellow]")
                    entity_results = [r for r in entity_results if 'anexo d' in r.get('metadata', {}).get('source', '').lower()]
            else:
                # Sin mapeo: usar heurística original
                doc_query = f"documento {entity_name}"
                entity_results = self.hybrid_search(doc_query, top_k=30, semantic_weight=0.3)
                
                # Mejor heurística: tomar cualquier 'Anexo D' cuyo TEXTO mencione la entidad
                anexo_results = []
                try:
                    all_docs = self.vector_store.collection.get()
                    for i, md in enumerate(all_docs.get('metadatas', [])):
                        src = (md or {}).get('source', '')
                        if 'anexo d' in src.lower():
                            txt = all_docs.get('documents', [''])[i] if i < len(all_docs.get('documents', [])) else ''
                            if entity_name.lower() in (txt.lower() + ' ' + src.lower()):
                                anexo_results.append({
                                    'text': txt,
                                    'metadata': md,
                                    'hybrid_score': 0.9,
                                    'id': all_docs.get('ids', [''])[i]
                                })
                except Exception:
                    pass
                
                if anexo_results:
                    console.print(f"[green]OK: Encontrado documento específico con {len(anexo_results)} fragmentos[/green]")
                    entity_results = anexo_results
                else:
                    # Fallback: búsqueda general por entidad
                    console.print(f"[yellow]No se encontró documento específico, buscando en todos los documentos...[/yellow]")
                    entity_query = f"información completa {entity_name}"
                    entity_results = self.hybrid_search(entity_query, top_k=30, semantic_weight=0.3)
                    entity_results = self._filter_by_entity(entity_results, entities)
            
            # Etapa 2: Buscar respuesta específica dentro de ese contexto
            console.print(f"[dim]Etapa 2: Buscando respuesta específica en contexto...[/dim]")
            results = self.hybrid_search(
                search_query,
                top_k=top_k*2,
                semantic_weight=semantic_weight_run,
                allowed_sources=(plan.get('candidate_docs') if plan.get('candidate_docs') and not locals().get('doc_scope', '') else None)
            )
            # Scoping por roles si hay candidatos (pero NO si es doc-scope explícito)
            try:
                if plan.get('candidate_docs') and not locals().get('doc_scope', ''):
                    before = len(results)
                    results = self._filter_to_candidates(results, plan['candidate_docs'])
                    # Solo aplicar si no filtra demasiado (mantener al menos 50% o mínimo 5)
                    if len(results) >= max(5, before // 2):
                        console.print(f"[dim]Scoping por roles (Etapa 2): {before} -> {len(results)}[/dim]")
                    else:
                        console.print(f"[yellow]Scoping por roles demasiado agresivo ({before} -> {len(results)}) - omitiendo[/yellow]")
                        results = self.hybrid_search(search_query, top_k=top_k*2, semantic_weight=semantic_weight_run)
            except Exception:
                pass
            
            # Combinar: priorizar resultados de la entidad por COINCIDENCIA DE FUENTE (más robusto que texto)
            allowed_sources = set()
            for er in entity_results:
                try:
                    src_er = (er.get('metadata', {}) or {}).get('source', '')
                    if src_er:
                        allowed_sources.add(src_er.lower())
                except Exception:
                    pass
            strict = []
            present_keys = set()
            for r in results:
                try:
                    src_r = (r.get('metadata', {}) or {}).get('source', '').lower()
                    key = f"{src_r}:{r.get('metadata', {}).get('page', 0)}"
                except Exception:
                    src_r = ''
                    key = ''
                if src_r in allowed_sources and key not in present_keys:
                    r['stage_boost'] = 1.25
                    r['hybrid_score'] *= r['stage_boost']
                    strict.append(r)
                    present_keys.add(key)
            # Si faltan, completar con entity_results directamente (evitar duplicados por fuente/página)
            if len(strict) < top_k:
                for er in entity_results:
                    try:
                        src_er = (er.get('metadata', {}) or {}).get('source', '').lower()
                        key_er = f"{src_er}:{er.get('metadata', {}).get('page', 0)}"
                    except Exception:
                        src_er = ''
                        key_er = ''
                    if key_er and key_er not in present_keys:
                        strict.append(er)
                        present_keys.add(key_er)
                        if len(strict) >= top_k:
                            break
            results = strict[:top_k]
        elif results is None:
            # Búsqueda normal (una etapa) - solo si no se hizo búsqueda especializada
            console.print(f"[dim]Búsqueda semántica ({semantic_weight*100:.0f}%) + keyword ({(1-semantic_weight)*100:.0f}%)...[/dim]")
            # Usar consulta expandida si fue construida
            # Priorizar ancla conversacional si existe
            try:
                if followup_anchor_active and anchor_phrase:
                    search_query = f"{anchor_phrase} {question}".strip()
            except Exception:
                pass
            search_q = locals().get('search_query', question)
            if 'search_query' in locals():
                search_q = search_query
            results = self.hybrid_search(
                search_q,
                top_k=top_k*2,
                semantic_weight=semantic_weight_run,
                allowed_sources=(plan.get('candidate_docs') if plan.get('candidate_docs') and not locals().get('doc_scope', '') else None)
            )
            # Scoping por roles si hay candidatos (pero NO si es doc-scope explícito)
            try:
                if 'plan' in locals() and plan.get('candidate_docs') and not locals().get('doc_scope', ''):
                    before = len(results)
                    results = self._filter_to_candidates(results, plan['candidate_docs'])
                    # Solo aplicar si no filtra demasiado (mantener al menos 50% o mínimo 5)
                    if len(results) >= max(5, before // 2):
                        console.print(f"[dim]Scoping por roles: {before} -> {len(results)}[/dim]")
                    else:
                        console.print(f"[yellow]Scoping por roles demasiado agresivo ({before} -> {len(results)}) - omitiendo[/yellow]")
                        results = self.hybrid_search(search_q, top_k=top_k*2, semantic_weight=semantic_weight_run)
            except Exception:
                pass
            
            # Filtrar por entidades (pero NO si es procedural y NO en follow-up con ancla)
            if entity_filter_strict and entities and not locals().get('followup_anchor_active', False):
                console.print(f"[dim]Filtrando por entidades relevantes...[/dim]")
                results = self._filter_by_entity(results, entities)
                results = results[:top_k]
            elif is_procedural:
                # Para procedimientos, solo limitar top_k sin filtrar agresivamente
                results = results[:top_k]
        
        console.print(f"[dim]OK: {len(results)} fragmentos recuperados[/dim]")
        
        # Asegurar presencia de al menos un resultado que mencione cada entidad (no solo comparaciones)
        if results and 'entities' in locals() and entities and self.flags.get('ensure_entity_sources', True) and not is_comparison:
            results = self._ensure_results_for_entities(results, entities, per_entity=1)
        
        # RE-RANKING: Mejorar orden de relevancia con modelo especializado
        results = self._rerank_results(question, results, top_k=top_k)
        
        # AJUSTE por rol de documento (role-based weighting) usando DocCards
        try:
            if self.config.get('use_doc_roles', True) and isinstance(self.doc_roles, dict) and self.doc_roles.get('docs'):
                preferred_roles = []
                if 'plan' in locals():
                    preferred_roles = plan.get('doc_roles_preferred', [])
                adjusted = []
                docs_cards = self.doc_roles.get('docs', {})
                attr_norm = ''
                if 'plan' in locals():
                    try:
                        a = plan.get('attribute')
                        if a:
                            attr_norm = a.lower().strip()
                    except Exception:
                        attr_norm = ''
                for r in results:
                    src = (r.get('metadata', {}) or {}).get('source', '')
                    card = docs_cards.get(src, {}) or docs_cards.get(Path(src).name, {}) if src else {}
                    bonus = 0.0
                    role = card.get('role')
                    cent = float(card.get('centrality', 0.0) or 0.0)
                    if role and role in preferred_roles:
                        bonus += 0.2
                    if cent > 0:
                        bonus += 0.1 * cent
                    if attr_norm:
                        try:
                            attrs = [x.lower() for x in (card.get('attributes_index', []) or [])]
                            if attr_norm in attrs:
                                bonus += 0.15
                        except Exception:
                            pass
                    # Penalizar procedimientos/manuales si hay entidad y no es procedural
                    if 'entities' in locals() and entities and not is_procedural and role in ['procedure', 'manual_scada']:
                        bonus -= 0.2
                    r['final_score'] = float(r.get('final_score', 0.0)) + bonus
                    adjusted.append(r)
                results = sorted(adjusted, key=lambda x: x.get('final_score', 0.0), reverse=True)
        except Exception:
            pass
        
        # BOOSTING/penalización por fuente para queries específicas (no agregación)
        if results and not is_aggregation and self.flags.get('boost_source_by_entity', True):
            ents = entities if 'entities' in locals() else []
            ql2 = question.lower()
            boosted = []
            for r in results:
                src = r.get('metadata', {}).get('source', '').lower()
                txt = r.get('text', '').lower()
                fs = r.get('final_score', 0.0)
                # Evaluar mención explícita de entidad
                has_ent_mention = bool(ents) and any(e.lower() in (txt + ' ' + src) for e in ents)
                # Boost: Anexo D solo si hay mención explícita de la entidad
                if 'anexo d' in src and ents:
                    if has_ent_mention:
                        fs += 0.5
                    else:
                        fs -= 0.4
                # Penalizar: documentos procedimentales/genéricos cuando hay entidad
                if ents and (any(p in src for p in ['pt_',' pt','pt ', 'manual', 'procedim', 'instructivo'])):
                    fs -= 0.4
                # Bonus si hay mención literal de la entidad
                if has_ent_mention:
                    fs += 0.2
                # Penalización si NO hay ninguna mención de la entidad en el chunk
                if ents and not has_ent_mention:
                    fs -= 0.35
                # Boost específico: si pregunta contiene 'servicio crom', priorizar documento BLC-ServicioCROM
                if ('servicio crom' in ql2 or 'serviciocrom' in ql2) and (
                    'serviciocrom' in src or 'blc-serviciocrom' in src or ('servicio' in src and 'crom' in src)
                ):
                    fs += 0.7
                r['final_score'] = fs
                boosted.append(r)
            results = sorted(boosted, key=lambda x: x.get('final_score', 0.0), reverse=True)
        
        # Diversificar por fuente para consultas de comparación (cobertura de entidades)
        if results and is_comparison and self.flags.get('diversify_sources_for_comparison', True):
            results = self._diversify_by_source(results, per_source_limit=2, max_results=top_k)
            # Heurística de promoción de fuentes esperadas para comparación específica (Kosten vs Loma Blanca)
            ql = question.lower()
            if ("kosten" in ql) and ("loma blanca" in ql) and self.flags.get('ensure_entity_sources', True):
                grenergy_idx = None
                goldwind_idx = None
                for idx, r in enumerate(results[:min(len(results), 15)]):
                    src = r.get('metadata', {}).get('source', '').lower()
                    txt = r.get('text', '').lower()
                    if grenergy_idx is None and 'grenergy' in src and 'kosten' in txt:
                        grenergy_idx = idx
                    if goldwind_idx is None and 'goldwind' in src and ('loma blanca' in txt or 'loma' in txt):
                        goldwind_idx = idx
                    if grenergy_idx is not None and goldwind_idx is not None:
                        break
                promoted = []
                indices = set()
                if grenergy_idx is not None:
                    promoted.append(results[grenergy_idx])
                    indices.add(grenergy_idx)
                if goldwind_idx is not None:
                    promoted.append(results[goldwind_idx])
                    indices.add(goldwind_idx)
                if promoted:
                    rest = [r for i, r in enumerate(results) if i not in indices]
                    results = promoted + rest
                # Asegurar presencia explícita de fuentes claves
                if self.flags.get('ensure_entity_sources', True):
                    results = self._ensure_source_for_entity(results, 'grenergy', 'kosten', limit=1)
                    results = self._ensure_source_for_entity(results, 'goldwind', 'loma blanca', limit=1)
            # Generalización: asegurar al menos un resultado por entidad
            if 'entities' in locals() and entities and self.flags.get('ensure_entity_sources', True):
                results = self._ensure_results_for_entities(results, entities, per_entity=1)
        
        # FILTRO DE CALIDAD: Eliminar documentos con scores muy bajos (irrelevantes)
        # EXCEPTO para queries de agregación, detalladas, comparación (opcional), LISTADO o DOC-SCOPE
        if results and not is_aggregation and not is_detailed and not (is_comparison and self.flags.get('skip_quality_filter_for_comparison', True)) and not locals().get('is_listing_ctx', False) and not locals().get('doc_scope', ''):
            # Mostrar distribución de scores para debug
            if results:
                raw_scores = [r.get('rerank_score', 0) for r in results[:10]]
                console.print(f"[dim]Top 10 scores: {', '.join([f'{s:.2f}' for s in raw_scores])}[/dim]")
            # Si TODOS los scores son muy bajos, omitir filtro para no perder recall
            s_max = max(raw_scores) if raw_scores else 0.0
            apply_quality_filter = True
            if s_max < 0.10:
                console.print(f"[yellow]Scores bajos globalmente (max < 0.10) - omitiendo filtro de calidad[/yellow]")
                apply_quality_filter = False
            
            # Si hay múltiples entidades (>= 3), relajar el filtro de calidad
            num_entities = len(entities) if 'entities' in locals() else 0
            if num_entities >= 3:
                console.print(f"[yellow]Consulta multi-entidad ({num_entities} entidades) - relajando filtro de calidad[/yellow]")
                apply_quality_filter = False

            # Filtrar por score normalizado si existe; fallback a score crudo
            try:
                ql_local = question.lower()
                is_numeric_ctx = any(k in ql_local for k in ['cuant', 'número', 'numero', 'mw', 'potencia', 'aerogeneradores', 'wtg'])
            except Exception:
                is_numeric_ctx = False
            min_norm = 0.10 if is_numeric_ctx else 0.15
            before_quality = list(results)
            if apply_quality_filter:
                if any('rerank_norm' in r for r in results[:5]):
                    quality_results = [r for r in results if r.get('rerank_norm', 0.0) >= min_norm]
                else:
                    min_rerank_score = -1.0
                    quality_results = [r for r in results if r.get('rerank_score', 0) >= min_rerank_score]
            else:
                quality_results = list(results)

            if quality_results:
                results = quality_results
                # Mensaje según criterio aplicado
                try:
                    if any('rerank_norm' in r for r in results[:3]):
                        console.print(f"[dim]OK: Filtro de calidad: {len(results)} documentos (rerank_norm >= {min_norm})[/dim]")
                    else:
                        console.print(f"[dim]OK: Filtro de calidad: {len(results)} documentos[/dim]")
                except Exception:
                    console.print(f"[dim]OK: Filtro de calidad: {len(results)} documentos[/dim]")
                
                # LÍMITE: Si hay muchos documentos, tomar solo los top 10 para evitar timeout
                # EXCEPTO cuando el usuario pidió revisar TODOS los Anexos D / CADA central
                if len(results) > 10 and not self._requires_full_anexos_coverage(question) and not locals().get('is_listing_ctx', False):
                    console.print(f"[yellow]Limitando a top 10 documentos para evitar timeout[/yellow]")
                    results = results[:10]
                # Asegurar cobertura mínima para preguntas numéricas (al menos 2 docs si hay disponibles)
                if is_numeric_ctx and len(results) < 2 and len(before_quality) >= 2:
                    extra = []
                    for r in before_quality:
                        if r not in results:
                            extra.append(r)
                        if len(results) + len(extra) >= 2:
                            break
                    if extra:
                        results = results + extra
        
        # OPTIMIZACIÓN: Aplicar filtro de calidad adaptativo
        try:
            results = self._adaptive_quality_filter(results, question)
        except Exception as e:
            console.print(f"[dim]Filtro adaptativo no aplicado: {e}[/dim]")
        
        # OPTIMIZACIÓN: Deduplicación semántica de resultados
        try:
            results = self._deduplicate_results(results, similarity_threshold=0.85)
        except Exception as e:
            console.print(f"[dim]Deduplicación no aplicada: {e}[/dim]")
        
        # OPTIMIZACIÓN: Limitar resultados por fuente (máx 2 por documento)
        try:
            results = self._limit_results_per_source(results, max_per_source=2)
        except Exception as e:
            console.print(f"[dim]Limitación por fuente no aplicada: {e}[/dim]")
        
        # OPTIMIZACIÓN FASE 3: Categorizar resultados para contexto estructurado
        try:
            results = self._categorize_results(results)
            console.print(f"[dim]Contexto categorizado por tipo de información[/dim]")
        except Exception as e:
            console.print(f"[dim]Categorización no aplicada: {e}[/dim]")
        
        if results and is_aggregation:
            console.print(f"[dim]OK: Modo agregación: usando TODOS los documentos sin filtro de calidad[/dim]")
        
        # Antes de construir contexto, ajustar resultados según tecnología y añadir vecinos de página
        try:
            if results:
                results = self._filter_results_by_technology(question, results)
                results = self._augment_with_page_neighbors(results)
        except Exception:
            pass
        # Si tras el filtrado no hay resultados suficientes, devolver respuesta conservadora
        if not results or len(results) == 0:
            brief = "No se encontró información en los documentos para esa consulta."
            return {
                'question': question,
                'results': [],
                'context': '',
                'answer': brief,
                'sources': [],
                'method': 'no_docs',
                'time': time.time() - _t0,
                'memory_hits': 0
            }

        # Construir contexto (OPTIMIZADO para chunks completos)
        if is_aggregation:
            # MODO AGREGACIÓN: Manejar dos casos
            # 1. Si tenemos "Listado Centrales" -> usar TODOS sus chunks
            # 2. Si tenemos Anexos D individuales -> un chunk por central
            
            # Verificar si estamos usando "Listado Centrales"
            ql_local = question.lower()
            tech_query = any(w in ql_local for w in ['tecnologia', 'tecnología', 'tecnologias', 'tecnologías'])
            full_cov_here = self._requires_full_anexos_coverage(question)
            has_listado = any('listado' in r['metadata']['source'].lower() and 'central' in r['metadata']['source'].lower() for r in results)
            # Si se pide tecnología o cobertura completa, FORZAR uso de Anexos D individuales
            force_annex = tech_query or full_cov_here
            if force_annex:
                only_annex = [r for r in results if ('anexo d' in r['metadata']['source'].lower()) and not ('listado' in r['metadata']['source'].lower() and 'central' in r['metadata']['source'].lower())]
                if only_annex:
                    results = only_annex
                    has_listado = False
            
            if has_listado:
                console.print(f"[dim]Usando listado general - Incluyendo multiples fragmentos del mismo documento...[/dim]")
                
                # Para Listado Centrales, PRIORIZAR páginas 1-2 (donde está la tabla)
                # Ordenar por página (ascendente) para tomar primero las páginas con la tabla
                listado_sorted = sorted(results, key=lambda x: x['metadata']['page'])
                
                # Tomar chunks de páginas 1-2 primero, luego el resto
                context_parts = []
                for i, r in enumerate(listado_sorted[:20], 1):  # Top 20 chunks del listado
                    source_name = r['metadata']['source'].split('.pdf')[0][:60]
                    page = r['metadata']['page']
                    text = r['text'][:1200]  # Más texto para capturar varias centrales (1000->1200)
                    context_parts.append(f"[Doc {i} - {source_name} p.{page}]\n{text}")
                
                context = "\n\n".join(context_parts)
                console.print(f"[dim]OK: Contexto construido con {len(context_parts)} fragmentos del listado (priorizando páginas 1-2)[/dim]")
            else:
                console.print(f"[dim]Usando documentos individuales - Agrupando por fuente unica...[/dim]")
                # Para Anexos D, agrupar por documento único (1 chunk por central)
                docs_by_source = {}
                for r in results:
                    source = r['metadata']['source']
                    if source not in docs_by_source:
                        docs_by_source[source] = []
                    docs_by_source[source].append(r)
                
                console.print(f"[dim]OK: Encontradas {len(docs_by_source)} fuentes únicas[/dim]")
                
                # Tomar el mejor chunk de cada documento
                context_parts = []
                for i, (source, chunks) in enumerate(sorted(docs_by_source.items()), 1):
                    # Tomar el chunk con mejor score de este documento
                    best_chunk = max(chunks, key=lambda x: x.get('final_score', x.get('hybrid_score', 0)))
                    source_name = source.split('.pdf')[0][:60]
                    page = best_chunk['metadata']['page']
                    text = best_chunk['text'][:800]  # Texto suficiente para encontrar potencia
                    
                    context_parts.append(f"[Doc {i} - {source_name} p.{page}]\n{text}")
                
                context = "\n\n".join(context_parts)
                console.print(f"[dim]OK: Contexto construido con {len(context_parts)} fuentes únicas[/dim]")
            
            # Antes de construir contexto largo/detallado, aplicar pista de doc+páginas si existe
            try:
                doc_hint = self._extract_doc_pages_hint(question)
                if doc_hint and results:
                    forced = []
                    pages = doc_hint.get('pages') or []
                    for pg in pages[:6]:
                        try:
                            forced.extend(self._search_in_specific_doc(doc_hint['doc'], page=pg, top_k=min(max(3, top_k//max(1,len(pages))), 10)))
                        except Exception:
                            continue
                    if forced:
                        seen = set()
                        merged = []
                        for r in forced + (results or []):
                            key = (r.get('metadata',{}).get('source',''), r.get('metadata',{}).get('page',0), (r.get('text','') or '')[:120])
                            if key in seen:
                                continue
                            seen.add(key)
                            merged.append(r)
                        results = merged
                        console.print(f"[dim]Hint aplicado (contexto): {doc_hint['doc']} páginas {pages}[/dim]")
            except Exception:
                pass
            
        elif is_detailed:
            # MODO DETALLADO: Obtener fragmentos de los documentos más relevantes
            console.print(f"[bold cyan]MODO DETALLADO ACTIVADO[/bold cyan]")
            console.print(f"[dim]Aplicando filtros por categoría y entidad para reducir ruido[/dim]")
            
            if not results:
                console.print(f"[yellow]ADVERTENCIA: No hay resultados para modo detallado[/yellow]")
                context = ""
                docs_by_source = {}
            else:
                # Identificar los documentos más relevantes basándose SOLO en re-rank scores
                # El re-ranker ya determinó cuáles son relevantes
                source_best_score = {}
                source_chunk_count = {}
                
                for r in results[:20]:  # Solo top 20 (ya re-rankeados por relevancia)
                    source = r.get('metadata', {}).get('source', '')
                    # Usar rerank_score (ya es el mejor indicador de relevancia)
                    score = r.get('rerank_score', -999)
                    
                    if source:
                        # Contar chunks por documento
                        if source not in source_chunk_count:
                            source_chunk_count[source] = 0
                            source_best_score[source] = score
                        
                        source_chunk_count[source] += 1
                        
                        # Mantener el MEJOR score (más cercano a 0)
                        if score > source_best_score[source]:
                            source_best_score[source] = score
                
                if not source_best_score:
                    console.print(f"[yellow]ADVERTENCIA: No se encontraron documentos fuente[/yellow]")
                    # Fallback a modo normal
                    docs_by_source = {}
                    context_parts = []
                    for i, r in enumerate(results[:10], 1):
                        source = r.get('metadata', {}).get('source', 'Unknown').split('.pdf')[0][:60]
                        page = r.get('metadata', {}).get('page', 0)
                        text = r.get('text', '')[:1000]
                        context_parts.append(f"[Doc {i} - {source} p.{page}]\n{text}")
                    context = "\n\n".join(context_parts)
                else:
                    # Tomar SOLO el documento con MEJOR rerank_score (el chunk #1 después de re-ranking)
                    # EXCEPCIÓN: Si hay un Anexo D específico de la entidad, priorizarlo sobre "Listado Centrales"
                    best_doc = results[0]['metadata']['source']
                    # Si hay sticky sources y ancla activa, priorizar documento pegajoso si aparece en resultados
                    try:
                        sticky = getattr(self, '_sticky_sources', None)
                        if sticky and int(sticky.get('ttl', 0)) > 0 and locals().get('followup_anchor_active', False):
                            sticky_set = set(sticky.get('sources', []) or [])
                            sticky_candidates = [r for r in results[:10] if r.get('metadata', {}).get('source') in sticky_set]
                            if sticky_candidates:
                                best_doc = max(sticky_candidates, key=lambda x: x.get('rerank_score', -999))['metadata']['source']
                                console.print(f"[dim]Sticky doc priorizado por ancla: {best_doc.split('.pdf')[0][:40]}[/dim]")
                    except Exception:
                        pass
                    
                    # PRIORIDAD 1: Si Etapa 1 encontró un Anexo D específico, usarlo
                    try:
                        target_anexo_etapa1 = getattr(self, '_target_anexo_etapa1', None)
                        if target_anexo_etapa1:
                            # Buscar ese anexo en los resultados
                            for r in results[:15]:
                                source = r['metadata']['source']
                                if target_anexo_etapa1.lower() in source.lower():
                                    best_doc = source
                                    console.print(f"[cyan]Priorizando Anexo D de Etapa 1: {best_doc.split('.pdf')[0][:40]}[/cyan]")
                                    break
                            # Limpiar flag
                            delattr(self, '_target_anexo_etapa1')
                    except Exception:
                        pass
                    
                    # PRIORIDAD 2: Buscar si hay un Anexo D específico en los top-5 resultados
                    if 'listado' in best_doc.lower() and 'central' in best_doc.lower():
                        # El mejor resultado es "Listado Centrales", buscar Anexo D específico
                        for r in results[:5]:
                            source = r['metadata']['source']
                            # Si encontramos un Anexo D que NO es Listado, priorizarlo
                            if 'anexo d' in source.lower() and 'listado' not in source.lower():
                                console.print(f"[yellow]Priorizando documento específico sobre listado general[/yellow]")
                                best_doc = source
                                break
                    
                    # DECISIÓN INTELIGENTE: ¿Necesita múltiples documentos?
                    needs_multi_doc = False
                    multi_doc_reason = ""
                    
                    # EXCEPCIÓN: Si Etapa 1 encontró un Anexo D específico, NO usar multi-doc (usar solo ese)
                    has_etapa1_anexo = False
                    try:
                        if getattr(self, '_target_anexo_etapa1', None):
                            has_etapa1_anexo = True
                    except Exception:
                        pass
                    
                    # 1. Consultas procedurales/troubleshooting requieren múltiples fuentes
                    if (is_procedural or is_troubleshooting) and not has_etapa1_anexo:
                        needs_multi_doc = True
                        multi_doc_reason = "procedural/troubleshooting"
                    
                    # 2. Planner sugiere múltiples roles (procedure + manual + analysis)
                    if not has_etapa1_anexo:
                        try:
                            if plan and isinstance(plan.get('doc_roles_preferred'), list) and len(plan.get('doc_roles_preferred', [])) >= 2:
                                needs_multi_doc = True
                                multi_doc_reason = "planner sugiere múltiples roles"
                        except Exception:
                            pass
                    
                    # 3. Top-5 resultados tienen alta diversidad de documentos (3+ docs distintos con score similar)
                    if not has_etapa1_anexo:
                        try:
                            top5_sources = [r['metadata']['source'] for r in results[:5]]
                            unique_top5 = set(top5_sources)
                            if len(unique_top5) >= 3:
                                # Verificar que los scores sean similares (no hay un claro ganador)
                                top_scores = [r.get('rerank_score', 0) for r in results[:5]]
                                if len(top_scores) >= 3:
                                    score_range = max(top_scores) - min(top_scores)
                                    if score_range < 0.3:  # Scores muy cercanos
                                        needs_multi_doc = True
                                        multi_doc_reason = "alta diversidad en top-5 con scores similares"
                        except Exception:
                            pass
                    
                    # 4. Consulta menciona múltiples aspectos/temas (maniobras + protecciones + notificación)
                    if not has_etapa1_anexo:
                        try:
                            ql_check = question.lower()
                            aspect_keywords = [
                                ['maniobra', 'procedimiento', 'protocolo'],
                                ['proteccion', 'relay', 'ansi'],
                                ['notifica', 'reporta', 'comunica'],
                                ['scada', 'monitoreo', 'alarma'],
                                ['mantenimiento', 'intervencion', 'reparacion']
                            ]
                            aspects_found = sum(1 for group in aspect_keywords if any(kw in ql_check for kw in group))
                            if aspects_found >= 2:
                                needs_multi_doc = True
                                multi_doc_reason = f"múltiples aspectos detectados ({aspects_found})"
                        except Exception:
                            pass
                    
                    # Seleccionar documentos
                    if needs_multi_doc:
                        # MODO MULTI-DOC: Balancear entre top documentos relevantes
                        console.print(f"[cyan]Modo multi-documento activado: {multi_doc_reason}[/cyan]")
                        
                        # Seleccionar top 3-5 documentos distintos con mejor score
                        selected_sources = []
                        seen_sources = set()
                        for r in results[:15]:  # Revisar top-15
                            src = r['metadata']['source']
                            if src not in seen_sources:
                                selected_sources.append(src)
                                seen_sources.add(src)
                                if len(selected_sources) >= 4:  # Máximo 4 documentos
                                    break
                        
                        # Si hay roles del planner, priorizar documentos que coincidan
                        try:
                            if plan and plan.get('doc_roles_preferred'):
                                preferred_roles = set(plan['doc_roles_preferred'])
                                role_matched_sources = []
                                for src in selected_sources:
                                    doc_info = self.doc_roles.get('docs', {}).get(src, {})
                                    doc_role = doc_info.get('role', '')
                                    if doc_role in preferred_roles:
                                        role_matched_sources.append(src)
                                # Priorizar docs con roles, luego agregar otros
                                other_sources = [s for s in selected_sources if s not in role_matched_sources]
                                selected_sources = role_matched_sources + other_sources
                        except Exception:
                            pass
                        
                        console.print(f"[dim]Documentos seleccionados: {len(selected_sources)}[/dim]")
                        for i, src in enumerate(selected_sources[:3], 1):
                            console.print(f"[dim]  {i}. {src.split('.pdf')[0][:50]}[/dim]")
                    else:
                        # MODO SINGLE-DOC: Solo el mejor documento
                        selected_sources = [best_doc]
                        console.print(f"[dim]Documento principal: {best_doc.split('.pdf')[0][:40]}[/dim]")
                        console.print(f"[dim]Score: {results[0].get('rerank_score', 0):.2f}, Chunks en top-20: {source_chunk_count.get(best_doc, 1)}[/dim]")

                    # Política de fuentes: excluir 'Listado Centrales' salvo queries de listado
                    try:
                        is_listing_query = self._is_listing_query(question)
                    except Exception:
                        is_listing_query = False
                    if not is_listing_query and selected_sources:
                        selected_sources = [s for s in selected_sources if not (('listado' in s.lower()) and ('central' in s.lower()))]
                        if not selected_sources:
                            # Fallback si filtró todo
                            selected_sources = [best_doc]

                    # Si hay entidad y no es listado, priorizar Anexos D específicos
                    if entities and len(entities) > 0 and not is_listing_query:
                        annex = [s for s in selected_sources if ('anexo d' in s.lower() and 'listado' not in s.lower())]
                        if annex:
                            selected_sources = annex
                        try:
                            target_anexo_etapa1 = getattr(self, '_target_anexo_etapa1', None)
                            if target_anexo_etapa1:
                                exact = [s for s in selected_sources if target_anexo_etapa1.lower() in s.lower()]
                                if exact:
                                    selected_sources = exact
                        except Exception:
                            pass
                    
                    # Obtener TODOS los chunks de los documentos seleccionados desde la base de datos
                    all_docs = self.vector_store.collection.get()
                    docs_by_source = {}
                    
                    # FILTRADO POR ENTIDAD: DESACTIVADO en modo detallado (confiar en re-ranker)
                    entity_filter_active = False
                    if False and entities and len(entities) > 0:  # DESACTIVADO
                        # Detectar consultas tipo PT (evitar filtrado agresivo por texto de chunk)
                        try:
                            ql = (question or '').lower()
                            ents_low = [e.lower() for e in entities]
                            pt_like_ctx = bool(re.search(r"\bpt\s*_?\d+\b", ql)) or any(('pt' in e and any(ch.isdigit() for ch in e)) for e in ents_low) or ('protocolo tecnico' in ql) or ('protocolo de cammesa' in ql)
                        except Exception:
                            pt_like_ctx = False
                        # Construir términos FUERTES: frases completas + tokens no genéricos
                        strong_terms = []
                        ban_tokens = {'de','del','la','el','los','las','parque','central','planta','solar','fotovoltaico','fotovoltaica','eolico','eólico','eolica','eólica','ps','pe','p.s.','p.e.','oeste','este','norte','sur'}
                        for ent in entities:
                            ent_l = ent.lower().strip()
                            if ent_l and ent_l not in strong_terms:
                                strong_terms.append(ent_l)
                            words = ent_l.split()
                            if len(words) > 1:
                                for t in words:
                                    if t and (len(t) >= 5) and (t not in ban_tokens) and not t.isdigit():
                                        if t not in strong_terms:
                                            strong_terms.append(t)
                        if not strong_terms:
                            strong_terms = [entities[0].lower()]
                        # Activar scoring por entidad solo si NO es PT-like y NO hay ancla follow-up
                        entity_filter_active = (not pt_like_ctx) and (not locals().get('followup_anchor_active', False))
                        console.print(f"[cyan]Filtrado por entidad (scoring): {entities[0]} (keywords: {', '.join(strong_terms[:5])})[/cyan]")
                    
                    for i, source in enumerate(all_docs['metadatas']):
                        doc_source = source.get('source', '')
                        if doc_source in selected_sources:
                            chunk_text = all_docs['documents'][i]
                            
                            # SCORING: calcular entity_score por chunk
                            entity_score = 0.0
                            if entity_filter_active:
                                chunk_lower = chunk_text.lower()
                                source_lower = (source.get('source', '') or '').lower()
                                try:
                                    from rapidfuzz import fuzz as _fuzz
                                    have_rf = True
                                except Exception:
                                    have_rf = False
                                
                                # Priorizar entidad completa (nombre compuesto)
                                import re as _re_es
                                primary_entity = entities[0].lower()
                                # Coincidencia exacta por frase con límites de palabra
                                exact_in_chunk = bool(_re_es.search(r"\b" + _re_es.escape(primary_entity) + r"\b", chunk_lower))
                                exact_in_source = bool(_re_es.search(r"\b" + _re_es.escape(primary_entity) + r"\b", source_lower))
                                if exact_in_chunk:
                                    entity_score += 6.0  # Más alto si la frase completa aparece en el texto
                                elif exact_in_source:
                                    entity_score += 4.0  # Alto si aparece en el nombre del archivo
                                
                                # Luego evaluar keywords individuales
                                partial_boost = 0.0
                                for kw in strong_terms:
                                    if kw == primary_entity:
                                        continue  # Ya evaluado arriba
                                    # Si no hay coincidencia exacta de la frase completa, rebajar impacto de tokens sueltos
                                    if kw in chunk_lower or kw in source_lower:
                                        partial_boost += (1.2 if (' ' in kw and exact_in_chunk) else 0.4)
                                    elif have_rf:
                                        try:
                                            if max(_fuzz.partial_ratio(kw, chunk_lower), _fuzz.partial_ratio(kw, source_lower)) >= (85 if ' ' in kw else 90):
                                                partial_boost += (0.8 if (' ' in kw and exact_in_chunk) else 0.3)
                                        except Exception:
                                            pass
                                # Limitar el aporte de tokens parciales si no hay match exacto de la frase
                                if not (exact_in_chunk or exact_in_source):
                                    partial_boost = min(partial_boost, 0.8)
                                entity_score += partial_boost
                            
                            if doc_source not in docs_by_source:
                                docs_by_source[doc_source] = []
                            docs_by_source[doc_source].append({
                                'text': chunk_text,
                                'metadata': source,
                                'rerank_score': 0,
                                'entity_score': entity_score
                            })
                    
                    total_chunks = sum(len(chunks) for chunks in docs_by_source.values())
                    if entity_filter_active:
                        console.print(f"[dim]Total de fragmentos recuperados (filtrados por entidad): {total_chunks}[/dim]")
                    else:
                        console.print(f"[dim]Total de fragmentos recuperados: {total_chunks}[/dim]")
                    
                    # Reordenar fuentes por relevancia: priorizar fuentes con evidencia numérica ligada a la entidad
                    # NUNCA priorizar "Listado Centrales" salvo que sea una query de listado explícito
                    def _source_score(src_name: str, chunks: list) -> float:
                        s = 0.0
                        name_l = (src_name or '').lower()
                        # PENALIZAR Listado Centrales si NO es una query de listado
                        try:
                            is_listing_query = self._is_listing_query(question)
                        except Exception:
                            is_listing_query = False
                        if ('listado' in name_l and 'central' in name_l) and not is_listing_query:
                            s -= 3.0  # Penalización fuerte para evitar priorizar listado en queries de detalle
                        # Bonus si hay números MW junto a la entidad
                        try:
                            import re as _re_s
                            pe = (entities[0] if entities else '').lower()
                            for ch in chunks:
                                txt = (ch.get('text') or '').lower()
                                if pe and pe in txt and _re_s.search(r"\b(\d+[\.,]?\d*)\s*mw\b", txt):
                                    s += 2.0
                                    break
                        except Exception:
                            pass
                        # Agregar suma de entity_score como base
                        try:
                            s += sum(float(c.get('entity_score', 0.0)) for c in chunks[:10]) / 10.0
                        except Exception:
                            pass
                        return s

                    ordered_sources = sorted(docs_by_source.keys(), key=lambda k: _source_score(k, docs_by_source[k]), reverse=True)

                    # Heurísticas por categoría de la pregunta
                    ql = (question or '').lower()
                    try:
                        import re as _re_cat
                    except Exception:
                        _re_cat = None
                    def _is_numeric_q():
                        return any(k in ql for k in ['potencia',' mw','cuantos','cuántos','cantidad','wtg']) and not any(k in ql for k in ['lista','listado'])
                    def _is_location_q():
                        return any(k in ql for k in ['donde','dónde','ubicación','ubicacion','coordenada','latitud','longitud'])
                    is_numeric = _is_numeric_q()
                    is_location = _is_location_q()

                    # Construir contexto con límites para reducir ruido
                    context_parts = []
                    doc_idx = 1
                    max_total_chunks = (40 if needs_multi_doc else 25)
                    max_per_doc = (12 if needs_multi_doc else 8)
                    total_count = 0
                    per_doc_count = {}
                    for source in ordered_sources:
                        chunks = docs_by_source[source]
                        # Ordenar chunks priorizando entity_score y luego por página
                        chunks_sorted = sorted(chunks, key=lambda x: (-float(x.get('entity_score', 0.0)), x['metadata']['page']))
                        
                        # FILTRAR chunks con score muy bajo (< 1.0) si hay filtrado activo
                        if entity_filter_active:
                            chunks_sorted = [c for c in chunks_sorted if c.get('entity_score', 0.0) >= 1.0]
                        
                        # Limitar por documento y aplicar filtros por categoría
                        per_doc_count[source] = 0
                        for chunk in chunks_sorted:
                            if total_count >= max_total_chunks or per_doc_count[source] >= max_per_doc:
                                break
                            source_name = chunk['metadata']['source'].split('.pdf')[0][:60]
                            page = chunk['metadata']['page']
                            text = chunk['text'][:1200]
                            chunk_lower = (chunk.get('text') or '').lower()

                            # Reglas por categoría: DESACTIVADAS (confiar en re-ranker y LLM)
                            # Los filtros estrictos causan contextos vacíos
                            skip_chunk = False
                            # if skip_chunk:  # Nunca se ejecuta
                            #     continue

                            context_parts.append(f"[Doc {doc_idx} - {source_name} p.{page}]\n{text}")
                            doc_idx += 1
                            total_count += 1
                            per_doc_count[source] += 1
                    
                    # Balancear chunks entre documentos si es multi-doc
                    if needs_multi_doc and len(docs_by_source) > 1:
                        # Limitar chunks por documento para dar espacio a todos
                        max_chunks_per_doc = max(5, 25 // len(docs_by_source))
                        context_parts_balanced = []
                        doc_idx_balanced = 1
                        for source, chunks in docs_by_source.items():
                            chunks_sorted = sorted(chunks, key=lambda x: (-float(x.get('entity_score', 0.0)), x['metadata']['page']))
                            for chunk in chunks_sorted[:max_chunks_per_doc]:
                                source_name = chunk['metadata']['source'].split('.pdf')[0][:60]
                                page = chunk['metadata']['page']
                                text = chunk['text'][:1200]
                                context_parts_balanced.append(f"[Doc {doc_idx_balanced} - {source_name} p.{page}]\n{text}")
                                doc_idx_balanced += 1
                        context_parts = context_parts_balanced
                    
                    console.print(f"[dim]OK: Contexto construido con {len(context_parts)} fragmentos de {len(docs_by_source)} documentos[/dim]")
                    context = "\n\n".join(context_parts)
                    
                    # DEBUG: Verificar que el contexto no esté vacío
                    if not context or len(context) < 100:
                        console.print(f"[red]ERROR: Contexto muy corto o vacío ({len(context)} chars)[/red]")
                        console.print(f"[yellow]docs_by_source keys: {list(docs_by_source.keys())}[/yellow]")
                    else:
                        console.print(f"[dim]Longitud del contexto: {len(context)} caracteres[/dim]")
                    # Persistir fuentes pegajosas (sticky) para follow-ups
                    try:
                        ttl = int(self.flags.get('sticky_sources_ttl', 2) or 2)
                        setattr(self, '_sticky_sources', {'sources': list(docs_by_source.keys()), 'ttl': ttl})
                    except Exception:
                        pass
        else:
            full_cov = self._requires_full_anexos_coverage(question)
            # Aumentar cobertura para listados o scope explícito
            scoped = True if locals().get('doc_scope') else False
            if full_cov:
                num_docs = 10
            elif locals().get('is_listing_ctx', False) or scoped:
                num_docs = 30
            else:
                num_docs = (4 if (self.flags.get('postprocess_location', True) and any(k in question.lower() for k in ["donde", "dónde", "ubicaci", "coordenada", "latitud", "longitud"])) else 3)
            approx_token_budget = (3400 if (full_cov or locals().get('is_listing_ctx', False)) else 2800)
            approx_chars_budget = approx_token_budget * 4
            context_parts = []
            used_chars = 0
            # Cobertura por entidad en comparaciones
            ql = question.lower()
            is_comparison_ctx = any(k in ql for k in ["compara", "comparar", "comparación", "diferencia", " vs ", "versus"])
            is_location_ctx = any(k in ql for k in ["donde", "dónde", "ubicaci", "coordenada", "latitud", "longitud"]) if self.flags.get('postprocess_location', True) else False
            # Reordenar resultados priorizando ubicación si aplica
            if is_location_ctx and results:
                loc_words = ["latitud", "longitud", "ubicaci", "pampa del castillo"]
                location_hits = [r for r in results if any(w in r['text'].lower() for w in loc_words)]
                others = [r for r in results if r not in location_hits]
                results_ordered = location_hits + others
            else:
                results_ordered = results
            
            # Reordenar por página si es LISTADO y hay Listado Centrales en resultados o scope explícito
            try:
                if locals().get('is_listing_ctx', False) and results:
                    listado_results = [r for r in results if ('listado' in r['metadata']['source'].lower() and 'central' in r['metadata']['source'].lower())]
                    # Si hay scope al Listado, usarlo
                    if scoped and locals().get('doc_scope', '').lower().replace(' ', '').endswith('listadocentrales.pdf'):
                        if listado_results:
                            results_ordered = sorted(listado_results, key=lambda x: x['metadata']['page'])
                    elif listado_results:
                        results_ordered = sorted(listado_results, key=lambda x: x['metadata']['page'])
                    # Asegurar más documentos para cubrir toda la tabla
                    num_docs = max(num_docs, 30)
            except Exception:
                pass

            if is_comparison_ctx and 'entities' in locals() and entities:
                taken = 0
                added_sources = set()
                for ent in entities:
                    # Elegir chunk con evidencia numérica/modelos si es posible
                    chosen = None
                    evidence_words = ["aerogenerador", "aerogeneradores", " mw", "senvion", "3.6m114", "3.4m114", " 16", "dieciseis", "dieciséis"]
                    for r in results_ordered:
                        txt = r['text'].lower()
                        src_full = r['metadata']['source']
                        if ent.lower() in txt or ent.lower() in src_full.lower():
                            if self.flags.get('prefer_evidence_chunks', True) and any(w in txt for w in evidence_words):
                                chosen = r
                                break
                            if chosen is None:
                                chosen = r
                    if chosen is not None:
                        source = chosen['metadata']['source'].split('.pdf')[0][:60]
                        page = chosen['metadata']['page']
                        remaining_docs = num_docs - taken
                        if remaining_docs <= 0:
                            continue
                        per_doc_budget = max(600, (approx_chars_budget - used_chars) // max(remaining_docs, 1))
                        piece = chosen['text']
                        if len(piece) > per_doc_budget:
                            piece = self._condense_text(piece, per_doc_budget)
                        used_chars += len(piece)
                        key = source.lower()
                        if key not in added_sources:
                            context_parts.append(f"[Doc {taken+1} - {source} p.{page}]\n{piece}")
                            added_sources.add(key)
                            taken += 1
                # Completar si quedan huecos
                i = taken
                for r in results_ordered:
                    if i >= num_docs:
                        break
                    source = r['metadata']['source'].split('.pdf')[0][:60]
                    if source.lower() in added_sources:
                        continue
                    page = r['metadata']['page']
                    remaining_docs = num_docs - i
                    per_doc_budget = max(600, (approx_chars_budget - used_chars) // max(remaining_docs, 1))
                    piece = r['text']
                    if len(piece) > per_doc_budget:
                        piece = self._condense_text(piece, per_doc_budget)
                    used_chars += len(piece)
                    context_parts.append(f"[Doc {i+1} - {source} p.{page}]\n{piece}")
                    i += 1
            else:
                # Preferir chunks que mencionen explícitamente la ENTIDAD cuando aplica (estricto)
                if 'entities' in locals() and entities and not is_comparison:
                    ents_l = [e.lower() for e in entities]
                    hits = []
                    for r in results_ordered:
                        blob = (r['text'] + ' ' + r['metadata']['source']).lower()
                        if any(e in blob for e in ents_l):
                            hits.append(r)
                    # Si la query es sobre ET/subestación, priorizar aún más por palabras clave de ET
                    et_q = any(k in ql for k in [" et ", "estación transformadora", "estacion transformadora", "pampa del castillo", "132 kv", "33 kv", "4tr08"]) 
                    if et_q and hits:
                        et_words = [" et ", "estación transformadora", "estacion transformadora", "pampa del castillo", "132 kv", "barra", "33 kv", "4tr08", "33/132"]
                        hits_et = [r for r in hits if any(w in (r['text']+" "+r['metadata']['source']).lower() for w in et_words)]
                        if hits_et:
                            results_ordered = hits_et
                        else:
                            results_ordered = hits
                    else:
                        results_ordered = hits if hits else results_ordered
                for i, r in enumerate(results_ordered[:num_docs], 1):
                    source = r['metadata']['source'].split('.pdf')[0][:60]
                    page = r['metadata']['page']
                    remaining_docs = num_docs - i + 1
                    per_doc_budget = max(600, (approx_chars_budget - used_chars) // max(remaining_docs, 1))
                    piece = r['text']
                    if len(piece) > per_doc_budget:
                        piece = self._condense_text(piece, per_doc_budget)
                    used_chars += len(piece)
                    context_parts.append(f"[Doc {i} - {source} p.{page}]\n{piece}")
            context = "\n\n".join(context_parts)
        
        # OPTIMIZACIÓN FASE 3: Usar contexto estructurado por categorías para consultas normales
        # (No aplicar para agregaciones, procedimientos o modos especiales)
        # Detectar si es listado
        try:
            is_listing_query = self._is_listing_query(question)
        except Exception:
            is_listing_query = False
        
        if not is_aggregation and not is_procedural and not is_listing_query and not is_troubleshooting:
            try:
                structured_context = self._build_structured_context(results, max_chars=6000)
                if structured_context and len(structured_context) > 200:
                    context = structured_context
                    console.print(f"[dim]Contexto estructurado por categorías aplicado[/dim]")
            except Exception as e:
                console.print(f"[dim]Contexto estructurado no aplicado: {e}[/dim]")
        
        # Advertencia si hay entidades no encontradas
        if entity_filter and entities and len(results) < 5:
            console.print(f"[yellow]ADVERTENCIA: Pocos resultados con '{', '.join(entities)}' - amplia la busqueda[/yellow]")
        
        # Buscar en memoria del usuario primero
        memory_results = self.memory.search_memory(question, limit=3)
        
        # Agregar memoria al contexto si hay resultados (COMPACTO)
        if memory_results:
            console.print(f"[dim]OK: Encontrados {len(memory_results)} registros en memoria del usuario[/dim]")
            memory_context = "\n".join([
                f"[MEM{i+1}] Q:{m['question'][:50]} A:{m['answer'][:150]}"
                for i, m in enumerate(memory_results)
            ])
            context = memory_context + "\n---\n" + context
        
        # Obtener contexto conversacional de forma INTELIGENTE
        # Solo usar contexto si la pregunta actual es continuación del tema anterior
        last_query = self.conversation.get_last_user_message()
        
        should_use_context = False if no_context else self._should_use_conversation_context(question, last_query)
        
        if should_use_context:
            conv_context = self.conversation.get_context(last_n=2)  # Mantener contexto
            console.print(f"[dim]Usando contexto conversacional (tema relacionado)[/dim]")
        else:
            conv_context = ""  # Tema nuevo, no usar contexto
            if last_query:
                console.print(f"[dim]Tema nuevo detectado - contexto limpio[/dim]")
        # Inyectar ENTIDAD OBJETIVO en el contexto para enfocar al LLM
        if 'entities' in locals() and entities and not is_comparison:
            try:
                target_ent = entities[0]
                conv_context = f"ENTIDAD OBJETIVO: {target_ent}\n" + (conv_context or "")
            except Exception:
                pass
        tech_filter = self._extract_tech_filter(question)
        vendor_filter = self._extract_vendor_filter(question)
        
        # Agregar contexto multi-documento para consultas PROCEDIMENTALES (incluir controles/frameworks)
        try:
            if locals().get('is_procedural', False) or locals().get('is_troubleshooting', False):
                key_sources = []
                if key_sources:
                    results = self._ensure_sources(results or [], key_sources, per_source_limit=1)
                # Reordenar por boost si se agregó material clave
                try:
                    results.sort(key=lambda x: x.get('final_score', x.get('hybrid_score', 0.0)) + x.get('priority_boost', 0.0), reverse=True)
                except Exception:
                    pass
                # Forzar modo detallado en procedurales
                is_detailed = True
        except Exception:
            pass

        # Generar respuesta
        answer = None
        used_fallback = False
        
        # Reordenamiento por entidad exacta detectada en pregunta/entidades
        try:
            exact_ent = entities[0] if entities else None
            if exact_ent and results:
                results = self._boost_results_for_exact_entity(results, exact_ent)
                exact_matches = [r for r in results if exact_ent.lower() in (r.get('text') or '').lower()]
                if len(exact_matches) >= 3:
                    results = exact_matches + [r for r in results if r not in exact_matches][:3]
                # Rehacer contexto a partir del top reordenado
                try:
                    ctx_parts = []
                    for r in results[:8]:
                        md = r.get('metadata', {})
                        src = md.get('source', 'Unknown')
                        page = md.get('page', 0)
                        prefix = f"[Doc - {src} p.{page}]"
                        ctx_parts.append(prefix + "\n" + (r.get('text') or ''))
                    context = "\n\n".join(ctx_parts)
                except Exception:
                    pass
                # Asegurar conv_context con ENTIDAD OBJETIVO
                try:
                    conv_context = f"ENTIDAD OBJETIVO: {exact_ent}\n" + (conv_context or "")
                except Exception:
                    pass
        except Exception:
            pass
        if use_llm:
            # Determinar modo de generación
            if is_aggregation:
                mode_text = "agregación (suma total)"
                search_mode = "agregación"
            elif is_detailed:
                mode_text = "detallada"
                search_mode = "detallada"
            else:
                is_multi_doc = self._is_multi_document_query(question)
                mode_text = "rápida"
                search_mode = "múltiples fuentes" if is_multi_doc else "búsqueda específica"
            
            console.print(f"[dim]Generando respuesta {mode_text} con {self.ollama_model} (modo: {search_mode})...[/dim]")
            
            # Contar documentos únicos si es agregación
            num_unique_docs = 0
            if is_aggregation:
                num_unique_docs = len(set(r['metadata']['source'] for r in results))
            
            # Priorizar resultados por pista explícita de documento+páginas si está presente
            hinted_results = None
            try:
                doc_hint = self._extract_doc_pages_hint(question)
                if doc_hint:
                    forced = []
                    pages = doc_hint.get('pages') or []
                    for pg in pages[:6]:
                        try:
                            forced.extend(self._search_in_specific_doc(doc_hint['doc'], page=pg, top_k=min(max(3, top_k//max(1,len(pages))), 10)))
                        except Exception:
                            continue
                    if forced:
                        seen = set()
                        merged = []
                        for r in forced + (results or []):
                            key = (r.get('metadata',{}).get('source',''), r.get('metadata',{}).get('page',0), (r.get('text','') or '')[:120])
                            if key in seen:
                                continue
                            seen.add(key)
                            merged.append(r)
                        hinted_results = merged
                        console.print(f"[dim]Hint aplicado: {doc_hint['doc']} páginas {pages} (priorizando resultados de esas páginas)[/dim]")
            except Exception:
                pass
            
            answer = None
            # LLM-FIRST: Scoring de snippets por LLM + extracción JSON con FOCUS (solo no-detallado/no-agrupación/no-conceptual)
            # El FOCUS general se mantiene activo incluso en plain_prompts (no impone secciones fijas)
            if (
                self.flags.get('mode_llm_first', False)
                and (not is_detailed)
                and (not is_aggregation)
                and (not is_conceptual)
            ):
                try:
                    attribute = None
                    try:
                        attribute = self.conceptual_map._extract_attribute(question)
                    except Exception:
                        attribute = None
                    base_results = hinted_results or results or []
                    ordered = list(base_results)
                    # Reordenar por scoring del propio LLM
                    try:
                        import time as _t
                        _t0_sc = _t.time()
                        snippets = self._collect_snippets_for_llm_scoring(base_results, entities or [], top_n=min(12, len(base_results)))
                        order_idx = self._llm_score_snippets(snippets, question, attribute, entities or [])
                        _t_sc = _t.time() - _t0_sc
                        if order_idx:
                            ordered = [base_results[i] for i in order_idx if 0 <= i < len(base_results)]
                            console.print(f"[dim]LLM scoring aplicado: top {min(5,len(order_idx))} snippets priorizados ({_t_sc:.1f}s)[/dim]")
                    except Exception as e:
                        console.print(f"[dim yellow]LLM scoring no disponible: {e}[/dim yellow]")
                    # Construir contexto 'focus-first' a partir del orden LLM
                    try:
                        context = self._build_context_from_results(ordered[:8])
                    except Exception:
                        pass
                    # Construir FOCUS prompt e inyectarlo en conv_context
                    try:
                        focus = self._build_focus_prompt(question, attribute, entities or [], length_mode)
                        conv_context = (focus + "\n" + (conv_context or "")).strip()
                        console.print(f"[dim cyan]FOCUS aplicado: {attribute or 'default'}[/dim cyan]")
                    except Exception:
                        pass
                    # Extracción JSON final
                    try:
                        _t0_ex = _t.time()
                        extr = self._llm_extract_json(context or '', question, focus if 'focus' in locals() else '')
                        _t_ex = _t.time() - _t0_ex
                        if isinstance(extr, dict) and extr.get('attribute_aligned') and extr.get('citations'):
                            answer = self._format_from_json(extr)
                            console.print(f"[dim]LLM-first extracción JSON completada ({_t_ex:.1f}s)\n[/dim]")
                            # Auto-revisión desactivada por defecto (causa contradicciones en Qwen3)
                            try:
                                if self.config.get('enable_self_review', False) and isinstance(length_mode, str) and length_mode.strip().lower() == 'short' and (not is_procedural):
                                    answer = self._self_review_answer(question, answer, context or '')
                            except Exception:
                                pass
                    except Exception as e:
                        console.print(f"[dim yellow]Extracción JSON falló: {e}[/dim yellow]")
                except Exception:
                    pass
            if (not answer) and isinstance(length_mode, str) and length_mode.strip().lower() == 'short' and (not is_procedural):
                try:
                    # Ruta determinística para conteos específicos
                    if self.flags.get('enable_deterministic_count', False) and self._is_specific_count_query(question):
                        det = self._try_deterministic_count_answer(question, hinted_results or results, entities or [], length_mode)
                        if det:
                            answer = det
                    # Fast snippet path si aún no respondió
                    if not answer and self.config.get('enable_fast_snippet', True):
                        fast = self._try_fast_snippet_answer(question, hinted_results or results, entities or [], length_mode)
                        if fast:
                            answer = fast
                except Exception:
                    pass
            if not answer:
                # Inyección de FOCUS detallado deshabilitada por defecto (evita secciones tipo "Cantidad de WTG")
                try:
                    if is_detailed and (not self.flags.get('disable_structured_sections', True)):
                        try:
                            focus_det = self._build_detailed_focus_prompt(question, entities or [], length_mode)
                            conv_context = (focus_det + "\n" + (conv_context or "")).strip()
                            console.print(f"[dim cyan]FOCUS (detallado) aplicado[/dim cyan]")
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    if callable(docs_callback):
                        _docs = []
                        for src in (results or [])[:5]:
                            md = src.get('metadata', {}) or {}
                            _name = md.get('source', 'Unknown')
                            try:
                                if _name != 'Unknown':
                                    _name = Path(_name).name
                            except Exception:
                                pass
                            _page = md.get('page', 1)
                            _score = src.get('final_score', src.get('rerank_score', src.get('hybrid_score', 0)))
                            try:
                                _score = round(float(_score), 2)
                            except Exception:
                                pass
                        try:
                            docs_callback(_docs)
                        except Exception:
                            pass
                except Exception:
                    pass
                # Gate de evidencia y llamada al LLM (OPTIMIZADO FASE 2 + C)
                if not answer:
                    try:
                        # Contar resultados de calidad usando CUALQUIER score disponible
                        def get_quality_score(r):
                            return r.get('final_score', 0) or r.get('rerank_score', 0) or r.get('hybrid_score', 0) * 0.5
                        
                        quality_results = len([r for r in (results or []) if get_quality_score(r) > 0.15])
                        has_substantial_context = len(context or '') > 2000
                        
                        # Detectar si es consulta de razonamiento (requiere conocimiento del LLM)
                        reasoning_keywords = [
                            'imagina', 'diseña', 'analiza por qué', 'razona', 'explica por qué',
                            'comparativa entre', 'diferencias entre', 'coincide', 'evolucionará',
                            'implicaciones tendría', 'determinarías', 'resolución de ambigüedad',
                            'si todos los', 'si una empresa', 'si una persona',
                            'qué es', 'que es', 'certificacion', 'certificación', 'framework',
                            'nse', 'cissp', 'ceh', 'oscp', 'comptia', 'giac', 'ccna', 'ccnp'
                        ]
                        is_reasoning_query = any(kw in question.lower() for kw in reasoning_keywords)
                        
                        # Si hay suficientes documentos relevantes, permitir respuesta aunque la entidad no aparezca literal
                        if 'entities' in locals() and entities and not self._has_entity_evidence(entities, results or [], context or ''):
                            if quality_results >= 5:
                                # Suficientes documentos de calidad -> permitir respuesta conceptual
                                console.print(f"[dim]Gate relajado: entidad no exacta pero {quality_results} docs relevantes[/dim]")
                            elif quality_results >= 3:
                                # Caso borde -> dejar que el LLM decida
                                console.print(f"[dim]Gate: {quality_results} docs relevantes, dejando que LLM evalúe[/dim]")
                            else:
                                # FASE C: Consulta de razonamiento con pocos docs -> habilitar conocimiento general
                                if is_reasoning_query and has_substantial_context:
                                    console.print(f"[dim]Gate: razonamiento detectado, pocos docs ({quality_results}), pero contexto sustancial -> permitir con [Conocimiento general][/dim]")
                                    # Inyectar instruccion al contexto para que el LLM use conocimiento general
                                    context = f"[INSTRUCCION DEL SISTEMA] Los documentos proporcionan contexto parcial. Para completar la respuesta, USA conocimiento general del dominio ciberseguridad/IT marcado con prefijo '[Conocimiento general]' segun las reglas establecidas.\n\n{context}"
                                elif is_reasoning_query and quality_results >= 1:
                                    # FASE C: Razonamiento con al menos 1 doc -> permitir hibrido
                                    console.print(f"[dim]Gate: razonamiento con {quality_results} docs -> habilitar modo hibrido[/dim]")
                                    context = f"[INSTRUCCION DEL SISTEMA] Usa los documentos como base. Si es necesario complementar, usa '[Conocimiento general]' marcado claramente.\n\n{context}"
                                else:
                                    # Pocos resultados y no es razonamiento -> aplicar gate
                                    console.print(f"[yellow]Gate de evidencia: solo {quality_results} docs de calidad, entidad no encontrada[/yellow]")
                                    if has_substantial_context:
                                        console.print("[dim]Gate: contexto sustancial presente, permitiendo respuesta[/dim]")
                                    else:
                                        answer = "No se encontró información suficiente en los documentos para esa consulta."
                    except Exception as e:
                        console.print(f"[dim]Gate no aplicado: {e}[/dim]")
                if not answer:
                    try:
                        answer = self.generate_with_ollama(
                            query=question,
                            context=context or '',
                            conv_context=conv_context or '',
                            detailed=is_detailed,
                            is_aggregation=is_aggregation,
                            num_centrales=0,
                            is_conceptual=is_conceptual,
                            is_procedural=is_procedural,
                            is_direct_comparison=locals().get('is_direct_comparison', False),
                            is_simple_numeric=locals().get('is_simple_numeric', False),
                            is_troubleshooting=locals().get('is_troubleshooting', False),
                            is_summary=locals().get('is_summary', False),
                            length_mode=length_mode,
                            stream=bool(stream),
                            token_callback=token_callback,
                            cancel_checker=cancel_checker
                        )
                        console.print(f"[dim]Respuesta recibida del LLM: {len(answer or '')} chars[/dim]")
                    except Exception as e:
                        console.print(f"[yellow]Fallo al invocar LLM: {e}[/yellow]")
        # Fallback cuando no hay LLM o la respuesta es vacía
        if not answer or not str(answer).strip():
            answer = self._synthesize_fallback_answer(question, results, is_aggregation, is_conceptual, is_procedural)
            used_fallback = True
            # Aplicar postproceso también al fallback para limpiar artefactos
            try:
                if self.flags.get('enable_postprocess', True):
                    answer = self._postprocess_answer(question, answer, context)
            except Exception:
                pass
        
        _elapsed = time.time() - _t0
        try:
            top_docs = [{
                'source': r.get('metadata', {}).get('source', ''),
                'page': r.get('metadata', {}).get('page', 0),
                'score': float(r.get('final_score', r.get('hybrid_score', 0)))
            } for r in (results[:3] if results else [])]
            approx_ctx_tokens = int(len(context) / 4) if context else 0
            approx_prompt_tokens = approx_ctx_tokens + int(len(question) / 4)
            log_event('rag_query', {
                'latency_s': round(_elapsed, 3),
                'approx_ctx_tokens': approx_ctx_tokens,
                'approx_prompt_tokens': approx_prompt_tokens,
                'top_docs': top_docs
            })
        except Exception:
            pass
        
        # Actualizar entidades del último turno para continuidad conversacional
        try:
            if 'entities' in locals() and entities:
                self.last_entities = list(entities)
        except Exception:
            pass
        # Decrementar TTL de fuentes pegajosas
        try:
            sticky = getattr(self, '_sticky_sources', None)
            if sticky and int(sticky.get('ttl', 0)) > 0:
                sticky['ttl'] = int(sticky['ttl']) - 1
                if sticky['ttl'] <= 0:
                    try:
                        delattr(self, '_sticky_sources')
                    except Exception:
                        pass
                else:
                    setattr(self, '_sticky_sources', sticky)
        except Exception:
            pass
        
        sources, _timing_breakdown = self._post_query_learning(
            question, answer, results, entities, use_llm, context, _t0, memory_results)

        return {
            'question': question,
            'results': results,
            'context': context,
            'answer': answer,
            'sources': sources,
            'method': 'hybrid_with_memory',
            'memory_hits': len(memory_results),
            'time': time.time() - _t0,
            'timing_breakdown': _timing_breakdown,
        }


    def _classify_query(self, question, length_mode, top_k):
        is_conceptual = self._is_conceptual_question(question)
        is_procedural = self._is_procedural_question(question)
        is_count_query = self._is_specific_count_query(question)
        is_comparison = self._is_comparison_query(question)
        is_aggregation = self._is_aggregation_query(question)
        is_direct_comparison = self._is_direct_comparison_query(question)
        is_simple_numeric = self._is_simple_numeric_query(question)
        is_troubleshooting = self._is_troubleshooting_query(question)
        is_summary = any(k in question.lower() for k in ["resumen", "resume", "sintesis", "sintesis"])
        is_detailed = self._detect_detailed_query(question)
        if is_detailed:
            console.print(f"[bold green]Modo detallado detectado - respuesta extensa[/bold green]")
        if isinstance(length_mode, str):
            lm = length_mode.strip().lower()
            if lm == "long":
                is_detailed = True
            elif lm == "short":
                if not is_detailed:
                    is_detailed = False
        if is_detailed and (isinstance(length_mode, str) and length_mode.strip().lower() == "short"):
            console.print(f"[yellow]Override: consulta detallada detectada en modo corto - forzando respuesta larga[/yellow]")
            length_mode = "long"
        try:
            is_listing_ctx = self._is_listing_query(question)
        except Exception:
            is_listing_ctx = False
        try:
            if is_listing_ctx or ("listado completo" in question.lower()):
                top_k = max(top_k, 50)
                console.print(f"[dim]Listado detectado - elevando top_k a {top_k}[/dim]")
        except Exception:
            pass
        if is_conceptual:
            console.print(f"[dim]Pregunta CONCEPTUAL/GENERAL detectada - busqueda amplia[/dim]")
        return {
            "is_conceptual": is_conceptual, "is_procedural": is_procedural,
            "is_count_query": is_count_query,
            "is_comparison": is_comparison, "is_aggregation": is_aggregation,
            "is_direct_comparison": is_direct_comparison, "is_simple_numeric": is_simple_numeric,
            "is_troubleshooting": is_troubleshooting, "is_summary": is_summary,
            "is_detailed": is_detailed, "is_listing_ctx": is_listing_ctx,
            "length_mode": length_mode, "top_k": top_k,
        }

    def _extract_and_clean_entities(self, question, entity_filter, is_conceptual, contextual_entities):
        entities = self._extract_entities(question) if entity_filter and not is_conceptual else []
        # LIMPIEZA Y PRIORIZACI\u00d3N de entidades
        try:
            if entities:
                # 1. Eliminar duplicados preservando orden
                seen = set()
                unique_entities = []
                for e in entities:
                    e_norm = e.lower().strip()
                    if e_norm not in seen:
                        seen.add(e_norm)
                        unique_entities.append(e)
                entities = unique_entities
                    
                # 2. Priorizar entidades compuestas (nombres de centrales) sobre simples
                # Separar en compuestas (2+ palabras) y simples
                compound = [e for e in entities if len(e.split()) >= 2]
                simple = [e for e in entities if len(e.split()) < 2]
                    
                # 3. Si hay compuestas, filtrar simples que son substrings de compuestas
                if compound:
                    filtered_simple = []
                    for s in simple:
                        # Mantener solo si NO es substring de ninguna compuesta
                        if not any(s in c for c in compound):
                            filtered_simple.append(s)
                    simple = filtered_simple
                    
                # 4. Reordenar: compuestas primero (m\u00e1s largas primero), luego simples
                compound_sorted = sorted(compound, key=len, reverse=True)
                simple_sorted = sorted(simple, key=len, reverse=True)
                entities = compound_sorted + simple_sorted
                    
                # 5. Limitar a top 3 entidades m\u00e1s relevantes para evitar ruido
                if len(entities) > 3:
                    entities = entities[:3]
        except Exception:
            pass
        # DETECCI\u00d3N DE AN\u00c1FORAS: "este parque", "esa central", "el mismo", etc.
        # Si la consulta tiene referencias anaf\u00f3ricas sin nombre espec\u00edfico, reusar entidad del turno anterior
        try:
            ql_check = question.lower()
            anaphora_patterns = [
                'este parque', 'ese parque', 'el parque', 'la central', 'esta central', 'esa central',
                'este proyecto', 'ese proyecto', 'esta planta', 'esa planta', 'el mismo', 'la misma',
                'lo mismo', 'dicho parque', 'dicha central', 'mencionado', 'anterior'
            ]
            has_anaphora = any(pat in ql_check for pat in anaphora_patterns)
                
            # Si tiene an\u00e1fora y no hay entidad espec\u00edfica detectada, reusar entidad previa
            if has_anaphora and (not entities or all(len(e.split()) == 1 for e in entities)):
                prev_ents = getattr(self, 'last_entities', [])
                if prev_ents:
                    entities = list(prev_ents)
                    console.print(f"[cyan]Referencia anafórica detectada - usando entidad previa: {', '.join(entities)}[/cyan]")
        except Exception:
            pass
            
        # Podar entidades d\u00e9biles/gen\u00e9ricas (ej.: 'en total', 'parque', 'solar', 'potencia', 'oeste')
        try:
            weak_tokens = {
                'en','total','parque','solar','fotovoltaico','fotovoltaica','potencia','mw','kw','de','del','la','el','los','las','oeste','este','norte','sur','central'
            }
            def _is_weak_entity(ent: str) -> bool:
                toks = [t for t in ent.lower().split() if t]
                return len(toks) > 0 and all((t in weak_tokens or len(t) <= 2) for t in toks)
            if entities:
                entities = [e for e in entities if not _is_weak_entity(e)]
                # Si todas eran d\u00e9biles y quedaron 0, intentamos reusar entidad previa del turno anterior
                if not entities:
                    prev_ents = getattr(self, 'last_entities', [])
                    if prev_ents:
                        entities = list(prev_ents)
                        console.print(f"[dim]Entidades d\u00e9biles detectadas - usando entidad previa: {', '.join(entities)}[/dim]")
        except Exception:
            pass
            
        # Si se enriqueció la query con contexto, usar las entidades contextuales
        if contextual_entities and not entities:
            entities = contextual_entities
            console.print(f"[dim]Usando entidades del contexto: {', '.join(entities)}[/dim]")
        return entities

    def _post_query_learning(self, question, answer, results, entities, use_llm, context, _t0, memory_results):
        # APRENDIZAJE AUTOMÁTICO: Detectar fallo-recuperación
        # Si la consulta anterior falló ("no se encontró") pero esta tuvo éxito, aprender
        try:
            if use_llm and answer and entities and self.config.get('use_conceptual_map', True):
                # Verificar si esta respuesta es exitosa
                is_success = 'no se encontr' not in answer.lower() and 'lo siento' not in answer.lower()
                
                if is_success and results:
                    # Obtener las últimas 2 consultas del historial
                    history = self.conversation.get_recent_messages(n=4)  # user, assistant, user, assistant
                    
                    if len(history) >= 3:
                        # history[-3] = consulta anterior del usuario
                        # history[-2] = respuesta anterior del asistente
                        # history[-1] = consulta actual (ya agregada)
                        prev_query = history[-3].get('content', '') if len(history) >= 3 else ''
                        prev_answer = history[-2].get('content', '') if len(history) >= 2 else ''
                        
                        # Detectar si la consulta anterior falló
                        prev_failed = ('no se encontr' in prev_answer.lower() or 
                                      'lo siento' in prev_answer.lower()[:100])
                        
                        if prev_failed and prev_query:
                            # Extraer entidades de la consulta fallida
                            prev_entities = self._extract_entities(prev_query)
                            
                            # Aprender de la recuperación
                            top_source = results[0] if results else {}
                            src = top_source.get('metadata', {}).get('source', 'Unknown')
                            pg = top_source.get('metadata', {}).get('page', 0)
                            
                            self.conceptual_map.learn_from_failure_recovery(
                                failed_query=prev_query,
                                failed_entities=prev_entities,
                                success_query=question,
                                success_entities=entities,
                                answer=answer,
                                source=src,
                                page=pg
                            )
        except Exception as e:
            console.print(f"[dim yellow]No se pudo aprender de fallo-recuperación: {e}[/dim yellow]")
        
        # APRENDER del resultado si hay alta confianza
        try:
            if use_llm and answer and entities and self.config.get('use_conceptual_map', True):
                # Solo aprender si la respuesta es corta, concreta y tiene fuente clara
                if len(answer) < 300 and results and 'no se encontr' not in answer.lower():
                    # Extraer atributo de la pregunta
                    attribute = self.conceptual_map._extract_attribute(question)
                    if attribute:
                        # Tomar la mejor fuente
                        top_source = results[0] if results else {}
                        src = top_source.get('metadata', {}).get('source', 'Unknown')
                        pg = top_source.get('metadata', {}).get('page', 0)
                        score = top_source.get('final_score', 0)
                        
                        # Confianza basada en score y longitud de respuesta
                        confidence = min(0.95, max(0.5, score * 0.8 + (1 - len(answer)/300) * 0.2))
                        
                        # Encolar para validación/aprendizaje diferido SOLO si hay evidencia numérica ligada a la entidad
                        entity_canonical = entities[0]
                        try:
                            evidence = None
                            for r in results:
                                txt = (r.get('text', '') or '')
                                src_r = (r.get('metadata', {}) or {}).get('source', '')
                                blob = (txt + ' ' + src_r).lower()
                                if entity_canonical.lower() in blob and any(ch.isdigit() for ch in txt):
                                    if any(k in txt.lower() for k in ['aerogenerador', 'aerogeneradores', 'wtg', 'turbina', 'turbinas', 'unidades', 'panel', 'paneles', 'módulo', 'modulo']):
                                        evidence = txt[:1200]
                                        break
                            if evidence and self._has_numeric_evidence(entity_canonical, results):
                                # Guardar solo si la respuesta no es un error/timeout del sistema
                                _ans_low = (answer or '').lower()
                                if any(tok in _ans_low for tok in ['error:', 'error', 'timeout', 'sin evidencia', 'no hay evidencia', 'no se pudo']):
                                    console.print("[dim yellow]ADVERTENCIA No se encola aprendizaje: respuesta contiene error/timeout del sistema[/dim yellow]")
                                elif self.enable_auto_learning and self.learning_queue:
                                    self.learning_queue.add_candidate(
                                        entity=entity_canonical,
                                        attribute=attribute,
                                        answer=answer,
                                        question=question,
                                        source=src,
                                        page=pg,
                                        confidence=confidence,
                                        evidence_text=evidence
                                    )
                            else:
                                console.print("[dim yellow]ADVERTENCIA No se encola aprendizaje: sin evidencia numérica vinculada a la entidad[/dim yellow]")
                        except Exception as _e:
                            console.print(f"[dim yellow]No se pudo encolar candidato: {_e}")
        except Exception as e:
            console.print(f"[dim yellow]No se pudo aprender: {e}[/dim yellow]")
        
        # Extraer fuentes únicas de los resultados
        sources = []
        try:
            seen_sources = set()
            for r in results:
                src = r.get('metadata', {}).get('source', '')
                if src and src not in seen_sources:
                    sources.append(src)
                    seen_sources.add(src)
        except Exception:
            pass
        
        # Recolectar breakdown de timers propagados por hybrid_search y _rerank_results
        _timing_breakdown = {}
        try:
            if results:
                hs_t = results[0].pop('_hs_timing', None)
                if hs_t:
                    _timing_breakdown.update(hs_t)
                rr_t = results[0].pop('_t_rerank_ms', None)
                if rr_t is not None:
                    _timing_breakdown['t_rerank_ms'] = rr_t
            _total_ms = round((time.time() - _t0) * 1000, 1)
            _timing_breakdown['t_total_ms'] = _total_ms
            _llm_ms = _timing_breakdown.get('_t_llm_ms')
            if _llm_ms is None:
                # Estimar: total - retrieval conocido
                _retrieval_known = sum(
                    _timing_breakdown.get(k, 0)
                    for k in ('t_embed_ms', 't_semantic_ms', 't_bm25_ms', 't_fusion_ms', 't_rerank_ms')
                )
                _timing_breakdown['t_llm_estimated_ms'] = round(_total_ms - _retrieval_known, 1)
        except Exception:
            pass
        return sources, _timing_breakdown








    def _build_structured_context(self, results: list, max_chars: int = 6000) -> str:
        """Delegado a ContextBuilder.build_structured_context()."""
        return self._ctx_builder.build_structured_context(results, max_chars)

    def _build_context_from_results(self, results: list) -> str:
        """Delegado a ContextBuilder.build_context_from_results()."""
        return self._ctx_builder.build_context_from_results(results)

    def _collect_snippets_for_llm_scoring(self, results: list, entities: list, top_n: int = 12) -> list:
        """Delegado a ContextBuilder.collect_snippets_for_llm_scoring()."""
        return self._ctx_builder.collect_snippets_for_llm_scoring(results, entities, top_n)

    def _build_focus_prompt(self, question: str, attribute: str, entities: list, length_mode: str) -> str:
        """Delegado a ContextBuilder.build_focus_prompt()."""
        return self._ctx_builder.build_focus_prompt(question, attribute, entities, length_mode)

    def _build_detailed_focus_prompt(self, question: str, entities: list, length_mode: str) -> str:
        """Delegado a ContextBuilder.build_detailed_focus_prompt()."""
        return self._ctx_builder.build_detailed_focus_prompt(question, entities, length_mode)

    def _llm_score_snippets(self, snippets: list, question: str, attribute: str, entities: list) -> list:
        """Delegado a ContextBuilder.llm_score_snippets()."""
        return self._ctx_builder.llm_score_snippets(snippets, question, attribute, entities)

    def _llm_extract_json(self, context: str, question: str, focus_block: str) -> dict:
        """Delegado a ContextBuilder.llm_extract_json()."""
        return self._ctx_builder.llm_extract_json(context, question, focus_block)

    def _format_from_json(self, data: dict) -> str:
        """Delegado a ContextBuilder.format_from_json()."""
        return self._ctx_builder.format_from_json(data)

    def display_result(self, result: dict, show_details: bool = True):
        """Muestra resultado"""
        
        console.print(Panel.fit(
            f"[bold cyan]Pregunta:[/bold cyan] {result['question']}",
            border_style="cyan"
        ))
        
        if result['answer']:
            console.print(f"\n[bold green]🤖 Respuesta:[/bold green]\n")
            console.print(result['answer'])
        
        if show_details:
            console.print(f"\n[bold yellow]📊 Top-5 Fragmentos (scores híbridos):[/bold yellow]")
            
            for i, r in enumerate(result['results'][:5], 1):
                source = r['metadata']['source'][:50]
                page = r['metadata']['page']
                h_score = r['hybrid_score']
                s_score = r['semantic_score']
                k_score = r['keyword_score']
                
                console.print(f"\n[bold]{i}. {source} (pág. {page})[/bold]")
                console.print(f"   Híbrido: {h_score:.3f} | Semántico: {s_score:.3f} | Keyword: {k_score:.3f}")
                
                # Preview
                preview = r['text'][:200].replace('\n', ' ')
                console.print(f"   [dim]{preview}...[/dim]")
        
        console.print("\n" + "─" * 80)
    
    def interactive_mode(self):
        """Modo interactivo"""
        console.print(Panel.fit(
            "[bold green]SISTEMA RAG HÍBRIDO[/bold green]\n"
            "Búsqueda Semántica + Keyword + Llama3\n\n"
            "Comandos:\n"
            "  - Escribe tu pregunta\n"
            "  - 'detalles': Toggle mostrar detalles\n"
            "  - 'salir': Terminar",
            border_style="green"
        ))
        
        show_details = True
        
        while True:
            try:
                question = input("\n💬 Tu pregunta: ").strip()
                
                if question.lower() in ['salir', 'exit', 'quit']:
                    console.print("\n[bold cyan]👋 Hasta luego![/bold cyan]")
                    break
                
                if question.lower() == 'detalles':
                    show_details = not show_details
                    console.print(f"[yellow]Mostrar detalles: {'activado' if show_details else 'desactivado'}[/yellow]")
                    continue
                
                if not question:
                    continue
                
                result = self.query(question)
                self.display_result(result, show_details=show_details)
                
            except KeyboardInterrupt:
                console.print("\n\n[bold cyan]👋 Hasta luego![/bold cyan]")
                break
            except Exception as e:
                console.print(f"\n[bold red]ERROR: Error: {e}[/bold red]")
                import traceback
                traceback.print_exc()


def test_hybrid_rag():
    """Test con pregunta de Loma Blanca 3"""
    console.print(Panel.fit(
        "[bold cyan]🧪 TEST: RAG Híbrido[/bold cyan]\n"
        "Pregunta: ¿Cuántos aerogeneradores tiene Loma Blanca 3?",
        border_style="cyan"
    ))
    
    rag = HybridRAG()
    
    # Test question
    question = "¿Cuántos aerogeneradores tiene Loma Blanca 3?"
    
    # Probar diferentes balances
    for semantic_weight in [0.3, 0.5, 0.7]:
        console.print(f"\n[bold yellow]═══ Balance: Semántica {semantic_weight*100:.0f}% / Keyword {(1-semantic_weight)*100:.0f}% ═══[/bold yellow]")
        
        result = rag.query(question, top_k=25, semantic_weight=semantic_weight, use_llm=False)
        
        # Verificar si encontró el chunk correcto
        found_correct = False
        position = None
        
        for i, r in enumerate(result['results'], 1):
            text_lower = r['text'].lower()
            if "loma blanca" in text_lower and ("iii" in text_lower or " 3" in text_lower):
                if "16" in r['text'] or "diez y seis" in text_lower:
                    found_correct = True
                    position = i
                    console.print(f"[bold green]OK: Chunk correcto encontrado en posición #{position}[/bold green]")
                    console.print(f"   Score híbrido: {r['hybrid_score']:.3f}")
                    console.print(f"   Score semántico: {r['semantic_score']:.3f}")
                    console.print(f"   Score keyword: {r['keyword_score']:.3f}")
                    break
        
        if not found_correct:
            console.print(f"[red]ERROR: Chunk correcto NO en top-25[/red]")
    
    # Generar respuesta con el mejor balance
    console.print(f"\n[bold cyan]═══ Generando Respuesta Final ═══[/bold cyan]")
    result = rag.query(question, top_k=30, semantic_weight=0.5)
    rag.display_result(result, show_details=True)
    
    # Validar
    console.print(f"\n[bold cyan]📊 Validación:[/bold cyan]")
    if result['answer']:
        answer_lower = result['answer'].lower()
        if '16' in result['answer'] or 'dieciséis' in answer_lower or 'diez y seis' in answer_lower:
            console.print("[bold green]✅ CORRECTO: Respuesta contiene 16 aerogeneradores[/bold green]")
        else:
            console.print("[bold yellow]PARCIAL: Respuesta generada pero sin el numero exacto[/bold yellow]")
            console.print(f"[dim]Respuesta: {result['answer'][:200]}...[/dim]")
    else:
        console.print("[yellow]Sin LLM activo[/yellow]")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_hybrid_rag()
    else:
        try:
            rag = HybridRAG()
            rag.interactive_mode()
        except Exception as e:
            console.print(f"\n[bold red]ERROR: ERROR: {e}[/bold red]")
            import traceback
            traceback.print_exc()
            sys.exit(1)
