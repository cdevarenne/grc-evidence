---
type: Stack Component
title: GRC agent LLM step
description: The optional Claude API step of this tool (narrate, triage, eval) and its usage ledger.
resource: ../../.claude/skills/grc-continuous-compliance/scripts/llm.py
tags: [ai, llm, grc-agent, self-evidence]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# What it is

The skill's own AI component. `llm.py` sends small digests of the bundle and the
scan to Claude and validates what comes back; the model writes prose and
proposals, never a status, a count, or a mapping.

# Bounds

Every synchronous call sets `max_tokens` and a 60-second timeout; a per-run
budget guard (`LLM_BUDGET_USD`) stops a call before it could overspend; the API
key comes from the environment.

# Record-keeping

Every call appends one line to `out/llm-usage.jsonl`: time, run id, task, mode,
model, a hash of the prompt, token counts, and cost. Prompts themselves are not
logged, only their hash. The report footer summarizes the run.

# Controls that apply

- [A.6 — AI system life cycle](../controls/iso42001/a.6.md): bounded calls
  (`max_tokens`, timeout, budget guard), secrets from the environment,
  validated output.
- [A.7 — Data for AI systems](../controls/iso42001/a.7.md): digests instead of
  raw findings; prompts hashed, not logged.
- [Art. 12 — Record-keeping](../controls/eu-ai-act/art-12.md): the ledger is an
  automatic event log. The article binds high-risk systems only; this tool is
  not one, so the link is good practice, not an obligation.

# Scanned by

- [Semgrep](../scanners/semgrep.md): the `llm-*` rules report no findings on
  `llm.py` (`semgrep scan --config policies/semgrep .claude/skills/grc-continuous-compliance/scripts`).
  They are not part of `make scan`, which targets `app/` only.
