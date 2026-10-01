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
