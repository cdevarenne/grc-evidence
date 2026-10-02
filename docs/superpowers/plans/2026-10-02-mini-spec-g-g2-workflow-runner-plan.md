# Mini Spec G — G2: The Workflow Runner, Implementation Plan

**Goal:** `grc agent <workflow>`, one way to run every agent workflow: a model
with only that workflow's allowlisted MCP tools, a draft validated against what
the tools returned, and a logged run. The runner proposes; it never changes a
status, a mapping, a suppression, or the repository outside `out/`.

**Spec:** `docs/superpowers/specs/2026-10-01-mini-spec-g-agentic-workflows.md`,
story G2, principles §2, and open questions 1–3. G1 (`grc mcp`, okf-grc 1.6.0)
is the tool surface.

## How this plan was checked

Prototyped on 2026-10-02 with Claude Code 2.1.287 headless (`claude -p`,
Haiku 4.5, on the Claude plan) and `grc mcp` over the demo repo's outputs:

- **Isolation works with flags only:** `--tools ""` removes every built-in tool
  (the session listed only the six `okf-grc` MCP tools: no shell, no file
  access); `--mcp-config` with `--strict-mcp-config` loads only our server;
  `--allowedTools` permits the workflow's tools. Asked to call `scan`, which was
  not allowed, the model was denied, the run reported it under
  `permission_denials`, and the repository was unchanged. A tool outside the
  allowlist is still listed to the model, so the run record must log denials.
- **The run is observable:** `--output-format stream-json --verbose` carries
  every `tool_use` and its full `tool_result`, so validation can check a draft
  against what the tools actually returned, and the run record can list them.
- **Validation is necessary:** the model listed the seven `not-satisfied`
  controls correctly, then wrote "totaling 425 findings across unsatisfied
  controls"; the tool results sum to 417. An invented number in an otherwise
  right answer is the failure G2's validation exists to catch.
- **Cost and time:** 5 turns, 16 s; on the plan, `claude -p` reports a notional
  $0.035 (not billed).
- **Limits available:** this Claude Code version has `--max-budget-usd` but no
  `--max-turns`, so the runner caps turns itself from the stream.
- **An API path exists in the SDK:** `anthropic` 1.11 has
  `client.beta.messages.tool_runner` (a tool-use loop with `max_iterations`) and
  `anthropic.lib.tools.mcp.async_mcp_tool`, which wraps an MCP client's tools.

## Design

**Command.** `grc agent <workflow> [--out out]` runs one workflow over the
repository it starts in, using the outputs of the latest run (it never scans;
a workflow that needs a fresh run says so). The default writes the draft
locally; nothing is published.

**Providers** (follow `LLM_MODE`, as narrate and triage do; one transcript
format for all three, so validation and the run record do not depend on the
provider):

- `claude-cli`: `claude -p` with `--tools ""`, `--strict-mcp-config`, an
  `--mcp-config` that starts this same engine's `grc mcp` (`python -m okf_grc.cli
  mcp`, so the tools match the runner's version), `--allowedTools` from the
  workflow, `--no-session-persistence`, `--output-format stream-json --verbose`,
  `--json-schema` for the draft, and `--max-budget-usd`. A tool outside the
  allowlist is listed to the model and its calls are denied.
- `anthropic`: the Messages API through the SDK's beta `tool_runner`, with
  `async_mcp_tool` over an in-process MCP client to `grc mcp`'s server. Only the
  allowlisted tools are sent, so the model never sees the others. The key comes
  from the environment, as for narrate and triage.
- `replay`: a recorded transcript from `tests/fixtures/agent/`, for tests and CI
  at $0.

**Limits** (tighter than narrate and triage, since an agent run loops):
`AGENT_BUDGET_USD` (default $0.25) is checked before every model call of the
`anthropic` loop and passed to Claude Code as `--max-budget-usd`; at most
`AGENT_MAX_TURNS` (default 8) model turns, after which the run stops and records
why (`max_iterations` for the API; the runner counts turns in Claude Code's
stream and stops the process). How Claude Code applies `--max-budget-usd` on a
plan, where it reports notional cost, was checked in R1: it stops the run
(`error_max_budget_usd`) once the notional cost passes the cap, after the turn
that passed it.

**Isolation found in R1:** without more flags, a headless run on the plan still
ran the person's session hooks and loaded their global `CLAUDE.md` (the model
quoted it). `--setting-sources ""`, `--disable-slash-commands`, and the
workflow's own `--system-prompt` remove both (the same question then answered
"NONE"); `--bare` would too but accepts only an API key. The auto-memory path is
still listed in the session.

**Workflow definition** (one module per workflow, under `src/okf_grc/agents/`):
a versioned prompt, the allowlisted tools, the draft's JSON Schema, and a
renderer to Markdown. The runner owns everything else.

**Validation** (before any draft is written), reusing narrate's rules:

- every number in the draft appears in a tool result the model received in this
  run (control keys and rule ids are identifiers, not numbers);
- every control key cited exists, and any status stated for it is that
  control's own;
- no "satisfied", "compliant", or "passes" about a control;
- the draft matches the workflow's schema.

A rejected draft is not written: the run record keeps it with the reasons, and
the command exits non-zero.

**Run record:** `out/agent/<workflow>-<run_id>.json`: the workflow and prompt
versions, the model, the engine version, the outputs' `run_id`, every tool call
with its arguments and result size, permission denials, turns, duration, the
reported cost (with `billed: false` on the plan), the validation result, and the
draft. The draft itself is `out/agent/<workflow>-<run_id>.md`. One line goes to
an agent ledger, `out/agent/usage.jsonl`, task `agent:<workflow>` (found in R1:
the report's LLM line reads every entry of the latest run in `llm-usage.jsonl`,
so agent runs there would be counted as narration).

**Untrusted text:** the prompt states the `untrusted` convention; the runner
never executes anything the model returns; drafts are written, never applied.

## Decisions (2026-10-02)

1. **Providers** (Spec G open question 2): `claude-cli`, `anthropic`, and
   `replay`, all in G2. The `anthropic` provider uses the SDK's beta
   `tool_runner` with `async_mcp_tool` (beta: pinned through `uv.lock`).
2. **Limits:** `AGENT_BUDGET_USD` (default $0.25) and `AGENT_MAX_TURNS`
   (default 8), separate from `LLM_BUDGET_USD`.
3. **Drafts** (open question 3): files under `out/agent/` only; publishing
   arrives with the first workflow that needs it, behind `--publish`.
4. **First workflow:** `posture`, a person-facing summary whose every number
   traces to a tool result; G4 follows on this runner.
5. **Release:** okf-grc 1.7.0; one `posture` run shown in the demo repo's
   README. The maintainer records the two replay fixtures (one Claude Code run on
   the plan, one API run with the key from the Keychain).

## Tasks

- **R1. Runner core and the Claude Code provider.** `grc agent`, the common
  transcript, the `claude-cli` command line and stream parsing (tool calls,
  results, denials, usage, turns, the final structured output), the turn cap,
  the run record, the ledger line, and the `replay` provider. Tests: the exact
  command line (no built-in tools, strict MCP config, the allowlist, the budget);
  a recorded stream replays to the same record; a denial is recorded; a run past
  the turn cap stops with a recorded reason; no file outside `out/agent/`
  changes.
- **R1b. The API provider.** `tool_runner` with `async_mcp_tool` over an
  in-process client, only allowlisted tools, the budget checked before each
  call, `max_iterations`, and the same transcript. Tests with a stubbed API
  client: only allowlisted tools are sent; the budget stops the loop before a
  call; the transcript matches the Claude Code provider's shape.
- **R2. Validation.** The rules above, shared with narrate where they overlap.
  Tests: the prototype's invented sum is rejected; a number from a tool result
  passes; an unknown control key, a wrong status, and "satisfied" are rejected.
- **R3. `posture` workflow.** Prompt, allowlist (`control_status`, `findings`,
  `gaps`, `suppressions`), schema, renderer; two runs recorded on the demo repo
  by the maintainer as replay fixtures: `LLM_MODE=claude-cli` (the plan) and
  `LLM_MODE=anthropic` (the API key; Haiku 4.5).
- **R4. Docs.** `docs/agents.md`: what a workflow is, the isolation flags and
  why, the run record, validation, limits; README and architecture updated.
- **R5. Release and adopter.** okf-grc 1.7.0; one `posture` run on the demo
  repo, shown in its README.

## Limits (stated in the docs)

- G2 adds no CI job: the `anthropic` provider makes unattended runs possible,
  and G7 decides whether one runs in CI.
- With Claude Code, the allowlist is enforced by permissions: a tool outside it
  is listed to the model and its calls are denied and recorded. With the API,
  tools outside it are never sent.
- The API provider uses a beta SDK helper; an SDK upgrade that changes it shows
  up in the provider's tests.
- Validation checks numbers, control keys, statuses, and claims of compliance;
  it does not judge whether the prose is useful. G6 measures that.

## Order

R1 → R1b → R2 → R3 → R4 → R5. Then G4 (gap to mapping proposal) on this runner.
