"""
DocCards: clasificación de rol por documento + resúmenes breves
Permite al planner saber qué documentos son hubs (entity_list), perfiles (entity_profile),
procedimientos, manuales, etc., y filtrar/ponderar la recuperación por rol.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Any
try:
    import requests  # type: ignore
except Exception:
    requests = None  # fallback si no está instalado

DOC_ROLES_PATH = Path("data/doc_roles.json")
DOC_ROLES_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_doc_roles(path: Path | str = DOC_ROLES_PATH) -> Dict[str, Any]:
    try:
        p = Path(path)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def save_doc_roles(doc_roles: Dict[str, Any], path: Path | str = DOC_ROLES_PATH) -> None:
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc_roles, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _guess_role_by_name(name: str) -> str:
    n = name.lower()
    # Roles para ciberseguridad
    if any(k in n for k in ["listado", "catalog", "inventory", "directory"]):
        if any(k in n for k in ["framework", "control", "iso", "nist", "pci", "hipaa"]):
            return "framework_list"
        if any(k in n for k in ["certificacion", "certification", "cissp", "ceh", "oscp"]):
            return "cert_list"
    if any(k in n for k in ["profile", "perfil", "standard"]):
        return "standard_profile"
    if any(k in n for k in ["proced", "procedimiento", "procedure", "protocolo", "instructivo", "instruct", "playbook", "runbook"]):
        return "procedure"
    if any(k in n for k in ["manual", "guide", "guia", "handbook"]):
        return "manual_reference"
    if any(k in n for k in ["soc", "operaciones", "operations", "incident response", "monitoring"]):
        return "security_ops"
    if any(k in n for k in ["analisis", "análisis", "reporte", "report", "assessment", "audit", "audit report"]):
        return "analysis_report"
    if any(k in n for k in ["threat", "amenaza", "intel", "intelligence", "ttp", "apt", "ioc"]):
        return "threat_intel"
    if any(k in n for k in ["policy", "politica", "compliance", "normativa", "regulatory"]):
        return "policy_compliance"
    return "other"


def _extract_basic_entities(text: str) -> List[str]:
    # Heurística para entidades de ciberseguridad: frameworks, certificaciones, empresas
    ents = set()
    try:
        # Frameworks y estándares: ISO 27001, NIST CSF, PCI-DSS, etc.
        for m in re.findall(r"\b(?:ISO|NIST|PCI-DSS|PCI DSS|HIPAA|GDPR|SOX|COBIT|ITIL|CIS|MITRE)\s*(?:CSF|SP)?\s*[0-9]*[-]*[0-9]*[A-Z]*\b", text):
            ents.add(m.strip())
        # Certificaciones: CISSP, CEH, OSCP, CISM, CompTIA Security+, etc.
        for m in re.findall(r"\b(?:CISSP|CEH|OSCP|CISM|CISA|CRISC|CCSP|GSEC|GCIH|GPEN|GWAPT|CompTIA Security\+|AWS Certified Security|Azure Security Engineer|GCP Professional Cloud Security)\b", text, re.IGNORECASE):
            ents.add(m.strip())
        # Empresas/organizaciones de seguridad
        for m in re.findall(r"\b(?:CrowdStrike|Palo Alto|Fortinet|Check Point|Cisco Security|Symantec|McAfee|Kaspersky|Trend Micro|FireEye|Mandiant|Rapid7|Tenable|Qualys|Splunk|IBM Security|Microsoft Security|Google Chronicle|AWS GuardDuty|Azure Sentinel)\b", text):
            ents.add(m.strip())
        # Tipos de amenazas
        for m in re.findall(r"\b(?:ransomware|malware|phishing|spear phishing|APT|DDoS|SQL injection|XSS|zero-day|exploit|vulnerability|CVE-[0-9]{4}-[0-9]+)\b", text, re.IGNORECASE):
            ents.add(m.strip())
    except Exception:
        pass
    return list(ents)[:20]


def _infer_attributes_presence(text: str) -> List[str]:
    t = text.lower()
    attrs = []
    # Controles de seguridad
    if any(k in t for k in ["firewall", "firewalls", "ids", "ips", "siem", "soar", "edr", "xdr", "mfa", "2fa", "sso"]):
        attrs.append("security_controls")
    # Áreas de ciberseguridad
    if any(k in t for k in ["pentest", "penetration test", "vulnerability assessment", "scan", "assessment"]):
        attrs.append("assessment")
    if any(k in t for k in ["incident response", "incidente", "ir", "forensics", "forense", "investigation"]):
        attrs.append("incident_response")
    if any(k in t for k in ["risk management", "risk assessment", "gestion de riesgo", "riesgo"]):
        attrs.append("risk_management")
    if any(k in t for k in ["compliance", "normativa", "regulatory", "audit", "auditoria", "governance", "gobierno"]):
        attrs.append("compliance")
    if any(k in t for k in ["cloud security", "seguridad cloud", "aws", "azure", "gcp", "container security", "kubernetes", "devsecops"]):
        attrs.append("cloud_security")
    if any(k in t for k in ["cryptography", "criptografia", "encryption", "cifrado", "ssl", "tls", "pki"]):
        attrs.append("cryptography")
    if any(k in t for k in ["network security", "networking", "segmentation", "zero trust", "microsegmentation", "vlan", "vpn"]):
        attrs.append("network_security")
    if any(k in t for k in ["application security", "appsec", "owasp", "sast", "dast", "code review", "secure coding", "sdlc"]):
        attrs.append("application_security")
    if any(k in t for k in ["identity", "access management", "iam", "privileged access", "pam", "rbac", "abac", "entitlements"]):
        attrs.append("identity_access")
    return attrs


def _estimate_centrality(name: str, text: str) -> float:
    n = name.lower()
    t = text.lower()
    score = 0.0
    # Documentos con múltiples frameworks/estándares son hubs importantes
    if "framework" in n or "standard" in n or "catalog" in n:
        score += 0.6
    # Documentos que cubren múltiples controles o requisitos
    control_indicators = len(set(t.split()) & set([
        "control", "controles", "requirement", "requisito", "clause", "clausula",
        "policy", "politica", "procedure", "procedimiento", "guideline", "guia"
    ]))
    score += min(0.3, control_indicators * 0.05)
    # Referencias a múltiples certificaciones
    cert_count = len(re.findall(r"\b(?:ISO|NIST|CISSP|CEH|OSCP|CISM|CISA)\b", text))
    score += min(0.2, cert_count * 0.05)
    # Documentos completos o de referencia
    if any(k in n for k in ["complete", "comprehensive", "reference", "handbook", "manual", "guide", "master"]):
        score += 0.1
    return min(1.0, score)


def build_doc_cards(vector_store) -> Dict[str, Any]:
    """Construye tarjetas por documento usando heurísticas (sin depender del LLM).
    Si luego queremos subir calidad, se puede inyectar un LLM para summary/role.
    """
    try:
        data = vector_store.collection.get()
        metadatas = data.get("metadatas", [])
        documents = data.get("documents", [])
        sources_seen = {}
        for i, md in enumerate(metadatas):
            src = (md or {}).get("source", "Unknown")
            if src not in sources_seen:
                text = documents[i] if i < len(documents) else ""
                role = _guess_role_by_name(src)
                entities_idx = _extract_basic_entities(text)
                attributes_idx = _infer_attributes_presence(text)
                summary = text.strip().split("\n\n")[0][:400] if text else ""
                centrality = _estimate_centrality(src, text)
                sources_seen[src] = {
                    "name": Path(src).name,
                    "path": src,
                    "role": role,
                    "summary": summary,
                    "entities_index": entities_idx,
                    "attributes_index": attributes_idx,
                    "centrality": centrality,
                    "quality": 0.7
                }
        return {"docs": sources_seen}
    except Exception:
        return {"docs": {}}


def select_docs_by_roles(doc_roles: Dict[str, Any], preferred_roles: List[str], entities: List[str] | None = None, attribute: str | None = None, limit: int = 40) -> List[str]:
    docs = doc_roles.get("docs", {}) if isinstance(doc_roles, dict) else {}
    if not docs:
        return []
    # Orden por centralidad desc
    items = list(docs.items())
    items.sort(key=lambda kv: float(kv[1].get("centrality", 0.0)), reverse=True)
    selected = []
    entities = [e.lower() for e in (entities or [])]
    attribute_norm = (attribute or "").lower().strip()
    primary = []
    fallback = []
    for src, card in items:
        if preferred_roles and card.get("role") not in preferred_roles:
            continue
        if entities:
            src_l = src.lower()
            ent_hit = any(e in src_l for e in entities)
            if not ent_hit:
                ent_hit = any(any(e in (s or "").lower() for e in entities) for s in card.get("entities_index", []))
            if not ent_hit:
                continue
        if attribute_norm:
            attrs = [a.lower() for a in (card.get("attributes_index", []) or [])]
            if attribute_norm in attrs:
                primary.append(src)
            else:
                fallback.append(src)
            if len(primary) + len(fallback) >= limit:
                break
        else:
            selected.append(src)
            if len(selected) >= limit:
                break
    if attribute_norm:
        return (primary + fallback)[:limit]
    return selected


def _ollama_generate(model: str, prompt: str, timeout: int = 30, options: dict | None = None) -> str:
    """Generate text using Ollama with safety checks and timeout."""
    if requests is None:
        return ""
    # Evitar descargas: confirmar que el modelo existe en /api/tags
    try:
        available = _ollama_list_models(timeout=5)
        if model not in available:
            return ""
    except Exception:
        # Si no podemos listar modelos, no forzar descarga
        return ""
    try:
        # Reducir timeout para evitar hangs
        default_opts = {
            "num_predict": 200,
            "temperature": 0.2,
            "num_ctx": 2048,
            "num_gpu": 99,
        }
        if isinstance(options, dict):
            default_opts.update(options)
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": default_opts,
            "keep_alive": "10m",
        }
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json=payload,
            timeout=timeout,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("response", "")
    except requests.Timeout:
        # Timeout explícito para debugging
        pass
    except Exception:
        pass
    return ""


def _ollama_list_models(timeout: int = 10) -> list[str]:
    if requests is None:
        return []
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=timeout)
        if resp.status_code == 200:
            data = resp.json() or {}
            models = [m.get("name", "") for m in data.get("models", []) if isinstance(m, dict)]
            return [m for m in models if m]
    except Exception:
        pass
    return []


def _resolve_llm_model(model_name: str) -> str:
    # Si pide auto, intentar elegir la variante más grande de Llama 3.1 disponible
    mn = (model_name or "").strip().lower()
    if mn in ("auto", "llama3.1", "llama3.1:auto") or mn.endswith(":auto"):
        models = _ollama_list_models()
        # Preferencia por Llama 3.1; luego Llama 3
        candidates = [m for m in models if m.lower().startswith("llama3.1")]
        if not candidates:
            candidates = [m for m in models if m.lower().startswith("llama3")]
        # Parsear tamaños
        def size_of(name: str) -> float:
            nl = name.lower()
            # buscar sufijo :<size>
            import re
            m = re.search(r":(\d+)(b|m)\b", nl)
            if not m:
                return 0.0
            val = float(m.group(1))
            unit = m.group(2)
            return val if unit == 'b' else val / 1000.0
        if candidates:
            best = max(candidates, key=size_of)
            return best
        # Fallback razonable
        return "llama3.1:8b"
    return model_name


def build_doc_cards_llm(
    vector_store,
    model_name: str = "granite33-8b-q4",
    max_docs: int = 0,
    llm_max_calls: int = 0,
    llm_ratio: float = 0.0,
    llm_timeout: int = 12,
    sample_chars: int = 800,
) -> Dict[str, Any]:
    """Build DocCards using LLM with fallback to heuristics.
    - First compute heuristics for all unique documents (fast)
    - Then refine top-N with LLM according to budget (llm_max_calls or llm_ratio)
    """
    try:
        model_name = _resolve_llm_model(model_name)
        
        # Get data with safety limit to prevent memory issues
        data = vector_store.collection.get()
        metadatas = data.get("metadatas", [])
        documents = data.get("documents", [])
        
        total_chunks = len(metadatas)
        if total_chunks > 20000:
            print(f"[WARN] VectorStore tiene {total_chunks} chunks. Procesando solo primeros 20000.")
            metadatas = metadatas[:20000]
            documents = documents[:20000]
        
        # 1) Heurísticas por documento único
        sources_seen: Dict[str, Any] = {}
        processed = 0
        for i, md in enumerate(metadatas):
            if max_docs and len(sources_seen) >= max_docs:
                break
            src = (md or {}).get("source", "Unknown")
            if src in sources_seen:
                continue
            processed += 1
            if processed % 50 == 0:
                print(f"  Heurísticas: {processed} documentos únicos...")
            text = documents[i] if i < len(documents) else ""
            sample = text.strip().split("\n\n")[0][:sample_chars] if text else ""
            role = _guess_role_by_name(src)
            summary = sample[:400]
            entities_idx = _extract_basic_entities(sample)
            attributes_idx = _infer_attributes_presence(sample)
            centrality = _estimate_centrality(src, sample)
            quality = 0.75
            sources_seen[src] = {
                "name": Path(src).name,
                "path": src,
                "role": role,
                "summary": summary,
                "entities_index": entities_idx,
                "attributes_index": attributes_idx,
                "centrality": float(centrality),
                "quality": float(quality),
            }
        
        # 2) Refinamiento con LLM según presupuesto
        budget = 0
        if llm_max_calls and llm_max_calls > 0:
            budget = int(llm_max_calls)
        elif llm_ratio and llm_ratio > 0:
            budget = int(max(1, llm_ratio * len(sources_seen)))
        
        if budget <= 0:
            print(f"\n[INFO] Heurístico puro: {len(sources_seen)} documentos únicos (sin LLM)")
            return {"docs": sources_seen}
        
        # Ordenar por centralidad descendente y tomar top-K
        keys_sorted = sorted(sources_seen.keys(), key=lambda k: float(sources_seen[k].get("centrality", 0.0)), reverse=True)
        targets = keys_sorted[:budget]
        print(f"\n[INFO] Refinando con LLM los top {len(targets)} documentos (de {len(sources_seen)})")
        
        llm_calls = 0
        chunks_by_source: Dict[str, List[str]] = {}
        for i, md in enumerate(metadatas):
            src = (md or {}).get("source", "Unknown")
            if src in targets:
                arr = chunks_by_source.get(src)
                if arr is None:
                    arr = []
                    chunks_by_source[src] = arr
                if len(arr) < 5:
                    arr.append(documents[i] if i < len(documents) else "")
        for idx, src in enumerate(targets, start=1):
            card = sources_seen.get(src, {})
            texts = chunks_by_source.get(src, [])
            parts = []
            for t in texts:
                if not t:
                    continue
                p = [x for x in t.strip().split("\n\n") if x.strip()]
                if p:
                    parts.append(p[0])
            sample = ("\n\n".join(parts))[:sample_chars] if parts else ""
            try:
                prompt = (
                    "Clasifica y resume el siguiente documento. Devuelve JSON con las claves: "
                    "role, summary, entities_index, attributes_index, centrality, quality.\n"
                    "Roles válidos: entity_list, entity_profile, procedure, manual_scada, grid_ops, analysis_report, other.\n"
                    f"TEXTO:\n{sample}\n\nJSON:"
                )
                out = _ollama_generate(
                    model_name,
                    prompt,
                    timeout=max(8, llm_timeout),
                    options={"temperature": 0, "num_predict": 256, "num_ctx": 3072},
                )
                if out:
                    parsed = None
                    try:
                        parsed = json.loads(out)
                    except Exception:
                        try:
                            import re as _re
                            m = _re.search(r"\{[\s\S]*\}$", out)
                            if m:
                                parsed = json.loads(m.group(0))
                        except Exception:
                            parsed = None
                    if isinstance(parsed, dict):
                        role_llm = parsed.get("role")
                        if role_llm:
                            card["role"] = role_llm
                        summary_llm = parsed.get("summary")
                        if summary_llm:
                            card["summary"] = summary_llm
                        ents_llm = parsed.get("entities_index") if isinstance(parsed.get("entities_index"), list) else []
                        attrs_llm = parsed.get("attributes_index") if isinstance(parsed.get("attributes_index"), list) else []
                        ents_prev = card.get("entities_index", []) or []
                        attrs_prev = card.get("attributes_index", []) or []
                        if ents_llm or ents_prev:
                            merged_ents = []
                            seen = set()
                            for e in ents_prev + ents_llm:
                                s = (e or "").strip()
                                if s and s.lower() not in seen:
                                    seen.add(s.lower())
                                    merged_ents.append(s)
                            card["entities_index"] = merged_ents
                        if attrs_llm or attrs_prev:
                            merged_attrs = []
                            seen_a = set()
                            for a in attrs_prev + attrs_llm:
                                s = (a or "").strip()
                                if s and s.lower() not in seen_a:
                                    seen_a.add(s.lower())
                                    merged_attrs.append(s)
                            card["attributes_index"] = merged_attrs
                        c = parsed.get("centrality")
                        if isinstance(c, (int, float)):
                            prev_c = float(card.get("centrality", 0.0) or 0.0)
                            card["centrality"] = float((prev_c + float(c)) / 2.0)
                        q = parsed.get("quality")
                        if isinstance(q, (int, float)):
                            prev_q = float(card.get("quality", 0.0) or 0.0)
                            card["quality"] = float(max(prev_q, float(q)))
                        llm_calls += 1
            except Exception:
                pass
            if idx % 10 == 0:
                print(f"  LLM: {idx}/{len(targets)} refinados...")
        
        print(f"\n[INFO] Procesados {len(sources_seen)} documentos únicos (LLM llamadas: {llm_calls})")
        return {"docs": sources_seen}
    except Exception as e:
        print(f"[ERROR] build_doc_cards_llm falló: {e}")
        return {"docs": {}}

def build_doc_cards_llm_incremental(
    vector_store,
    existing: Dict[str, Any] | None = None,
    model_name: str = "granite33-8b-q4",
    max_docs: int = 0,
    llm_max_calls: int = 0,
    llm_ratio: float = 0.0,
    llm_timeout: int = 12,
    sample_chars: int = 800,
) -> Dict[str, Any]:
    """Construye DocCards SOLO para fuentes nuevas y las fusiona con las existentes.
    - Lee doc_roles existentes (si no se proveen, usa data/doc_roles.json)
    - Genera heurísticas para nuevas fuentes y refina con LLM según presupuesto
    - Devuelve el diccionario final fusionado {"docs": {...}}
    """
    try:
        base = existing if isinstance(existing, dict) else load_doc_roles()
        base_docs = (base or {}).get("docs", {})
        out_docs: Dict[str, Any] = dict(base_docs)
        data = vector_store.collection.get()
        metadatas = data.get("metadatas", [])
        documents = data.get("documents", [])
        new_sources: Dict[str, Any] = {}
        for i, md in enumerate(metadatas):
            src = (md or {}).get("source", "Unknown")
            if src in out_docs:
                continue
            if max_docs and len(new_sources) >= max_docs:
                break
            text = documents[i] if i < len(documents) else ""
            sample = text.strip().split("\n\n")[0][:sample_chars] if text else ""
            role = _guess_role_by_name(src)
            summary = sample[:400]
            entities_idx = _extract_basic_entities(sample)
            attributes_idx = _infer_attributes_presence(sample)
            centrality = _estimate_centrality(src, sample)
            quality = 0.75
            new_sources[src] = {
                "name": Path(src).name,
                "path": src,
                "role": role,
                "summary": summary,
                "entities_index": entities_idx,
                "attributes_index": attributes_idx,
                "centrality": float(centrality),
                "quality": float(quality),
            }
        if not new_sources:
            return {"docs": out_docs}
        model_name = _resolve_llm_model(model_name)
        budget = 0
        if llm_max_calls and llm_max_calls > 0:
            budget = int(llm_max_calls)
        elif llm_ratio and llm_ratio > 0:
            budget = int(max(1, llm_ratio * len(new_sources)))
        targets = []
        if budget > 0:
            keys_sorted = sorted(new_sources.keys(), key=lambda k: float(new_sources[k].get("centrality", 0.0)), reverse=True)
            targets = keys_sorted[:budget]
        # Recolectar hasta 5 chunks por fuente objetivo
        chunks_by_source: Dict[str, List[str]] = {}
        if targets:
            for i, md in enumerate(metadatas):
                src = (md or {}).get("source", "Unknown")
                if src in targets:
                    arr = chunks_by_source.get(src)
                    if arr is None:
                        arr = []
                        chunks_by_source[src] = arr
                    if len(arr) < 5:
                        arr.append(documents[i] if i < len(documents) else "")
            for src in targets:
                card = new_sources.get(src, {})
                texts = chunks_by_source.get(src, [])
                parts = []
                for t in texts:
                    if not t:
                        continue
                    p = [x for x in t.strip().split("\n\n") if x.strip()]
                    if p:
                        parts.append(p[0])
                sample = ("\n\n".join(parts))[:sample_chars] if parts else ""
                try:
                    prompt = (
                        "Clasifica y resume el siguiente documento. Devuelve JSON con las claves: "
                        "role, summary, entities_index, attributes_index, centrality, quality.\n"
                        "Roles válidos: entity_list, entity_profile, procedure, manual_scada, grid_ops, analysis_report, other.\n"
                        f"TEXTO:\n{sample}\n\nJSON:"
                    )
                    out = _ollama_generate(
                        model_name,
                        prompt,
                        timeout=max(8, llm_timeout),
                        options={"temperature": 0, "num_predict": 256, "num_ctx": 3072},
                    )
                    if out:
                        parsed = None
                        try:
                            parsed = json.loads(out)
                        except Exception:
                            try:
                                import re as _re
                                m = _re.search(r"\{[\s\S]*\}$", out)
                                if m:
                                    parsed = json.loads(m.group(0))
                            except Exception:
                                parsed = None
                        if isinstance(parsed, dict):
                            role_llm = parsed.get("role")
                            if role_llm:
                                card["role"] = role_llm
                            summary_llm = parsed.get("summary")
                            if summary_llm:
                                card["summary"] = summary_llm
                            ents_llm = parsed.get("entities_index") if isinstance(parsed.get("entities_index"), list) else []
                            attrs_llm = parsed.get("attributes_index") if isinstance(parsed.get("attributes_index"), list) else []
                            ents_prev = card.get("entities_index", []) or []
                            attrs_prev = card.get("attributes_index", []) or []
                            if ents_llm or ents_prev:
                                merged_ents = []
                                seen = set()
                                for e in ents_prev + ents_llm:
                                    s = (e or "").strip()
                                    if s and s.lower() not in seen:
                                        seen.add(s.lower())
                                        merged_ents.append(s)
                                card["entities_index"] = merged_ents
                            if attrs_llm or attrs_prev:
                                merged_attrs = []
                                seen_a = set()
                                for a in attrs_prev + attrs_llm:
                                    s = (a or "").strip()
                                    if s and s.lower() not in seen_a:
                                        seen_a.add(s.lower())
                                        merged_attrs.append(s)
                                card["attributes_index"] = merged_attrs
                            c = parsed.get("centrality")
                            if isinstance(c, (int, float)):
                                prev_c = float(card.get("centrality", 0.0) or 0.0)
                                card["centrality"] = float((prev_c + float(c)) / 2.0)
                            q = parsed.get("quality")
                            if isinstance(q, (int, float)):
                                prev_q = float(card.get("quality", 0.0) or 0.0)
                                card["quality"] = float(max(prev_q, float(q)))
                except Exception:
                    pass
        out_docs.update(new_sources)
        return {"docs": out_docs}
    except Exception:
        return {"docs": out_docs if 'out_docs' in locals() else {}}
