#!/usr/bin/env python3
"""build_knowledge.py — batch standalone (RES-002 §10.1 Opcion A).

Compila conocimiento existente sin LLM y publica ka_v1.0.0 al Artifact Registry.

Uso:

    python build_knowledge.py [--registry PATH] [--build-id ID] [--promote]

Por defecto:
    --registry  knowledge_artifacts
    --build-id  ka_v1.0.0
    --promote   true
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from knowledge_builder.compiler import KnowledgeCompiler
from src.artifact_registry.registry import ArtifactRegistry


def _load_equivalences_text() -> str:
    """Extrae EQUIVALENCES_EMBEDDED_TEXT de rag_hybrid.py sin instanciar la clase."""
    import re
    source = (PROJECT_ROOT / "rag_hybrid.py").read_text(encoding="utf-8")
    match = re.search(r'EQUIVALENCES_EMBEDDED_TEXT\s*=\s*"""(.*?)"""', source, re.DOTALL)
    if not match:
        raise RuntimeError("No se encontro EQUIVALENCES_EMBEDDED_TEXT en rag_hybrid.py")
    return match.group(1)


def _load_entity_aliases() -> dict:
    """Extrae el dict entity_aliases de rag_hybrid.py."""
    return {
        "iso 27001": ["iso 27001", "iso27001", "iso 27k", "isms"],
        "nist csf": ["nist csf", "nist cybersecurity framework", "cybersecurity framework", "nist framework"],
        "cissp": ["cissp", "certified information systems security professional", "(isc)2"],
        "ceh": ["ceh", "certified ethical hacker", "ethical hacker"],
        "mitre att&ck": ["mitre att&ck", "mitre attack", "mitre attck", "attack framework"],
        "owasp": ["owasp", "open web application security project"],
        "splunk": ["splunk", "splunk siem", "splunk enterprise security"],
    }


def _load_doc_roles() -> dict:
    """Carga doc_roles.json si existe."""
    path = PROJECT_ROOT / "data" / "doc_roles.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def main():
    parser = argparse.ArgumentParser(description="Knowledge Builder — batch standalone compiler")
    parser.add_argument("--registry", default="knowledge_artifacts", help="Registry root path")
    parser.add_argument("--build-id", default="ka_v1.0.0", help="Build ID")
    parser.add_argument("--builder-version", default="1.0.0", help="Builder version")
    parser.add_argument("--confidence-policy", default="weighted", help="Confidence policy name")
    parser.add_argument("--no-promote", action="store_true", help="Publish but do not promote")
    parser.add_argument("--diff-report", default=None, help="Write diff report to this path")
    args = parser.parse_args()

    print("[1/5] Loading deterministic knowledge sources...")
    equivalences_text = _load_equivalences_text()
    entity_aliases = _load_entity_aliases()
    doc_roles = _load_doc_roles()
    print(f"      Equivalences text: {len(equivalences_text)} chars")
    print(f"      Entity aliases: {len(entity_aliases)} entries")
    print(f"      Doc roles: {len(doc_roles.get('docs', {}))} documents")

    print("[2/5] Compiling knowledge (front-end -> KIR -> passes -> validation -> model -> codegen)...")
    compiler = KnowledgeCompiler(
        equivalences_text=equivalences_text,
        entity_aliases=entity_aliases,
        doc_roles=doc_roles if doc_roles else None,
        builder_version=args.builder_version,
        confidence_policy=args.confidence_policy,
        build_id=args.build_id,
    )
    result = compiler.compile()
    print(f"      KIR claims: {result.kir_claim_count}")
    print(f"      Extractors: {', '.join(result.extractor_ids)}")
    print(f"      Validation: {result.validation.passed} passed, {result.validation.rejected} rejected, {len(result.validation.quarantined)} quarantined")
    print(f"      Model stats: {result.model_stats}")
    print(f"      Artifacts: {len(result.artifacts)}")

    print("[3/5] Validating against warm-v1 contract...")
    from src.contract.validator import validate_build
    errors = validate_build(result.manifest, result.artifacts)
    if errors:
        print(f"      FAIL: {len(errors)} contract errors:")
        for e in errors[:10]:
            print(f"        - {e}")
        sys.exit(1)
    print("      OK: contract validation passed")

    print("[4/5] Publishing to Artifact Registry...")
    registry_root = Path(args.registry)
    registry = ArtifactRegistry(registry_root)
    promote = not args.no_promote
    build_id = compiler.publish(result, registry, promote=promote)
    print(f"      Published: {build_id} (promoted={promote})")

    print("[5/5] Writing Cold Artifacts...")
    from knowledge_builder.backend.cold_codegen import ColdCodegen
    cold_codegen = ColdCodegen(output_dir=registry_root / "cold")
    cold_codegen.write_to_dir(result.cold_artifacts, build_id)

    if args.diff_report:
        print(f"      Generating diff report: {args.diff_report}")
        from knowledge_builder.diff_report import DiffReportGenerator
        gen = DiffReportGenerator()
        report = gen.generate(result)
        Path(args.diff_report).write_text(report, encoding="utf-8")
        print(f"      Diff report written to: {args.diff_report}")

    print()
    print(f"BUILD COMPLETE: {build_id}")
    print(f"  Artifacts: {len(result.artifacts)}")
    print(f"  Contract: warm-v1")
    print(f"  Builder: {args.builder_version}")
    print(f"  Promoted: {promote}")


if __name__ == "__main__":
    main()
