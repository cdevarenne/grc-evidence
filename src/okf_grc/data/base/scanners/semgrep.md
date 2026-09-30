---
type: Scanner
title: Semgrep
description: Static analysis of application code.
resource: https://github.com/semgrep/semgrep
tags: [sast, cc6.1]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-25T00:00:00+00:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-25T14:50:00-07:00"
---
# Covers

Pattern-based static analysis of the Python source, using the vendored ruleset
in `policies/semgrep/` so results are offline and reproducible.

# Evidences

- [CC6.1 — Logical Access](../controls/cc6.1.md)

# Rules

Rule-to-control declarations live on guardrail concepts, for example
[Bound every LLM call](../policies/llm-unbounded-call.md).
