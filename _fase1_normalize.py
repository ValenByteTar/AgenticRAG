# -*- coding: utf-8 -*-
"""
FASE 1.3 - Verificar output de _normalize_query para las queries fallidas.
No requiere cargar el pipeline completo, solo EquivalencesManager.
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

QUERIES = {
    1: "Que es el NIST Cybersecurity Framework?",
    6: "Que hace el comando chmod en Linux?",
    9: "Que es SQL injection?",
    10: "Que es cross-site scripting (XSS)?",
    12: "Que es information security governance segun CISM?",
    17: "Que es el modelo de responsabilidad compartida en la nube?",
    18: "Que es la Zero Trust Architecture segun NIST?",
    23: "Cuales son las principales vulnerabilidades web segun OWASP y como se mencionan en las guias de pentest disponibles?",
    41: "Que es un framework de seguridad?",
    42: "Como me preparo para la certificacion?",
    45: "Como audito el sistema?",
    46: "Que es un agente?",
    49: "Que es la nube?",
    50: "Estoy preparando una auditoria, que necesito?",
    59: "Como se protege una infraestructura critica segun los marcos de ciberseguridad disponibles en el corpus?",
    66: "Que es la seguridad en OT/ICS?",
    68: "Que es la ingenieria social segun los documentos disponibles?",
    75: "Describe como implementar Zero Trust desde cero en una organizacion: principios, herramientas, fases de madurez y casos de uso mencionados en los documentos disponibles.",
}


def main():
    from equivalences_manager import EquivalencesManager
    from rag_hybrid import EQUIVALENCES_EMBEDDED_TEXT

    mgr = EquivalencesManager(EQUIVALENCES_EMBEDDED_TEXT, flags={})
    print(f"Equivalencias cargadas: {len(mgr.equivalences)} grupos\n")
    print("=" * 90)
    print("FASE 1.3: output de _normalize_query (delega a EquivalencesManager.normalize_query)")
    print("=" * 90)

    for qid, q in QUERIES.items():
        try:
            normalized = mgr.normalize_query(q)
        except Exception as e:
            normalized = f"ERROR: {e}"
        altered = "SI" if normalized.strip().lower() != q.strip().lower() else "NO"
        print(f"\n[ID {qid}] altered={altered}")
        print(f"  input:  '{q}'")
        print(f"  output: '{normalized}'")

    print("\n" + "=" * 90)
    print("FASE 4.BIS pre-check: expand() (que se usa para glosario/contexto adicional)")
    print("=" * 90)
    for qid, q in list(QUERIES.items())[:6]:
        try:
            expanded = mgr.expand(q)
        except Exception as e:
            expanded = f"ERROR: {e}"
        print(f"\n[ID {qid}] expand():")
        print(f"  '{expanded[:200]}'")


if __name__ == "__main__":
    main()
