# Mini Spec C — Suppression Workflow (reviewed, expiring, never silent)

- **Date:** 2026-09-28
- **Status:** reviewed 2026-09-28 (decisions in §8)
- **Depends on:** v1, Spec A (framework keys). Spec B is untouched except where noted.
- **LLM cost:** none. The workflow is deterministic.

## 1. Why

v1 has no way to say "this finding is wrong" or "we accept this risk until a
date". Today every finding stays open forever, so real signal drowns in known
noise, and the only escape is a scanner-native inline skip that hides the
finding with no owner, reason, or end date. A GRC tool needs the opposite: a
suppression that is written down, reviewed by a person, expires, and stays
visible in every output.

## 2. Goal and definition of done

A suppression is a reviewed record in the bundle. It changes how one matching
finding is counted, never whether the finding is shown.

**Done when:**

1. A `false-positive` suppression removes its finding from the control's status
   and from the coverage-gap list, and the report lists it under **Suppressed**
   with owner, reason, and expiry.
2. An `accepted-risk` suppression keeps its finding on the control, marked
   accepted, and leaves the control's status unchanged (`not-satisfied`: an
   accepted risk is still a violation). OSCAL records each accepted finding as a
   risk with status `deviation-approved`.
3. An expired suppression no longer applies: the finding is counted again and
   the report lists the suppression under **Expired suppressions**.
4. A suppression that matches no finding is listed under **Unused
   suppressions**, so stale records get removed.
5. The bundle conformance test rejects a suppression without an owner, a
   reason, an expiry within 90 days of approval, or a human `verified` entry.
6. OSCAL output still validates. `make test` and `make test-integration` pass.

**Out of scope:** scanner-native inline skips (still honored by the scanners
themselves), bulk or wildcard suppressions, approval workflows outside git.

## 3. Rules

- **No wildcards.** A suppression matches one finding by `tool`, `rule_id`, and
  `target`, exactly. An optional `message_contains` narrows it further (one rule
  can fire on several resources in one file).
- **It never maps anything.** A suppression cannot move a finding onto a
  control or off one. Grounding is unchanged.
- **Accepted risk needs a control.** `accepted-risk` applies only to a finding
  that maps to a control; on a coverage gap it is rejected at load time
  (there is no control whose risk is being accepted).
- **Expiry is mandatory.** At most 90 days after approval. The date used for
  expiry is injectable (`--today`) so tests are deterministic.
- **Review is the gate.** A suppression is a concept like any other: it needs a
  human `verified` entry, and the conformance test fails without one.

## 4. Bundle changes (`knowledge/`)

New folder and concept type:

```
knowledge/suppressions/
├── index.md
└── <id>.md        type: Suppression
```

```yaml
type: Suppression
title: Namespace is set at deploy time, not in the manifest
kind: false-positive          # false-positive | accepted-risk
finding:
  tool: checkov
  rule_id: CKV_K8S_21
  target: app/k8s/service.yaml
  message_contains: "Service.default.widgets-api"   # optional
owner: human:cdevarenne
approved: "2026-09-28"
expires: "2026-12-27"         # <= approved + 90 days
tags: [suppression]
verified: [...]
```

Body sections: `# Reason` (required), `# Compensating control` (optional; for
`accepted-risk`).

## 5. Code changes

- `okf_lib.py`: parse `Suppression` concepts; validate `kind`, `finding`,
  `owner`, dates, the 90-day window. `MAX_SUPPRESSION_DAYS = 90`. `Bundle.suppressions()`.
- `map_findings.py`: match each finding against active suppressions (after
  mapping, before status). New top-level keys in `mapping.json`:
  - `suppressed`: `[{finding, suppression, kind, controls}]`;
  - `expired_suppressions`, `unused_suppressions`: suppression ids.
  - `false-positive` findings leave `controls[*].findings` and `unmapped`.
  - `accepted-risk` findings stay in `controls[*].findings` with
    `"accepted": "<suppression id>"`; the status is unchanged. No new status.
  - `--today` (default: the current UTC date).
- `to_oscal.py`: accepted risks become `risks` with status
  `deviation-approved`, linked to the finding's observation; the control's
  finding stays `not-satisfied`. False positives keep their observation and are
  named in `remarks`, never as findings. `docs/oscal-subset.md` documents both.
- `render_report.py`: sections **Suppressed**, **Expired suppressions**,
  **Unused suppressions**; accepted findings marked inline; the risk-posture
  line counts suppressed findings separately.
- `digest.py` (Spec B): the scan digest counts open findings only, with
  suppressed and accepted findings as separate counts, so narrate never
  describes them as open.

## 6. Sample data

- One `false-positive` on a real coverage gap from the sample scan that is not a
  seeded issue (seed S2 must stay an honest gap).
- One `accepted-risk` on a mapped finding, with a compensating-control note.
- Unit-test fixtures (not in `knowledge/`): an expired suppression, an unused
  one, and an `accepted-risk` on a gap (rejected).
- `app/SEEDED.yaml` gains an `expect.suppressed: <kind>` form, asserted by the
  integration test.

## 7. Tests

- Unit: exact matching and `message_contains`; expiry at the boundary day;
  unused detection; `accepted-risk` on a gap rejected; statuses for both kinds;
  OSCAL `deviation-approved` risk validates; report sections (golden file).
- Conformance: every suppression has owner, reason, window ≤ 90 days, and a
  human `verified` entry.
- Integration: the two sample suppressions land as expected; OSCAL validates.

## 8. Review decisions (2026-09-28)

1. **Accepted risk keeps the status `not-satisfied`; no new status.** The
   acceptance is recorded on the finding, in the report, and in OSCAL as a
   `deviation-approved` risk. (A separate `risk-accepted` status was considered
   and dropped: OSCAL findings have only `satisfied` and `not-satisfied`, so it
   would not survive into the machine-readable output.)
2. **90-day maximum window.**
3. **Suppressions live in `knowledge/`** as reviewed concepts.

## 9. Tasks (estimate: 2 focused days)

1. `okf_lib`: `Suppression` concept, validation, conformance rules.
2. `map_findings`: matching, expiry, unused; `mapping.json` keys; `--today`.
3. `to_oscal`: `deviation-approved` risks; false-positive remarks; schema tests.
4. `render_report`: the three sections and inline markers; golden file.
5. `digest.py`: open-only counts for narrate.
6. Sample suppressions (human gate: review and `verified`), `SEEDED.yaml`,
   integration test.
7. README: "Suppressions" section; remove the "No suppression workflow" limit.
