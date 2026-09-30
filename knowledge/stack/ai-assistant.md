---
type: Stack Component
title: AI assistant feature
description: DRF views that send widget text to an LLM and return or store the result; never run.
resource: ../../app/assistant/
tags: [ai, django, drf, python, llm]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-29T17:21:00-07:00"
---
# What it is

Two views: `summarize` returns a model-written summary of a widget, and
`rewrite_description` stores model output on the widget. Seeded with
AI-governance issues AI-1 to AI-6; see `app/SEEDED.yaml`.

# Controls that apply

- [CC6.1 — Logical Access](../controls/cc6.1.md)
- [A.4 — Resources for AI systems](../controls/iso42001/a.4.md)
- [A.6 — AI system life cycle](../controls/iso42001/a.6.md)
- [A.7 — Data for AI systems](../controls/iso42001/a.7.md)
- [Art. 50 — Transparency obligations for certain AI systems](../controls/eu-ai-act/art-50.md)

# Declared in

- [AI system inventory](../ai-inventory.md)

# Scanned by

- [Semgrep](../scanners/semgrep.md)
- [Conftest](../scanners/conftest.md)
