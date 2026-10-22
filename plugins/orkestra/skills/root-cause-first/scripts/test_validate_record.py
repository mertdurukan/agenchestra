#!/usr/bin/env python3
"""Minimal consistency-check smoke suite; run with Python standard library."""
import copy
import json
from pathlib import Path
from validate_record import validate

root = Path(__file__).resolve().parents[1]
base = json.loads((root / "examples/diagnostic-record.example.json").read_text(encoding="utf-8"))
assert not validate(base), validate(base)

def invalid(change):
    x = copy.deepcopy(base)
    change(x)
    assert validate(x), x

invalid(lambda x: x.update(disposition="verified_resolved"))  # Partial checks are not enough
invalid(lambda x: x.update(cause_confidence="not_applicable"))
invalid(lambda x: x["verification"][0].update(evidence=["nonexistent"]))
invalid(lambda x: x["verification"][0].update(result="passed", evidence=[]))
valid = copy.deepcopy(base)
valid.update(disposition="verified_resolved", verification_status="passed")
valid["evidence"].append({"id":"E3","kind":"runtime","location":"canary/metric-evidence","observation":"Accepted outcome verified"})
valid["verification"][1] = {"kind":"outcome","result":"passed","evidence":["E3"]}
assert not validate(valid), validate(valid)
invalid(lambda x: x.update(task_kind="planned_change", disposition="verified_change", verification_status="passed"))
print("All contract smoke tests passed")
