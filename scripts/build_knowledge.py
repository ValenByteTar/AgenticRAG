#!/usr/bin/env python3
"""build_knowledge.py — batch standalone (RES-002 §10.1 Opcion A, ADR-0021).

Builder CLI con 4 subcomandos (ADR-0021):

    python build_knowledge.py extract   — extractores -> KIR crudo (con cache)
    python build_knowledge.py compile   — KIR -> passes -> KnowledgeModel
    python build_knowledge.py validate  — validation report sobre KnowledgeModel
    python build_knowledge.py publish   — codegen + Artifact Registry

Sin subcomando, ejecuta los 4 en secuencia (retrocompatible).

Uso:

    python build_knowledge.py [--registry PATH] [--build-id ID] [--promote]
    python build_knowledge.py extract [--use-llm] [--cache-dir PATH]
    python build_knowledge.py compile [--kir-file PATH]
    python build_knowledge.py validate [--model-file PATH]
    python build_knowledge.py publish [--model-file PATH] [--registry PATH]
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
from knowledge_builder.kir import KIR
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


def _make_compiler(args) -> KnowledgeCompiler:
    """Build a KnowledgeCompiler from CLI args."""
    return KnowledgeCompiler(
        equivalences_text=_load_equivalences_text(),
        entity_aliases=_load_entity_aliases(),
        doc_roles=_load_doc_roles() or None,
        builder_version=args.builder_version,
        confidence_policy=args.confidence_policy,
        build_id=args.build_id,
        use_llm_extractor=args.use_llm,
        llm_model=args.llm_model,
        llm_max_docs=args.llm_max_docs,
        llm_verbose=args.verbose,
        llm_max_workers=getattr(args, "llm_max_workers", 4),
        llm_num_predict=getattr(args, "llm_num_predict", 800),
        llm_num_ctx=getattr(args, "llm_num_ctx", 4096),
        use_semantic_validation=args.semantic_validation,
        cache_dir=getattr(args, "cache_dir", None),
        use_cache=not getattr(args, "no_cache", False),
    )


# ------------------------------------------------------------------ #
# Subcommand: extract
# ------------------------------------------------------------------ #
def cmd_extract(args):
    print("[extract] Running extractors -> KIR...")
    compiler = _make_compiler(args)
    kir = compiler.extract_only()
    print(f"  KIR claims: {kir.claim_count()}")
    print(f"  Extractors: {', '.join(kir.extractor_ids())}")

    kir_file = Path(args.kir_file) if args.kir_file else PROJECT_ROOT / "kir" / "merged_kir.json"
    kir_file.parent.mkdir(parents=True, exist_ok=True)
    kir_file.write_text(json.dumps(kir.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  KIR written to: {kir_file}")
    print("[extract] DONE")


# ------------------------------------------------------------------ #
# Subcommand: compile
# ------------------------------------------------------------------ #
def cmd_compile(args):
    kir_file = Path(args.kir_file) if args.kir_file else PROJECT_ROOT / "kir" / "merged_kir.json"
    if not kir_file.exists():
        print(f"[compile] ERROR: KIR file not found: {kir_file}")
        print("  Run 'build_knowledge.py extract' first.")
        sys.exit(1)

    print(f"[compile] Loading KIR from {kir_file}...")
    kir = KIR.from_dict(json.loads(kir_file.read_text(encoding="utf-8")))
    print(f"  KIR claims: {kir.claim_count()}")

    print("[compile] Running passes -> KnowledgeModel...")
    compiler = _make_compiler(args)
    model, validation, cold_data = compiler.compile_only(kir)
    print(f"  Validation: {validation.passed} passed, {validation.rejected} rejected, {len(validation.quarantined)} quarantined")
    print(f"  Model stats: {model.stats()}")

    model_file = Path(args.model_file) if args.model_file else PROJECT_ROOT / "model" / "knowledge_model.json"
    model_file.parent.mkdir(parents=True, exist_ok=True)
    model_payload = {
        "build_id": args.build_id,
        "builder_version": args.builder_version,
        "model_stats": model.stats(),
        "validation": validation.to_dict(),
        "cold_data": cold_data,
    }
    model_file.write_text(json.dumps(model_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Model written to: {model_file}")
    print("[compile] DONE")


# ------------------------------------------------------------------ #
# Subcommand: validate
# ------------------------------------------------------------------ #
def cmd_validate(args):
    model_file = Path(args.model_file) if args.model_file else PROJECT_ROOT / "model" / "knowledge_model.json"
    if not model_file.exists():
        print(f"[validate] ERROR: Model file not found: {model_file}")
        print("  Run 'build_knowledge.py compile' first.")
        sys.exit(1)

    print(f"[validate] Loading model from {model_file}...")
    model_payload = json.loads(model_file.read_text(encoding="utf-8"))
    validation_dict = model_payload.get("validation", {})

    from knowledge_builder.validate.validator import ValidationResult
    validation = ValidationResult(
        errors=validation_dict.get("errors", []),
        warnings=validation_dict.get("warnings", []),
        quarantined=validation_dict.get("quarantined", []),
        passed=validation_dict.get("passed", 0),
        rejected=validation_dict.get("rejected", 0),
    )

    compiler = _make_compiler(args)
    from knowledge_builder.model.knowledge_model import KnowledgeModel
    kir = KIR.from_dict(model_payload.get("cold_data", {}).get("kir", {"metadata": {}}))
    model = KnowledgeModel.from_kir(kir, builder_version=model_payload.get("builder_version", "1.0.0"))

    report = compiler.validate_only(model, validation)
    print(f"  Valid: {report['is_valid']}")
    print(f"  Errors: {len(report['errors'])}")
    print(f"  Warnings: {len(report['warnings'])}")
    print(f"  Quarantined: {len(report['quarantined'])}")
    print(f"  Model stats: {report['model_stats']}")

    validated_file = PROJECT_ROOT / "validated" / "validation_report.json"
    validated_file.parent.mkdir(parents=True, exist_ok=True)
    validated_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Report written to: {validated_file}")

    if not report["is_valid"]:
        print("[validate] FAILED — model is not valid. Cannot publish.")
        sys.exit(1)
    print("[validate] DONE")


# ------------------------------------------------------------------ #
# Subcommand: publish
# ------------------------------------------------------------------ #
def cmd_publish(args):
    model_file = Path(args.model_file) if args.model_file else PROJECT_ROOT / "model" / "knowledge_model.json"
    if not model_file.exists():
        print(f"[publish] ERROR: Model file not found: {model_file}")
        print("  Run 'build_knowledge.py compile' first.")
        sys.exit(1)

    print(f"[publish] Loading model from {model_file}...")
    model_payload = json.loads(model_file.read_text(encoding="utf-8"))
    cold_data = model_payload.get("cold_data", {})

    from knowledge_builder.model.knowledge_model import KnowledgeModel
    kir = KIR.from_dict(cold_data.get("kir", {"metadata": {}}))
    model = KnowledgeModel.from_kir(kir, builder_version=model_payload.get("builder_version", "1.0.0"))

    print("[publish] Codegen + publishing to Artifact Registry...")
    compiler = _make_compiler(args)
    registry_root = Path(args.registry)
    registry = ArtifactRegistry(registry_root)
    promote = not args.no_promote

    build_id, manifest, artifacts, cold_artifacts = compiler.publish_only(
        model, cold_data, registry, promote=promote
    )
    print(f"  Published: {build_id} (promoted={promote})")
    print(f"  Artifacts: {len(artifacts)}")

    print("[publish] Validating against warm-v1 contract...")
    from src.contract.validator import validate_build
    errors = validate_build(manifest, artifacts)
    if errors:
        print(f"  FAIL: {len(errors)} contract errors:")
        for e in errors[:10]:
            print(f"    - {e}")
        sys.exit(1)
    print("  OK: contract validation passed")

    print("[publish] Writing Cold Artifacts...")
    from knowledge_builder.backend.cold_codegen import ColdCodegen
    cold_codegen = ColdCodegen(output_dir=registry_root / "cold")
    cold_codegen.write_to_dir(cold_artifacts, build_id)

    print()
    print(f"PUBLISH COMPLETE: {build_id}")
    print(f"  Artifacts: {len(artifacts)}")
    print(f"  Contract: warm-v1")
    print(f"  Builder: {args.builder_version}")
    print(f"  Promoted: {promote}")


# ------------------------------------------------------------------ #
# Default: run all 4 phases in sequence (retrocompatible)
# ------------------------------------------------------------------ #
def cmd_all(args):
    print("[1/5] Loading deterministic knowledge sources...")
    equivalences_text = _load_equivalences_text()
    entity_aliases = _load_entity_aliases()
    doc_roles = _load_doc_roles()
    print(f"      Equivalences text: {len(equivalences_text)} chars")
    print(f"      Entity aliases: {len(entity_aliases)} entries")
    print(f"      Doc roles: {len(doc_roles.get('docs', {}))} documents")
    if args.use_llm:
        print(f"      LLM extractor: {args.llm_model} (max {args.llm_max_docs} docs)")
    if args.semantic_validation:
        print(f"      Semantic validation: enabled ({args.llm_model})")

    print("[2/5] Compiling knowledge (extract -> compile -> validate -> codegen)...")
    compiler = KnowledgeCompiler(
        equivalences_text=equivalences_text,
        entity_aliases=entity_aliases,
        doc_roles=doc_roles if doc_roles else None,
        builder_version=args.builder_version,
        confidence_policy=args.confidence_policy,
        build_id=args.build_id,
        use_llm_extractor=args.use_llm,
        llm_model=args.llm_model,
        llm_max_docs=args.llm_max_docs,
        llm_verbose=args.verbose,
        llm_max_workers=getattr(args, "llm_max_workers", 4),
        llm_num_predict=getattr(args, "llm_num_predict", 800),
        llm_num_ctx=getattr(args, "llm_num_ctx", 4096),
        use_semantic_validation=args.semantic_validation,
        cache_dir=getattr(args, "cache_dir", None),
        use_cache=not getattr(args, "no_cache", False),
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


def _add_common_args(parser):
    parser.add_argument("--registry", default="knowledge_artifacts", help="Registry root path")
    parser.add_argument("--build-id", default="ka_v1.0.0", help="Build ID")
    parser.add_argument("--builder-version", default="1.0.0", help="Builder version")
    parser.add_argument("--confidence-policy", default="weighted", help="Confidence policy name")
    parser.add_argument("--use-llm", action="store_true", help="Enable LLM extractor (E5, Granite 4.1 3B Q6)")
    parser.add_argument("--llm-model", default="ibm/granite4.1:3b-q6_K", help="LLM model for extraction")
    parser.add_argument("--llm-max-docs", type=int, default=50, help="Max documents to process with LLM")
    parser.add_argument("--llm-max-workers", type=int, default=4, help="Parallel chunks per document (Fase 4)")
    parser.add_argument("--llm-num-predict", type=int, default=1200, help="Max tokens to generate (Fase 4)")
    parser.add_argument("--llm-num-ctx", type=int, default=4096, help="Context window size (Fase 4)")
    parser.add_argument("--semantic-validation", action="store_true", help="Enable LLM-based semantic validation")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--cache-dir", default=None, help="KIR cache directory (default: cache/)")
    parser.add_argument("--no-cache", action="store_true", help="Disable KIR cache")
    parser.add_argument("--no-promote", action="store_true", help="Publish but do not promote")


def main():
    parser = argparse.ArgumentParser(description="Knowledge Builder — batch standalone compiler (ADR-0021)")
    subparsers = parser.add_subparsers(dest="command")

    # extract
    p_extract = subparsers.add_parser("extract", help="Extractors -> KIR crudo (con cache)")
    _add_common_args(p_extract)
    p_extract.add_argument("--kir-file", default=None, help="Output KIR file path")

    # compile
    p_compile = subparsers.add_parser("compile", help="KIR -> passes -> KnowledgeModel")
    _add_common_args(p_compile)
    p_compile.add_argument("--kir-file", default=None, help="Input KIR file path")
    p_compile.add_argument("--model-file", default=None, help="Output model file path")

    # validate
    p_validate = subparsers.add_parser("validate", help="Validation report sobre KnowledgeModel")
    _add_common_args(p_validate)
    p_validate.add_argument("--model-file", default=None, help="Input model file path")

    # publish
    p_publish = subparsers.add_parser("publish", help="Codegen + Artifact Registry")
    _add_common_args(p_publish)
    p_publish.add_argument("--model-file", default=None, help="Input model file path")

    # default (no subcommand) — retrocompatible
    _add_common_args(parser)
    parser.add_argument("--diff-report", default=None, help="Write diff report to this path")

    args = parser.parse_args()

    if args.command == "extract":
        cmd_extract(args)
    elif args.command == "compile":
        cmd_compile(args)
    elif args.command == "validate":
        cmd_validate(args)
    elif args.command == "publish":
        cmd_publish(args)
    else:
        cmd_all(args)


if __name__ == "__main__":
    main()
