"""
Script temporal: ejecuta búsquedas de ancla para construir ground-truth de paginas.
Solo lectura sobre la coleccion legacy. Se puede borrar tras generar el dataset.
"""
import sqlite3, os, sys
from pathlib import Path

DB = str(Path(__file__).parent.parent.parent / "chroma_bge_m3" / "chroma.sqlite3")
CANDIDATES = ["cybersec_docs_bge_m3", "crom_protocols_bge_m3"]

def get_seg_ids(cur):
    for name in CANDIDATES:
        cur.execute("SELECT id FROM collections WHERE name=?", (name,))
        row = cur.fetchone()
        if row:
            cid = row[0]
            cur.execute("SELECT id FROM segments WHERE collection=?", (cid,))
            segs = [r[0] for r in cur.fetchall()]
            if segs:
                return segs, name
    sys.exit("No collection found")

def search(cur, seg_ids, keyword, limit=4):
    ph = ",".join("?"*len(seg_ids))
    cur.execute(f"""
        SELECT src.string_value, pg.int_value, SUBSTR(doc.string_value,1,160)
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
    # (label, keyword)
    ("NIST_five_functions",        "five functions"),
    ("NIST_identify_protect",      "Identify, Protect, Detect"),
    ("NIST_SP800_53_controls",     "security and privacy controls"),
    ("NIST_RMF_steps",             "Risk Management Framework"),
    ("PCI_DSS_req6",               "Requirement 6"),
    ("PCI_DSS_req8",               "Requirement 8"),
    ("PCI_DSS_req10",              "Requirement 10"),
    ("PCI_DSS_v4_overview",        "PCI DSS v4.0"),
    ("CISSP_domains",              "eight domains"),
    ("CISSP_cia_triad",            "confidentiality, integrity and availability"),
    ("CISM_governance",            "information security governance"),
    ("CCSP_shared_responsibility", "shared responsibility"),
    ("CCSP_cloud_deployment",      "deployment models"),
    ("OWASP_WSTG_sql_injection",   "SQL injection"),
    ("OWASP_WSTG_xss",             "cross-site scripting"),
    ("OWASP_WSTG_methodology",     "testing methodology"),
    ("Nmap_syn_scan",              "SYN scan"),
    ("Nmap_version_detection",     "version detection"),
    ("Linux_hardening_ssh",        "SSH hardening"),
    ("Linux_hardening_firewall",   "iptables"),
    ("SOC_11strategies_tier",      "tier 1"),
    ("SOC_11strategies_metrics",   "metrics"),
    ("ZeroTrust_principles",       "never trust, always verify"),
    ("ZeroTrust_microsegmentation","microsegmentation"),
    ("IR_Windows_artifacts",       "Windows artifacts"),
    ("IR_Windows_memory",          "memory forensics"),
    ("COBIT_governance",           "governance objectives"),
    ("COBIT_domains",              "COBIT domain"),
    ("Social_eng_pretexting",      "pretexting"),
    ("Social_eng_phishing",        "phishing"),
    ("Cloud_security_CSP",         "cloud service provider"),
    ("MS365_conditional_access",   "Conditional Access"),
    ("Pentest_report_2023",        "penetration test"),
    ("Breach_report_2022",         "data breach"),
    ("SOC_tools_siem",             "SIEM"),
    ("Linux_commands_chmod",       "chmod"),
]

conn = sqlite3.connect(DB)
cur = conn.cursor()
seg_ids, cname = get_seg_ids(cur)
print(f"Coleccion: {cname}\n")
print(f"{'LABEL':<35} {'SOURCE':<55} {'PAGE':>5}")
print("-"*100)
for label, kw in ANCHORS:
    rows = search(cur, seg_ids, kw)
    if not rows:
        print(f"{label:<35} {'-- no result --':<55}")
    else:
        src, page, snippet = rows[0]
        src_short = (src or "")[-52:] if src else ""
        print(f"{label:<35} {src_short:<55} {page!s:>5}")
conn.close()
