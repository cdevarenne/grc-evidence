# OSCAL subset emitted

`to_oscal.py` emits OSCAL **1.2.3** JSON: a component definition, an assessment
plan, and assessment results, side by side in `out/oscal/`. All three validate
against the NIST JSON schemas vendored in `tests/fixtures/oscal/`. This is a documented
subset, not a complete OSCAL implementation.

## component-definition.json

| Field | Source |
|---|---|
| `metadata` | title, `last-modified` (scan time), `version` 0.1.0, `oscal-version` 1.2.3 |
| `components[]` | one per `Stack Component` concept; `type: software` |
| `control-implementations[]` | one per framework the component's concept links to (SOC 2, ISO/IEC 42001, EU AI Act) |
| `control-implementations[].implemented-requirements[]` | one per linked control that some concept declares rules for; `control-id` is the code within that framework's source (`cc6.1`, `a.6`, `art-50`) |
| `control-implementations[].source` | `#<uuid>` of that framework's back-matter resource: "AICPA Trust Services Criteria (SOC 2)"; "ISO/IEC 42001:2023 Annex A (placeholder …)"; "Regulation (EU) 2024/1689 (EU AI Act)" with an `rlinks` href to EUR-Lex |

## assessment-plan.json

What the scan intends to assess. Props this repo defines use the namespace
`https://github.com/cdevarenne/okf-grc-skill/ns/oscal`.

| Field | Source |
|---|---|
| `import-ssp.href` | **placeholder** `#system-security-plan-not-modeled`: no system security plan is modeled |
| `local-definitions.components[]` | one per `Stack Component` concept, with the same UUID as in the component definition |
| `local-definitions.activities[]` | one per scanner run in `run_scan.py` (Semgrep; Trivy config; Trivy fs; Checkov; Conftest): a step with the exact command, a `tool-version` prop from `tools.lock`, a `method` prop `TEST`, and `related-controls` = the in-scope controls that some concept declares that tool's rules for |
| `terms-and-conditions.parts[]` | the suppression policy (`rules-of-engagement`) and the grounding rule (`methodology`) |
| `reviewed-controls` | one `control-selection` per framework: **every control applicable at the declared AI risk tier**, including controls no scanner evidences; `remarks` names the not-applicable ones |
| `assessment-subjects[]` | the stack components, selected by UUID |
| `assessment-assets` | one component per scanner, titled with its pinned version; one platform (`make scan`) that uses them |
| `tasks[]` | one `action` task, "Automated compliance scan", associating every activity with every subject |

A control in the plan that the results mark `not-assessed` is a coverage gap
at the control level: it was intended but no scanner evidences it. Trivy's two
runs share one tool name, so each lists every control a Trivy rule evidences.

## assessment-results.json

| Field | Source |
|---|---|
| `import-ap.href` | `assessment-plan.json`, the plan written next to it (relative, so the files travel together) |
| `results[0].reviewed-controls` | one `control-selection` per framework, described by the framework's source title; includes every control whose status is not `not-assessed` or `not-applicable` (always a subset of the plan's) |
| `results[0].observations[]` | one per scanner finding; `methods: [TEST]` |
| `results[0].findings[]` | one per control with open violations; `target.status.state` is always `not-satisfied` |
| `results[0].risks[]` | one per unmapped finding, titled "Coverage gap: …", `status: open`; and one per accepted-risk suppression, titled "Accepted risk: …", `status: deviation-approved`, with the owner, expiry, and reason in its description |
| `results[0].remarks` | lists controls with no violations detected, controls not assessed, controls not applicable at the declared AI risk tier (by `framework:code` key), and false-positive suppressions (by suppression id) |

## Deliberately not modeled

- SSP, POA&M, and profiles. The assessment plan's required `import-ssp` is
  therefore a placeholder.
- Manual test procedures: every planned activity is an automated scanner run.
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
- A suppressed finding as a pass: a false positive keeps its observation and is
  named in `remarks`; an accepted risk keeps its control's `not-satisfied`
  finding and adds a `deviation-approved` risk. OSCAL findings have only
  `satisfied` and `not-satisfied`, so there is no separate accepted state.
