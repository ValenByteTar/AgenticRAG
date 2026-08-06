"""Deterministic runner for canonical benchmark v2.

Modes:
  - readiness (default): reports whether v2 has reviewed contracts and can run.
  - observation: evaluates a runtime-observation JSON without using an LLM.

The legacy evaluator remains untouched. This runner deliberately returns INVALID
for cases whose human-reviewed claims or corpus coverage are still pending.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = ROOT / "tests" / "eval" / "canonical" / "cybersec_eval_questions_v2.json"
DEFAULT_REPORTS = ROOT / "tests" / "eval" / "canonical" / "reports"

VALID_DECISIONS = {"answer", "decline", "clarify", "retry_retrieval", "partial_answer"}


def load_json(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def iter_observations(payload: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    cases = payload.get("cases", payload)
    if isinstance(cases, list):
        return (case for case in cases if isinstance(case, dict))
    if isinstance(cases, dict):
        return (
            dict(observation, case_id=case_id)
            for case_id, observation in cases.items()
            if isinstance(observation, dict)
        )
    raise ValueError("Observation payload must contain a list or object of cases")


def validate_dataset(dataset: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    questions = dataset.get("questions")
    if not isinstance(questions, list):
        return ["questions must be a list"]
    if dataset.get("version") != "2.0":
        errors.append("benchmark version must be 2.0")
    if dataset.get("builder_independence") is not True:
        errors.append("builder_independence must be true")
    ids = [q.get("id") for q in questions if isinstance(q, dict)]
    if len(ids) != len(set(ids)):
        errors.append("question ids must be unique")
    legacy_ids = [q.get("legacy_id") for q in questions if isinstance(q, dict)]
    if len(legacy_ids) != len(set(legacy_ids)):
        errors.append("legacy_id values must be unique")
    if dataset.get("question_count") != len(questions):
        errors.append("question_count does not match questions length")
    return errors


def readiness_case(case: Dict[str, Any]) -> Dict[str, Any]:
    claims = case.get("expected_claims") or []
    req = case.get("evidence_requirements") or {}
    coverage = case.get("corpus_coverage") or {}
    review_status = case.get("migration_status")
    ready = bool(
        claims
        and req.get("required_claims")
        and req.get("minimum_claim_coverage") is not None
        and req.get("minimum_evidence_quality") is not None
        and review_status == "approved"
        and coverage.get("status") not in {"uncertain_requires_review", "knowledge_gap_introduced"}
    )
    return {
        "case_id": case.get("id"),
        "legacy_id": case.get("legacy_id"),
        "status": "ready" if ready else "pending_human_review",
        "expected_claims": len(claims),
        "corpus_status": coverage.get("status", "unknown"),
    }


def evaluate_case(case: Dict[str, Any], observation: Dict[str, Any]) -> Dict[str, Any]:
    case_id = case.get("id")
    contract = case.get("evidence_requirements") or {}
    expected_claims = set(case.get("query", {}).get("required_evidence") or [])
    if not expected_claims:
        expected_claims = {c.get("claim_id") for c in case.get("expected_claims", []) if c.get("claim_id")}

    if not expected_claims or case.get("migration_status") != "approved":
        return {"case_id": case_id, "status": "INVALID", "reason": "ground_truth_pending"}

    decision = (observation.get("decision") or {}).get("type")
    if decision not in VALID_DECISIONS:
        return {"case_id": case_id, "status": "INVALID", "reason": "missing_or_unknown_decision"}

    evidence = observation.get("evidence_set") or []
    supported = set()
    provenance_errors = []
    for item in evidence:
        supported.update(item.get("supports_claims") or [])
        provenance = item.get("provenance") or {}
        if contract.get("require_provenance") and not (
            provenance.get("source_doc_id") and
            (provenance.get("source_chunk_ids") or provenance.get("span_id"))
        ):
            provenance_errors.append(item.get("artifact_id", "unknown"))

    coverage = len(expected_claims & supported) / len(expected_claims)
    minimum_coverage = float(contract.get("minimum_claim_coverage") or 0.0)
    violations = []
    if coverage < minimum_coverage:
        violations.append({"type": "missing_required_claim", "severity": "major"})
    if provenance_errors:
        violations.append({"type": "missing_provenance", "severity": "critical", "artifacts": provenance_errors})

    decision_policy = case.get("decision_policy") or {}
    allowed = set(decision_policy.get("allowed_decisions") or VALID_DECISIONS)
    if decision not in allowed:
        violations.append({"type": "decision_not_allowed", "severity": "major", "decision": decision})

    if violations:
        return {
            "case_id": case_id,
            "status": "FAIL",
            "decision": decision,
            "claim_coverage": round(coverage, 4),
            "violations": violations,
        }
    return {
        "case_id": case_id,
        "status": "PASS",
        "decision": decision,
        "claim_coverage": round(coverage, 4),
        "violations": [],
    }


def build_readiness_report(dataset: Dict[str, Any], errors: List[str]) -> Dict[str, Any]:
    cases = [readiness_case(case) for case in dataset.get("questions", [])]
    counts: Dict[str, int] = {}
    for case in cases:
        counts[case["status"]] = counts.get(case["status"], 0) + 1
    return {
        "benchmark_id": dataset.get("benchmark_id"),
        "benchmark_version": "canonical-v2",
        "benchmark_status": dataset.get("status"),
        "evaluation_contract": dataset.get("evaluation_contract"),
        "mode": "readiness",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_errors": errors,
        "ready_for_normative_evaluation": not errors and counts.get("pending_human_review", 0) == 0,
        "counts": counts,
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic canonical benchmark v2 evaluation")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--observations", type=Path, help="Runtime observations JSON; enables evaluation mode")
    parser.add_argument("--report", type=Path, help="Optional output JSON report")
    args = parser.parse_args()

    dataset = load_json(args.cases)
    errors = validate_dataset(dataset)
    if args.observations:
        payload = load_json(args.observations)
        by_id = {str(item.get("case_id")): item for item in iter_observations(payload)}
        results = [evaluate_case(case, by_id[case["id"]]) if case["id"] in by_id else {
            "case_id": case["id"], "status": "INVALID", "reason": "missing_observation"
        } for case in dataset.get("questions", [])]
        report = {
            "benchmark_id": dataset.get("benchmark_id"),
            "benchmark_version": "canonical-v2",
            "benchmark_status": dataset.get("status"),
            "evaluation_contract": dataset.get("evaluation_contract"),
            "mode": "observation",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dataset_errors": errors,
            "results": results,
        }
    else:
        report = build_readiness_report(dataset, errors)

    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + "\n", encoding="utf-8")
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
