# Status and roadmap

Where the project stands and what is specified next. See [architecture.md](architecture.md) for how the proposed features fit together and the order to build them in.

`v1.0` is complete for this use case: three frameworks, suppressions, a
cost-bounded LLM step with a measured eval, and linked OSCAL component
definition, assessment plan, and assessment results.

[`v1.1.0`](https://github.com/cdevarenne/grc-evidence/releases/tag/v1.1.0) (released 2026-10-01) makes it an installable
engine, Spec F Part A: the `grc-evidence` package and its `grc` CLI, a configurable
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

`1.8.0` binds each number in an agent's draft to what it counts, after a review
found a 1.7.0 draft citing a reported number next to the wrong thing, and gives a
rejected draft one correction round.

`1.8.1` binds a number right beside a control, rule, or suppression to that
identifier only, so it cannot pass by matching an unrelated total.

`2.0.0` collects SOC 2 Type 2 evidence over an audit window (Spec H Part A):
repo settings and the change population from the GitHub API for N repos, an
auditor's sample, a hash-chained evidence ledger, and each control's history
over the window. The package is renamed `grc-evidence` (module `grc_evidence`;
`okf_grc` stays as a deprecated alias for one minor release), and the output
contract is 1.2.

Built beyond the engine:

- **Adopter repo** (Spec F Part B):
  [grc-evidence-boutique](https://github.com/cdevarenne/grc-evidence-boutique)
  applies the released engine to Google's `microservices-demo`, with its own CI
  (a compliance gate on every pull request and a nightly scan). The prototyping
  for it produced 1.2.0 and 1.2.1. See its
  [case study](https://github.com/cdevarenne/grc-evidence-boutique/blob/main/docs/case-study.md)
  and [Spec F](superpowers/specs/2026-09-29-mini-spec-f-engine-and-adopter-repo.md).
- **Agentic workflows, first part** (Spec G, G1 and G2): `grc mcp`
  ([docs/mcp.md](mcp.md)) and `grc agent posture` ([docs/agents.md](agents.md)).

Next:

- **Spec H Part B:** scan N repos with the code scanners (clone, scan,
  aggregate, shard in CI).
- **Spec I:** signed risk acceptances, an OSCAL POA&M, and an attestation for an
  empty population.

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
- **Agentic workflows, remaining stories** The MCP server (G1, 1.6.0) and the
  workflow runner with its first workflow, `posture` (G2, 1.7.0 to 1.8.1), are
  built. Still specified but not started: gap-to-mapping proposals (G4), their
  evaluation (G6), change review on pull requests (G3), then G5 and G7, in that
  order. Each drafts; a person approves:
  [Spec G](superpowers/specs/2026-10-01-mini-spec-g-agentic-workflows.md).
