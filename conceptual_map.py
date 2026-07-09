"""
Sistema de Mapa Conceptual para RAG
Permite al sistema "aprender" atajos de consultas frecuentes y hechos verificados
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple
from rich.console import Console

console = Console()


class ConceptualMap:
    """
    Mapa conceptual que almacena:
    - Hechos verificados por entidad (ej: "VMRS tiene 12 inversores")
    - Atajos de consultas frecuentes
    - Relaciones entre entidades y atributos
    """
    
    def __init__(self, map_path: str = "data/conceptual_map.json"):
        self.map_path = Path(map_path)
        self.map_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Estructura del mapa
        self.entity_facts = {}  # {entity: {attribute: {answer, source, confidence, ...}}}
        self.query_shortcuts = {}  # {query_normalized: entity.attribute}
        self.entity_aliases = {}  # {alias: canonical_entity}
        
        # Cargar mapa existente
        self._load()
    
    def _load(self):
        """Carga mapa desde disco"""
        try:
            if self.map_path.exists():
                with open(self.map_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.entity_facts = data.get('entity_facts', {})
                    self.query_shortcuts = data.get('query_shortcuts', {})
                    self.entity_aliases = data.get('entity_aliases', {})
                    console.print(f"[dim]Mapa conceptual cargado: {len(self.entity_facts)} entidades, {len(self.query_shortcuts)} atajos[/dim]")
        except Exception as e:
            console.print(f"[yellow]No se pudo cargar mapa conceptual: {e}[/yellow]")
    
    def _save(self):
        """Guarda mapa en disco"""
        try:
            data = {
                'entity_facts': self.entity_facts,
                'query_shortcuts': self.query_shortcuts,
                'entity_aliases': self.entity_aliases,
                'last_updated': datetime.now().isoformat()
            }
            with open(self.map_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            console.print(f"[yellow]No se pudo guardar mapa conceptual: {e}[/yellow]")
    
    def _normalize_query(self, query: str) -> str:
        """Normaliza query para matching"""
        import re
        q = query.lower().strip()
        # Remover signos de interrogación, acentos, etc.
        q = re.sub(r'[¿?¡!]', '', q)
        q = re.sub(r'\s+', ' ', q)
        return q.strip()
    
    def _normalize_entity(self, entity: str) -> str:
        """Normaliza nombre de entidad"""
        entity_lower = entity.lower().strip()
        # Buscar en aliases
        if entity_lower in self.entity_aliases:
            return self.entity_aliases[entity_lower]
        return entity_lower
    
    def _extract_attribute(self, query: str) -> Optional[str]:
        """Extrae el atributo que se pregunta (inversores, potencia, etc.)"""
        query_lower = query.lower()
        
        # Patrones de atributos comunes para ciberseguridad
        patterns = {
            'controles': ['control', 'controles', 'requisito', 'requisitos', 'dominio'],
            'version': ['versión', 'version', 'release', 'actualización', 'actualizacion'],
            'severidad': ['severidad', 'cvss', 'puntuación', 'puntuacion', 'score'],
            'cve': ['cve', 'vulnerabilidad', 'vulnerabilidades', 'exploit'],
            'framework': ['framework', 'estandar', 'estándar', 'norf', 'iso', 'nist'],
            'vendor': ['fortinet', 'cisco', 'microsoft', 'comptia', 'giac', 'offensive', 'palo alto', 'crowdstrike', 'vendor', 'fabricante'],
            'certificacion': ['certificación', 'certificacion', 'certified', 'cissp', 'ceh', 'oscp', 'nse', 'ccna', 'ccnp'],
            'incidente': ['incidente', 'respuesta', 'contención', 'contencion', 'erradicación', 'erradicacion', 'forense'],
            'tecnologia': ['tecnología', 'tecnologia', 'tipo', 'herramienta', 'tool', 'producto'],
            'fecha': ['cuando', 'cuándo', 'fecha', 'año', 'publicado', 'actualizado']
        }
        # Caso especial: si pregunta por severidad y menciona CVE, sin intención de conteo → 'severidad'
        try:
            has_sev = any(k in query_lower for k in patterns['severidad'])
            has_cve = any(k in query_lower for k in patterns['cve'])
            has_count = any(k in query_lower for k in ['cuantos', 'cuántos', 'cantidad', 'número', 'numero', 'how many'])
            if has_sev and has_cve and not has_count:
                return 'severidad'
        except Exception:
            pass
        # Búsqueda normal por patrones
        for attr, keywords in patterns.items():
            for kw in keywords:
                if kw in query_lower:
                    return attr
        
        return None
    
    def query_shortcut(self, query: str, entities: list) -> Optional[Dict]:
        """
        Intenta responder usando atajos del mapa conceptual
        
        Returns:
            Dict con {answer, source, page, confidence} si existe atajo
            None si no hay atajo
        """
        if not entities:
            return None
        
        # Normalizar query
        query_norm = self._normalize_query(query)
        
        # 1. Buscar atajo directo de query
        if query_norm in self.query_shortcuts:
            shortcut_path = self.query_shortcuts[query_norm]
            entity_key, attr = shortcut_path.split('.', 1) if '.' in shortcut_path else (shortcut_path, None)
            
            if entity_key in self.entity_facts and attr and attr in self.entity_facts[entity_key]:
                fact = self.entity_facts[entity_key][attr]
                console.print(f"[green]✓ Atajo encontrado: {shortcut_path}[/green]")
                return fact
        
        # 2. Buscar por entidad + atributo
        entity = self._normalize_entity(entities[0])
        attribute = self._extract_attribute(query)
        
        if entity in self.entity_facts and attribute and attribute in self.entity_facts[entity]:
            fact = self.entity_facts[entity][attribute]
            console.print(f"[green]✓ Conocimiento previo: {entity}.{attribute}[/green]")
            return fact
        
        return None
    
    def learn_fact(self, entity: str, attribute: str, answer: str, source: str, page: int = 0, confidence: float = 0.9):
        """
        Aprende un nuevo hecho verificado
        
        Args:
            entity: Nombre de la entidad (ej: "NIST CSF")
            attribute: Atributo (ej: "controles", "version")
            answer: Respuesta verificada (ej: "108 controles de seguridad")
            source: Fuente del dato
            page: Página del documento
            confidence: Confianza en el dato (0-1)
        """
        entity_norm = self._normalize_entity(entity)
        
        # Crear estructura si no existe
        if entity_norm not in self.entity_facts:
            self.entity_facts[entity_norm] = {}
        
        # Guardar hecho
        self.entity_facts[entity_norm][attribute] = {
            'answer': answer,
            'source': source,
            'page': page,
            'confidence': confidence,
            'last_verified': datetime.now().isoformat()
        }
        
        console.print(f"[dim cyan]📚 Aprendido: {entity_norm}.{attribute} = {answer[:50]}...[/dim cyan]")
        
        # Guardar en disco
        self._save()
    
    def add_query_shortcut(self, query: str, entity: str, attribute: str):
        """Añade un atajo de query a entidad.atributo"""
        query_norm = self._normalize_query(query)
        entity_norm = self._normalize_entity(entity)
        shortcut_path = f"{entity_norm}.{attribute}"
        
        self.query_shortcuts[query_norm] = shortcut_path
        self._save()
    
    def add_entity_alias(self, alias: str, canonical: str):
        """Añade un alias de entidad (ej: VMRS -> Villa María del Río Seco)"""
        alias_norm = alias.lower().strip()
        canonical_norm = canonical.lower().strip()
        
        if alias_norm != canonical_norm:
            self.entity_aliases[alias_norm] = canonical_norm
            console.print(f"[dim]Alias añadido: {alias} -> {canonical}[/dim]")
            self._save()
    
    def remove_fact(self, entity: str, attribute: str) -> bool:
        """Elimina un hecho específico entity.attribute del mapa conceptual."""
        try:
            entity_norm = self._normalize_entity(entity)
            if entity_norm in self.entity_facts and attribute in self.entity_facts[entity_norm]:
                del self.entity_facts[entity_norm][attribute]
                # Limpiar entidad si queda vacía
                if not self.entity_facts[entity_norm]:
                    del self.entity_facts[entity_norm]
                # Limpiar atajos que apunten a este hecho
                to_delete = []
                for q, path in self.query_shortcuts.items():
                    if path == f"{entity_norm}.{attribute}":
                        to_delete.append(q)
                for q in to_delete:
                    del self.query_shortcuts[q]
                self._save()
                console.print(f"[yellow]Hecho eliminado: {entity_norm}.{attribute}[/yellow]")
                return True
        except Exception as e:
            console.print(f"[dim yellow]No se pudo eliminar hecho: {e}[/dim yellow]")
        return False

    def remove_entity(self, entity: str) -> bool:
        """Elimina completamente una entidad del mapa conceptual (hechos y atajos)."""
        try:
            entity_norm = self._normalize_entity(entity)
            removed = False
            if entity_norm in self.entity_facts:
                del self.entity_facts[entity_norm]
                removed = True
            # Eliminar atajos ligados a la entidad
            to_delete = []
            for q, path in self.query_shortcuts.items():
                if path.startswith(f"{entity_norm}."):
                    to_delete.append(q)
            for q in to_delete:
                del self.query_shortcuts[q]
            if removed or to_delete:
                self._save()
                console.print(f"[yellow]Entidad eliminada del mapa: {entity_norm}[/yellow]")
                return True
        except Exception as e:
            console.print(f"[dim yellow]No se pudo eliminar entidad: {e}[/dim yellow]")
        return False
    def get_entity_facts(self, entity: str) -> Dict:
        """Obtiene todos los hechos conocidos de una entidad"""
        entity_norm = self._normalize_entity(entity)
        return self.entity_facts.get(entity_norm, {})
    
    def clear_low_confidence_facts(self, min_confidence: float = 0.7):
        """Limpia hechos con baja confianza"""
        removed = 0
        for entity in list(self.entity_facts.keys()):
            for attr in list(self.entity_facts[entity].keys()):
                if self.entity_facts[entity][attr].get('confidence', 1.0) < min_confidence:
                    del self.entity_facts[entity][attr]
                    removed += 1
            # Limpiar entidades vacías
            if not self.entity_facts[entity]:
                del self.entity_facts[entity]
        
        if removed > 0:
            console.print(f"[dim]Limpiados {removed} hechos de baja confianza[/dim]")
            self._save()
    
    def learn_from_failure_recovery(self, failed_query: str, failed_entities: list, 
                                     success_query: str, success_entities: list, 
                                     answer: str, source: str, page: int = 0):
        """
        Aprende automáticamente cuando una consulta falla pero luego se recupera.
        
        Ejemplo:
        - Consulta 1: "VMRS" -> No encontró (falló)
        - Consulta 2: "Villa María del Río Seco" -> SÍ encontró (éxito)
        
        El sistema aprende que "VMRS" es un alias válido y crea atajos.
        
        Args:
            failed_query: Query que falló
            failed_entities: Entidades detectadas en la query fallida
            success_query: Query que tuvo éxito
            success_entities: Entidades detectadas en la query exitosa
            answer: Respuesta exitosa
            source: Fuente del dato
            page: Página del documento
        """
        try:
            # 1. Aprender alias si las entidades son diferentes pero relacionadas (similaridad por tokens)
            if failed_entities and success_entities:
                failed_entity = failed_entities[0].lower().strip()
                success_entity = success_entities[0].lower().strip()
                if failed_entity and success_entity and failed_entity != success_entity:
                    def _tokset(s: str):
                        import re
                        return {t for t in re.split(r"[^a-záéíóúñ0-9]+", s.lower()) if t and len(t) > 2}
                    fset = _tokset(failed_entity)
                    sset = _tokset(success_entity)
                    overlap = len(fset & sset)
                    base = max(1, min(len(fset), len(sset)))
                    similar = overlap / base >= 0.5 or (overlap >= 1 and (failed_entity in success_entity or success_entity in failed_entity))
                    if similar:
                        self.add_entity_alias(failed_entity, success_entity)
                        console.print(f"[green]🎓 Aprendizaje automático: '{failed_entity}' -> '{success_entity}'[/green]")
                    else:
                        console.print(f"[dim yellow]Alias omitido (baja similitud): '{failed_entity}' vs '{success_entity}'[/dim yellow]")
            
            # 2. Extraer atributo común de ambas queries
            attribute = self._extract_attribute(failed_query) or self._extract_attribute(success_query)
            
            if attribute and success_entities:
                # Evitar aprender 'tecnologia' con respuesta que parece solo MW
                import re
                if attribute == 'tecnologia' and re.search(r"\b\d+(?:[\.,]\d+)?\s*mw\b", (answer or '').lower()):
                    console.print("[dim yellow]Aprendizaje omitido: 'tecnologia' con valor MW no es un hecho válido[/dim yellow]")
                    return
                # 3. Aprender el hecho con alta confianza
                entity_canonical = success_entities[0]
                self.learn_fact(
                    entity=entity_canonical,
                    attribute=attribute,
                    answer=answer[:200],  # Limitar longitud
                    source=source,
                    page=page,
                    confidence=0.95  # Alta confianza porque fue verificado
                )
                
                # 4. Crear atajo para la query fallida (ahora funcionará)
                self.add_query_shortcut(failed_query, entity_canonical, attribute)
                console.print(f"[green]🎓 Atajo creado: '{failed_query}' ahora funcionará directamente[/green]")
        
        except Exception as e:
            console.print(f"[dim yellow]No se pudo aprender de la recuperación: {e}[/dim yellow]")
    
    def stats(self) -> Dict:
        """Estadísticas del mapa conceptual"""
        total_facts = sum(len(facts) for facts in self.entity_facts.values())
        return {
            'entities': len(self.entity_facts),
            'total_facts': total_facts,
            'query_shortcuts': len(self.query_shortcuts),
            'aliases': len(self.entity_aliases)
        }
