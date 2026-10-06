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

## Repository settings (Spec H)

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
  protection, and `403` on a repo the token cannot administer. The GraphQL `branchProtectionRules` field needs the same
  permission (`FORBIDDEN` on the second repo), so the collector does not use it.
- **The collector reads both, rulesets first.** A repo's rules are readable only
  when both reads succeed: rulesets `200`, and classic protection `200` or a
  `404` with the message "Branch not protected". Any other `404` (for example
  "Branch not found") is not read as "no protection". A `403` on either gives `scm-rules-unreadable`, never
  a pass. So on a repo the token cannot administer, the rules are reported as
  unreadable even when its rulesets are empty.
- **Not yet checked:** the Actions `GITHUB_TOKEN`. It has no administration
  permission, so in CI classic protection is expected to be unreadable on every
  repo, the token's own repo included.
