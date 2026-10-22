#!/usr/bin/env python3
"""Structural consistency checks for root-cause-first records.

This is an optional CI/orchestrator guard, NOT proof that tests ran,
that evidence is authentic, or that a production action was authorized.
Usage: python scripts/validate_record.py path/to/record.json
"""
import json
import sys
from pathlib import Path

ENUMS = {
    "task_kind": {"failure", "incident", "planned_change"},
    "depth": {"light", "standard", "deep"},
    "cause_confidence": {"confirmed", "supported", "unknown", "not_applicable"},
    "implementation_status": {"not_started", "mitigated", "implemented", "rolled_back", "blocked"},
    "verification_status": {"not_run", "partial", "passed", "failed"},
    "disposition": {"verified_resolved", "verified_change", "mitigated", "implemented_unverified", "unresolved", "blocked"},
}


def validate(data):
    errors = []
    if not isinstance(data, dict):
        return ["Record must be a JSON object"]
    for field, permitted in ENUMS.items():
        if data.get(field) not in permitted:
            errors.append(f"{field} must be one of: {', '.join(sorted(permitted))}")
    for field in ("expected", "observed"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            errors.append(f"{field} must be a non-empty string")
    evidence = data.get("evidence", [])
    if not isinstance(evidence, list):
        errors.append("evidence must be a list")
        evidence = []
    evidence_ids = set()
    for i, e in enumerate(evidence):
        if not isinstance(e, dict) or not all(isinstance(e.get(k), str) and e[k].strip() for k in ("id", "kind", "location", "observation")):
            errors.append(f"evidence[{i}] must have nonempty id, kind, location, observation")
        else:
            if e["id"] in evidence_ids:
                errors.append(f"Duplicate evidence id {e['id']}")
            evidence_ids.add(e["id"])
    checks = data.get("verification", [])
    if not isinstance(checks, list):
        errors.append("verification must be a list")
        checks = []
    for i, c in enumerate(checks):
        if not isinstance(c, dict) or c.get("kind") not in {"causal", "correctness", "regression", "outcome", "operational", "security"} or c.get("result") not in {"passed", "failed", "not_run", "blocked"} or not isinstance(c.get("evidence", []), list):
            errors.append(f"verification[{i}] has invalid kind/result/evidence")
            continue
        for ref in c.get("evidence", []):
            if ref not in evidence_ids:
                errors.append(f"verification[{i}] references unknown evidence {ref}")
        if c["result"] == "passed" and not c.get("evidence"):
            errors.append(f"verification[{i}] claims passed without evidence reference")
    kind = data.get("task_kind")
    conf = data.get("cause_confidence")
    disposition = data.get("disposition")
    status = data.get("verification_status")
    impl = data.get("implementation_status")
    if kind == "planned_change" and conf != "not_applicable":
        errors.append("planned_change should use cause_confidence=not_applicable")
    if kind in {"failure", "incident"} and conf == "not_applicable":
        errors.append("failures/incidents cannot use cause_confidence=not_applicable")
    if disposition in {"verified_resolved", "verified_change"}:
        if status != "passed" or impl != "implemented":
            errors.append("verified disposition requires implemented change and passed verification_status")
        if not any(isinstance(c, dict) and c.get("kind") == "outcome" and c.get("result") == "passed" for c in checks):
            errors.append("verified disposition requires passed outcome check")
        if not any(isinstance(c, dict) and c.get("kind") in {"correctness", "regression"} and c.get("result") == "passed" for c in checks):
            errors.append("verified disposition requires passed correctness or regression check")
    if disposition == "verified_resolved" and (kind not in {"failure", "incident"} or conf not in {"confirmed", "supported"}):
        errors.append("verified_resolved requires a failure/incident and confirmed/supported cause")
    if disposition == "verified_change" and kind != "planned_change":
        errors.append("verified_change is only for planned_change")
    if disposition == "mitigated" and impl != "mitigated":
        errors.append("mitigated disposition requires implementation_status=mitigated")
    if disposition == "implemented_unverified" and impl != "implemented":
        errors.append("implemented_unverified requires implementation_status=implemented")
    if disposition == "blocked" and impl != "blocked":
        errors.append("blocked disposition requires implementation_status=blocked")
    if status == "passed" and any(isinstance(c, dict) and c.get("result") == "failed" for c in checks):
        errors.append("verification_status passed contradicts failed verification check")
    return errors


def main():
    if len(sys.argv) != 2:
        print("Usage: validate_record.py record.json", file=sys.stderr)
        return 2
    try:
        data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Record unreadable: {exc}", file=sys.stderr)
        return 2
    errors = validate(data)
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print("Record internally consistent (not independently verified).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
