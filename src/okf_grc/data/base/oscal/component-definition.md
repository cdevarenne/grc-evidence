---
type: Reference
title: OSCAL output
description: The OSCAL 1.2.3 component-definition and assessment-results the skill emits.
resource: https://pages.nist.gov/OSCAL/
tags: [oscal, nist]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-25T00:00:00+00:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-25T14:50:00-07:00"
---
# Output

- `out/oscal/component-definition.json` — each [stack component](../stack/index.md)
  with the controls that apply to it as implemented requirements.
- `out/oscal/assessment-results.json` — one result: findings per assessed
  control with violations, observations per scanner finding, and coverage gaps
  as open risks. A clean control gets no finding: automation never attests.

# Subset

v1 emits a documented subset of OSCAL, not full conformance. The fields used,
and the placeholders for required fields the demo does not model, are listed in
`docs/oscal-subset.md`.
