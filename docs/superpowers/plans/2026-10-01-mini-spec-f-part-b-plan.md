# Mini Spec F — Part B: An Adopter Repo, Implementation Plan

**Goal:** a separate public repo, `okf-grc-demo-boutique`, applies the released
engine to Google's `microservices-demo` and runs it in CI: a scan on every pull
request with a status gate, a nightly rescan, and reviewed upstream bumps.
Part B also needs engine changes, found by prototyping; they ship first, here,
as `v1.2.0`.

**Spec:** `docs/superpowers/specs/2026-09-29-mini-spec-f-engine-and-adopter-repo.md`
(stories F8–F11 and C3–C6; decisions in §6).

## How this plan was checked

Prototyped on 2026-10-01 with the engine at `631a5bc`: a scratch repo with
`microservices-demo` as a real git submodule under `upstream/` at the pinned
`38e7348eb289` (release v0.10.7, still upstream `main`), `grc init --target
upstream`, a `grc.yaml` for its layout, and `grc run`.

- **It runs:** 626 findings in 22 s, no errors. Semgrep scans files inside the
  submodule (the LangChain `llm-unbounded-call` rule fires on
  `src/shoppingassistantservice/shoppingassistantservice.py`, so ISO/IEC 42001
  A.6 is `not-satisfied`). Conftest: 12 `deny_latest_tag`; the upstream
  manifests already run as non-root and declare no public bucket.
- **Statuses:** 4 controls `not-satisfied` (cc6.1, cc7.1, cc8.1, A.6), 5
  `no-violations-detected`, 9 `not-assessed`; 462 findings from 48 rules are
  coverage gaps, led by Trivy `KSV-0020`/`0021`/`0104` (55 each) and Checkov
  `CKV_K8S_21` (35).
- **Four engine gaps** (below, E1–E4) block a faithful adopter setup.

## Engine changes first (this repo, released as `v1.2.0`)

**E1. Inputs beside the target.** With a submodule as the target, the AI
inventory must live outside it (upstream code is never edited), and Conftest
must read it there. Today `inventory` is target-relative and `conftest.inputs`
rejects `..`. Change: `..` is allowed in both when every resolved path stays
inside the repo; each resolved input is also checked to stay inside the repo,
which rejects symlinks that leave it (#70, with the decided opt-in).

**E2. `grc init` never writes into a submodule.** It wrote
`upstream/ai-inventory.yaml`. Change: when the target is a git submodule (a
gitlink), the inventory goes to the repo root and the starter `grc.yaml` points
at it.

**E3. Skip paths for Trivy too.** Trivy scanned `helm-chart/` templates,
`kustomize/`, `release/` (duplicates of the static manifests), and upstream's
`.github/`; only Checkov can skip paths. Change: a top-level `skip_paths` that
Trivy (`--skip-dirs`) and Checkov (`--skip-path`) both honor; `checkov.skip_paths`
stays and adds to it (additive, contract 1.x).

**E4. Every input counts for `dirty`.** The prototype's `run.json` said
`dirty: false` while `knowledge/`, `grc.yaml`, and `policies/` were untracked:
only the target is checked. Change: untracked files under the target, the
knowledge bundle, the policy paths, the inventory, and `grc.yaml` all count.

**E5. `grc gate`** (C4): compares `out/mapping.json` with a baseline
`expected/control-status.json` and exits non-zero when a control moves to
`not-satisfied` or a suppression has expired (a scanner or config error already
fails `grc run`); controls already `not-satisfied` in the baseline do not fail.
`grc gate --write-baseline` creates the file; `--summary FILE` appends the
control-status table as Markdown (C3's job summary).

Each with tests in the usual way; regression gate unchanged; then tag `v1.2.0`.

## The adopter repo (`okf-grc-demo-boutique`)

**B1 (F8). Repo setup.** Public GitHub repo; `upstream/` submodule at
`38e7348eb289`; MIT for its own files, upstream keeps Apache-2.0. The engine
installs from the `v1.2.0` tag (`uv tool install git+…@v1.2.0`); `grc
bootstrap` in CI.

**B2 (F9). The bundle.** `grc init --target upstream`; a person writes the 12
service concepts plus GKE and Memorystore (what each is, and the controls it
implements), the inventory (the shopping assistant with `sdk: langchain`; risk
tier `limited` with the recorded reason, decision 7), and the `grc.yaml` from
the prototype. Expected after E1–E3: Art. 50 reads `not-assessed` (its only
rule cannot read LangChain), fewer duplicate Trivy findings.

**B3 (F9). Triage the gaps.** `grc triage` (Haiku 4.5, API key from the
Keychain or Claude Code) proposes a control or `none` for the 48 gap rules; a
person decides. Where a mapping goes is a decision (below).

**B4 (F10). Expected results.** `grc gate --write-baseline` commits
`expected/control-status.json` at the pinned commit; CI's gate is the test.
CVE counts are not asserted.

**B5 (C3). Pull-request scan.** Install the engine at its tag, `grc bootstrap`,
`grc run --require-clean`, `grc gate --summary "$GITHUB_STEP_SUMMARY"`, upload
`out/` as an artifact. Actions pinned to SHAs, read-only token, no LLM step.

**B6 (C5). Nightly scan.** Scheduled rescan of `main` with a fresh Trivy
database; on a gate failure, open or update one issue (`issues: write` only in
that job).

**B7 (C6). Upstream bumps.** Dependabot `gitsubmodule` (and `github-actions`):
a bump's pull request shows its compliance change through B5; the author
updates `expected/` in the same pull request.

**B8 (F11). Walkthrough README.** Install, `grc init`, the config, the first
report, one triaged gap, one suppression, what CI publishes, and the same run
through the skill.

## Decisions needed

1. **Where gap mappings go.** Most of the 48 gap rules are generic (Trivy KSV,
   Checkov `CKV_K8S_*`, `CKV_DOCKER_*`): mapping them helps every adopter.
   Proposed: generic scanner rules are mapped in the engine's base bundle
   (released as `v1.2.x`); rules about this app's own code or configuration are
   mapped in the adopter's bundle.
2. **Engine first.** E1–E5 land and `v1.2.0` is tagged before the adopter repo
   is created. Proposed: yes; the prototype shows the repo cannot be set up
   faithfully on `v1.1.0`.
3. **Creating the GitHub repo** (outward-facing): the user creates it, or asks
   for `gh repo create cdevarenne/okf-grc-demo-boutique --public`.

## Order

E1 → E2 → E3 → E4 → E5 → tag `v1.2.0`; then B1 → B2 → B3 (with base-bundle
mappings released as `v1.2.x` per decision 1) → B4 → B5 → B6 → B7 → B8.
