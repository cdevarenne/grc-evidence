---
type: Semgrep Rule
title: Bound every LLM call
description: Every model call sets both a timeout and a max_tokens limit.
resource: ../../policies/semgrep/llm-unbounded-call.yaml
tags: [semgrep, ai, iso42001:a.6]
rule_ids:
  - semgrep:llm-unbounded-call
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Rule

A model call with no timeout can hang a request worker; a call with no
`max_tokens` bound has no cap on cost or output size.

# Satisfies

- [A.6 — AI system life cycle](../controls/iso42001/a.6.md)

The EU AI Act robustness article (Art. 15) is a high-risk obligation, so this
rule is not declared against it; see the crosswalk for the link.

# Enforced at

- Semgrep in CI, using the vendored ruleset in `policies/semgrep/`

# Remediation

Pass `timeout=` and `max_tokens=` on every `messages.create` call, sized to the
feature's latency and cost budget.
