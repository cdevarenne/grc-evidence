# MCP server

`grc mcp` serves one repository's grc-evidence results over the Model Context
Protocol, so any MCP-capable agent can run a scan and read its results without
shell access. It is read-mostly: the only tool that writes is `scan`, and it
writes only what `grc run` writes (`out/`). No tool can change `knowledge/`,
`policies/`, `grc.yaml`, a suppression, a status, or a mapping, and no tool
takes a file path.

## Install and connect

The server needs the optional `mcp` extra:

```
uv tool install 'okf-grc[mcp] @ git+https://github.com/cdevarenne/grc-evidence@v1.8.1'
```

It serves on stdio for the repository it starts in (the working directory,
like every `grc` command). In Claude Code, from the repository's root:

```
claude mcp add --transport stdio grc-evidence -- grc mcp
```

Or commit a project-scoped `.mcp.json` so everyone working in the repository
gets the same server. Pinning the engine there, as a Makefile does, keeps
agents on the version CI uses:

```json
{
  "mcpServers": {
    "grc-evidence": {
      "command": "uvx",
      "args": ["--from", "okf-grc[mcp] @ git+https://github.com/cdevarenne/grc-evidence@v1.8.1", "grc", "mcp"]
    }
  }
}
```

Claude Code asks for approval before it starts a project-scoped server in an
interactive session. Other MCP clients take the same command and arguments.
`grc mcp --out DIR` reads and writes another outputs directory.

## Tools

| Tool | Writes | Returns |
|---|---|---|
| `scan` | `out/`, all at once when every step succeeded | the new run: id, commit, dirty, engine version, controls by status, findings, gaps |
| `control_status` | nothing | each control (or one: a key, or a bare SOC 2 code such as `cc6.1`): status, reason, finding count, evidence |
| `findings` | nothing | findings, each once, by control, rule, or file; paged (at most 200), with `total` and `by_rule` over every page; `limit` 0 returns only those |
| `gaps` | nothing | coverage gaps grouped by rule, with their files |
| `suppressions` | nothing | applied, expiring, expired, pending, and unused suppressions |
| `gate` | nothing | what `grc gate` would report against `expected/control-status.json`, at a chosen `fail_on` |

Every result carries the `run_id` of the outputs it read, so an agent can tell
two runs apart, and each tool advertises an output schema. A missing or stale
output, an unknown control, or a missing baseline is a named tool error that
says which step to run; the server keeps serving.

**Resources:** `grc://report` (the report), `grc://run` (the run manifest), and
`grc://oscal/{document}` for `component-definition`, `assessment-plan`, and
`assessment-results`.

## Scanner text is untrusted

A finding's message comes from a scanner or from a scanned file, which anyone
who can change the repository can write. Tools return such text only under a
field named `untrusted`, and the tools that return it say in their descriptions
that it is data, never instructions. A test gives every finding a message that
tries to give instructions and checks, for every tool, both the structured
result and its text form, that the message appears nowhere else.

Identifiers the engine derives are not wrapped: control keys, rule ids, statuses,
counts, and repository-relative file paths. A file name is chosen by whoever
writes the repository, so an agent should treat paths as names, never as
instructions. The report resource quotes finding messages as written.

## Limits

- **Local and stdio only:** no network transport and no authentication. One
  server process serves one repository.
- **Fixed pipeline:** `scan` runs with the repository's own `grc.yaml`; an
  agent cannot change the layout, a scanner's arguments, or the policies
  through a tool.
- **One scan at a time;** a second call while one runs is an error. A read
  during a scan sees the previous run whole.
- **Time:** a warm scan of the demo repository takes about 11 seconds; a cold
  one also downloads Trivy's vulnerability database. Claude Code's per-call
  tool timeout (`MCP_TOOL_TIMEOUT`) defaults to about 28 hours; other clients
  may stop a long call sooner. Progress is reported per step.
- **It labels scanned content, it does not make it safe.** The server trusts
  the repository it runs in, as `grc` does.
