"""
Sistema de Memoria Incremental para RAG
Permite al usuario corregir y agregar información que se guarda para futuras consultas
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


class MemorySystem:
    """Sistema de memoria para aprendizaje incremental"""
    
    def __init__(self, db_path: str = "memory.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Inicializa base de datos SQLite"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tabla de correcciones/información adicional
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                source TEXT DEFAULT 'user_input',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                category TEXT,
                keywords TEXT
            )
        """)
        
        # NOTA: conversation_history se maneja en memoria via ConversationHistory class
        # No se persiste en DB para mejor performance
        
        # Tabla de sinónimos/equivalencias
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS term_synonyms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_term TEXT NOT NULL,
                synonym TEXT NOT NULL,
                category TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(canonical_term, synonym)
            )
        """)
        
        # Índices para búsqueda rápida
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_keywords 
            ON user_knowledge(keywords)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_synonyms 
            ON term_synonyms(synonym)
        """)
        
        conn.commit()
        conn.close()
    
    def add_knowledge(self, question: str, answer: str, 
                     category: str = None, keywords: List[str] = None) -> int:
        """
        Agrega nueva información a la memoria
        
        Args:
            question: Pregunta o tema
            answer: Respuesta o información
            category: Categoría (opcional)
            keywords: Lista de palabras clave
        
        Returns:
            ID del registro creado
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        keywords_str = json.dumps(keywords) if keywords else None
        
        cursor.execute("""
            INSERT INTO user_knowledge (question, answer, category, keywords)
            VALUES (?, ?, ?, ?)
        """, (question, answer, category, keywords_str))
        
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return record_id
    
    def search_memory(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Busca en la memoria del usuario
        
        Args:
            query: Consulta de búsqueda
            limit: Número máximo de resultados
        
        Returns:
            Lista de coincidencias
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Búsqueda simple por contenido (FTS sería mejor pero más complejo)
        query_lower = query.lower()
        
        cursor.execute("""
            SELECT id, question, answer, category, keywords, timestamp
            FROM user_knowledge
            WHERE LOWER(question) LIKE ? 
               OR LOWER(answer) LIKE ?
               OR LOWER(keywords) LIKE ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (f"%{query_lower}%", f"%{query_lower}%", f"%{query_lower}%", limit))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row[0],
                'question': row[1],
                'answer': row[2],
                'category': row[3],
                'keywords': json.loads(row[4]) if row[4] else [],
                'timestamp': row[5],
                'source': 'user_memory'
            })
        
        conn.close()
        return results
    
    def get_all_knowledge(self, limit: int = 50) -> List[Dict]:
        """Obtiene toda la memoria del usuario"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, question, answer, category, timestamp
            FROM user_knowledge
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row[0],
                'question': row[1],
                'answer': row[2],
                'category': row[3],
                'timestamp': row[4]
            })
        
        conn.close()
        return results
    
    def delete_knowledge(self, record_id: int) -> bool:
        """Elimina un registro de memoria"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM user_knowledge WHERE id = ?", (record_id,))
        deleted = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        return deleted
    
    def get_stats(self) -> Dict:
        """Obtiene estadísticas de la memoria"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM user_knowledge")
        total_records = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT category, COUNT(*) 
            FROM user_knowledge 
            WHERE category IS NOT NULL
            GROUP BY category
        """)
        categories = dict(cursor.fetchall())
        
        cursor.execute("SELECT COUNT(*) FROM term_synonyms")
        total_synonyms = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_records': total_records,
            'categories': categories,
            'total_synonyms': total_synonyms,
            'db_path': self.db_path
        }
    
    def add_synonyms(self, canonical_term: str, synonyms: List[str], category: str = None) -> int:
        """
        Agrega sinónimos para un término canónico
        
        Args:
            canonical_term: Término principal/canónico
            synonyms: Lista de sinónimos
            category: Categoría opcional (ej: 'equipos', 'tecnologías')
        
        Returns:
            Número de sinónimos agregados
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        added = 0
        canonical_lower = canonical_term.lower().strip()
        
        for synonym in synonyms:
            synonym_lower = synonym.lower().strip()
            if synonym_lower == canonical_lower:
                continue  # No agregar término como sinónimo de sí mismo
            
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO term_synonyms (canonical_term, synonym, category)
                    VALUES (?, ?, ?)
                """, (canonical_lower, synonym_lower, category))
                
                if cursor.rowcount > 0:
                    added += 1
            except sqlite3.IntegrityError:
                pass  # Ya existe
        
        conn.commit()
        conn.close()
        
        return added
    
    def get_synonyms(self, term: str) -> List[str]:
        """
        Obtiene todos los sinónimos de un término (expansión bidireccional)
        
        Args:
            term: Término a expandir
        
        Returns:
            Lista de sinónimos (incluyendo el término original y su canónico)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        term_lower = term.lower().strip()
        synonyms = set([term_lower])
        
        # Buscar si el término ES un sinónimo (obtener canónico y otros sinónimos)
        cursor.execute("""
            SELECT canonical_term FROM term_synonyms WHERE synonym = ?
        """, (term_lower,))
        
        canonical = cursor.fetchone()
        if canonical:
            canonical_term = canonical[0]
            synonyms.add(canonical_term)
            
            # Obtener todos los otros sinónimos del canónico
            cursor.execute("""
                SELECT synonym FROM term_synonyms WHERE canonical_term = ?
            """, (canonical_term,))
            
            for row in cursor.fetchall():
                synonyms.add(row[0])
        else:
            # Buscar si el término ES canónico (obtener todos sus sinónimos)
            cursor.execute("""
                SELECT synonym FROM term_synonyms WHERE canonical_term = ?
            """, (term_lower,))
            
            for row in cursor.fetchall():
                synonyms.add(row[0])
        
        conn.close()
        return list(synonyms)
    
    def get_all_synonyms(self) -> Dict[str, List[str]]:
        """Obtiene todos los sinónimos organizados por término canónico"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT canonical_term, GROUP_CONCAT(synonym, ', ')
            FROM term_synonyms
            GROUP BY canonical_term
        """)
        
        result = {}
        for row in cursor.fetchall():
            canonical = row[0]
            synonyms = row[1].split(', ') if row[1] else []
            result[canonical] = synonyms
        
        conn.close()
        return result


class ConversationHistory:
    """Maneja el historial de conversación para contexto"""
    
    def __init__(self, max_history: int = 10):
        self.max_history = max_history
        self.current_session = []
    
    def add_message(self, role: str, content: str):
        """Agrega mensaje al historial (user/assistant)"""
        self.current_session.append({
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat()
        })
        
        # Mantener solo últimos N mensajes
        if len(self.current_session) > self.max_history * 2:
            self.current_session = self.current_session[-(self.max_history * 2):]
    
    def get_last_user_message(self) -> Optional[str]:
        """Obtiene el último mensaje del usuario"""
        for msg in reversed(self.current_session):
            if msg['role'] == 'user':
                return msg['content']
        return None
    
    def get_context(self, last_n: int = 3) -> str:
        """
        Obtiene contexto reciente para el LLM
        
        Args:
            last_n: Número de intercambios (user+assistant) a incluir
        
        Returns:
            Contexto formateado
        """
        # Tomar últimos N intercambios
        recent = self.current_session[-(last_n * 2):]
        
        if not recent:
            return ""
        
        context_lines = ["HISTORIAL DE CONVERSACIÓN RECIENTE:"]
        for msg in recent:
            role_name = "Usuario" if msg['role'] == 'user' else "Asistente"
            context_lines.append(f"{role_name}: {msg['content']}")
        
        return "\n".join(context_lines)
    
    def clear(self):
        """Limpia el historial"""
        self.current_session = []
    
    def get_last_assistant_message(self) -> Optional[str]:
        """Obtiene el último mensaje del asistente"""
        for msg in reversed(self.current_session):
            if msg['role'] == 'assistant':
                return msg['content']
        return None
    
    def get_recent_messages(self, n: int = 4) -> list:
        """
        Obtiene los últimos N mensajes del historial
        
        Args:
            n: Número de mensajes a obtener
        
        Returns:
            Lista de mensajes (dicts con 'role', 'content', 'timestamp')
        """
        return self.current_session[-n:] if self.current_session else []


def extract_keywords(text: str) -> List[str]:
    """Extrae palabras clave simples del texto"""
    import re
    
    # Limpiar y tokenizar
    words = re.findall(r'\b[A-ZÁÉÍÓÚÑa-záéíóúñ]{3,}\b', text)
    
    # Stopwords básicas
    stopwords = {
        'que', 'qué', 'los', 'las', 'una', 'uno', 'del', 'para', 
        'con', 'por', 'tiene', 'está', 'son', 'como', 'más'
    }
    
    keywords = [w.lower() for w in words if w.lower() not in stopwords]
    
    # Deduplicar manteniendo orden
    seen = set()
    unique_keywords = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique_keywords.append(kw)
    
    return unique_keywords[:10]  # Top 10 keywords


def parse_memory_command(query: str) -> Optional[Dict]:
    """
    Detecta y parsea comandos de memoria del usuario
    
    Soporta patrones como:
    - "Guarda en tu memoria que X es igual a Y"
    - "Recuerda que A es lo mismo que B y C"
    - "X = Y = Z"
    
    Returns:
        Dict con 'canonical' y 'synonyms' o None si no es un comando
    """
    import re
    
    query_lower = query.lower().strip()
    
    # Patrón 1: "guarda/recuerda que X es [igual a/lo mismo que] Y [e/y] Z"
    patterns = [
        r'(?:guarda|recuerda|aprende|memoriza).*?que\s+(.+?)\s+(?:es|son)\s+(?:igual|lo mismo|equivalente|sinónimo).*?(?:a|que)\s+(.+)',
        r'(?:guarda|recuerda|aprende).*?memoria.*?que\s+(.+?)\s+(?:es|son|=)\s+(.+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, query_lower, re.IGNORECASE)
        if match:
            left = match.group(1).strip()
            right = match.group(2).strip()
            
            # Separar por conectores (y, e, igual a, =, comas)
            all_terms = re.split(r'\s+(?:y|e|igual\s+a|lo\s+mismo\s+que)\s+|,\s*|=', f"{left}, {right}")
            all_terms = [t.strip().strip('"\'') for t in all_terms if t.strip()]
            
            if len(all_terms) >= 2:
                return {
                    'canonical': all_terms[0],
                    'synonyms': all_terms[1:],
                    'raw_query': query
                }
    
    # Patrón 2: Formato directo "X = Y = Z"
    if '=' in query and 'guarda' not in query_lower:
        terms = [t.strip().strip('"\'') for t in query.split('=') if t.strip()]
        if len(terms) >= 2:
            return {
                'canonical': terms[0],
                'synonyms': terms[1:],
                'raw_query': query
            }
    
    return None
