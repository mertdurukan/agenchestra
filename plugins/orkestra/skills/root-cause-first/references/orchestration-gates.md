# Orchestrator Contract — Gates, Delegation, Evidence, Disposition

The SKILL.md sets guidance; these gates describe a **workflow design**. The skill alone cannot enforce mandatory tool execution, privilege checks or state transitions. Implement them in the orchestrator's state machine, CI, hooks or task runner as appropriate.

## State and decision gates

| Gate | Minimum evidence | Allowed next actions | Explicit exception |
| --- | --- | --- | --- |
| G0 TRIAGED | Task kind, scope, impact and constraints | Read-only diagnosis; plan a change | Approved, narrowly scoped emergency containment |
| G1 LOCALIZED | Execution path/invariant or missing evidence identified; competing hypotheses for ambiguous issues | Diagnostic experiments, G2 synthesis | Light planned/routine changes may go to G3 via impact analysis |
| G2 EXPLAINED | Causal mechanism with references **or** unknown cause and bounded-risk rationale | G3 resolution planning | Safe reversible experiment under uncertainty |
| G3 AUTHORIZED | Proposed action, scoped diff, approval as applicable, regression/outcome oracle, rollback or stated irreversibility | Implement/mitigate | Follow higher-priority production change controls |
| G4 CHECKED | Actual tests/observations, not merely proposed tests; recorded unavailable checks, rollout signals and residual risk | Close with accurate disposition; reopen | Evidence or resource limitations mean unverified/incomplete outcome |

**Security and authority:** All production actions, access to confidential data, destructive commands and external effects remain subject to existing permissions and explicit user/organization approvals. A machine-readable `authorized=true` flag is a claim in an artifact, not evidence of actual authorization.

## Keep independent fields; do not overload confidence/status

- `cause_confidence`: `confirmed | supported | unknown | not_applicable` (refers to diagnosis only).
- `implementation_status`: `not_started | mitigated | implemented | rolled_back | blocked`.
- `verification_status`: `not_run | partial | passed | failed` (refers to actual executed checks).
- `disposition`: `verified_resolved | verified_change | mitigated | implemented_unverified | unresolved | blocked`.

Do **not** infer cause confidence from green tests; do **not** infer successful deployment from completed implementation; do **not** call emergency mitigation a permanent fix. For a failure, `verified_resolved` requires cause evidence at least `supported`, verified outcome, and relevant regression checks. A reversible fix with unknown cause can be described as `mitigated` pending RCA; do not misstate it as a proven durable correction.

## Evidence record (adapt as needed)

```json
{
  "task_kind": "failure",
  "depth": "deep",
  "impact": "Some tenant queries are routed to the wrong tool",
  "expected": "Route inventory forecast intent to the domain forecast tool",
  "observed": "Routing trace selects stock lookup for forecast intent",
  "evidence": [
    {"id": "E1", "kind": "trace", "location": "trace://redacted-run", "observation": "forecast intent classified as inventory lookup"}
  ],
  "hypotheses": [
    {"id": "H1", "statement": "Policy precedence favors generic inventory rule", "predicts": "priority-rule match appears before specific forecast rule", "test": "Replay normalized intent with policy trace", "result": "pending"}
  ],
  "causal_model": {
    "trigger": "Forecast request with generic stock term",
    "conditions": ["Generic rule priority exceeds domain-specific rule"],
    "mechanism": "Policy rule overrides intended domain selection",
    "contributors": ["Policy test lacks overlapping-intent case"],
    "failed_safeguards": ["No overlap-resolution assertion"]
  },
  "cause_confidence": "supported",
  "action": {"kind": "corrective", "scope": "routing policy", "rollback": "restore previous policy version"},
  "verification": [
    {"kind": "regression", "result": "not_run", "evidence": []},
    {"kind": "outcome", "result": "not_run", "evidence": []}
  ],
  "implementation_status": "not_started",
  "verification_status": "not_run",
  "disposition": "unresolved",
  "residual_risks": ["Other ambiguous intents not yet checked"]
}
```

This is a **diagnostic record example**, not a runtime schema or actual collected trace. Use the optional `scripts/validate_record.py` to detect inconsistent closure assertions, not to authenticate evidence or user approval.

## Delegation and independent verification

**Dispatch:** Supply worker with evidence references, bounded goal, domain boundaries, allowed tools/permissions, constraints, hypothesis to test, and exact return schema. Avoid multiple workers concurrently editing the same files.

**Investigator returns:** Observations, tests performed, results (including negatives), evidence location, revised hypotheses and remaining uncertainty. Investigators should not silently implement fixes.

**Implementer receives:** Agreed diagnosis/uncertainty, requested bounded intervention, test oracle, negative cases, approval/rollback requirements. Returns precise changes and actually executed validation.

**Verifier independently checks:** Original issue, side effects, affected contracts, failure mode variants, and real outcome. It may falsify the diagnosis or reopen G1/G2. Independence is especially valuable at high severity and does not require a second agent for trivial tasks.

**Synthesis:** Orchestrator traces contradictory claims to original sources; chooses explanation with best evidence, not agent majority vote; records residual uncertainty and next discriminating test.

## Investigation stopping policy

Do not impose a rigid number of terminal commands or fixed “five whys.” Ask before each further probe: *Which decision would this result change?* If none, stop. Escalate when user impact, potential harm or missing verification makes a guess unsafe. When blocked, report exact missing capability and keep the task in `blocked`/`unresolved`, not an invented success state.

## Learning loop and follow-up

For significant or repeated incidents, record (1) immediate mitigation, (2) permanent correction, (3) prevention, (4) detection, (5) recovery, and (6) validation of each implemented follow-up. Prioritize by impact and recurrence risk; assign ownership and tracking ID. If prevention is deferred, make the accepted residual risk explicit.
