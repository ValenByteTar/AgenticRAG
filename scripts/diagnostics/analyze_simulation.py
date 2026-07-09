"""
Analizador de resultados de simulación (50 casos)
- Evalúa pertinencia, concisión y política de fuentes
- Genera un reporte con causas de FAIL accionables
"""

import json
import glob
import os
from datetime import datetime

RESULT_FIELDS = [
    "id", "query", "category", "answer_length", "passed", "reasons",
    "off_topic", "too_long", "source_policy_violations", "missing_sources"
]

# Palabras/temas que suelen ser ruido para consultas específicas
NOISE_TOPICS = [
    "objeto y alcance", "responsabilidades", "archivo-biblioteca", "publicidad de su aprobacion",
    "ingreso de nuevos usuarios", "procedimiento", "pt4", "pt11"
]

# Reglas por categoría
CATEGORY_RULES = {
    # Respuestas cortas, directas
    "numeric_query": {
        "max_len": 120,
        "ban_listado": True,
        "require_entities": False,
        "required_sources_contains": [],
    },
    "entity_variant": {
        "max_len": 220,
        "ban_listado": True,
        "require_entities": True,
        "required_sources_contains": ["anexo d - dqd"],
    },
    "equipment_model": {
        "max_len": 160,
        "ban_listado": True,
        "require_entities": True,
        "required_sources_contains": ["anexo d - dqd"],
    },
    "document_query": {
        "max_len": 1400,
        "ban_listado": False,
        "require_entities": False,
        "required_sources_contains": ["pt"],
    },
    "follow_up": {
        "max_len": 240,
        "ban_listado": True,
        "require_entities": False,
        "required_sources_contains": [],
    },
    "comparison": {
        "max_len": 800,
        "ban_listado": True,
        "require_entities": True,
        "required_sources_contains": ["anexo d"],
    },
    "listing": {
        "max_len": 1800,
        "ban_listado": False,
        "require_entities": False,
        "required_sources_contains": ["listado"],
    },
    "count": {
        "max_len": 240,
        "ban_listado": False,
        "require_entities": False,
        "required_sources_contains": ["listado"],
    },
    "location": {
        "max_len": 260,
        "ban_listado": True,
        "require_entities": True,
        "required_sources_contains": [],
    },
    "procedural": {
        "max_len": 1200,
        "ban_listado": True,
        "require_entities": False,
        "required_sources_contains": ["pt"],
    },
    "conceptual": {
        "max_len": 500,
        "ban_listado": True,
        "require_entities": False,
        "required_sources_contains": [],
    },
    "multi_document": {
        "max_len": 600,
        "ban_listado": True,
        "require_entities": False,
        "required_sources_contains": ["anexo d"],
    },
    "out_of_domain": {
        "max_len": 200,
        "ban_listado": True,
        "require_entities": False,
        "required_sources_contains": [],
    },
    "short_query": {
        "max_len": 200,
        "ban_listado": True,
        "require_entities": False,
        "required_sources_contains": [],
    },
    "detailed_query": {
        "max_len": 1600,
        "ban_listado": True,
        "require_entities": True,
        "required_sources_contains": ["anexo d"],
    },
    "tech_filter": {
        "max_len": 600,
        "ban_listado": False,
        "require_entities": False,
        "required_sources_contains": ["anexo d"],
    },
    "cells": {"max_len": 260, "ban_listado": True, "require_entities": True, "required_sources_contains": []},
    "substation": {"max_len": 260, "ban_listado": True, "require_entities": True, "required_sources_contains": []},
    "aggregation": {"max_len": 600, "ban_listado": False, "require_entities": False, "required_sources_contains": ["listado"]},
    "acronym": {"max_len": 240, "ban_listado": True, "require_entities": False, "required_sources_contains": []},
    "troubleshooting": {"max_len": 600, "ban_listado": True, "require_entities": False, "required_sources_contains": []},
}


def load_latest_results():
    files = sorted(glob.glob("simulation_results_*.json"))
    if not files:
        raise FileNotFoundError("No se encontraron archivos simulation_results_*.json")
    return files[-1]


def analyze(results_json_path):
    with open(results_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    results = data.get('results', [])

    summary = {
        'total': len(results),
        'passed': 0,
        'failed': 0,
        'by_category': {},
        'items': []
    }

    for r in results:
        q = r.get('query', '')
        cat = r.get('category', 'unknown')
        ans = r.get('answer', '')
        ans_len = int(r.get('answer_length', len(ans or '')))
        v = r.get('validation', {})
        passed = bool(v.get('passed', False))
        reasons = list(v.get('reasons', []))
        sources = r.get('sources', []) or []

        # Normalizar nombres de fuentes
        source_names = []
        for s in sources:
            name = s.get('name') or s.get('source') or ''
            name = name.lower()
            source_names.append(name)

        rules = CATEGORY_RULES.get(cat, CATEGORY_RULES['detailed_query'])

        # 1) Exceso de longitud
        too_long = ans_len > rules['max_len']
        if too_long and 'Respuesta muy corta' in reasons:
            reasons = [x for x in reasons if x != 'Respuesta muy corta']
        if too_long:
            reasons.append(f"Excede max_len({rules['max_len']})")

        # 2) Política de fuentes: Listado Centrales
        source_policy_violations = []
        if rules['ban_listado']:
            if any(('listado' in n and 'central' in n) for n in source_names):
                source_policy_violations.append('Listado Centrales incluido indebidamente')
        # 2b) Fuentes requeridas
        for req in rules['required_sources_contains']:
            if not any(req in n for n in source_names):
                source_policy_violations.append(f"Falta fuente requerida: {req}")

        # 3) Off-topic heurística
        ans_l = (ans or '').lower()
        off_topic = any(t in ans_l for t in NOISE_TOPICS) and cat in (
            'numeric_query','entity_variant','equipment_model','location','short_query'
        )
        if off_topic:
            reasons.append('Contenido fuera de foco para la categoría')

        # 4) Fuentes presentes
        missing_sources = len(source_names) == 0
        if missing_sources:
            reasons.append('Sin fuentes devueltas por API')

        # Consolidar
        is_ok = passed and not too_long and not source_policy_violations and not off_topic and not missing_sources

        item = {
            'id': r.get('id'),
            'query': q,
            'category': cat,
            'passed': is_ok,
            'reasons': reasons + source_policy_violations,
            'answer_length': ans_len,
            'off_topic': off_topic,
            'too_long': too_long,
            'source_policy_violations': source_policy_violations,
            'missing_sources': missing_sources,
            'sources': source_names[:5]
        }
        summary['items'].append(item)
        if is_ok:
            summary['passed'] += 1
        else:
            summary['failed'] += 1
        bc = summary['by_category'].setdefault(cat, {'total':0,'passed':0})
        bc['total'] += 1
        bc['passed'] += int(is_ok)

    # Guardar reporte
    out_path = f"analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # Imprimir resumen breve
    print(f"\nResumen: {summary['passed']}/{summary['total']} OK")
    print("Por categoría:")
    for cat, st in sorted(summary['by_category'].items()):
        rate = 100.0 * st['passed'] / max(1, st['total'])
        print(f"  - {cat:18s}: {st['passed']}/{st['total']} ({rate:.0f}%)")
    print(f"\nGuardado: {out_path}")
    return summary, out_path


if __name__ == '__main__':
    path = load_latest_results()
    print(f"Analizando: {path}")
    analyze(path)
