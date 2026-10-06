# Limits

What grc-evidence does not do, or does only partly. Read this before relying on a report.

- **Evidence, not attestation** A control with no violations is reported as
  `no-violations-detected`, never `satisfied`. Automated scans evidence a SOC 2
  criterion; they do not attest it.
- **Suppressions are exact and short-lived by design.** Each one matches a
  single finding, lasts at most 90 days, and needs a human review; there are no
  wildcard or bulk suppressions. Scanner-native inline skips (e.g.
  `checkov:skip`) are still honored by the scanners themselves and bypass this
  record.
- **Static manifests only** Helm or Kustomize output is not rendered before
  scanning.
- **Sized for the sample app.** Scanner JSON is read in memory, and the
  scanner set is fixed in `run_scan.py`.
- **Scan layout from `grc.yaml`** By default Conftest reads `k8s/**/*.{yaml,yml}`,
  `infra/**/*.tf`, and `ai-inventory.yaml` under the target. An optional
  `grc.yaml` at the repo root changes the target, the knowledge bundle, the AI
  inventory, Conftest's inputs, directories Trivy and Checkov skip (`skip_paths`,
  e.g. a Helm chart whose templates are not rendered), Checkov's frameworks, and the
  Semgrep and Rego policies, and the time each scanner may run (`scanner_timeout`,
  900 seconds by default; a scanner past it is stopped and named). Conftest inputs
  may reach beside the target with `..` (an inventory next to a submodule) but
  never out of the repo, and a symlink out of the repo is refused unless
  `allow_external_symlinks: true`. See
  `src/grc_evidence/config.py`. Conftest patterns that match nothing stop the scan
  with an error; an explicit `conftest.inputs: []` turns Conftest off instead,
  `run.json` lists it under `not_run`, and a control whose rules are all
  Conftest's reads `not-assessed` (reason `rules-not-run`), not a clean result.
- **LLM eval is small and single-run.** The triage eval has 57 labeled cases,
  labeled by the implementing agent and reviewed by the maintainer, not by an
  independent second labeler. Most configurations were run once; the two final
  candidates were re-run three times, which showed a spread of up to three
  cases per run, so differences of a case or two are not evidence.
- **The bundle is readable anywhere, reusable in part.** Any OKF tool can read
  it (`make render` uses the OKF reference visualizer). The control, crosswalk,
  and scanner concepts carry over to another project; the stack, the policies'
  `rule_ids`, the suppressions, and the AI inventory describe this repo's sample
  app. The engine knows only the three frameworks here: adding one means
  changing `okf_lib.py`, not just adding concepts.
- **Declared risk tier only** The AI Act tier is read from
  `app/ai-inventory.yaml`; nothing classifies the system. There is no
  conformity assessment, model evaluation, or NIST AI RMF control set
  (crosswalk links only).

## Type 2 evidence (Spec H)

- **GitHub only, read only.** The collectors read the GitHub API and never write
  to it. GitLab and other SCMs, live cloud configuration and ticket systems are
  not covered. Target repos are not cloned or scanned by the code scanners
  (Spec H Part B).
- **A posture is the state on the day it is read.** The window report uses only
  the evidence ledger and never back-fills an earlier day from a current
  reading. A repo opts into the ledger with a `window` in `grc.yaml`.
- **What counts as an approval.** A reviewer's latest approving, change-request
  or dismissed review before the merge, not the author's, and only when the
  reviewer can push to the repo and approved the final commit. A comment does
  not withdraw an approval. A bot's review counts only when
  `github.accepted_bots` lists it with a reason; the change then carries the
  flag `bot_approval`, for an auditor to accept or reject.
- **Lists are cut at 100.** GitHub returns at most 100 reviews or checks per
  change. With more, the change is flagged `reviews_incomplete` (no approver
  counts) or `checks_incomplete` (its CI conclusion is `incomplete`).
- **A change can be missed in one run.** The collector pages through merged pull
  requests, newest update first; a change updated while it pages can move ahead
  of the cursor. The cost grows with the number of pull requests updated since
  the window start; the ledger records it per run. GitHub search is not used,
  because it stops at 1,000 results.
- **A rate limit stops the run** with the retry or reset time, and nothing is
  written. There is no retry loop; the next scheduled run tries again.
- **Pseudonymization replaces logins and drops titles.** With `people:
  pseudonymous`, every login becomes `p-` plus 10 hex characters of an HMAC with
  a salt that is never written, and titles are left empty, because a title can
  hold a login. Check names and branch names are kept. Recorded test fixtures
  hold pseudonyms and empty titles only, which a test enforces.
- **Agents cannot collect.** The MCP `scan` tool skips the collectors and never
  writes the ledger; controls evidenced only by GitHub rules come back
  `not-assessed` (`rules-not-run`).
- **`GRC_GITHUB_FIXTURES` is for tests and offline examples only.** When it names
  a folder, the collectors read recorded responses from it instead of GitHub.
  A real evidence run must not set it.
- **The evidence ledger shows tampering, it does not prevent it.** `grc ledger
  verify` fails on an edited, deleted or reordered line, and on a line recorded
  before the line before it or in the future, so no appended line can fill a
  past gap in the window report. But a made-up entry appended now, with the
  current time, passes. What guards against that is who can write the ledger:
  in the demo only the nightly job pushes the `ledger` branch.

### Repository settings

Recorded on 2026-10-06 with a fine-grained token (Contents, Metadata and
Administration: read on the owner's repos). The commands and results are in
[`tests/fixtures/github/spike/README.md`](../tests/fixtures/github/spike/README.md).

- **Rulesets are readable on any public repo.**
  `GET /repos/{owner}/{repo}/rules/branches/{branch}` needs only metadata read.
  It returned `200` with `[]` on the owner's repo and on
  `GoogleCloudPlatform/microservices-demo`.
- **Classic branch protection needs administration read.**
  `GET /repos/{owner}/{repo}/branches/{branch}/protection` returned `404` with
  the message "Branch not protected" on the owner's repo, which has no
  protection, and `403` on a repo the token cannot administer. The GraphQL
  `branchProtectionRules` field needs the same permission (`FORBIDDEN` on the
  second repo), so the collector does not use it.
- **The collector reads both, rulesets first.** A repo's rules are readable only
  when both reads succeed: rulesets `200`, and classic protection `200` or a
  `404` with the message "Branch not protected". Any other `404` (for example
  "Branch not found") is not read as "no protection". A `403` on either gives
  `scm-rules-unreadable`, never a pass. So on a repo the token cannot
  administer, the rules are reported as unreadable even when its rulesets are
  empty.
- **Bypass actors.** Admins when the rules are not enforced on them, a ruleset
  bypass actor in any mode, and a classic review bypass allowance all give
  `scm-bypass`. A ruleset whose bypass list the token cannot read gives
  `scm-rules-unreadable`. Bypass lists were not part of the spike: the owner's
  repos have no rulesets.
- **The Actions `GITHUB_TOKEN` has no administration permission**, so it cannot
  read classic protection. The demo's collectors use a fine-grained read-only
  token instead (Metadata, Contents and Administration: read). It expires; the
  nightly run then fails with a named error until it is renewed.
