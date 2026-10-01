# Outputs

What a scan writes to `out/`, and the contract downstream tools can rely on.

## Output contract

`make scan` (`grc run`) writes `out/findings.json` and `out/mapping.json`, each
with a `schema_version`, and ends with `out/run.json`: the run id, the scanned
commit (and whether tracked files had uncommitted changes), the engine, base
bundle, and scanner versions, the resolved scan layout, and the sha256 of every
output. The OSCAL assessment results carry the same run id. JSON Schemas for
the three files ship with the engine in `src/okf_grc/data/schemas/`; additive
changes bump the minor version, anything else the major. A sample is in
[`examples/run.json`](../examples/run.json).

## OSCAL output

`make scan` writes three OSCAL 1.2.3 documents to `out/oscal/`, each validated
against the NIST schema in the tests:

- **`component-definition.json`**: the stack components and the controls each
  one implements, one source per framework.
- **`assessment-plan.json`**: what the scan intends to assess. Every control
  applicable at the declared AI risk tier (including controls no scanner
  evidences), one activity per scanner run with its exact command and pinned
  version, the stack components as subjects, and the suppression policy and
  grounding rule as terms and conditions.
- **`assessment-results.json`**: what the scan found. It imports the plan, so a
  control the plan names and the results mark `not-assessed` reads as a gap
  in coverage, not a pass.

The plan's required link to a system security plan is a placeholder
(`#system-security-plan-not-modeled`); no SSP is modeled. See
[`docs/oscal-subset.md`](oscal-subset.md) and the sample output in
[`examples/oscal/`](../examples/oscal/).
