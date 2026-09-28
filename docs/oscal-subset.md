# OSCAL subset emitted

`to_oscal.py` emits OSCAL **1.2.3** JSON. Both documents validate against the
NIST JSON schemas vendored in `tests/fixtures/oscal/`. This is a documented
subset, not a complete OSCAL implementation.

## component-definition.json

| Field | Source |
|---|---|
| `metadata` | title, `last-modified` (scan time), `version` 0.1.0, `oscal-version` 1.2.3 |
| `components[]` | one per `Stack Component` concept; `type: software` |
| `control-implementations[]` | one per framework the component's concept links to (SOC 2, ISO/IEC 42001, EU AI Act) |
| `control-implementations[].implemented-requirements[]` | one per linked control that some concept declares rules for; `control-id` is the code within that framework's source (`cc6.1`, `a.6`, `art-50`) |
| `control-implementations[].source` | `#<uuid>` of that framework's back-matter resource: "AICPA Trust Services Criteria (SOC 2)"; "ISO/IEC 42001:2023 Annex A (placeholder …)"; "Regulation (EU) 2024/1689 (EU AI Act)" with an `rlinks` href to EUR-Lex |

## assessment-results.json

| Field | Source |
|---|---|
| `import-ap.href` | **placeholder** `#assessment-plan-not-modeled`: v1 has no assessment plan |
| `results[0].reviewed-controls` | one `control-selection` per framework, described by the framework's source title; includes every control whose status is not `not-assessed` or `not-applicable` |
| `results[0].observations[]` | one per scanner finding; `methods: [TEST]` |
| `results[0].findings[]` | one per control with open violations; `target.status.state` is always `not-satisfied` |
| `results[0].risks[]` | one per unmapped finding, titled "Coverage gap: …", `status: open` |
| `results[0].remarks` | lists controls with no violations detected, controls not assessed, and controls not applicable at the declared AI risk tier (by `framework:code` key) |

## Deliberately not modeled

- Assessment plan, SSP, POA&M, and profiles.
- A machine-readable SOC 2 catalog: the Trust Services Criteria are not
  published as an OSCAL catalog, so `control-id` values are the criterion codes.
- Parties, roles, and responsible-parties.
- A `satisfied` finding: a clean automated scan evidences a control but does not
  attest it, so controls with no violations are listed in `remarks` instead.
- Coverage gaps as `findings`: an OSCAL finding must target a control, and
  targeting one would invent the mapping the grounding rule forbids.
- An ISO/IEC 42001 catalog: ISO publishes no OSCAL catalog and the text is
  copyrighted, so the source is a clean-room placeholder resource with no link,
  and `control-id` values are the Annex A group ids (`a.6`).
- `not-applicable` as a finding: a control excluded by the declared AI risk tier
  is not assessed, so it is named in `remarks`, never reported as a pass.
