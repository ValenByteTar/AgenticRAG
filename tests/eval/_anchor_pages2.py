"""
Igual que _anchor_pages.py pero fuerza la coleccion legacy para obtener anclas completas.
"""
import sqlite3, sys
from pathlib import Path

DB = str(Path(__file__).parent.parent.parent / "chroma_bge_m3" / "chroma.sqlite3")
FORCE_COLLECTION = "crom_protocols_bge_m3"

def get_seg_ids(cur, name):
    cur.execute("SELECT id FROM collections WHERE name=?", (name,))
    row = cur.fetchone()
    if not row:
        sys.exit(f"Coleccion '{name}' no encontrada")
    cid = row[0]
    cur.execute("SELECT id FROM segments WHERE collection=?", (cid,))
    return [r[0] for r in cur.fetchall()]

def search(cur, seg_ids, keyword, limit=3):
    ph = ",".join("?"*len(seg_ids))
    cur.execute(f"""
        SELECT src.string_value, pg.int_value, SUBSTR(doc.string_value,1,200)
        FROM embeddings e
        LEFT JOIN embedding_metadata src ON src.id=e.id AND src.key='source'
        LEFT JOIN embedding_metadata pg  ON pg.id =e.id AND pg.key='page'
        LEFT JOIN embedding_metadata doc ON doc.id=e.id AND doc.key='chroma:document'
        WHERE e.segment_id IN ({ph})
          AND LOWER(doc.string_value) LIKE LOWER(?)
        ORDER BY src.string_value, pg.int_value
        LIMIT ?
    """, seg_ids+[f"%{keyword}%", limit])
    return cur.fetchall()

ANCHORS = [
    ("NIST_CSF_five_functions",       "Identify, Protect, Detect, Respond"),
    ("NIST_CSF_overview",             "Cybersecurity Framework"),
    ("NIST_SP800_53_controls",        "security and privacy controls"),
    ("NIST_RMF_steps",                "Risk Management Framework"),
    ("NIST_RMF_categorize",           "categorize the system"),
    ("PCI_DSS_req6_vulnmgmt",         "Requirement 6"),
    ("PCI_DSS_req8_identity",         "Requirement 8"),
    ("PCI_DSS_req10_logging",         "Requirement 10"),
    ("PCI_DSS_v4_scoping",            "PCI DSS v4"),
    ("CISSP_eight_domains",           "eight domains"),
    ("CISSP_cia",                     "confidentiality, integrity"),
    ("CISSP_access_control",          "access control"),
    ("CISM_governance",               "information security governance"),
    ("CCSP_shared_resp",              "shared responsibility"),
    ("CCSP_deployment_models",        "deployment models"),
    ("CCSP_cloud_risks",              "cloud risk"),
    ("OWASP_WSTG_sqli",               "SQL injection"),
    ("OWASP_WSTG_xss",                "cross-site scripting"),
    ("OWASP_WSTG_auth",               "authentication testing"),
    ("Nmap_syn_scan",                 "SYN scan"),
    ("Nmap_os_detect",                "OS detection"),
    ("Nmap_scripts",                  "NSE script"),
    ("Linux_hardening_ssh",           "sshd_config"),
    ("Linux_hardening_passwd",        "password policy"),
    ("Linux_iptables",                "iptables"),
    ("SOC_11strat_tiers",             "tier 1"),
    ("SOC_11strat_playbook",          "playbook"),
    ("SOC_11strat_metrics",           "mean time to detect"),
    ("ZeroTrust_never_trust",         "never trust"),
    ("ZeroTrust_microseg",            "microsegmentation"),
    ("ZeroTrust_NIST",                "zero trust architecture"),
    ("IR_Windows_evtx",               "Windows Event Log"),
    ("IR_Windows_prefetch",           "Prefetch"),
    ("IR_memory",                     "memory forensics"),
    ("COBIT_governance_obj",          "governance objective"),
    ("COBIT_APO",                     "APO domain"),
    ("Social_pretexting",             "pretexting"),
    ("Social_phishing",               "phishing attack"),
    ("Cloud_sec_CSP",                 "cloud service provider"),
    ("MS365_cond_access",             "Conditional Access"),
    ("MS365_MFA",                     "multi-factor authentication"),
    ("Pentest_methodology",           "penetration testing methodology"),
    ("Breach_2022_report",            "data breach"),
    ("SOC_tools_SIEM",                "SIEM tool"),
    ("SOC_tools_SOAR",                "SOAR"),
    ("Linux_chmod",                   "chmod"),
    ("DevSecOps_pipeline",            "CI/CD pipeline"),
    ("ISO27001_annexA",               "Annex A"),
    ("ISO27001_ISMS",                 "information security management system"),
    ("ISO27001_audit",                "internal audit"),
]

conn = sqlite3.connect(DB)
cur = conn.cursor()
seg_ids = get_seg_ids(cur, FORCE_COLLECTION)
print(f"Coleccion: {FORCE_COLLECTION}  ({len(seg_ids)} segmentos)\n")
print(f"{'LABEL':<35} {'SOURCE (ultimos 55 chars)':<57} {'PG':>4}  SNIPPET")
print("-"*130)
results = {}
for label, kw in ANCHORS:
    rows = search(cur, seg_ids, kw)
    if not rows:
        results[label] = None
        print(f"{label:<35} {'-- no result --':<57}")
    else:
        src, page, snippet = rows[0]
        src_s = (src or "")
        src_short = src_s[-55:] if len(src_s) > 55 else src_s
        snip = (snippet or "").replace("\n"," ")[:80].encode("ascii","replace").decode()
        src_short_safe = src_short.encode("ascii","replace").decode()
        print(f"{label:<35} {src_short_safe:<57} {str(page):>4}  {snip}")
        results[label] = {"source": src, "page": page}
conn.close()

found = sum(1 for v in results.values() if v)
print(f"\nAnclados: {found}/{len(ANCHORS)}")
