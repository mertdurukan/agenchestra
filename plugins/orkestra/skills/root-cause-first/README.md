# root-cause-first (v2.1.0)

A reusable Claude Code / Agent Skills workflow for evidence-driven engineering investigation, planned change analysis, and verification discipline.

## Install

Copy this whole folder to `<repository>/.claude/skills/root-cause-first/` for project scope, or `~/.claude/skills/root-cause-first/` for personal scope. Invoke with `/root-cause-first` or let Claude load it when relevant. A short always-on rule in your project's `CLAUDE.md` is recommended for consistent discovery (see the separately delivered `CLAUDE_HANDOFF_ROOT_CAUSE_FIRST.md`).

The skill does not install any hooks or modify permissions. It is **not** by itself an enforcement mechanism. Optional validator: `python scripts/validate_record.py examples/diagnostic-record.example.json`, `python scripts/test_validate_record.py`.

## Files

- `SKILL.md` — main decision and workflow protocol.
- `references/method-selection.md` — when and how to use different diagnosis techniques.
- `references/symptom-hypothesis-catalog.md` — testable alternative explanations, not presumed causes.
- `references/agentic-llm-diagnostics.md` — routing, planning, retrieval, tool, generation, guardrail and eval analysis.
- `references/orchestration-gates.md` — gate semantics and delegation/evidence contracts.
- `references/evaluation-cases.md` — behavior eval rubric.
- `scripts/` and `examples/` — optional self-contained structural checks.

Use actual environment evidence and respect existing production/change approvals. Emergency containment can precede deep RCA when authorized; reported confidence and closure must match observed checks.
