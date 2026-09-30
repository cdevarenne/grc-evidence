---
type: ISO/IEC 42001 Control
framework: iso42001
title: A.6 — AI system life cycle
description: AI systems are designed, built, deployed, and operated under defined controls.
tags: [iso42001, iso42001:a.6]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-29T17:21:00-07:00"
---
# Intent

An AI system is built and run with the same engineering discipline as other
production software: secrets are managed, calls to models are bounded, and
deployment and operation follow documented requirements.

# Clause

ISO/IEC 42001:2023 Annex A, control group A.6 (AI system life cycle). Clause id
and group name only; the standard's text is not reproduced here.

# Satisfied by

- [No hard-coded LLM API keys](../../policies/llm-hardcoded-key.md)
- [Bound every LLM call](../../policies/llm-unbounded-call.md)

# Crosswalk

- [SOC 2 ↔ ISO/IEC 42001](../../crosswalk/soc2-iso42001.md)
- [ISO/IEC 42001 ↔ EU AI Act](../../crosswalk/iso42001-ai-act.md)
