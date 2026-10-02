# Agent workflows

`grc agent <workflow>` runs one agent workflow over the latest run's outputs: a
model that may call only that workflow's [MCP tools](mcp.md), a draft checked
against what those tools returned, and a record of the run. The runner proposes;
it never changes a status, a mapping, a suppression, or anything outside
`out/agent/`, and it never publishes the draft.

```
grc run                                  # the outputs the workflow reads
LLM_MODE=claude-cli grc agent posture    # or LLM_MODE=anthropic with ANTHROPIC_API_KEY set
```

## Workflows

| Workflow | Tools it may call | Draft |
|---|---|---|
| `posture` | `control_status`, `findings`, `gaps`, `suppressions` | for the person who owns the repository: the controls not satisfied with their largest finding groups, the coverage gaps, the suppressions in force, and next steps |

A workflow is one module under `src/okf_grc/agents/`: a versioned prompt and
task, its allowlisted tools, the draft's JSON Schema (every object closed with
`additionalProperties: false`, which the Messages API requires), and a renderer
to Markdown. Each has recorded runs under `tests/fixtures/agent/` that replay in
the tests at no cost.

## Providers

`LLM_MODE` picks the model provider, as for `grc narrate` and `grc triage`:

- **`claude-cli`:** Claude Code headless (`claude -p`) on the person's Claude
  plan. Needs Claude Code on the PATH and the `mcp` extra.
- **`anthropic`:** the Messages API through the SDK's tool runner (a beta helper,
  pinned through `uv.lock`) with an in-process MCP client. Needs the `llm` and
  `mcp` extras and `ANTHROPIC_API_KEY` in the environment.
- **`replay`** (the default): a recorded transcript, for tests.

Both live providers produce the same transcript, so validation and the run
record do not depend on which ran.

## Isolation

A Claude Code run starts with:

| Flag | Why |
|---|---|
| `--tools ""` | no built-in tools: no shell, no file reads or edits |
| `--mcp-config` (this engine's `grc mcp`) and `--strict-mcp-config` | only our MCP server, at the runner's own version; no other server the person has configured |
| `--allowedTools` | only the workflow's tools may run; a call to any other is denied |
| `--setting-sources ""`, `--disable-slash-commands`, `--system-prompt` | no user or project settings, hooks, plugins, skills, or `CLAUDE.md` |
| `--no-session-persistence`, `--max-budget-usd` | no saved session; the budget |

The third row was found by testing, not assumed: without those flags, a
headless run on the plan ran the person's session hooks and loaded their global
`CLAUDE.md`, and the model quoted it when asked; with them, it answered that it
had none. `--bare` isolates too, but accepts only an API key, not a plan. The
auto-memory location is still listed in such a session.

With Claude Code, a tool outside the allowlist is still listed to the model; its
calls are denied and recorded under `denials`. With the API, tools outside it are
never sent.

## Limits

- **`AGENT_BUDGET_USD`** (default $0.25): checked before every next call of the
  API loop, and passed to Claude Code as `--max-budget-usd`. Claude Code applies
  it on a plan too, to the cost it reports without billing, and stops after the
  turn that passed it, so a run can end slightly over.
- **`AGENT_MAX_TURNS`** (default 8): model replies per run. The API runner's
  `max_iterations`; for Claude Code, which has no turn flag, the runner counts
  replies in its stream and stops the process.
- **`LLM_MODEL`** (default `claude-haiku-4-5`): the API provider needs a model
  with a known price, so its budget can be checked.

These are separate from narrate's `LLM_BUDGET_USD`, because an agent run loops.

## What a run writes

Under `out/agent/`:

- `<workflow>-<UTC time>.json`: the run record: the workflow and its prompt's
  hash, the engine version, the `run_id` of the outputs it read, every tool call
  with its arguments and full result, denials, turns, token usage, cost and
  whether it was billed, why it stopped early (budget, turns), and the validation
  result.
- `<workflow>-<UTC time>.md`: the draft, only when it passed validation.
- `usage.jsonl`: one line per run. It is kept apart from `out/llm-usage.jsonl`,
  whose entries the report sums as its narration cost.

## Validation

Before a draft is written, the runner checks it against the tool results of the
same run:

- every number in it, in its text (digits, or words from zero to twenty) and in
  its numeric fields, appears in some tool result; run ids are names, not
  numbers;
- every control it names exists, and a status it gives a control (in a field
  next to the control, or in a sentence that names only that control) is that
  control's own;
- no control is called satisfied, compliant, or passed;
- the schema's required fields are present (both providers also enforce the
  schema on the model's side).

A rejected draft is not written; the run record keeps it with the reasons, and
`grc agent` exits non-zero. The tools report the totals a summary needs
(controls and findings by status, gap rules and findings, findings per rule,
suppressions by state), so a draft never has to compute one: a sum no tool
reported is rejected even when it is right. In testing, a model wrote 425
findings where the tool results add up to 417, and in a later run wrote the
correct 417 before any tool reported it; both drafts were rejected.

What it does not check: whether a number that does appear in a tool result is
attached to the right thing (a count of one rule's findings cited as a count of
deployments passes), and whether the prose is useful. Measuring that is the
evaluation step that comes next (Spec G, G6).

## Costs observed

On the demo repository, a `posture` run with Claude Code took 3 turns and about
10 tool calls, reported at $0.07 to $0.09 on the plan (not billed). On this
repository's sample app, the same workflow through the API with Haiku 4.5 cost
$0.037.
