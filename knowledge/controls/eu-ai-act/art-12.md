---
type: EU AI Act Article
framework: eu-ai-act
title: Art. 12 — Record-keeping
description: High-risk AI systems automatically log events over their lifetime.
tags: [eu-ai-act, eu-ai-act:art-12]
applies_when:
  risk_tier: [high]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-28T11:45:59-07:00"
---
# Intent

A high-risk system records events automatically, so its operation can be
traced after the fact. The records themselves must be protected.

# Scope

Applies to high-risk AI systems only (Chapter III). The sample app declares
`risk_tier: limited` in `app/ai-inventory.yaml`, so this article reports
`not-applicable`.

# Source

[Regulation (EU) 2024/1689, Article 12](https://eur-lex.europa.eu/eli/reg/2024/1689/oj) (paraphrased).

# Satisfied by

- [Do not log prompts or completions](../../policies/llm-prompt-logged.md)

# Crosswalk

- [ISO/IEC 42001 ↔ EU AI Act](../../crosswalk/iso42001-ai-act.md)
