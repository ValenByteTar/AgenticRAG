"""
Historial de conversacion para contexto del LLM.
Extraido de memory_system.py (RES-009) — preservado por uso activo.
"""
from datetime import datetime
from typing import Optional


class ConversationHistory:
    """Maneja el historial de conversacion para contexto"""

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

        if len(self.current_session) > self.max_history * 2:
            self.current_session = self.current_session[-(self.max_history * 2):]

    def get_last_user_message(self) -> Optional[str]:
        """Obtiene el ultimo mensaje del usuario"""
        for msg in reversed(self.current_session):
            if msg['role'] == 'user':
                return msg['content']
        return None

    def get_context(self, last_n: int = 3) -> str:
        """Obtiene contexto reciente para el LLM"""
        recent = self.current_session[-(last_n * 2):]

        if not recent:
            return ""

        context_lines = ["HISTORIAL DE CONVERSACION RECIENTE:"]
        for msg in recent:
            role_name = "Usuario" if msg['role'] == 'user' else "Asistente"
            context_lines.append(f"{role_name}: {msg['content']}")

        return "\n".join(context_lines)

    def clear(self):
        """Limpia el historial"""
        self.current_session = []

    def get_last_assistant_message(self) -> Optional[str]:
        """Obtiene el ultimo mensaje del asistente"""
        for msg in reversed(self.current_session):
            if msg['role'] == 'assistant':
                return msg['content']
        return None

    def get_recent_messages(self, n: int = 4) -> list:
        """Obtiene los ultimos N mensajes del historial"""
        return self.current_session[-n:] if self.current_session else []
