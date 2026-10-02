# Status and roadmap

Where the project stands and what is specified next. See [architecture.md](architecture.md) for how the proposed features fit together and the order to build them in.

`v1.0` is complete for this use case: three frameworks, suppressions, a
cost-bounded LLM step with a measured eval, and linked OSCAL component
definition, assessment plan, and assessment results.

[`v1.1.0`](https://github.com/cdevarenne/okf-grc-skill/releases/tag/v1.1.0) (released 2026-10-01) makes it an installable
engine, Spec F Part A: the `okf-grc` package and its `grc` CLI, a configurable
scan layout (`grc.yaml`), the base bundle shipped with the engine, a versioned
output contract with a run manifest, `grc init` and `grc check`, AI rules that
also read LangChain, CI on every push, and a release on every version tag.

`1.2.0` adds what an adopter repo needs, found by prototyping Spec F Part B on
`microservices-demo`: Conftest inputs beside the target (an inventory next to a
submodule) with symlinks out of the repo refused unless allowed, `grc init` that
never writes into a submodule, `skip_paths` for Trivy and Checkov, `dirty` that
covers every input, and `grc gate` against a committed baseline.

`1.2.1` maps the generic coverage gaps triage found on `microservices-demo`
into the base bundle: SOC 2 A1.1 (capacity) and eight guardrails whose rules
are third-party scanner checks (`Scanner Check`), and adds `grc sync-base` so
an adopter can take a newer base.

`1.3.0` makes `grc gate` fail on new findings at or above a severity, not only
on controls newly `not-satisfied`: on `microservices-demo` every SOC 2 control
already fails, so a status-only gate passed a new critical CVE.

`1.4.0` lets a repo with no Kubernetes or Terraform files turn Conftest off
(`conftest.inputs: []`; its controls read `not-assessed`, not clean), and
closes the 2026-10-01 review's hygiene items: ruff and mypy in CI, one-line
engine errors, version-checked `mapping.json` readers, bounded batch polling.

`1.5.0` ships the agent skill with the engine: `grc install-skill` adds it to
any repo, `grc sync-base` keeps it current, and it reads the layout from
`grc.yaml` instead of assuming this repo's.

`1.6.0` adds `grc mcp`, an MCP server whose tools run the pipeline and read
its outputs (Spec G, G1), and a stricter `grc gate`: coverage gaps and repeats
count, and a new code or configuration finding fails at any severity.

`1.7.0` adds `grc agent` (Spec G, G2): a workflow runner that gives a model only
the workflow's MCP tools, through Claude Code or the Messages API, and writes a
draft only if every number and status checks out against the tool results; its
first workflow, `posture`, summarizes a scan for the repository's owner.

Deliberately left out, or not started:

- **System security plan (SSP)** An SSP states how an organization
  implements each control: its boundary, roles, and narrative. That comes from
  people, not scanners; generating one here would be thin or invented, so the
  plan's `import-ssp` stays a documented placeholder.
- **POA&M (Plan of Action and Milestones)** Remediation plans with owners and 
  dates are the natural next OSCAL model; open findings and accepted risks are 
  already its inputs.
- **Compliance data layer** A rebuildable Postgres + pgvector projection of
  the bundle and of scan history (search, graph queries, control health over
  time) is specified but not started:
  [Spec E](superpowers/specs/2026-09-29-mini-spec-e-compliance-data-layer.md).
- **Adopter repo** A separate repo that applies the engine to a sample app
  like Google's `microservices-demo`, with its own CI, is Spec F Part B:
  specified but not started (Part A, the engine, is built):
  [Spec F](superpowers/specs/2026-09-29-mini-spec-f-engine-and-adopter-repo.md).
- **Agentic workflows** An MCP server over the engine and workflows in which an
  agent proposes (change review, gap-to-mapping patches, suppression drafts) and
  a person approves: specified, not started:
  [Spec G](superpowers/specs/2026-10-01-mini-spec-g-agentic-workflows.md).
