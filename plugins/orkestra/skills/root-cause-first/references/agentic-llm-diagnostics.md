# Agentic AI / LLM / RAG — Stage-wise Root-Cause Playbook

**Core rule:** An incorrect final response is a symptom, not a diagnosis of “bad prompt.” Localize the first incorrect decision or artifact in the complete execution trace before choosing prompt, policy, schema, data or code changes.

## Capture and safely replay a representative failure

Record (redacting personal data, tenant secrets and credentials):

- User intent, expected behavior, actual outcome, acceptance criteria and risk level.
- Conversation/context version, system/developer instruction revisions, model/deployment identifiers, available tool catalog/schema versions and routing/policy configuration.
- Trace/span or run ID, agent transitions, selected/omitted tools, tool arguments/results, validation/guardrail decisions, retrieval queries/results and terminal synthesis.
- Data/knowledge index version, timestamps, environment/tenant scope, permissions, timeout/retry budget and dependencies.
- Evaluation item identifier, expected tool/plan/output when known, and whether failure is **reproducible, stochastic or input-distribution-specific**.

Do not assume identical model inputs guarantee identical output. Freeze deterministic components, then sample a representative set of LLM runs where variability matters. Never dump sensitive prompt or tool payloads into unprotected logs or reports.

## Locate the first failing boundary

| Trace boundary | Distinguishing evidence | Investigate before changing |
| --- | --- | --- |
| Intent interpretation | User intent vs extracted task/entities/constraints | Ambiguity, missing context, schema of intent, normalization |
| Routing / policy | Wrong domain/tool/workflow selected | Routing registry, priority/conflicts, policy precedence, guardrails, evaluation examples |
| Planning / orchestration | Steps reordered, omitted, repeated, unjustified handoff | DAG dependencies, budget/termination rules, state transitions, workflow ownership |
| Tool contract / arguments | Tool correct but args invalid or mismapped | Parametric schema, validation, type system, naming, defaults, authorized scopes |
| Domain tool / execution | Correct call but wrong result or side effect | Service logic, DB queries, permissions, freshness, idempotency, error propagation |
| Retrieval | Necessary source not found or wrong evidence ranked | Query transform, ACL filters, parsing/chunking/index, retrieval recall, rerank, metadata, version |
| Context assembly | Correct evidence retrieved but omitted/distorted | Packing, truncation, citation mapping, conflicting context, instruction priority |
| Generation / reasoning | Evidence available but conclusion unsupported | Output contract, groundedness, ambiguity, model limits, constrained generation |
| Guardrails / safety | Unsafe content acted on, valid request wrongly blocked | Trust boundaries, injection paths, policy evaluation, false positive/negative patterns |
| Verification / evaluation | Wrong answer marked correct or regression missed | Gold labels, grader bias, metric choice, distribution coverage, trace assertions |

A later-stage failure can originate upstream; follow evidence, not component labels. When the correct boundary is unclear, probe tools and policies independently with fixed inputs.

## Distinguishing experiments

1. **Routing failure?** Replay the same normalized intent through the deterministic policy/router; inspect the winning rule and rejected alternatives. If routing is correct but final action wrong, investigate planning/agent compliance.
2. **Tool misuse?** Hold tool output constant, validate selected tool + arguments against schema, permissions and domain invariants; compare correct vs incorrect call traces.
3. **RAG omission?** Check whether expected source appears in candidate retrieval (recall), reranked top-k, final context and cited answer in that order. Fix the first boundary that drops/corrupts it.
4. **Hallucination?** Supply the correct grounded evidence and test structured answer validity/attribution. Do not change retrieval if evidence was already available.
5. **Intermittent errors?** Separate deterministic failures from sample variability; cluster examples by task class, tenant, tool, prompt/model version and trace failure stage.
6. **Guardrail errors?** Inspect trusted-vs-untrusted input origin, normalization, policy decision, tool privilege scope and blocked/allowed exemplars. Add adversarial negatives and positives.
7. **Regression after change?** Compare baseline and candidate on a frozen representative eval dataset, then controlled runtime/canary samples as policy permits. Track quality, false-positive/false-negative tradeoffs, latency, cost and security.

## Verification policy for nondeterministic systems

- **Unit/contract tests:** deterministic parsers, policies, validators, schemas, state transitions, tool error handling.
- **Trace-based tests:** required/forbidden actions, tool selection, order, handoffs, authorized arguments, grounding, escalation, termination.
- **Outcome evals:** task-specific expected behavior, representative failure slices and negative cases, labels reviewed where possible; measure both quality and severe failure rate.
- **Operational checks:** monitoring for drift, changed models/prompts/indexes, latency/token cost, silent fallback and tool side effects.

A single successful LLM run is not a statistically reliable regression signal. No universal pass-rate threshold exists: use task-specific baselines, sample size and risk thresholds. LLM-as-judge scores need calibration against human/domain-owner reviews. Keep security and correctness thresholds separate when stakes warrant.

**Architecture rule:** Prefer deterministic code for known contracts/state transitions, configuration/policy for variable business rules, and LLM reasoning only for tasks requiring interpretation or synthesis. Choose the intervention at the **first proven failing boundary**, not the most easily editable prompt.
