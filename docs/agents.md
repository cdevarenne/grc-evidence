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

A workflow is one module under `src/grc_evidence/agents/`: a versioned prompt and
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
same run, read as structured data:

- **every number is bound to what it counts:** a `{key, findings}` or
  `{rule, findings}` pair must match the count the tools reported exactly; a
  number in text (digits, or words from zero to twenty) right after a control,
  rule, or suppression (within 16 characters) or right before one ("12
  deny_latest_tag") must be that identifier's count; any other number must be
  the count of the nearest identifier in its sentence, of the object it belongs
  to, or a total the tools reported (controls and findings by status, gap rules
  and findings, a filter's total, suppressions by state and the findings each
  covers). Run ids, dates the tools reported (as written by the tools or with a
  month name, and their years), strings they returned verbatim, and framework
  names (SOC 2, ISO/IEC 42001) are names, not counts;
- every control it names exists, and a status it gives a control (in a field
  next to the control, or in a sentence that names only that control) is that
  control's own;
- no control is called satisfied, compliant, or passed;
- the schema's required fields are present (both providers also enforce the
  schema on the model's side).

A rejected draft goes back to the model once, with the reasons, on what is left
of the budget; the corrected draft is checked the same way. A draft rejected
twice is not written; the run record keeps every attempt with its reasons, and
`grc agent` exits non-zero.

Binding came from reviews. In okf-grc 1.7.0, validation only required that a
number appear somewhere in the tool results; the demo repository's `posture`
draft passed it with "plus 11 additional CVEs at 4 findings each", where 11 is
a count the tools reported but the right figure was 7. 1.8.0 bound numbers to
their neighbors, yet its first run on the same outputs passed "and 7 more CVEs"
next to a CVE (4) because 7 was also a reported total; 1.8.1 binds a number
that close to an identifier to that identifier only. Its run on the same outputs
gave three rules a range ("each have 12-13 findings"); that draft was rejected,
and the correction round put each count next to its rule, which passed.
Binding cannot tell a true derived count from a false one, so it rejects both:
a number reaches a person only if a tool reported it for that thing. A number
farther from any identifier can still match a total by coincidence. Earlier, a model wrote 425 findings where the tool
results add up to 417, and in a later run the correct 417 before any tool
reported it; both were rejected too.

What it does not check: words. The same corrected draft called CC7.1 "system
monitoring" (it is vulnerability detection); a person reviews every draft, and
measuring how often drafts are right is the evaluation step that comes next
(Spec G, G6). A tool result the runner cannot parse binds nothing: Claude Code
saves a very large result to a local file and shows the model only a preview,
so workflows ask for totals (`findings` with `limit` 0) rather than long lists.

## Costs observed

On the demo repository, a `posture` run with Claude Code took 3 turns and about
10 tool calls, reported at $0.07 to $0.09 on the plan (not billed). On this
repository's sample app, the same workflow through the API with Haiku 4.5 cost
$0.037.
