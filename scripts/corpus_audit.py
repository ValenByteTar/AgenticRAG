#!/usr/bin/env python3
"""corpus_audit.py — Audita y excluye documentos fuera del dominio de ciberseguridad.

Genera data/corpus_exclusions.json con la lista de archivos a excluir,
clasificados por razón. Opcionalmente mueve los archivos excluidos a
data/extracted_texts_excluded/ para preservar reversibilidad.

Uso:
    python scripts/corpus_audit.py [--move] [--verbose]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXTRACTED_DIR = PROJECT_ROOT / "data" / "extracted_texts"
EXCLUDED_DIR = PROJECT_ROOT / "data" / "extracted_texts_excluded"
OUTPUT_FILE = PROJECT_ROOT / "data" / "corpus_exclusions.json"

# --------------------------------------------------------------------------- #
# Categorías de exclusión
# --------------------------------------------------------------------------- #

BROKEN_EXTRACTIONS = [
    "35 LinkedIn Secrets You Need to Know.txt",
    "6 Step - Project Management for Successful Project.txt",
    "8 ways to get a job in cybersecurity.txt",
    "API Security Checklist .txt",
    "Burp Suite UHD.txt",
    "CISO Playbook Mergers and Acquisitions.txt",
    "CISO Point of View Guide Data Protection.txt",
    "Code of Practice App Store Operators and Developers.txt",
    "Cyber practices for remote workers.txt",
    "Disaster Recovery Planning.txt",
    "Generación FV-Diesel.txt",
    "How To Avoid Burnout.txt",
    "How to become a CISO.txt",
    "In The Eyes Of A Recruiter.txt",
    "InstructivoSolar.txt",
    "Official_Certified_Data_Privacy_Solutios_Engineer_CDPSE_Review_Manual.txt",
    "OWASP Top 10.txt",
    "Secure Coding Cheatsheets.txt",
    "SQL Cheat Sheet 2023.txt",
    "Web Pentesting Checklist .txt",
    "Why I Never Talk About Family At Work.txt",
]

ELECTRICAL_DOMAIN = [
    "Anexo D - Adecoagro.txt",
    "Anexo D - Algarrobo.txt",
    "Anexo D - BellVille.txt",
    "Anexo D - BioAnglo.txt",
    "Anexo D - Bioelectrica.txt",
    "Anexo D - DQD.txt",
    "Anexo D - ENVISION.txt",
    "Anexo D - GOLDWIND.txt",
    "Anexo D - GRENERGY.txt",
    "Anexo D - Harz Energy.txt",
    "Anexo D - La Florida.txt",
    "Anexo D - Listado Centrales.txt",
    "Anexo D - Pampetrol.txt",
    "Anexo D - Pollos San Mateos.txt",
    "Anexo D - SEEDS ENERGY.txt",
    "Anexo D - TENARIS.txt",
    "Anexo D - TOZZIGREEN.txt",
    "Anexo D - TotalEnergies.txt",
    "BLC-ServicioCROM.txt",
    "Calculo de maximo reactivo para PE.txt",
    "GOLDWIND - Reportes Semanales de SCADA.txt",
    "InstructivoMotores.txt",
    "InstructivoSolar2.txt",
    "ManualScadaSolar.txt",
    "ProcedimientoCROM.txt",
    "ProcedimientosCAMMESA.txt",
    "PT4 Ingreso de Nuevos Usuarios.txt",
    "PT8 Reglamento Operativo del Sadi.txt",
    "RESET AEROGENERADORES GOLDWIND.txt",
    "Requisitos Ingreso Generadores MEM.txt",
    "SimbologiaElectrica.txt",
]

OFFICE_SOFT_SKILLS = [
    "10 visuals that will help you to become a better you.txt",
    "100 Excel Functions you should know in one handy PDF.txt",
    "50 Excel Shortcuts PDF (2).txt",
    "50 Excel Shortcuts PDF.txt",
    "7 relatable visuals Impostor Syndrome.txt",
    "Advanced Excel to be a Professional .txt",
    "BEHAVIORAL INTERVIEW QUESTIONS.txt",
    "CHANGE MANAGEMENT TOOLKIT.txt",
    "Change Management Checklist (How to Do It Right).txt",
    "Excel Charting Data Analytics.txt",
    "Excel Formulas in Single Document.txt",
    "Excel Shortcuts .txt",
    "Excel® VBA Notes for Professionals.txt",
    "If you often overthink, read this.txt",
]

AI_HYPE = [
    "43 AI Powered Tools to Boost Productivity.txt",
    "AI AGENTS .txt",
    "How to use ChatGPT.txt",
]

FINANCIAL_RISK = [
    "BANK_REGULATION,_RISK_MANAGEMENT,_AND_COMPLIANCETHEORY,_PRACTICE.txt",
    "Financial_Reporting_of_Environmental_Liabilities_and_Risks_after.txt",
    "Financial_Risk_Management_for_Islamic_Banking_and_Finance_by_Ioan.txt",
    "FOUNDATIONS_OF_FINANCIAL_RISK_AN_OVERVIEW_OF_FINANCIAL_RISK_AND.txt",
    "Handbook_in_Monte_Carlo_Simulation_Applications_in_Financial_Engineering.txt",
    "Liquidity Risk Managing Funding and Asset Risk by Erik Banks.txt",
    "Managing_Risks_in_Commercial_and_Retail_Banking_by_Amalendu_Ghosh.txt",
    "Mapping_the_Risks_and_Risk_Management_Practices_in_Islamic_Banking.txt",
    "Operational_Risk_Management_in_Banks_Regulatory,_Organisational.txt",
    "Quantitative_risk_management_concepts,_techniques_and_tools_by_Alexander.txt",
    "Risk_management_and_shareholders_value_in_banking_from_risk_measurement.txt",
    "Risk_management_for_central_banks_and_other_public_investors_by.txt",
    "Value_at_Risk_and_Bank_Capital_Management_Risk_Adjusted_Performance.txt",
]

NON_SECURITY_CERTS = [
    "1-Routing Basics.txt",
    "101 Linux commands .txt",
    "250 Practice Questions For Terraform Associate Certification.txt",
    "50 Interview Questions with Answers CCNA PDF.txt",
    "Accountability Framework Self-Assessment Questionnaires.txt",
    "Azure Fundamentals AZ-900 Study Notes.txt",
    "Data Science Interviews Ultimate Guide.txt",
    "German_Ethics_Committe_Man,_and_Machine_Challenges_Posed_By_AI.txt",
    "HackSpace – January 2023.txt",
    "Learning DevOps.txt",
    "Linux For Beginners.txt",
    "Linux Networking.txt",
    "Linux Notes for Professionals.txt",
    "OReilly LINUX NETWORK ADMINISTRATOR'S GUIDE.txt",
]

BROKEN_SLIDES = [
    "Cloud Security Concept .txt",
    "Cloud Security concepts.txt",
    "IPsec Your Quick Review Guide to Network Security.txt",
    "Password Security (3).txt",
]

# --- Pass 2: electrical/CAMMESA files that slipped first pass ---
ELECTRICAL_DOMAIN_PASS2 = [
    "ContactoSoporte.txt",
    "InformacionOptimumPG.txt",
    "InstructivoEolico.txt",
    "Novedades y Estados Operativos SOTR.txt",
    "NovedadesTipicas.txt",
    "PT11 Analisis de Perturbaciones.txt",
    "PT15 Habilitación de Operadores.txt",
    "PT25 Mercado de Reserva Instantanea.txt",
    "Protecciones-1.txt",
    "Protecciones-2.txt",
    "Protecciones-3.txt",
    "Protecciones-4.txt",
    "RECUPERACIÓN DEL SADI.txt",
    "Tabla de Codigos ANSI.txt",
]

# --- Pass 2: content duplicates (same content, different filename) ---
CONTENT_DUPLICATES = [
    "3rd Party.txt",
    "ISO 27001 Mapping contros.txt",
    "Malware Sandboxing.txt",
    "Cyber Security Interview Questions .txt",
    "CYBER SECURITY FRAMEWORKS.txt",
    "A CISO Guide Cyber Defence.txt",
    "Conceptual Guide to Enterprise Cyber Security 2023 (2).txt",
    "ALL ABOUT PHISHING.txt",
    "CISO.txt",
    "CISA YEAR IN REVIEW 2022.txt",
    "The 5 CISO Archetypes.txt",
    "NIST SP 800-61.txt",
    "Information Security Incident Example Policy.txt",
    "Cost of a Data Breach Report, 2022.txt",
    "CYBERSECURITY BASICS.txt",
    "GDPR Data Protection Principals.txt",
    "Vendor Security Checklist_MoS.txt",
    "NIST CSF Checklist.txt",
    "Davos report on Global Cybersecurity for 2023.txt",
    "Global Cybersecurity Outlook 2023.txt",
    "ISO-27001-self-assessment-checklist.txt",
    "NIST SP 800-30.txt",
    "PCI_DSS_V4.x_TRA_Guidance.txt",
    "Infrastructure Penetration Testing Checklist.pdf.txt",
    "10 ISO 27001 Internal Audit Checklist.txt",
    "ISO 27001 Internal Audit Checklist.txt",
    "Introduction To Cyber Security.txt",
    "Using BIA to Inform Risk Prioritization and Response.txt",
    "NIST Zero Trust Architecture.txt",
    "Access Control Guidance for Cloud Systems.txt",
    "Ransomware Risk Management.txt",
    "PCI DSS v4.0 RoC FAQs.txt",
    "Phishing .txt",
    "CISCO Privacy Benchmark Study 2023.txt",
    "Secure Coding Practices (2).txt",
    "100 SOC Tools .txt",
    "Threat Hunting Survival Guide.txt",
    "DORA checklist 1.1.txt",
    "Incident & Vulnerability Response Playbooks.txt",
    "Cybersecurity_Incident_&_Vulnerability_Response_Playbooks (2).txt",
    "Windows Event Log.txt",
]

# --- Pass 2: .pdf.txt duplicate variants (keep non-.pdf.txt version) ---
PDF_TXT_DUPLICATES = [
    "Infrastructure Penetration Testing Checklist.pdf.txt",
]

# --- Pass 2: financial stragglers with different filename than pass 1 ---
FINANCIAL_RISK_PASS2 = [
    "Value_at_Risk_and_Bank_Capital_Management_Risk_Adjusted_Performance.txt",
    "Financial_Risk_Management_for_Islamic_Banking_and_Finance_by_Ioan.txt",
]

NEAR_DUPLICATES = [
    "200 IT Security Job Interview Questions  (2).txt",
    "2023 Global Privacy Predictions (2).txt",
    "API Security Checklist (2).txt",
    "API Security Checklist.txt",
    "Artificial Intelligence Risk Management Framework .txt",
    "Artificial Intelligence Risk Management Framework (2).txt",
    "Artificial Intelligence Risk Management Framework (3).txt",
    "AWS Security  (2).txt",
    "Azure DevOps Security CheckList (2).txt",
    "Best Practices for MITRE ATT&CK® Mapping (2).txt",
    "BSI 200-1 (2).txt",
    "CEH Exam Guide .txt",
    "ChatGPT for Offensive Security (2).txt",
    "CISSP Study giude PDF.txt",
    "Cloud Pentesting Cheatsheet (2).txt",
    "Cloud Security Best Practices .txt",
    "CompTIA Security+ Exam Study Guide (2).txt",
    "Conceptual Guide to Enterprise Cyber Security 2023 .txt",
    "Cyber Hygiene (2).txt",
    "Cybersecurity Checklist.txt",
    "Cybersecurity Frameworks.txt",
    "Cybersecurity_Incident_&_Vulnerability_Response_Pl (2).txt",
    "DevSecOps Fundamentals Guidebook (2).txt",
    "Enabling a Threat Hunting Capability in AWS (2).txt",
    "EXCEL FOR ANALYTICS THE ULTIMATE GUIDE.txt",
    "EXCEL Formulas Bible.txt",
    "EXCEL STEP BY STEP GUIDE Mark Nicholls.txt",
    "GDPR Data Protection Principles (2).txt",
    "GDPR for Third-Party Risk Management (2).txt",
    "Information Risk Insights Study (2).txt",
    "Introduction To Cybersecurity (2).txt",
    "ISO 27001 Implementation Roadmap (2).txt",
    "ISO 27001 Internal Audit Checklist (2).txt",
    "Kubernetes Security Cheat Sheet (2).txt",
    "Network Security Checklist (2).txt",
    "NIS2.txt",
    "NIST Cloud Computing Forensic Science Challenges (2).txt",
    "NIST CSF Checklist (2).txt",
    "NIST.IR.8286D.txt",
    "NIST RISK MANAGEMENT FRAMEWORK (2).txt",
    "Password Security (2).txt",
    "Red Teaming Toolkit (2).txt",
    "Risk assessment process handbook (2).txt",
    "Risk_Management_Framework_for_Information_Systems_and_Organizations (2).txt",
    "SOC ANALYST INTERVIEW QUESTIONS (2).txt",
    "SOC Analyst Interview Questions.txt",
    "SOFTWARE SUPPLY CHAIN SECURITY THREAT LANDSCAPE .txt",
    "Threat Intelligence Handbook (2).txt",
    "Top 10 CI_CD Security Risks (2).txt",
    "Top 50 Cyber Security Interview Questions PDF (2).txt",
    "Top 50 Cybersecurity Interview Questions.txt",
    "Vendor Security Checklist  (2).txt",
    "Windows 11 Security Book (2).txt",
]

CATEGORY_MAP = {
    "broken_extraction": BROKEN_EXTRACTIONS,
    "electrical_domain": ELECTRICAL_DOMAIN,
    "electrical_domain_pass2": ELECTRICAL_DOMAIN_PASS2,
    "office_soft_skills": OFFICE_SOFT_SKILLS,
    "ai_hype": AI_HYPE,
    "financial_risk": FINANCIAL_RISK,
    "financial_risk_pass2": FINANCIAL_RISK_PASS2,
    "non_security_cert": NON_SECURITY_CERTS,
    "broken_slides": BROKEN_SLIDES,
    "near_duplicate": NEAR_DUPLICATES,
    "content_duplicate": CONTENT_DUPLICATES,
    "pdf_txt_duplicate": PDF_TXT_DUPLICATES,
}


def build_exclusion_list() -> list[dict]:
    """Build the full exclusion list with reasons."""
    excluded = []
    seen = set()
    for reason, files in CATEGORY_MAP.items():
        for fname in files:
            if fname in seen:
                continue
            seen.add(fname)
            fpath = EXTRACTED_DIR / fname
            size = fpath.stat().st_size if fpath.exists() else 0
            excluded.append({
                "file": fname,
                "reason": reason,
                "size": size,
            })
    return sorted(excluded, key=lambda x: (x["reason"], x["file"]))


def write_manifest(excluded: list[dict]) -> None:
    """Write the exclusion manifest to data/corpus_exclusions.json."""
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_excluded": len(excluded),
        "total_bytes": sum(x["size"] for x in excluded),
        "excluded": excluded,
    }
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Manifest written to: {OUTPUT_FILE}")
    print(f"  Total excluded: {len(excluded)} files")
    print(f"  Total bytes: {manifest['total_bytes']:,}")


def move_excluded(excluded: list[dict], verbose: bool = False) -> None:
    """Move excluded files to data/extracted_texts_excluded/."""
    EXCLUDED_DIR.mkdir(parents=True, exist_ok=True)
    moved = 0
    missing = 0
    for item in excluded:
        src = EXTRACTED_DIR / item["file"]
        dst = EXCLUDED_DIR / item["file"]
        if not src.exists():
            missing += 1
            if verbose:
                print(f"  [SKIP] Not found: {item['file']}")
            continue
        if dst.exists():
            if verbose:
                print(f"  [SKIP] Already moved: {item['file']}")
            continue
        shutil.move(str(src), str(dst))
        moved += 1
        if verbose or moved % 25 == 0:
            print(f"  [MOVED] {moved}/{len(excluded)}: {item['file'][:50]}")
    print(f"Moved: {moved}, Missing: {missing}")


def main():
    parser = argparse.ArgumentParser(
        description="Audit and exclude non-cybersecurity documents from corpus"
    )
    parser.add_argument(
        "--move", action="store_true",
        help="Move excluded files to data/extracted_texts_excluded/",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    excluded = build_exclusion_list()

    # Print summary by category
    from collections import Counter
    cat_counts = Counter(x["reason"] for x in excluded)
    print("=== Exclusion summary ===")
    for cat, count in sorted(cat_counts.items()):
        print(f"  {cat:25s}: {count:3d} files")
    print(f"  {'TOTAL':25s}: {len(excluded):3d} files")
    print()

    write_manifest(excluded)

    if args.move:
        print()
        print("Moving excluded files...")
        move_excluded(excluded, verbose=args.verbose)

    print("Done.")


if __name__ == "__main__":
    main()
