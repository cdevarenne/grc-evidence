---
type: Rego Policy
title: AI inventory is complete
description: Every AI component of the app has an entry in the AI system inventory.
resource: ../../policies/rego/ai_inventory_complete.rego
tags: [opa, conftest, ai, iso42001:a.4]
rule_ids:
  - conftest:ai_inventory_complete
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-28T11:45:59-07:00"
---
# Rule

The AI inventory (`ai-inventory.yaml` under the scan target) lists every component with its kind and every
inventoried AI system. A component of kind `assistant` with no system entry is
an AI feature the organization does not govern.

# Satisfies

- [A.4 — Resources for AI systems](../controls/iso42001/a.4.md)

# Enforced at

- Conftest in CI, reading the AI inventory

# Remediation

Add a `systems` entry for the component with its owner, model provider, and
purpose, then review its risk tier.
