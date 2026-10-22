## Root-Cause-First Engineering Policy

For substantive software or operational work, apply the `root-cause-first` skill.
Classify failures, active incidents and planned changes separately; choose diagnostic depth by impact, uncertainty and action risk.
For failures, investigate evidence and causal alternatives before claiming a permanent fix. For planned changes, analyze current behavior, dependencies and side effects without inventing a root cause.
During incidents, prioritize **authorized safe containment** over lengthy investigation; do not call a mitigation a confirmed correction.
Never fabricate tests, traces, approvals or causal certainty. Verify actual user/system outcomes and report incomplete work precisely.
Propagate evidence, uncertainty and verification obligations to subagents. For high-risk tasks, keep investigation, implementation and verification logically separate.
If strict enforcement is required, implement approval and state-transition guards in the orchestrator workflow; text instructions alone are not an access-control mechanism.
