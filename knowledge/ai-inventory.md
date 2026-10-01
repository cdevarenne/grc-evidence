---
type: Reference
title: AI system inventory
description: The inventory file that lists AI components and declares the EU AI Act risk tier.
resource: ../app/ai-inventory.yaml
tags: [ai, inventory, risk-tier]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-29T17:21:00-07:00"
  - by: "human:cdevarenne"
    at: "2026-10-01T09:25:00-07:00"
---
# What it holds

- `risk_tier`: the declared EU AI Act risk class (`minimal`, `limited`, `high`).
  `map_findings.py` reads it and compares it with each control's `applies_when`.
  A control whose `applies_when` excludes the tier reports `not-applicable`,
  never a gap and never `no-violations-detected`.
- `components`: every app component with its `kind`.
- `systems`: the inventoried AI systems. The
  [AI inventory is complete](policies/ai-inventory-complete.md) policy checks
  that every `assistant` component has one. A system may name its `sdk`
  (`anthropic`, `langchain`); when every system does, a control whose only rules
  read none of those SDKs reports `not-assessed`, not `no-violations-detected`.

# Declared tier

The sample app declares `limited`: the assistant talks to people, so Art. 50
applies, but it is not a high-risk use under Annex III.
