---
type: Semgrep Rule
title: Bound every LLM call
description: Every model call sets both a timeout and a token limit.
resource: ../../policies/semgrep/llm-unbounded-call.yaml
tags: [semgrep, ai, iso42001:a.6]
rule_ids:
  - semgrep:llm-unbounded-call
sdks: [anthropic, langchain]  # the AI SDKs the rule reads
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-29T17:21:00-07:00"
  - by: "human:cdevarenne"
    at: "2026-10-01T09:25:00-07:00"
---
# Rule

A model call with no timeout can hang a request worker; a call with no
token limit has no cap on cost or output size. The rule reads Anthropic SDK
calls (`messages.create`) and LangChain chat models (`Chat*(...)`).

# Satisfies

- [A.6 — AI system life cycle](../controls/iso42001/a.6.md)

The EU AI Act robustness article (Art. 15) is a high-risk obligation, so this
rule is not declared against it; see the crosswalk for the link.

# Enforced at

- Semgrep in CI, using the vendored ruleset in `policies/semgrep/`

# Remediation

Pass `timeout=` and `max_tokens=` on every `messages.create` call, or set
`timeout` and `max_tokens` (`max_output_tokens` for Google) on the LangChain
chat model, sized to the feature's latency and cost budget.
