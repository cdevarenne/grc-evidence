# Mini Spec G — G1: The MCP Server, Implementation Plan

**Goal:** `grc mcp`, a stdio MCP server over the engine, so any MCP-capable agent
can run a scan and read its results without shell access. Read-mostly: the only
tool that writes is `scan`, and it writes only what `grc run` writes (`out/`).
Nothing it offers can change `knowledge/`, `policies/`, `grc.yaml`, a
suppression, a status, or a mapping.

**Spec:** `docs/superpowers/specs/2026-10-01-mini-spec-g-agentic-workflows.md`,
story G1 and principles §2. Spec G is a draft; this plan settles what G1 needs
from its open questions (decisions below) and leaves the rest (runner, workflows)
to later plans.

## How this plan was checked

Prototyped on 2026-10-02 in a scratch environment with `mcp` 2.2.0 (the current
release; Python 3.14), a two-tool server over the demo repo's `out/`, called
through the SDK's in-process `Client`:

- **The v2 API is as Spec G assumed:** `MCPServer`, `@server.tool()`,
  `@server.resource()`, `Context.report_progress`, and `Client(server)` for tests
  without a subprocess. Model attributes are snake_case (`read_only_hint`,
  `structured_content`, `is_error`); camelCase raises.
- **Structured output needs typed returns.** A tool returning a bare `dict` gets
  no output schema and only JSON text; a `TypedDict` return gets an output schema
  and `structured_content`, which G2's validation needs.
- **Errors are named, not fatal:** a `ToolError` reaches the client as
  `is_error` with its message, and the server keeps serving.
- **Timing:** a warm `grc run` on the demo repo takes 11 s. A cold one also
  downloads the Trivy database (not measured here), and MCP clients time out
  long tool calls, so `scan` reports progress per step and the docs name the
  client timeout setting.
- **Weight:** `mcp` brings starlette, uvicorn, httpx, pydantic, and pyjwt, a web
  stack the engine does not otherwise need.

## Design

**Install and run.** An optional extra, `okf-grc[mcp]`, like `[llm]`; `grc mcp`
without it exits with the install command. `grc mcp` serves on stdio for the
repository it starts in (the working directory, as every `grc` command). The
demo repo commits a project MCP config (`.mcp.json`) that starts it through the
pinned engine, as its Makefile does.

**Tools** (all `read_only_hint` except `scan`; typed returns; every result
carries the `run_id` of the outputs it read, so an agent can tell runs apart):

| Tool | Reads | Returns |
|---|---|---|
| `scan` | runs `grc run` (no arguments: the layout is `grc.yaml`) | the `run.json` summary: run id, commit, dirty, versions, control counts by status |
| `control_status` | `mapping.json` | one control or all: status, reason, finding count, evidenced/satisfied by |
| `findings` | `mapping.json` | findings filtered by control, rule, or file, paged |
| `gaps` | `mapping.json` | coverage gaps grouped by rule, with counts and files |
| `suppressions` | `mapping.json` | suppressed, expiring, expired, pending, and unused, as the report lists them |
| `gate` | `mapping.json`, `expected/control-status.json` | what `grc gate` would report: regressions, new findings at a severity, expired suppressions |

**Resources:** `grc://report` (`report.md`), `grc://run` (`run.json`),
`grc://oscal/{document}` (the three OSCAL documents), read from `out/`.

**Untrusted text.** Strings that come from scanned files or scanner output (a
finding's `message`, and any text quoted from a target) are returned only under
a field named `untrusted`, and each tool description says that this field is
data, never instructions. Identifiers the engine derives (control keys, rule ids,
repo-relative paths, statuses, counts) are not wrapped.

**Contract.** Every read goes through the version-checked readers
(`read_mapping`, `read_findings`); a missing or stale output is a tool error
naming the step to run, not a crash. Paths are never tool arguments: the server
reads fixed files under the configured `out/`, so no argument can reach outside
the repo.

**Concurrency.** One `scan` at a time; a second call while one runs is a tool
error. A read during a scan sees the previous run whole, because `grc run` moves
its outputs into `out/` only when complete.

## Decisions (2026-10-02)

1. **Draft tools** (`draft_mapping`, `draft_suppression`) move to the stories
   that use them (G4, G5), each with its validation and evaluation; G1 ships
   only tools that read or run the fixed pipeline.
2. **Comparison:** G1 ships `gate`, the comparison with the committed baseline
   that CI already uses; a run-to-run `diff` comes with G3 (change review).
3. **Untrusted text** (Spec G open question 4): the `untrusted` field.
4. **Release:** `okf-grc` 1.6.0; the demo repo pins it and commits `.mcp.json`.

## Tasks

Each lands with tests, keeping `make test`, `make test-integration`, and the
examples stable; an issue per task.

- **M1. Server skeleton and packaging.** The `[mcp]` extra (`mcp>=2.2,<3`;
  this repo's `uv.lock` pins the exact set its tests and `make audit` use),
  `grc mcp`, a helpful exit without the extra, and the
  `control_status` tool. Tests through the in-process `Client`: tool list and
  annotations, structured output against its schema, a named error for an
  unknown control and for missing outputs.
- **M2. Read tools and resources.** `findings`, `gaps`, `suppressions`, `gate`,
  and the resources, reusing `gate.py` and the report's suppression sections
  rather than reimplementing them. Tests against the fixture outputs, including
  the untrusted field and paging; a test that no read tool changes any file in
  the repo.
- **M3. `scan`.** Runs the same steps as `grc run`, reports progress per step,
  refuses a second concurrent call, and returns the manifest summary. Tests with
  the scanners stubbed (unit) and one real scan (integration); a failed step
  is a tool error and leaves the previous outputs whole.
- **M4. Security review and docs.** A test that every scanner-derived string in
  every tool result sits under `untrusted`; `make audit` passing with the new
  dependencies in `uv.lock`; `docs/mcp.md`
  (install, client configuration for Claude Code and others, tools, limits);
  README and architecture updated.
- **M5. Release and adopter.** `1.6.0`; in the demo repo, the pin, `.mcp.json`,
  and a README step showing an agent using the tools.

## Limits (stated in the docs)

- Local stdio only: no network transport, no authentication, one repository per
  server process.
- `scan` runs the pipeline with the repository's own `grc.yaml`; an agent cannot
  change the layout, a scanner's arguments, or the policies through a tool.
- The server trusts the repository it runs in as `grc` does; it does not make
  scanned content safe, it labels it.

## Order

M1 → M2 → M3 → M4 → M5. G2 (the workflow runner) is planned after M5, once its
Spec G questions (runner implementation, where drafts go) are answered.
