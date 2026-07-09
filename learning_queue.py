"""
Sistema de Cola de Aprendizaje Diferido con Validación Automática
Permite validar candidatos de aprendizaje en segundo plano sin bloquear consultas
"""

import json
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List
from rich.console import Console
import requests

console = Console()


class LearningCandidate:
    """Candidato para aprendizaje que requiere validación"""
    
    def __init__(self, entity: str, attribute: str, answer: str, 
                 question: str, source: str, page: int, confidence: float,
                 evidence_text: str = ""):
        self.entity = entity
        self.attribute = attribute
        self.answer = answer
        self.question = question
        self.source = source
        self.page = page
        self.confidence = confidence
        self.evidence_text = evidence_text or ""
        self.timestamp = datetime.now().isoformat()
        self.id = f"{entity}_{attribute}_{int(time.time())}"
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'entity': self.entity,
            'attribute': self.attribute,
            'answer': self.answer,
            'question': self.question,
            'source': self.source,
            'page': self.page,
            'confidence': self.confidence,
            'evidence_text': self.evidence_text,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict):
        candidate = cls(
            entity=data['entity'],
            attribute=data['attribute'],
            answer=data['answer'],
            question=data['question'],
            source=data['source'],
            page=data['page'],
            confidence=data['confidence'],
            evidence_text=data.get('evidence_text', "")
        )
        candidate.id = data['id']
        candidate.timestamp = data['timestamp']
        return candidate


class LearningQueue:
    """
    Cola de aprendizaje con validación en segundo plano
    
    Características:
    - No bloquea consultas del usuario
    - Valida candidatos cuando el sistema está idle
    - Usa lock para evitar conflictos con consultas activas
    """
    
    def __init__(self, queue_path: str = "data/learning_queue.json", 
                 ollama_url: str = "http://localhost:11434",
                 ollama_model: str = "granite-3.3-8b-instruct-q5km:latest",
                 conceptual_map = None):
        self.queue_path = Path(queue_path)
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self.conceptual_map = conceptual_map  # Referencia al mapa conceptual para verificar duplicados
        
        # Cola de candidatos pendientes
        self.pending_candidates: List[LearningCandidate] = []
        
        # Lock para sincronización
        self.query_lock = threading.Lock()  # Lock para consultas del usuario
        self.validation_lock = threading.Lock()  # Lock para validación
        
        # Estado
        self.is_validating = False
        self.is_query_active = False
        
        # Thread de validación
        self.validation_thread = None
        self.stop_validation = False
        
        # Notificaciones para la interfaz web
        self.current_notification = None  # {'status': 'learning'|'approved'|'rejected', 'entity': str, 'attribute': str, 'timestamp': float}
        self.notification_history = []  # Historial de últimas notificaciones
        
        # Cargar cola existente
        self._load_queue()
        
        # Iniciar thread de validación
        self._start_validation_thread()
    
    def _load_queue(self):
        """Carga cola desde disco"""
        try:
            if self.queue_path.exists():
                with open(self.queue_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.pending_candidates = [
                        LearningCandidate.from_dict(c) for c in data.get('pending', [])
                    ]
                    console.print(f"[dim]Cola de aprendizaje cargada: {len(self.pending_candidates)} candidatos[/dim]")
        except Exception as e:
            console.print(f"[yellow]No se pudo cargar cola de aprendizaje: {e}[/yellow]")
    
    def _save_queue(self):
        """Guarda cola en disco"""
        try:
            data = {
                'pending': [c.to_dict() for c in self.pending_candidates],
                'last_updated': datetime.now().isoformat()
            }
            with open(self.queue_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            console.print(f"[yellow]No se pudo guardar cola de aprendizaje: {e}[/yellow]")
    
    def add_candidate(self, entity: str, attribute: str, answer: str,
                     question: str, source: str, page: int = 0, 
                     confidence: float = 0.7, evidence_text: str = ""):
        """
        Agrega un candidato a la cola de validación
        
        Args:
            entity: Entidad (ej: "NIST CSF")
            attribute: Atributo (ej: "controles")
            answer: Respuesta a validar
            question: Pregunta original
            source: Fuente del documento
            page: Página del documento
            confidence: Confianza inicial
        """
        # Filtrar entidades genéricas
        generic_entities = ['framework', 'estandar', 'estándar', 'control', 'certificación', 'certificacion',
                           'herramienta', 'tool', 'software', 'vulnerabilidad', 'amenaza']
        if entity.lower() in generic_entities:
            console.print(f"[dim yellow]⚠ Candidato rechazado: entidad genérica '{entity}'[/dim yellow]")
            return
        
        # Filtrar respuestas muy largas (probablemente no son hechos concretos)
        if len(answer) > 300:
            console.print(f"[dim yellow]⚠ Candidato rechazado: respuesta muy larga ({len(answer)} chars)[/dim yellow]")
            return
        
        # Verificar si ya existe en el mapa conceptual (evitar duplicados)
        if self.conceptual_map:
            entity_norm = entity.lower().strip()
            if entity_norm in self.conceptual_map.entity_facts:
                if attribute in self.conceptual_map.entity_facts[entity_norm]:
                    console.print(f"[dim yellow]⚠ Candidato rechazado: ya existe {entity}.{attribute} en el mapa[/dim yellow]")
                    return
        
        # Verificar si ya está en la cola pendiente (evitar duplicados en cola)
        for candidate in self.pending_candidates:
            if candidate.entity.lower() == entity.lower() and candidate.attribute == attribute:
                console.print(f"[dim yellow]⚠ Candidato rechazado: ya está en cola {entity}.{attribute}[/dim yellow]")
                return
        
        # Crear candidato
        candidate = LearningCandidate(
            entity=entity,
            attribute=attribute,
            answer=answer,
            question=question,
            source=source,
            page=page,
            confidence=confidence,
            evidence_text=evidence_text or ""
        )
        
        # Agregar a cola
        self.pending_candidates.append(candidate)
        self._save_queue()
        
        # Notificar a la interfaz web
        self.current_notification = {
            'status': 'learning',
            'entity': entity,
            'attribute': attribute,
            'timestamp': time.time()
        }
        
        # Solo imprimir en consola (no en web)
        console.print(f"[dim cyan]📋 Candidato agregado a cola: {entity}.{attribute}[/dim cyan]")
    
    def _start_validation_thread(self):
        """Inicia thread de validación en segundo plano"""
        self.validation_thread = threading.Thread(target=self._validation_loop, daemon=True)
        self.validation_thread.start()
    
    def _validation_loop(self):
        """Loop de validación que corre en segundo plano"""
        while not self.stop_validation:
            try:
                # Esperar antes de validar
                time.sleep(180)  # Revisar cada 3 minutos (180 segundos)
                
                # Si hay candidatos pendientes y no hay query activa
                if self.pending_candidates and not self.is_query_active:
                    # Intentar adquirir lock de validación
                    if self.validation_lock.acquire(blocking=False):
                        try:
                            self.is_validating = True
                            self._validate_next_candidate()
                        finally:
                            self.is_validating = False
                            self.validation_lock.release()
            
            except Exception as e:
                console.print(f"[dim red]Error en validación: {e}[/dim red]")
                time.sleep(10)  # Esperar más si hay error
    
    def _validate_next_candidate(self):
        """Valida el siguiente candidato en la cola"""
        if not self.pending_candidates:
            return
        
        candidate = self.pending_candidates[0]
        
        console.print(f"[dim cyan]🔍 Validando: {candidate.entity}.{candidate.attribute}...[/dim cyan]")
        
        # Validar con LLM
        is_valid, reason = self._validate_with_llm(candidate)
        
        if is_valid:
            console.print(f"[green]✓ Candidato aprobado: {candidate.entity}.{candidate.attribute}[/green]")
            
            # Guardar en el mapa conceptual
            if self.conceptual_map:
                try:
                    self.conceptual_map.learn_fact(
                        entity=candidate.entity,
                        attribute=candidate.attribute,
                        answer=candidate.answer,
                        source=candidate.source,
                        page=candidate.page,
                        confidence=candidate.confidence
                    )
                    console.print(f"[green]📚 Guardado en mapa conceptual: {candidate.entity}.{candidate.attribute}[/green]")
                except Exception as e:
                    console.print(f"[red]Error guardando en mapa: {e}[/red]")
            
            # Notificar aprobación a la interfaz web
            self.current_notification = {
                'status': 'approved',
                'entity': candidate.entity,
                'attribute': candidate.attribute,
                'timestamp': time.time()
            }
            self.notification_history.append(self.current_notification.copy())
            
            # Remover de cola
            self.pending_candidates.pop(0)
            self._save_queue()
            # Retornar para que se aprenda
            return candidate
        else:
            console.print(f"[yellow]✗ Candidato rechazado: {reason}[/yellow]")
            
            # Notificar rechazo a la interfaz web
            self.current_notification = {
                'status': 'rejected',
                'entity': candidate.entity,
                'attribute': candidate.attribute,
                'reason': reason,
                'timestamp': time.time()
            }
            self.notification_history.append(self.current_notification.copy())
            
            # Remover de cola
            self.pending_candidates.pop(0)
            self._save_queue()
            return None
    
    def _validate_with_llm(self, candidate: LearningCandidate) -> tuple[bool, str]:
        """
        Valida un candidato usando el LLM
        
        Returns:
            (is_valid, reason)
        """
        try:
            # Reglas semánticas por atributo (filtros rápidos)
            ans_low = (candidate.answer or '').lower()
            attr = (candidate.attribute or '').lower()
            import re as _sem
            # 0) Rechazar 'tecnologia' si la respuesta es solo puntuación numérica sin mencionar tecnología
            if attr == 'tecnologia':
                if _sem.search(r"\b\d+(?:[\.,]\d+)?\b", ans_low) and not any(k in ans_low for k in ['firewall', 'siem', 'edr', 'xdr', 'ids', 'ips', 'nmap', 'metasploit', 'splunk', 'crowdstrike', 'fortinet', 'cisco', 'palo alto', 'tool', 'herramienta']):
                    return False, "'tecnologia' con solo número no es válido sin mencionar tecnología"
            # 1) 'controles' debe contener número y mención de controles/requisitos
            if attr == 'controles':
                if not _sem.search(r"\b\d+\b", ans_low) or not any(k in ans_low for k in ['control','requisito','dominio','categoria','category']):
                    return False, "'controles' sin número o sin tokens de controles/requisitos"
            # 2) 'version' debe contener número o versión explícita
            if attr == 'version':
                if not _sem.search(r"\b\d+(?:\.\d+)*\b", ans_low) or not any(k in ans_low for k in ['version','versión','release','v']):
                    return False, "'version' sin número de versión"
            # 3) 'severidad' debe contener CVSS o escala de severidad
            if attr == 'severidad':
                if not _sem.search(r"\b\d+(?:\.\d+)?\b", ans_low) or not any(k in ans_low for k in ['cvss','critical','alta','media','baja','critical','high','medium','low','sever']):
                    return False, "'severidad' sin valor CVSS/escala"
            # Rechazo temprano: respuestas de error del sistema o timeouts no son hechos válidos
            if any(tok in ans_low for tok in ['error:', 'error', 'timeout', 'sin evidencia', 'no hay evidencia', 'no se pudo']):
                return False, "Respuesta contiene error/timeout del sistema"

            # Chequeo local: si la respuesta contiene números, deben aparecer en la evidencia
            import re as _re
            numbers = _re.findall(r"\d+", candidate.answer or "")
            if numbers and candidate.evidence_text:
                ev_lower = (candidate.evidence_text or "").lower()
                if not all(any(n in ev_lower for n in numbers) for n in set(numbers)):
                    return False, "Los números de la respuesta no aparecen en la evidencia"

            # Prompt de validación LIGERO
            prompt = f"""Valida si esta información es correcta y específica usando SOLO la evidencia provista.

ENTIDAD: {candidate.entity}
ATRIBUTO: {candidate.attribute}
PREGUNTA: {candidate.question}
RESPUESTA: {candidate.answer}
FUENTE: {candidate.source} (página {candidate.page})

EVIDENCIA (fragmento del documento):
{(candidate.evidence_text or '')[:1200]}

CRITERIOS DE VALIDACIÓN:
1. ¿La respuesta es específica para la entidad "{candidate.entity}"? (no genérica)
2. Si la respuesta contiene NÚMEROS, esos números deben aparecer literalmente en la EVIDENCIA y estar asociados al atributo.
3. ¿La respuesta responde directamente la pregunta?

Responde SOLO con:
- "VÁLIDO" si cumple los 3 criterios
- "INVÁLIDO: [razón breve]" si no cumple

Respuesta:"""

            # Llamar a Ollama con timeout y tokens aumentados para hardware limitado
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 150,  # Más tokens para respuesta detallada
                        "num_gpu": 99,
                        "num_thread": 8
                    },
                    "keep_alive": "0s"
                },
                timeout=45  # Timeout de 45 segundos para hardware limitado
            )
            
            if response.status_code == 200:
                result = response.json()
                answer = result.get('response', '').strip().upper()
                
                if 'VÁLIDO' in answer or 'VALIDO' in answer:
                    return True, "Aprobado por LLM"
                else:
                    # Extraer razón
                    reason = answer.replace('INVÁLIDO:', '').replace('INVALIDO:', '').strip()
                    return False, reason if reason else "Rechazado por LLM"
            else:
                return False, f"Error en validación: {response.status_code}"
        
        except requests.Timeout:
            console.print(f"[yellow]⚠ Timeout en validación - reintentando más tarde[/yellow]")
            return False, "Timeout"
        except Exception as e:
            console.print(f"[yellow]⚠ Error en validación: {e}[/yellow]")
            return False, f"Error: {str(e)[:50]}"
    
    def mark_query_active(self):
        """Marca que hay una query activa (bloquea validación)"""
        self.is_query_active = True
    
    def mark_query_inactive(self):
        """Marca que la query terminó (permite validación)"""
        self.is_query_active = False
    
    def wait_for_validation(self, timeout: float = 30):
        """
        Espera a que termine la validación en curso (si hay alguna)
        
        Args:
            timeout: Tiempo máximo de espera en segundos
        """
        start_time = time.time()
        while self.is_validating:
            if time.time() - start_time > timeout:
                console.print(f"[yellow]⚠ Timeout esperando validación[/yellow]")
                break
            time.sleep(0.1)
    
    def get_validated_candidate(self) -> Optional[LearningCandidate]:
        """
        Obtiene el siguiente candidato validado (si hay alguno)
        
        Returns:
            LearningCandidate si hay uno validado, None si no
        """
        # Este método sería llamado periódicamente por el sistema principal
        # para aplicar los candidatos validados al mapa conceptual
        pass
    
    def get_stats(self) -> Dict:
        """Obtiene estadísticas de la cola"""
        return {
            'pending_candidates': len(self.pending_candidates),
            'is_validating': self.is_validating,
            'is_query_active': self.is_query_active
        }
    
    def get_notification(self) -> Optional[Dict]:
        """
        Obtiene la notificación actual para la interfaz web
        
        Returns:
            Dict con status, entity, attribute, timestamp
            None si no hay notificación o ya expiró
        """
        if self.current_notification:
            # Verificar si la notificación no ha expirado
            # - learning: no expira (hasta que se valide)
            # - approved/rejected: expira después de 60 segundos
            age = time.time() - self.current_notification['timestamp']
            
            if self.current_notification['status'] == 'learning':
                # No expira mientras esté en cola
                return self.current_notification
            elif age < 60:  # approved/rejected duran 60 segundos
                return self.current_notification
            else:
                # Limpiar notificación expirada
                self.current_notification = None
        return None
    
    def clear_notification(self):
        """Limpia la notificación actual"""
        self.current_notification = None
    
    def stop(self):
        """Detiene el thread de validación"""
        self.stop_validation = True
        if self.validation_thread:
            self.validation_thread.join(timeout=5)
