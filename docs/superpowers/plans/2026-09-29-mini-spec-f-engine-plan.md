# Mini Spec F — A Reusable Engine: Implementation Plan (Part A)

**Goal:** the pipeline becomes an installable package, `okf-grc`, with a `grc`
CLI, a configurable scan layout, a reusable base bundle shipped as package
data, and a versioned output contract with provenance. This repo becomes the
first adopter of its own engine, and CI runs on every push. Part B (the
`okf-grc-demo-boutique` repo) gets its own plan once Part A is released.

**Spec:** `docs/superpowers/specs/2026-09-29-mini-spec-f-engine-and-adopter-repo.md`
(reviewed 2026-09-29; decisions in §6).

**Scope:** stories F1–F7 and C1–C2. F7's optional agent packaging (a plugin
manifest) is deferred: nothing in Part B needs it.

## How this plan was checked

Probed on 2026-09-29 against `main` (`40632a0`), before writing:

- **Packaging works from a git tag.** A scratch `okf-grc` project with the
  `uv_build` backend, a `grc` console script, and data under
  `src/okf_grc/data/` ran the same way through `uv run grc` (editable) and
  `uv tool install git+file://…@v0.2.0`: it read a base-bundle file and
  `tools.lock` through `importlib.resources`, ran a packaged `bootstrap.sh`, and
  reported its version through `importlib.metadata`.
- **Scanner flags exist.** Checkov 3.3.19 has `--skip-path`; Semgrep 1.178.0
  accepts repeated `--config` (two rule files in one run: both fired, no
  errors).
- **Blast radius.** 64 import lines across `tests/`, the scripts, and
  `scripts/record_llm_fixtures.py` import the pipeline modules by bare name
  (`from okf_lib import …`). `tests/test_ci_workflow.py` asserts the workflow is
  manual-only, and `tests/test_skill_md.py` asserts `make narrate` in
  `SKILL.md`; both change on purpose. `knowledge/stack/grc-agent.md` points its
  `resource` at the scripts' current path.

Each task is prototyped before its issue and implementation (plan →
prototype → test → issue → implement → commit); this plan fixes the design,
the interfaces, the tests, and the acceptance checks, not the final code.

## Global constraints

- Commits on `main`, authored by `cdevarenne`, no co-author trailer, short
  messages, `Closes #N`. Every commit ships tests; docs-only commits say so.
  The user pushes.
- US English. Python 3.14. Type hints everywhere; docstrings on public APIs.
- **Regression gate for every task:** `make test` and `make test-integration`
  pass, and `make examples` output is unchanged apart from its timestamp,
  except where a task says its outputs change (T4 only).
- No LLM step, no paid call, no network beyond the pinned scanner downloads.
- **Human gates:** any new or edited concept needs a `verified` entry from a
  person before `test_every_concept_is_human_verified` passes (T3, T5, T6).

## Decisions (2026-09-29)

1. **Version:** the package becomes `1.1.0`; the first engine release is tagged
   `v1.1.0` (the repo is tagged `v1.0`; `pyproject.toml` said `0.1.0`).
2. **`findings.json` shape (T4):** wrapped now as
   `{"schema_version": "1.0", "findings": [...]}`, while the contract is new;
   readers in this repo change in the same task.

## Task order

T1 → T2 → T3 → T4 → T5 → T6 → T7, sequential (each builds on the last). C1
follows T1 (paths change in T1); C2 follows C1.

---

## T1 (F2): Package `okf-grc` with a `grc` CLI

**Files:** move `.claude/skills/grc-continuous-compliance/scripts/*.py` to
`src/okf_grc/`; move `tools.lock` and `scripts/bootstrap.sh` to
`src/okf_grc/data/`; create `src/okf_grc/cli.py`; modify `pyproject.toml`,
`Makefile`, `.claude/skills/grc-continuous-compliance/SKILL.md` (paths only),
`knowledge/stack/grc-agent.md` (`resource` path), every test and
`scripts/record_llm_fixtures.py` (imports).

**Design:**

- `pyproject.toml`: `name = "okf-grc"`, the version from decision 1,
  `[project.scripts] grc = "okf_grc.cli:main"`, `uv_build` backend; the `llm`
  extra and dev group unchanged; drop the pytest `pythonpath` (the project is
  installed editable by `uv sync`).
- Imports become `from okf_grc.<module> import …`; no module renames, no logic
  changes.
- `grc <subcommand>` with `bootstrap`, `scan`, `map`, `oscal`, `report`, `run`
  (scan → map → oscal → report). Each subcommand parses the same options its
  script takes today and calls the same function; `init` and `check` arrive in
  T5.
- `grc bootstrap` runs the packaged `bootstrap.sh` with the repo root as its
  working directory, so scanners land in the adopter's `.tools/`; the script
  reads `tools.lock` from the package, not the repo.
- A package-data helper, `okf_grc.data.path(name) -> Traversable`, is the only
  place that knows the data layout.
- Makefile targets call `uv run grc …`; `include tools.lock` points at the new
  path.

**Tests:** each subcommand's parser (options and defaults); `run` calls the
four steps in order (monkeypatched); `data.path` finds `tools.lock` and
`bootstrap.sh`; integration: `uv tool install` from the working tree into a
temporary tool dir, then `grc --version` and `grc run` on this repo.

**Acceptance:** regression gate; `uv tool install git+file://…` works from a
local tag.

## T2 (F1): Configurable scan layout (`grc.yaml`)

**Files:** create `src/okf_grc/config.py`; modify `run_scan.py`,
`map_findings.py`, `to_oscal.py`, `render_report.py`, `cli.py`.

**Design:**

- `Config` (frozen dataclass): `target`, `knowledge`, `inventory`,
  `conftest_inputs` (globs), `checkov_frameworks`, `checkov_skip_paths`,
  `semgrep_configs`, `rego`. `load_config(repo: Path) -> Config` reads
  `grc.yaml` if present; defaults equal today's constants
  (`CONFTEST_PATTERNS`, the Checkov frameworks, `policies/semgrep`,
  `policies/rego`, `app`, `knowledge`, `app/ai-inventory.yaml`).
- Validation raises `ConfigError`: unknown keys, wrong types, and any path
  (including glob bases) that resolves outside the repo root.
- `scanner_runs(config, conftest_inputs)` builds the argv from the config:
  repeated `--config` for Semgrep, one `--skip-path` per entry for Checkov.
- `conftest_inputs` resolves `config.conftest_inputs`; its no-files error
  names `conftest.inputs`.
- Every CLI subcommand takes `--config` (default `grc.yaml`, optional);
  `--target` and friends override the file.

**Tests:** defaults equal the v1.0 constants; unknown key, path escape, and a
non-list value each raise `ConfigError`; a fixture layout (`deploy/`,
`terraform/`) yields the expected Conftest and Checkov argv; the no-inputs
error names `conftest.inputs`.

**Acceptance:** regression gate with no `grc.yaml` present.

## T3 (F3): Base bundle as package data

**Files:** create `src/okf_grc/data/base/` (controls, crosswalk, scanners, the
generic guardrail concepts) and `src/okf_grc/data/policies/{rego,semgrep}`
(the generic rules and their tests); `drf-allowany` stays in the repo's
`policies/semgrep/` as the sample app's own rule; modify `Makefile`
(`conftest verify` and `semgrep --test` over both locations),
`knowledge/index.md`, base concepts that mention `app/`.

**Design:**

- `data/base/` is the source of truth for reusable concepts. Per decision 3,
  this repo's `knowledge/` keeps copies of them next to its sample-app concepts;
  `knowledge/index.md` gains `base_version` in its frontmatter.
- Rules are copied like concepts: this repo's `policies/` holds copies of
  `data/policies/` next to its own `drf-allowany`, and the config points at the
  repo copies. (Changed while prototyping: running rules from the installed
  package would put the install path, different on every machine, into the
  assessment plan's recorded commands.)
- Base concepts lose sample-app text (e.g. `controls/eu-ai-act/art-12.md:24`).

**Tests:** conformance on `data/base/` alone and on `knowledge/`; no base
concept links to or names a path under `app/`; every base concept in
`knowledge/` equals its `data/base/` source; the root-index test allows
`base_version`.

**Human gate:** each edited base concept needs a fresh `verified` entry.

**Acceptance:** regression gate.

## T4 (F4): Output contract and run manifest

**Files:** create `src/okf_grc/data/schemas/{findings,mapping,run}.schema.json`
and `src/okf_grc/manifest.py`; modify `run_scan.py`, `map_findings.py`,
`to_oscal.py`, `cli.py`.

**Design:**

- `findings.json` and `mapping.json` carry `schema_version: "1.0"` (shape per
  decision 2).
- `out/run.json`: `schema_version`, `run_id` (UUIDv5 over the output hashes and
  the time), the scanned repo's commit (`git rev-parse HEAD`, or `null` with
  `"not a git repository"`), the engine version, `base_version`, scanner
  versions from `tools.lock`, the sha256 of the loaded config, the sha256 of
  each output file, and the run time. Written last by `grc run`.
- OSCAL assessment results carry the `run_id` as a namespaced prop.
- Schemas ship as package data so consumers validate against the version they
  installed.

**Tests:** fixture outputs validate against their schemas; removing a required
field fails validation; manifest hashes match the files; integration: every
output of `make scan` validates and `run.json` names the current commit.

**Acceptance:** regression gate, except outputs gain `schema_version`,
`run.json`, and the OSCAL prop; `make examples` regenerated in this task.

## T5 (F5): `grc init` and `grc check`

**Files:** create `src/okf_grc/adopt.py`; modify `cli.py`.

**Design:**

- `grc init` in a repo: copies `data/base/` into `knowledge/` with
  `base_version` in `knowledge/index.md`; writes a starter `grc.yaml`
  (commented, defaults filled in), `ai-inventory.yaml` (`risk_tier` left for a
  person, with the allowed values), and one unverified `stack/` stub per
  `src/*/` directory. It refuses to overwrite any existing file and lists what
  it wrote.
- `grc check` compares each base concept in `knowledge/` with the installed
  engine's `data/base/` and lists concepts without a human `verified` entry;
  exit status 1 when either list is non-empty.
- `make test` runs `grc check` on this repo.

**Tests:** `init` on an empty fixture repo yields a bundle that loads and a
config that validates; a second `init` refuses and writes nothing; `check`
flags a modified base concept and an unverified concept; `check` passes on this
repo.

**Acceptance:** regression gate.

## T6 (F6): AI rules for LangChain; SDK-aware evidence

**Files:** create Semgrep rules (and `.py` test fixtures) under
`data/policies/semgrep/` for LangChain chat-model calls, and their guardrail
concepts under `data/base/policies/`; modify `map_findings.py` and the
inventory schema notes in `knowledge/ai-inventory.md`.

**As built (2026-10-01):** the prototype extended the existing rules instead
of adding siblings, so no guardrail concept is new and no mapping changes.
`llm-unbounded-call` and `llm-output-unreviewed-write` (Anthropic-only) gained
LangChain patterns; `llm-hardcoded-key` gained literal `*api_key=` arguments;
`llm-prompt-logged` already reads any SDK; `llm-no-ai-disclosure` stays
Anthropic-only (`sdks: [anthropic]`), so Art. 50 reports `not-assessed` for a
LangChain-only inventory.

**Design:**

- Rules cover, for LangChain chat models, the four checks the spec lists:
  unbounded calls, prompts logged, output written without review, keys in
  code. Which existing `llm-*` rules are SDK-specific is settled in the
  prototype. Exact
  patterns come from the prototype against clean-room fixtures written for
  this repo (no code copied from `microservices-demo`).
- Guardrail concepts declare `sdks: [anthropic]` or `sdks: [langchain]`;
  inventory systems may declare `sdk`.
- In `map_findings`: a control whose only evidence is SDK-scoped rules, when
  the inventory lists AI systems and none uses a covered SDK, reports
  `not-assessed` with reason `rules-do-not-cover-sdk`. An inventory with no
  systems changes nothing (unknown means assess, as with the risk tier), so the
  sample app's results stay the same.

**Tests:** `semgrep --test` on the new fixtures; mapping tests for covered,
uncovered, and no-systems inventories.

**Human gate:** the new guardrail concepts.

**Acceptance:** regression gate.

## T7 (F7): The skill calls `grc`

**Files:** modify `.claude/skills/grc-continuous-compliance/SKILL.md`,
`tests/test_skill_md.py`, README ("Using the skill").

**Design:** the workflow steps call `grc bootstrap`, `grc run`, and the
existing narrate and triage entry points through `grc`; the skill reads
`grc.yaml` in the repo it runs in. Grounding rules and the reviewer list are
unchanged.

**Tests:** every `grc …` command named in `SKILL.md` is a real subcommand
(parsed from the CLI); the existing grounding-rule assertions still hold.

**Acceptance:** regression gate.

---

## C1: CI on every push and pull request

**Files:** modify `.github/workflows/ci.yml`, `tests/test_ci_workflow.py`.

**Design:** triggers `push` (to `main`) and `pull_request`; job `test`:
`make bootstrap`, `make test`; job `integration`: restores `.tools/` and the
Trivy cache from `actions/cache` keyed on the hash of `tools.lock`, then
`make test-integration`. Unchanged: actions pinned to commit SHAs,
`contents: read`, no persisted credentials, a timeout per job.

**Tests:** the test file asserts the new triggers, both jobs and their steps,
the cache key on `tools.lock`, and the unchanged hardening checks.

## C2: Release on a version tag

**Files:** create `.github/workflows/release.yml` and
`tests/test_release_workflow.py`.

**Design:** on `push` of a `v*` tag: run `make test`, fail unless the tag
equals `v` + the package version, then `gh release create` with generated
notes. `contents: write` only in this workflow.

**Tests:** trigger, version check step, pinned actions, and permissions.

## After Part A

Tag `v1.1.0` (per decision 1) once T1–T7, C1, and C2 are merged and CI is
green; then plan Part B against that tag.
