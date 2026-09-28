# Mini Spec D — OSCAL Assessment Plan

- **Date:** 2026-09-28
- **Status:** reviewed 2026-09-28 (all three §8 recommendations accepted)
- **Depends on:** v1, Spec A (frameworks, applicability), Spec C (suppression policy).
- **LLM cost:** none.

## 1. Why

`assessment-results.json` points at an assessment plan that does not exist:
its required `import-ap` is the placeholder `#assessment-plan-not-modeled`. An
auditor reading the results cannot see what was planned: which controls were
in scope, which tools ran with which versions, against which components, under
which rules for exceptions. This spec emits a real OSCAL 1.2.3 assessment plan
from the same bundle and links the results to it.

## 2. Goal and definition of done

`make scan` also writes `out/oscal/assessment-plan.json`, and the results
import it.

**Done when:**

1. `out/oscal/assessment-plan.json` validates against the NIST OSCAL 1.2.3
   assessment-plan schema (vendored in `tests/fixtures/oscal/`).
2. `assessment-results.json` sets `import-ap.href` to `assessment-plan.json`
   (the file next to it); the `#assessment-plan-not-modeled` placeholder is gone.
3. The plan names, per framework, the controls in scope; every control the
   results review is in the plan (tested as a subset).
4. The plan lists one activity per scanner run, with the command and the
   pinned version from `tools.lock`, and the controls its declared rules
   evidence.
5. The plan's subjects are the bundle's stack components, with the same UUIDs
   as in `component-definition.json`.
6. The suppression policy (exact match, human review, 90-day maximum) is stated
   in the plan's terms and conditions.
7. Output is deterministic for a fixed `--now`; `make test` and
   `make test-integration` pass.

**Out of scope:** a system security plan (SSP), POA&M, OSCAL profiles, and
manual test procedures.

## 3. The one remaining placeholder

The assessment-plan schema requires `import-ssp` (a link to a system security
plan). This repo does not model an SSP, so the plan carries
`#system-security-plan-not-modeled`, documented in `docs/oscal-subset.md`. The
placeholder moves one step down the chain; it does not disappear. Modeling an
SSP is its own spec.

## 4. Plan contents (`to_oscal.py`)

| Field | Source |
|---|---|
| `metadata` | title, `last-modified` (`--now`), version, `oscal-version` 1.2.3 |
| `import-ssp.href` | `#system-security-plan-not-modeled` (see §3) |
| `local-definitions.components` | one per `Stack Component` concept, same UUID as the component-definition |
| `local-definitions.activities` | one per scanner run in `run_scan.py` (Semgrep, Trivy config, Trivy fs, Checkov, Conftest): a step with the command, a prop with the pinned version, `related-controls` = in-scope controls its declared rules evidence |
| `terms-and-conditions` | the suppression policy (§2.6) and the grounding rule, as parts |
| `reviewed-controls` | one `control-selection` per framework: the controls in scope (§5) |
| `assessment-subjects` | `component` subjects, one per stack component |
| `assessment-assets.assessment-platforms` | one platform: the `make scan` pipeline with its pinned tools |
| `tasks` | one `action` task, "Automated compliance scan", with every activity and every subject |

The results keep their own `reviewed-controls` (what was actually reviewed);
the plan says what was intended.

## 5. Which controls are "in scope"

Recommended: **every applicable control in the bundle** — all controls except
those `not-applicable` at the declared AI risk tier — including controls no
scanner evidences. The plan then shows the gap between intent and evidence
directly: a control planned but `not-assessed` in the results is a coverage gap
at the control level.

Alternative: only controls some rule declaration evidences (the plan would
then match the results by construction and show no gap).

## 6. Code changes

- `to_oscal.py`: `assessment_plan(bundle, mapping, now)`; `assessment_results`
  sets `import-ap.href` to `assessment-plan.json`; `main()` writes the third
  file. The plan's UUID is stable for a fixed `--now`.
- `run_scan.py`: expose the scanner runs (name, argv, pinned version key) as
  data the plan can read, so the plan cannot drift from what actually runs.
- `tests/fixtures/oscal/oscal_assessment-plan_schema.json`: vendored NIST schema.
- `docs/oscal-subset.md`: an assessment-plan table; the `import-ap` row changes;
  the new `import-ssp` placeholder is listed.

## 7. Tests

- Unit: schema validation; determinism; `import-ap.href`; AR reviewed controls
  ⊆ AP reviewed controls; not-applicable controls excluded from the plan;
  component UUIDs equal the component-definition's; one activity per scanner
  run with its pinned version; suppression policy present.
- Integration: all three OSCAL files validate after `make scan`.

## 8. Design choices to confirm in review

1. **In-scope controls = every applicable control** (recommended, §5).
2. **`import-ssp` placeholder** `#system-security-plan-not-modeled` rather
   than a minimal generated SSP (recommended: an SSP is a larger model and its
   own spec).
3. **Relative `import-ap.href`** `assessment-plan.json` (recommended: the
   files travel together in `out/oscal/`).

## 9. Tasks (estimate: 1–2 focused days)

1. Vendor the assessment-plan schema; scanner runs as data in `run_scan.py`.
2. `assessment_plan()` with schema, determinism, and content tests.
3. Results import the plan; subset test; integration validates three files.
4. `docs/oscal-subset.md` and README: the plan, the moved placeholder.
