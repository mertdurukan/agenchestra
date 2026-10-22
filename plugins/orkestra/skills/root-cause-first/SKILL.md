---
name: root-cause-first
description: Evidence-driven troubleshooting and safe-change discipline for software engineering orchestrators. Use for bugs, failing tests, regressions, incidents, recurring errors, data issues, performance degradation, security failures, agent/LLM/RAG failures, and nontrivial feature, refactor, infrastructure, or configuration changes. Select a proportional diagnostic method, distinguish causal evidence from guesses, contain incidents safely, verify outcomes, and prevent recurrence. Do not invent root causes for planned changes.
metadata:
  version: "2.1.0"
---

# Root-Cause-First — Orchestrator Protocol

**Invariant:** Establish what differs from the intended behavior; explain it with the strongest available evidence; intervene at the responsible boundary; separately verify the intervention and the real-world outcome. Never claim a root cause or a test result that the evidence does not support.

This skill is a **decision and execution protocol**, not a mandatory long-form report and not a runtime permission system. Actual mandatory gates must be enforced by the orchestrator/workflow. Keep routine cases concise.

## 1. Route the task before doing RCA

Classify the **task kind** and **diagnostic depth** separately:

| Task kind | Primary objective | Required approach |
| --- | --- | --- |
| **Failure** | Explain an observed deviation | Triage -> hypothesis -> discriminating evidence -> causal intervention |
| **Active incident** | Reduce harm and restore safe operation | Authorized containment/mitigation first when urgency demands; preserve evidence where safe; then investigate |
| **Planned change** | Deliver a requested behavior without unsafe side effects | Current-state, requirement, dependency, invariant and impact analysis; **do not fabricate a failure/root cause** |

Choose depth using **impact, uncertainty, blast radius, reversibility, recurrence, and detectability**:

- **Light:** low-impact, understood, localized, reversible. Confirm baseline/intent, constraints, result.
- **Standard:** ordinary defects, features and integrations. Trace the relevant path, test the main hypothesis/assumption, verify behavior and regression.
- **Deep:** ambiguous, recurring, security/data-sensitive, cross-service, high-risk, or poorly detectable issues. Compare hypotheses, establish a causal model, independently validate, and plan rollout/prevention.

Severity/urgency is **not** diagnostic depth. A high-severity incident may need immediate simple mitigation and later deep investigation. Escalate depth after a failed fix, conflicting evidence, recurrence, new dependencies or widened impact.

## 2. Non-skippable decision gates

### G0 — Triage and protect

- State **expected vs observed** behavior (for planned changes: current vs desired), scope, impact, timing, constraints and affected users/systems.
- For active incidents, assess containment, authorized rollback, feature-disablement or traffic isolation **before** lengthy diagnosis; avoid destructive actions and protect evidence as practicable.
- Establish a baseline and a safe way to observe effects. Protect personal data, secrets, tenant boundaries and production integrity. Lack of access is a limitation, not permission to assume success.

**Gate:** One bounded problem statement and task/depth selection; emergency mitigation is separately permitted under existing authorization policy.

### G1 — Localize failure and choose a diagnostic method

- Reconstruct the **actual execution/data path** and locate the **first known divergence** from an invariant or contract. Use logs, traces, metrics, code, tests, config and change history as available.
- Create a short **hypothesis ledger**, prioritizing plausible alternatives (normally top 2–3, not an exhaustive brainstorming list). For each: supporting evidence, disconfirming evidence, predicted observation and cheapest **safe discriminating test**. Consult the [symptom → competing hypotheses catalogue](references/symptom-hypothesis-catalog.md) for candidate causes, **never as confirmed facts**.
- Select an appropriate method from [method-selection](references/method-selection.md). Prefer controlled boundary tests, comparisons and falsification over unstructured searching. Record negative results and confounders.
- For agentic/LLM/RAG systems, use the [stage-wise diagnostic playbook](references/agentic-llm-diagnostics.md) instead of defaulting to prompt changes.

**Gate:** Localized deviation or explicit evidence gap, and a testable next hypothesis. Do not treat temporal proximity, an error string, apparent correlation, an LLM-generated explanation, or a seemingly precise probability as proof. Assign no numerical root-cause probabilities without a defensible calibrated model and data.

### G2 — Establish sufficient causal understanding

- Describe, when relevant: **trigger -> enabling conditions -> failure mechanism -> observed effect**, plus **contributing factors** and **missing/failed safeguards**. Complex failures can have multiple causes; never force a single arbitrary “root.”
- Use **Confirmed** only when reproducible/interventional or converging independent evidence supports the mechanism and serious alternatives are addressed. Use **Supported** for a defensible but not decisive explanation; **Unknown** otherwise. For planned changes use **Not applicable**.
- Decide whether more investigation would change the next action. Continue when risk is high or a cheap high-information test exists; otherwise stop with explicit uncertainty and a bounded/reversible experiment or mitigation. Do not demand impossible causal certainty.

**Gate:** Evidence-linked causal model **or** a documented, risk-bounded decision under uncertainty. A speculative permanent fix must never be presented as definitive.

### G3 — Select and execute the correct intervention

- Distinguish **mitigation** (impact reduction), **corrective action** (causal mechanism), **prevention** (reduce recurrence), and **detection/recovery** (reduce future impact/duration).
- Compare candidates by causal coverage, minimal sufficient scope, correctness, blast radius, security, reversibility, compatibility, operational complexity and maintainability.
- Define expected effect, verification oracle, negative cases and rollback/feature-flag/canary as warranted **before editing**. Use approvals for production, destructive, sensitive, or security-impacting actions under the surrounding policy.
- Reject symptom masking, arbitrary timeout inflation, unconditional retries, silent exception swallowing, prompt-only band-aids and hardcoded exceptions **unless the causal model supports them**. Retries are appropriate when bounded, backoff/jitter-aware and safe for idempotency/side effects.

**Gate:** Planned intervention + evidence-based rationale + authorization as required + measurable verification plan. The skill does not confer execution permission.

### G4 — Independently verify, monitor and learn

Verify **distinct claims**, as applicable:

1. **Causal test:** does a controlled comparison or before/after evidence support the proposed mechanism?
2. **Change correctness:** do unit/integration/contract/security/negative/regression tests show the patch or change works?
3. **Outcome:** does the actual user/system behavior meet the acceptance criterion? Check relevant runtime/e2e signals; a green test alone is insufficient.
4. **Operational resilience:** canary/rollout and post-deploy error rate, latency, invariants, alerting and rollback signals if relevant.

If a test is unavailable, say **not run**; never convert it to “passed.” If verification fails or the symptom returns, **re-open hypotheses**, including the last attempted fix, instead of stacking patches.

For substantial/recurring incidents, record actionable prevention, detection and recovery improvements with owner, priority, measurable success and tracking reference. Learn without blaming individuals; “human error” is not the final systemic explanation.

**Gate:** Mark `Verified resolved` only for a verified permanent fix with adequate causal support, or `Verified change` for a validated planned change. `Mitigated`, `Implemented — unverified`, `Unresolved`, and `Blocked` are valid honest outcomes. A restored service with unknown cause remains **Mitigated / cause Unknown**, not a proven durable repair.

## 3. Delegation, limits and reporting

- Orchestrator owns the overall causal model and gate decisions. Delegate **bounded evidence collection or independent competing hypotheses** before parallel code edits; use independent review/verification at higher risk.
- Workers report `observations + evidence references + hypotheses + tests/results + confidence + affected boundary + proposed action + risks`. Reconcile contradictory results against source evidence, not agent confidence or consensus.
- Prefer read-only diagnosis until G3; worker authority and production permissions are inherited from actual system controls, not from this document.
- Limit thrashing: before another command or hypothesis, ask what decision its result will change. Expand scope only from evidence.
- Use [orchestrator gates and evidence contract](references/orchestration-gates.md) for machine-readable records and optional guard checks. For calibration use [evaluation cases](references/evaluation-cases.md).

**Compact completion report** (Standard/Deep; Light can be one sentence):

```text
Kind/depth: <Failure | Incident | Planned change> / <Light | Standard | Deep>
Deviation: <expected vs observed; affected scope>
Causality: <mechanism + contributors or Not applicable> [Confirmed | Supported | Unknown | Not applicable]
Evidence: <repro/trace/test/code reference + relevant negative tests/limitations>
Intervention: <mitigation/correction/change; why here; rollback if relevant>
Verification: <specific checks executed: pass/fail/not run; observed outcome>
Disposition: <Verified resolved | Verified change | Mitigated | Implemented — unverified | Unresolved | Blocked>
Residual: <uncertainty, remaining risks, tracked follow-up>
```

Never expose private reasoning traces or secrets in reports. Report observable evidence and engineering rationale only. Do not store sensitive payloads in diagnostic artifacts.
