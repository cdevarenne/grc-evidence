---
type: Semgrep Rule
title: No hard-coded LLM API keys
description: Model-provider API keys must come from the environment or a secret store.
resource: ../../policies/semgrep/llm-hardcoded-key.yaml
tags: [semgrep, ai, cc6.1, iso42001:a.6]
rule_ids:
  - semgrep:llm-hardcoded-key
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Rule

A string literal assigned to an `*_API_KEY` name puts a credential in source
control, where anyone with read access can use it.

# Satisfies

- [CC6.1 — Logical Access](../controls/cc6.1.md)
- [A.6 — AI system life cycle](../controls/iso42001/a.6.md)

# Enforced at

- Semgrep in CI, using the vendored ruleset in `policies/semgrep/`

# Remediation

Read the key from the environment (for example `os.environ["ANTHROPIC_API_KEY"]`)
or a secret manager, and rotate any key that was committed.
