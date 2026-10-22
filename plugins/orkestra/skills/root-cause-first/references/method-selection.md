# Method Selection — Use the smallest method that separates plausible causes

**Rule:** Choose a method based on the observable failure pattern, not because a methodology is popular. Different methods can be composed; none automatically proves causality. Begin with safe, cheap, high-information tests.

| Observable pattern | Recommended method | How to apply / stopping signal | Common failure |
| --- | --- | --- | --- |
| A recent deployment/config/data change may be involved | **Change correlation + differential debugging** | Compare last known good vs first bad revision, environment, inputs and dependency versions; bisect when deterministic and safe; control for traffic/time/environment changes | "It changed recently, so it caused it" |
| Fault boundary unknown across layers | **Execution tracing + divide-and-conquer** | Trace request/trace IDs or data lineage end-to-end; check contracts at boundaries; bisect execution stages; stop at first observed divergence | Inspecting only the top-level error or UI |
| Two or more plausible explanations | **Hypothesis-driven debugging** | State alternatives and their opposing predictions; choose a safe discriminating test by information gained per cost/risk; keep null/negative findings | Testing only the favorite hypothesis |
| Failure needs multiple conditions | **Causal graph / contributing-factor analysis** | Separate trigger, enabling conditions, mechanism, propagation, safeguards and outcome; draw branches; ask counterfactuals when possible | Forcing one linear “root cause” |
| Boolean combinations of component failures | **Fault tree analysis** | Work backwards from a well-defined undesirable top event with AND/OR relationships; validate branch evidence | Treating a hypothetical tree as observed fact |
| Need depth on a fairly linear, well-evidenced chain | **5 Whys (branch-aware)** | Ask successive causal questions with evidence for each link; branch when multiple contributing factors appear; stop at actionable, supported mechanisms | Arbitrary five levels, blame, unsupported inference |
| Possible bottleneck/overload | **Profiling + latency/queue analysis** | Segment latency, throughput, queue time, CPU/memory/IO, saturation and load; compare P95/P99 and baselines | Increasing timeout without measuring bottleneck |
| Intermittent race/deadlock/retry storm | **Event timeline + state/concurrency analysis** | Correlate ordered events, locks, retries, idempotency keys, schedules and state transitions; use replay/controlled stress where safe | Interpreting unaligned clocks or one log as full order |
| Data wrong, missing or stale | **Data lineage + invariant/contract validation** | Track source -> transformation -> storage -> serving; verify schema, units, keys, freshness, cardinality and tenant context | Fixing display/query while upstream data is corrupt |
| Recurring failure or prior patch ineffective | **Recurrence + failed-safeguard analysis** | Compare old/new failures, same causal mechanism?, why previous action did not prevent or detect it, related variants | Adding one more special case |
| New feature, refactor or config change | **Dependency/impact and invariant analysis** | Inspect actual current flow, contracts and consumers; define intended effect, compatibility and rollback; test affected boundaries | Inventing RCA where no failure occurred |
| High-impact prospective risk | **Lightweight FMEA / hazard analysis** | Identify failure modes, impact, likelihood indicators, detectability and safeguards for proposed actions | Treating arbitrary numeric scores as objective certainty |
| Outage or active harm | **Incident triage + containment + timeline** | Confirm customer impact, protect systems and preserve evidence; apply authorized reversible mitigation first; investigate after stabilization | Delaying safe restoration for full postmortem |

## Universal diagnostic procedure

1. **Define oracle:** Specify an observable expected result/invariant and the failing result. Capture known-good comparison if available.
2. **Localize:** Identify the first boundary at which actual behavior diverges. Determine whether the symptom is upstream/downstream of the defect.
3. **Rank hypotheses:** Keep a small list ordered by plausibility and discriminating value; include cross-layer candidates when warranted. Do not fabricate precise probabilities.
4. **Design falsification:** For each hypothesis define: `if true -> observation X`; `if false -> observation Y`; the safest test; result and confounders. A test that yields the same result under all hypotheses offers little value.
5. **Run controlled comparisons:** Prefer one-variable changes or stable test environments; note nondeterminism, external changes and observation side effects. Production experiments require appropriate authorization.
6. **Build causal model:** Record trigger, enabling conditions, mechanism, effects, propagation and safeguards; distinguish root/contributing/escape points. A missing safeguard explains why impact escaped even if it did not trigger the defect.
7. **Stop rationally:** Stop investigating when evidence supports a sufficiently safe decision and additional tests have low information value relative to risk/cost; otherwise ask for missing access/data or select a reversible mitigation. Record uncertainty.
8. **Explore recurrence surface:** Search sibling endpoints, versions, tenants, queues, templates or similar contracts when risk warrants. Fixing one instance does not imply the class of failures is gone.

## Evidence hierarchy (guidance, not numerical proof)

- **Strong:** bounded reproducible test showing failure-before/pass-after with independent runtime or contract signals; controlled intervention that separates causal alternatives; correlated trace and invariant violation across relevant boundaries.
- **Moderate:** several independent logs/metrics/code-path observations consistent with a mechanism, without a safe decisive intervention.
- **Weak:** temporal correlation alone, one stack trace, a plausible code smell, one LLM explanation, one green test, or symptom disappearance after an uncontrolled change.

Evidence must be relevant and timestamp/context scoped. One “strong” test may still be confounded; conflicting data requires explicit reconciliation. Do not equate a patch's passing test with a confirmed historical root cause.

## Prevention taxonomy

For material failures propose measures in different categories, not only more patches:

- **Prevent:** remove invalid assumptions, improve contracts, validation, idempotency, access isolation, capacity limits, version compatibility.
- **Detect:** add targeted observability/alerts, integrity checks, contract tests, semantic evals or anomaly signals.
- **Contain:** isolate fault domains, enforce budgets, circuit breakers, bulkheads, feature flags, human approval boundaries.
- **Recover:** safe retries where supported, rollback/replay procedures, backups, tested restoration and runbooks.

Use action items with **owner + measurable acceptance criterion + priority + tracking reference** for substantial incidents. Avoid vague “add monitoring” tasks.
