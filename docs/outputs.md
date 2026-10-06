# Outputs

What a scan writes to `out/`, and the contract downstream tools can rely on.

## Output contract

`make scan` (`grc run`) writes `out/findings.json` and `out/mapping.json`, each
with a `schema_version`, and ends with `out/run.json`: the run id, the scanned
commit, whether the scan inputs differed from it (`dirty`: changed tracked files,
or untracked files under the target, which are listed in `untracked`), the
engine, base bundle, and scanner versions, the resolved scan layout, and the
sha256 of every output. The OSCAL assessment results carry the same run id.

`grc run` writes into a staging directory and moves the outputs into `out/` only
after `run.json` exists, so a failed run leaves the previous run whole.
`grc run --require-clean` refuses to scan inputs that differ from the commit,
or a directory outside git; CI should use it. JSON Schemas for
the three files ship with the engine in `src/grc_evidence/data/schemas/`; additive
changes bump the minor version, anything else the major. A sample is in
[`examples/run.json`](../examples/run.json).

## Type 2 evidence (Spec H)

When `grc.yaml` lists GitHub repos with collectors, `grc run` also writes
`out/collect/`, and `run.json` hashes each file it wrote (contract 1.2):

| File | What it holds |
|---|---|
| `collect/github-findings.json` | the collectors that ran (`collectors`) and their findings, tool `github`, targets `github:<owner>/<name>` or `github:<owner>/<name>#<number>` |
| `collect/scm-posture.json` | per repo: the default branch, whether its rules are readable, required reviews, required checks, `bypass`, and each scanner job (present, can fail) |
| `collect/population.csv` | one row per change merged into a production branch in the window: `repo,number,title,author,merged_by,merged_at,merge_sha,base,approvers,flags` |
| `collect/changes.json` | the same rows with the checks on each merge commit, and per repo the summary: `in_population`, `merged_all_branches` (the denominator) and a count per flag |

Commands that read them:

- `grc sample --list sample.csv` writes `out/collect/sample-evidence.csv`
  (`repo,number,merged_at,approvers,ci_conclusion,scanner_checks,missing`) for
  the changes an auditor sampled. A change with a gap is listed in `missing`.
- `grc window` writes `out/window.json` and `out/window.md`: per control, the
  first date it was satisfied, the last evidence, and the gaps over the window.

The evidence ledger (`evidence/ledger.jsonl`, written only when `grc.yaml` has a
`window`) is append-only JSON Lines with a hash chain; `grc ledger verify`
checks it. Each line records the collector, the repo, the window, what was
read, the hash of each output, the summary and the rate-limit cost. Samples:
[`examples/collect/`](../examples/collect/).

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
