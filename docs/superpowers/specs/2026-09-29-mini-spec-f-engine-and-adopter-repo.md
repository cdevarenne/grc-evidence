# Mini Spec F — A Reusable Engine and an Adopter Repo

- **Date:** 2026-09-29
- **Status:** draft; needs review before a plan.
- **Depends on:** v1.0 (Specs A–D). Independent of Spec E.
- **LLM cost:** none. CI runs the deterministic pipeline only.

## 1. Why

This repo shows the skill on a sample app it was built around. It does not show
how a security or trust team applies it to their own systems, or how it fits
into a DevSecOps pipeline. Three things block that today:

- **Fixed layout (C2).** `run_scan.py` hard-codes `CONFTEST_PATTERNS`
  (`k8s/**`, `infra/**/*.tf`, `ai-inventory.yaml`); the Makefile, `SKILL.md`,
  and the inventory path assume `app/`.
- **Engine and sample are one unit.** The pipeline runs only from this repo's
  Makefile, and `knowledge/` mixes reusable concepts (controls, crosswalk,
  scanners) with concepts about the sample app (stack, suppressions, AI
  inventory, `drf-authenticated-writes`). Some reusable concepts mention `app/`
  (e.g. `controls/eu-ai-act/art-12.md:24`).
- **No contract and no continuous run.** Nothing downstream can rely on the
  shape of `findings.json` or `mapping.json`, and CI is manual-only and has
  never run.

The direction is a compliance engine that pipelines and agents call, not a
skill that must be invoked by hand. Spec F builds the foundation for that: an
installable engine with a configurable layout, a versioned output contract with
provenance, and a separate repo that adopts it for
[`GoogleCloudPlatform/microservices-demo`](https://github.com/GoogleCloudPlatform/microservices-demo)
(Apache-2.0) with CI. The agent-facing layers come after (§7).

## 2. Principles

- **The engine is the product; the skill is one way in.** Pipelines call the
  CLI; agents call it through a skill (and later an MCP server). All of them get
  the same deterministic results.
- **The output is a contract.** `findings.json`, `mapping.json`, and a run
  manifest are versioned and schema-validated, so downstream tools (a GRC
  platform, an agent) can rely on them.
- **The agent decides when, code decides what.** Anything that later leaves the
  engine (to a GRC platform, a ticket, an auditor) is produced by code from these
  outputs, with provenance attached, never composed by an LLM.
- **The adopter's repo holds everything an auditor needs.** Its `knowledge/`
  bundle, config, suppressions, and scan outputs are versioned there.
- **Defaults reproduce v1.0.** With no config, the sample app scans exactly as
  today: `make examples` output is unchanged apart from its timestamp.
- **Same grounding, same honesty.** A finding still reaches a control only
  through `rule_ids`. A rule that cannot see a codebase's language or SDK must
  not make its controls read `no-violations-detected` for that code.
- **Fail closed.** A bad config, a path outside the repo, or a scanner with no
  inputs stops the run with an error that names the config key.

## 3. The adopter target

`microservices-demo` at a pinned commit (`38e7348eb289`, 2026-09-18). Layout,
checked through the GitHub API on 2026-09-29:

| Path | What |
|---|---|
| `src/<service>/` | 12 services (Go, C#, Node.js, Python, Java), 13 Dockerfiles (one a debug variant) |
| `src/shoppingassistantservice/` | Python Flask service using `langchain-google-genai` (Gemini) and AlloyDB: the AI component |
| `kubernetes-manifests/*.yaml` | static manifests for 11 services (not the shopping assistant) |
| `kustomize/components/shopping-assistant/shoppingassistantservice.yaml` | the shopping assistant's manifest, only as a Kustomize component |
| `terraform/*.tf` | GKE and Memorystore infrastructure |
| `helm-chart/`, `kustomize/`, `release/` | templated or duplicated manifests |

Consequences: the default Conftest layout matches nothing here (so #45's error
fires), Helm and Kustomize are not rendered (a v1.0 limit), and the AI Semgrep
rules match only Anthropic-SDK calls in Python (`$CLIENT.messages.create`,
`.content[$I].text`), so they would not fire on LangChain/Gemini code.

## 4. Stories

### Part A — this repo

**F1. Configurable scan layout (C2).** As an adopter, I describe my repo's
layout in one file instead of moving my files.

- `grc.yaml` at the repo root (optional): `target`, `knowledge`, `inventory`,
  `conftest.inputs` (globs), `checkov.frameworks`, `checkov.skip_paths`,
  `semgrep.configs`, `rego`. Unknown keys and non-list values are errors; every
  path is checked to stay inside the repo (as `_check_target` does now).
- Defaults equal today's constants, so no config means v1.0 behaviour.
- `run_scan`, `map_findings`, and `to_oscal` read the same loaded config; the
  assessment plan records the resolved inputs (as A4 does now).
- The "no Conftest inputs" error names `conftest.inputs`.
- Tests: defaults equal v1.0 constants; unknown key, path escape, and
  non-list value each raise; a config pointing at a fixture layout produces the
  expected Conftest argv. Acceptance: `make examples` unchanged but for the
  timestamp.

**F2. An installable CLI.** As a pipeline owner, I install the engine at a
pinned version and run it without this repo's Makefile or any agent.

- `grc` with subcommands `bootstrap`, `scan`, `map`, `oscal`, `report`, `run`
  (all four), `init`, `check`. Each wraps today's script functions; no logic
  moves into the CLI.
- Installable from a git tag (`uv tool install git+…@vX.Y.Z`), with the base
  bundle, policies, and `tools.lock` shipped as package data. `grc bootstrap`
  installs the pinned scanners into the adopter's `.tools/`.
- This repo's Makefile and `SKILL.md` call `grc`; outputs stay in `out/`.
- Tests: each subcommand's argument parsing; `run` equals the four steps; an
  install into a clean environment runs `grc run` on a fixture repo.

**F3. Split the base bundle from the sample app.** As a maintainer, I ship
reusable knowledge separately from knowledge about one app.

- `base/` (shipped with the engine): `controls/`, `crosswalk/`, `scanners/`, and
  the generic guardrails (`require-non-root`, `deny-latest-tag`,
  `no-public-bucket`, `ai-inventory-complete`, the `llm-*` rules) with their
  Rego and Semgrep sources.
- The sample app's bundle keeps `stack/`, `suppressions/`, `ai-inventory.md`,
  and `drf-authenticated-writes`.
- Remove sample-app text and links from base concepts (e.g. `art-12.md:24`);
  each such edit gets a fresh `verified` entry.
- Tests: conformance runs on the base bundle alone and on the combined bundle;
  a test fails if any base concept links to or names a path under `app/`.

**F4. Output contract and provenance.** As a downstream consumer (a GRC
platform connector, an agent, an auditor), I can rely on the output's shape and
trace every result to what produced it.

- JSON Schemas for `findings.json` and `mapping.json`, each output carrying a
  `schema_version`. Additive changes bump the minor version; anything else the
  major.
- A run manifest `out/run.json`: the scanned repo's commit, the engine version,
  the base bundle version, scanner versions from `tools.lock`, a hash of the
  loaded config, a sha256 of each output file, and the run time.
- The OSCAL assessment results reference the run manifest's id.
- Tests: every output of `make scan` validates against its schema; the
  manifest's hashes match the files; a schema test fails when a required field
  is removed.

**F5. `grc init` and `grc check`.** As an adopter, I start from a working
bundle and learn when the base I copied has moved.

- `init` copies `base/` into the adopter's `knowledge/` with a
  `base_version` stamp in `knowledge/index.md`, and writes starter
  `grc.yaml`, `ai-inventory.yaml`, and `stack/` stubs (one per `src/*/`
  directory, marked unverified). It refuses to overwrite existing files.
- `check` reports base concepts that differ from the installed engine's base
  version, and concepts without a `verified` entry.
- Tests: `init` on an empty fixture repo yields a bundle that loads; a second
  `init` refuses; `check` flags a modified base concept.

**F6. AI rules for LangChain.** As an adopter with a LangChain/Gemini service,
I get AI-governance evidence, not a false clean result.

- Extend the `llm-*` Semgrep rules (or add siblings) to LangChain chat-model
  calls: unbounded calls (no timeout or token limit), prompts logged, output
  written without review, keys in code. Semgrep rule tests with clean-room
  fixtures modelled on common LangChain usage (no code copied from upstream).
- A rule's concept declares the SDKs it understands. A control whose only
  evidence is a rule that does not cover the adopter's AI component reads
  `not-assessed`, not `no-violations-detected`. This needs a new inventory
  field: the SDK each AI system uses (`systems: []` has no schema today).
- Tests: Semgrep `--test` on the new fixtures; a mapping test for the
  uncovered-SDK case.

**F7. The skill calls the engine (optional packaging last).** As an agent user,
I get the same results through the skill as a pipeline gets through the CLI.

- `SKILL.md` calls the installed `grc` and reads `grc.yaml` in the repo it runs
  in; the grounding rules and the "leave to a reviewer" list are unchanged.
- Optional, last: thin packaging for agents that install skills from a
  package (a Claude Code plugin manifest with `"source": "./"`, other agents'
  skill locations). No engine code lives in the packaging.
- Tests: `SKILL.md` references only commands `grc` provides.

### Part B — the adopter repo (`okf-grc-demo-boutique`, name open)

**F8. Repo setup.** `microservices-demo` as a git submodule at the pinned
commit under `upstream/`; the repo adds only `grc.yaml`, `knowledge/`,
`ai-inventory.yaml`, CI, and a README. Upstream code is never edited or
copied, so its Apache-2.0 license stays with it. The engine is installed at a
pinned version.

**F9. The adopter's bundle.** `grc init`, then a person writes: one stack
concept per service plus GKE and Memorystore; `ai-inventory.yaml` declaring the
shopping assistant (its risk tier is a person's decision, see §6); `grc.yaml`
pointing Conftest at `upstream/kubernetes-manifests/*.yaml`,
`upstream/terraform/*.tf`, and the shopping-assistant manifest, and Checkov
away from `helm-chart/` and `release/`. Coverage gaps are triaged
(`make triage` locally) and mapped by a person through `rule_ids`.

**F10. Expected results.** No seeded ledger exists for a real app, so the repo
commits `expected/control-status.json` (control key → status) at the pinned
commit. A test asserts the scan reproduces it. CVE counts are not asserted:
Trivy's database moves daily.

**F11. Walkthrough.** The README shows: install the engine, `grc init`, the
config, the first report, one triaged gap, one suppression, what CI publishes,
and the same run through the skill in a coding agent.

### Part C — CI

**C1. Test this repo on every push.** Turn `.github/workflows/ci.yml` from
`workflow_dispatch` into push and pull-request triggers: `make test` always;
`make test-integration` with `.tools/` and the Trivy cache restored from a
cache keyed on `tools.lock`. See §6 on cost.

**C2. Release the engine.** On a `v*` tag: run the tests, check that the
package version equals the tag, and publish a GitHub release. Adopters pin a
version.

**C3. Scan every pull request in the adopter repo.** Install the engine at its
pinned version, restore `.tools/`, run `grc run`, upload `out/` (report, OSCAL,
mapping, run manifest) as a build artifact, and write the control-status table
to the job summary. No LLM step runs (no API key in CI).

**C4. Gate.** `grc gate --baseline expected/control-status.json` fails the job
when a control moves to `not-satisfied`, a suppression has expired, or a
scanner or config error occurred. Controls already `not-satisfied` in the
baseline do not fail the job. Which conditions gate is a decision (§6).

**C5. Nightly scan.** Scheduled run on `main`: rescans with a fresh Trivy
database, so new CVEs and expiring suppressions surface without a code change;
it opens or updates one issue when a control's status changes.

**C6. Upstream bumps.** Dependabot's `gitsubmodule` updates open a pull request
when `microservices-demo` moves; C3 shows the compliance change that bump
brings, and the author updates `expected/` in the same pull request.

## 5. Out of scope

An MCP server, GRC platform connectors, and agentic orchestration (§7);
rendering Helm or Kustomize output; frameworks beyond the three here (adding
one still means changing `okf_lib.py`); Semgrep rules for Go, C#, Node.js, or
Java services (they get Trivy and Checkov coverage only; the report says so);
LLM steps in CI; SSP and POA&M; the Spec E data layer; deploying the demo app.

## 6. Open questions for review

1. **Distribution.** A Python package installed from a git tag (recommended:
   light, and the scanners stay pinned by `tools.lock`), or a container image
   with the scanners inside (hermetic for CI, heavier to build and publish).
2. **Base bundle delivery.** Copy into the adopter's `knowledge/` on `init`
   with a version stamp (recommended: one self-contained bundle that the OKF
   visualizer renders and an auditor reads at the scanned commit), or load the
   base from the engine at run time next to the adopter's bundle (always
   current, but split across two places).
3. **Upstream inclusion.** Submodule (recommended: nothing copied, pin bumps
   become reviewable pull requests) or a fork (closest to "a team adds this to
   its own repo", but it carries upstream's nine workflows and GCP deploy
   setup).
4. **Gate conditions** for C4.
5. **CI cost.** CI is off on these repos for cost. Public repositories get
   standard GitHub-hosted runners without charge, which I believe covers C1,
   C3, and C5; to confirm before enabling.
6. **The shopping assistant's AI Act risk tier** (`limited` is the likely
   reading for a shopping chatbot; a person decides and records why).
7. **Names:** the engine package, the CLI, and the adopter repo.

## 7. After Spec F (not specified)

Each builds on F4's contract and is proven on the adopter repo:

- **An MCP server** over the engine, so any agent that speaks MCP can run a
  scan, read control status, list gaps, and draft mappings or suppressions.
- **GRC platform connectors** that push results (OSCAL or `mapping.json` with
  the run manifest) to a platform such as Vanta, with a dry run and idempotent
  writes. Whether a platform takes writes through its MCP server or its API,
  and whether it ingests OSCAL, is to check per platform.
- **An agentic pipeline** that runs this engine alongside other tools,
  triages, and calls the connectors, with a person approving what reaches the
  platform. An agent in CI needs a paid model API.

## 8. Order

F1 → F2 → F3 → F4 → F5 → F6 → F7 in this repo, each keeping `make test`,
`make test-integration`, and `make examples` stable; C1 and C2 alongside. Then
F8 → F9 → F10 → F11 with C3 → C4 → C5 → C6 in the adopter repo.
