"""`grc agent`: run an agent workflow over the latest run's outputs, with only that workflow's MCP tools, and write a
validated draft. The runner proposes; it never changes a status, a mapping, a suppression, or anything outside
`out/agent/`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any, TypedDict

from grc_evidence.claims import FORBIDDEN, STATUS, normalize
from grc_evidence.contract import read_mapping
from grc_evidence.errors import GrcError
from grc_evidence.llm import DEFAULT_MODEL, PRICES, cost_usd

Json = dict[str, Any]
SERVER = "grc-evidence"  # the MCP server's name in a run's config: its tools are mcp__grc-evidence__<tool>
DEFAULT_BUDGET_USD = 0.25
DEFAULT_MAX_TURNS = 8
FIXTURES = Path("tests/fixtures/agent")
MAX_TOKENS = 4096  # per model reply
# A control a draft cites: a full key, or a bare SOC 2 code such as cc6.1 (read as soc2:cc6.1).
FULL_KEY = re.compile(r"\b(soc2:(?:cc|a)\d+\.\d+|iso42001:a\.\d+|eu-ai-act:art-\d+)\b", re.IGNORECASE)
BARE_SOC2 = re.compile(r"(?<![\w:.-])((?:cc|a)\d+\.\d+)\b", re.IGNORECASE)
WORDS = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
         "seventeen eighteen nineteen twenty").split()
NUMBER_WORD = re.compile(r"\b(" + "|".join(WORDS) + r")\b", re.IGNORECASE)  # "Seven controls" is a number too
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")  # a date the tools reported, such as an expiry: a name, not a count
FRAMEWORK_NAME = re.compile(r"\b(?:SOC\s?2|ISO(?:/IEC)?\s?42001(?::2023)?|(?:NIST\s)?(?:SP\s)?800-53|2024/1689|Art(?:icle)?\.?\s?\d+)\b", re.IGNORECASE)
MONTHS = ("january february march april may june july august september october november december").split()
DATE_IN_WORDS = re.compile(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2})\b(?:,?\s+\d{4})?", re.IGNORECASE)
# A number this soon after an identifier ("CVE-1 (4), and 7 more"), or right before one ("12 deny_latest_tag"), is that
# identifier's count, never a total that happens to match. Farther before one ("5 coverage gaps (rule, ...)",
# "188 findings in soc2:cc6.1") it may count something larger, so a reported total or a nearby count binds it.
AFTER_AN_IDENTIFIER, BEFORE_AN_IDENTIFIER = 16, 3
INTEGER = re.compile(r"(?<![\w.])\d+(?![\w.]\w)")
UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)  # run ids: names, not numbers
CLAUSE = re.compile(r"(?<=[.;!?])\s+|\n+")  # sentences and lines, keeping "rule: 13" together
SEGMENT = re.compile(r"(?<=[.;:!?])\s+|\n+")  # sentences and lines: a status must sit next to its control
CORRECTION = """

Your previous draft was rejected for these reasons:
{problems}

Your previous draft:
{draft}

Call the tools again as you need and answer with a corrected draft. Every number must be the count the tools
report for what it sits next to (a control's count next to its key, a rule's next to the rule), or a total they
report; leave out any number you cannot place that way."""
USAGE_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
STRUCTURED_OUTPUT = "StructuredOutput"  # how Claude Code returns the --json-schema draft: its own, not a workflow tool


class AgentError(GrcError, RuntimeError):
    """An agent run that could not start or finish: no outputs to read, a missing recording, a crashed model CLI."""


@dataclass(frozen=True)
class Workflow:
    """What one workflow asks: its prompt and task, the MCP tools it may call, and the draft's shape."""

    name: str
    version: str
    prompt: str
    task: str
    tools: tuple[str, ...]
    schema: Json
    render: Callable[[Json], str]


class ToolCall(TypedDict):
    name: str
    arguments: Json
    result: str
    is_error: bool


class Transcript(TypedDict):
    """One run, the same shape whichever provider ran it; validation and the run record read only this."""

    provider: str
    model: str
    tool_calls: list[ToolCall]
    denials: list[str]
    turns: int
    usage: dict[str, int]
    cost_usd: float
    billed: bool
    output: Json | None
    stopped: str | None  # why the run ended without a draft: max_turns, budget, or the model CLI's error


Provider = Callable[[Workflow, Path, "Limits"], Transcript]


@dataclass(frozen=True)
class Limits:
    model: str = DEFAULT_MODEL
    budget_usd: float = DEFAULT_BUDGET_USD
    max_turns: int = DEFAULT_MAX_TURNS

    @classmethod
    def from_env(cls) -> Limits:
        """LLM_MODEL, AGENT_BUDGET_USD, and AGENT_MAX_TURNS, with the defaults above."""
        return cls(
            model=os.environ.get("LLM_MODEL", DEFAULT_MODEL),
            budget_usd=float(os.environ.get("AGENT_BUDGET_USD", DEFAULT_BUDGET_USD)),
            max_turns=int(os.environ.get("AGENT_MAX_TURNS", DEFAULT_MAX_TURNS)),
        )


def claude_argv(workflow: Workflow, limits: Limits, mcp_config: Path) -> list[str]:
    """Claude Code headless, isolated: no built-in tools, only this engine's MCP server and the workflow's tools, no
    user or project settings (hooks, plugins, CLAUDE.md), no skills, no saved session."""
    return [
        "claude", "-p", "--model", limits.model, "--output-format", "stream-json", "--verbose",
        "--system-prompt", workflow.prompt, "--json-schema", json.dumps(workflow.schema),
        "--tools", "", "--mcp-config", str(mcp_config), "--strict-mcp-config",
        "--setting-sources", "", "--disable-slash-commands", "--no-session-persistence",
        "--max-budget-usd", str(limits.budget_usd),
        "--allowedTools", *[f"mcp__{SERVER}__{tool}" for tool in workflow.tools],
    ]


class StreamReader:
    """Builds a transcript from Claude Code's stream-json events, counting the model's replies as turns."""

    def __init__(self, model: str, max_turns: int) -> None:
        self.model, self.max_turns = model, max_turns
        self.calls: dict[str, ToolCall] = {}
        self.replies: set[str] = set()
        self.billed = False
        self.result: Json | None = None

    def feed(self, event: Json) -> bool:
        """Take one event; True once the model has replied more than `max_turns` times."""
        if event.get("type") == "system" and event.get("subtype") == "init":
            self.billed = event.get("apiKeySource", "none") != "none"  # an API key pays; a plan does not
        elif event.get("type") == "assistant":
            message = event["message"]
            self.replies.add(message["id"])
            for block in message.get("content", []):
                if block.get("type") == "tool_use" and block["name"] != STRUCTURED_OUTPUT:
                    self.calls[block["id"]] = {"name": block["name"], "arguments": block.get("input") or {}, "result": "", "is_error": False}
        elif event.get("type") == "user":
            for block in event.get("message", {}).get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("tool_use_id") in self.calls:
                    call = self.calls[block["tool_use_id"]]
                    call["result"], call["is_error"] = _text(block.get("content")), bool(block.get("is_error"))
        elif event.get("type") == "result":
            self.result = event
        return len(self.replies) > self.max_turns

    def transcript(self, stopped_early: bool) -> Transcript:
        result = self.result or {}
        usage = result.get("usage") or {}
        subtype = result.get("subtype")
        stopped = "max_turns" if stopped_early else ("budget" if subtype == "error_max_budget_usd" else (subtype if result.get("is_error") else None))
        if self.result is None and not stopped_early:
            stopped = "no result from the model CLI"
        denied = {d.get("tool_name", "").removeprefix(f"mcp__{SERVER}__") for d in result.get("permission_denials", [])}
        calls: list[ToolCall] = [
            {"name": c["name"].removeprefix(f"mcp__{SERVER}__"), "arguments": c["arguments"], "result": c["result"], "is_error": c["is_error"]}
            for c in self.calls.values()
        ]
        return {
            "provider": "claude-cli",
            "model": self.model,
            "tool_calls": [c for c in calls if c["name"] not in denied],  # a call to a denied tool never ran
            "denials": sorted(denied),
            "turns": len(self.replies),
            "usage": {k: int(usage.get(k, 0)) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")},
            "cost_usd": float(result.get("total_cost_usd") or 0.0),
            "billed": self.billed,
            "output": None if stopped else result.get("structured_output"),
            "stopped": stopped,
        }


def _text(content: Any) -> str:
    """A tool result's text, whether the stream gives it as a string or as content blocks."""
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content or [] if isinstance(b, dict))


def read_stream(lines: Iterable[str], model: str, max_turns: int) -> tuple[Transcript, bool]:
    """A transcript from stream-json lines, and whether the turn cap stopped it (the caller then stops the CLI)."""
    reader = StreamReader(model, max_turns)
    for line in lines:
        if line.strip() and reader.feed(json.loads(line)):
            return reader.transcript(stopped_early=True), True
    return reader.transcript(stopped_early=False), False


def run_claude(workflow: Workflow, out: Path, limits: Limits, popen: Callable[..., Any] = subprocess.Popen) -> Transcript:
    """The `claude-cli` provider: one isolated `claude -p` run against this engine's `grc mcp`."""
    config = {"mcpServers": {SERVER: {"command": sys.executable, "args": ["-m", "grc_evidence.cli", "mcp", "--out", str(out.absolute())]}}}
    with tempfile.TemporaryDirectory(prefix="grc-agent-") as tmp:
        mcp_config = Path(tmp) / "mcp.json"
        mcp_config.write_text(json.dumps(config), encoding="utf-8")
        try:
            proc = popen(claude_argv(workflow, limits, mcp_config), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, encoding="utf-8")
        except FileNotFoundError as e:
            raise AgentError("claude not found on PATH: install Claude Code, or use LLM_MODE=anthropic") from e
        proc.stdin.write(workflow.task)
        proc.stdin.close()
        transcript, early = read_stream(proc.stdout, limits.model, limits.max_turns)
        if early:
            proc.terminate()
        stderr = proc.stderr.read()
        proc.wait()
    if transcript["stopped"] == "no result from the model CLI":
        raise AgentError(f"claude exited {proc.returncode} without a result: {stderr.strip()[-300:]}")
    return transcript


class _RecordingClient:
    """The in-process MCP client the API's tool runner calls through, recording each call and what it returned."""

    def __init__(self, client: Any, calls: list[ToolCall]) -> None:
        self.client, self.calls = client, calls

    async def call_tool(self, name: str, arguments: Json | None = None, **kwargs: Any) -> Any:
        result = await self.client.call_tool(name, arguments)
        text = "".join(getattr(c, "text", "") for c in result.content) or json.dumps(result.structured_content)
        self.calls.append({"name": name, "arguments": arguments or {}, "result": text, "is_error": bool(result.is_error)})
        return result


def run_anthropic(workflow: Workflow, out: Path, limits: Limits, http_client: Any = None) -> Transcript:
    """The `anthropic` provider: the Messages API's tool runner over an in-process `grc mcp` server. Only the
    workflow's tools are sent, so the model never sees the others; the budget is checked before every next call."""
    try:
        import anyio
        from anthropic import APIError, AsyncAnthropic
        from anthropic.lib.tools.mcp import async_mcp_tool
        from mcp.client import Client

        from grc_evidence.mcp_server import build_server
    except ImportError as e:
        raise AgentError("LLM_MODE=anthropic needs the llm and mcp extras: grc-evidence[llm,mcp]") from e
    if limits.model not in PRICES:
        raise AgentError(f"no price for {limits.model!r}, so its budget cannot be checked; one of {', '.join(PRICES)}")
    calls: list[ToolCall] = []

    async def go() -> Transcript:
        usage = dict.fromkeys(USAGE_KEYS, 0)
        cost, turns, stopped, output, last = 0.0, 0, None, None, None
        async with Client(build_server(out)) as mcp:
            recording = _RecordingClient(mcp, calls)
            tools = [async_mcp_tool(t, recording) for t in (await mcp.list_tools()).tools if t.name in workflow.tools]  # type: ignore[arg-type]
            api = AsyncAnthropic(http_client=http_client) if http_client else AsyncAnthropic()
            runner = api.beta.messages.tool_runner(
                model=limits.model, max_tokens=MAX_TOKENS, system=workflow.prompt, tools=tools,
                messages=[{"role": "user", "content": workflow.task}], max_iterations=limits.max_turns,
                output_config={"format": {"type": "json_schema", "schema": workflow.schema}},
            )
            async for message in runner:
                turns, last = turns + 1, message
                reply = {k: getattr(message.usage, k, 0) or 0 for k in USAGE_KEYS}
                usage = {k: usage[k] + reply[k] for k in USAGE_KEYS}
                cost += cost_usd(limits.model, reply)
                if message.stop_reason == "tool_use" and cost >= limits.budget_usd:
                    stopped = "budget"  # the runner would call the model again: stop before it does
                    break
        if stopped is None and last is not None and last.stop_reason == "tool_use":
            stopped = "max_turns"
        elif stopped is None and last is not None:
            text = "".join(b.text for b in last.content if b.type == "text")
            try:
                output = json.loads(text)
            except json.JSONDecodeError:
                stopped = "the model's final reply was not JSON"
        return {
            "provider": "anthropic", "model": limits.model, "tool_calls": calls, "denials": [], "turns": turns,
            "usage": usage, "cost_usd": round(cost, 6), "billed": True, "output": output, "stopped": stopped,
        }

    try:
        return anyio.run(go)
    except BaseExceptionGroup as group:  # raised inside the MCP client's task group, so it arrives wrapped
        if (match := group.subgroup(APIError)) is None:
            raise
        refused = match.exceptions[0]
        while isinstance(refused, BaseExceptionGroup):
            refused = refused.exceptions[0]
        raise AgentError(f"the API refused the request: {refused}") from refused
    except APIError as e:
        raise AgentError(f"the API refused the request: {e}") from e


def run_replay(workflow: Workflow, out: Path, limits: Limits, fixtures: Path = FIXTURES) -> Transcript:
    """The `replay` provider: a recorded transcript, for tests and CI at $0."""
    path = fixtures / f"{workflow.name}.json"
    if not path.is_file():
        raise AgentError(f"no recorded run at {path}; record one with LLM_MODE=claude-cli or anthropic")
    return json.loads(path.read_text(encoding="utf-8"))


def _cited(text: str) -> set[str]:
    """The control keys a text names."""
    return {k.lower() for k in FULL_KEY.findall(text)} | {f"soc2:{k.lower()}" for k in BARE_SOC2.findall(text)}


def _walk(value: Any, context: str | None = None) -> tuple[list[tuple[str, str | None]], list[tuple[Json, str | None]]]:
    """Every string in a draft with the identifier of its nearest enclosing object (its `key` or `rule`), and every
    object with its own."""
    if isinstance(value, dict):
        own = value.get("key") or value.get("rule") or context
        parts = [_walk(v, own) for v in value.values()]
        return [t for p in parts for t in p[0]], [(value, own), *(o for p in parts for o in p[1])]
    if isinstance(value, list):
        parts = [_walk(v, context) for v in value]
        return [t for p in parts for t in p[0]], [o for p in parts for o in p[1]]
    return ([(value, context)], []) if isinstance(value, str) else ([], [])


@dataclass(frozen=True)
class Facts:
    """What the tools of one run reported: counts by identifier, totals, and the strings they returned verbatim."""

    counts: dict[str, set[int]]
    totals: set[int]
    verbatim: tuple[str, ...]
    years: set[int]  # of the dates the tools reported, such as "expires in 2026": names, not counts
    days: set[tuple[int, int]]  # (month, day) of the dates the tools reported, for dates written with a month name  # strings with digits, longest first: masked in a draft, so their digits are not counts


def _names(identifier: str) -> list[str]:
    """How a draft may write an identifier: as reported, a rule without its tool, a SOC 2 key without `soc2:`."""
    name = identifier.lower()
    prefix, _, rest = name.partition(":")
    return [name, rest] if rest and prefix != "iso42001" and prefix != "eu-ai-act" else [name]


def _strings(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return [value] if isinstance(value, str) and any(c.isdigit() for c in value) and len(value) >= 4 else []


def facts(calls: list[ToolCall]) -> Facts:
    """The counts and totals the tools reported in a run, read from their structured results. A result that is not
    JSON (Claude Code saves a very large one to a file and shows the model a preview) contributes nothing."""
    counts: dict[str, set[int]] = {}
    totals: set[int] = set()
    verbatim: set[str] = set()

    def add(identifier: str, n: Any) -> None:
        if isinstance(n, int) and not isinstance(n, bool):
            for name in _names(identifier):
                counts.setdefault(name, set()).add(n)

    for call in calls:
        try:
            result = json.loads(call["result"])
        except json.JSONDecodeError:
            continue
        if not isinstance(result, dict):
            continue
        verbatim.update(_strings(result))
        for entry in result.get("controls", []):
            add(entry.get("key", ""), entry.get("findings"))
        for rule, n in result.get("by_rule", {}).items():
            add(rule, n)
        for gap in result.get("gaps", []):
            add(gap.get("rule", ""), gap.get("findings"))
        for suppression, n in result.get("findings_by_suppression", {}).items():
            add(suppression, n)
        for field in ("by_status", "findings_by_status", "counts"):
            totals.update(v for v in result.get(field, {}).values() if isinstance(v, int))
        totals.update(v for field in ("total", "rules", "findings") if isinstance(v := result.get(field), int) and not isinstance(v, bool))
    dates = [d for v in verbatim for d in DATE.findall(v)]
    years, days = {int(d[:4]) for d in dates}, {(int(d[5:7]), int(d[8:10])) for d in dates}
    return Facts(counts, totals, tuple(sorted(verbatim, key=len, reverse=True)), years, days)


def _blank(text: str, pattern: re.Pattern[str]) -> str:
    return pattern.sub(lambda m: " " * len(m.group()), text)


def _unbound(text: str, known: Facts, context: str | None) -> list[str]:
    """Numbers in `text` that are neither a count the tools reported for the identifier next to them (before or
    after, in the same sentence) or for the enclosing object's identifier, nor a total the tools reported."""
    names = sorted({name for name in known.counts}, key=len, reverse=True)
    identifier = re.compile(r"(?<![\w-])(" + "|".join(map(re.escape, names)) + r")(?![\w-])", re.IGNORECASE) if names else None
    own = {n for name in _names(context) for n in known.counts.get(name, set())} if context else set()
    unbound = []
    for clause in CLAUSE.split(normalize(text)):
        masked = clause
        for pattern in (UUID, DATE, FRAMEWORK_NAME):
            masked = _blank(masked, pattern)
        masked = DATE_IN_WORDS.sub(lambda m: " " * len(m.group()) if (MONTHS.index(m.group(1).lower()) + 1, int(m.group(2))) in known.days
                                   else m.group(), masked)
        # Identifiers first, so a count can bind to one; then other strings the tools returned verbatim.
        spans = [(m.start(), m.end(), m.group(1).lower()) for m in identifier.finditer(masked)] if identifier else []
        for start, stop, _ in spans:
            masked = masked[:start] + " " * (stop - start) + masked[stop:]
        for literal in known.verbatim:
            masked = _blank(masked, re.compile(re.escape(literal), re.IGNORECASE))
        numbers = [(m.start(), m.end(), int(m.group())) for m in INTEGER.finditer(masked)]
        numbers += [(m.start(), m.end(), WORDS.index(m.group(1).lower())) for m in NUMBER_WORD.finditer(masked)]
        for at, end, n in sorted(numbers):
            before = [(stop, name) for start, stop, name in spans if stop <= at]
            after = [(start, name) for start, stop, name in spans if start >= end]
            beside = {name for stop, name in before[-1:] if at - stop <= AFTER_AN_IDENTIFIER}
            beside |= {name for start, name in after[:1] if start - end <= BEFORE_AN_IDENTIFIER}
            if beside:  # right next to an identifier: its count (or its object's), never a total that happens to match
                allowed = {c for name in beside for c in known.counts[name]} | own
            else:
                near = (known.counts[before[-1][1]] if before else set()) | (known.counts[after[0][1]] if after else set())
                allowed = known.totals | known.years | own | near
            if n not in allowed:
                unbound.append(f"{n} in {clause.strip()[:80]!r}")
    return unbound


def validate(workflow: Workflow, transcript: Transcript, mapping: Json) -> list[str]:
    """Why the draft cannot be written; empty when it can.

    The model may say only what the tools showed it in this run, and each number must be what it is next to: a
    count the tools reported for that control or rule (exactly, in a `{key|rule, findings}` pair), or a total they
    reported. Every control named exists, a status given to a control is that control's, and no control is called
    satisfied or compliant. The providers enforce the draft's schema; its required fields are checked again here.
    """
    if transcript["stopped"]:
        return [f"the run stopped: {transcript['stopped']}"]
    draft = transcript["output"]
    if not isinstance(draft, dict):
        return ["the run produced no structured draft"]
    errors = [f"missing field {field!r}" for field in workflow.schema.get("required", []) if field not in draft]
    statuses = {key: entry["status"] for key, entry in mapping["controls"].items()}
    known = facts(transcript["tool_calls"])
    texts, objects = _walk(draft)
    unbound = [u for text, context in texts for u in _unbound(text, known, context)]
    for obj, own in objects:
        reported = {n for name in _names(own) for n in known.counts.get(name, set())} if own else set()
        for field, n in obj.items():
            if isinstance(n, int | float) and not isinstance(n, bool):
                pair = field == "findings" and own and ("key" in obj or "rule" in obj)
                if (n not in reported) if pair else (n not in known.totals | reported):
                    unbound.append(f"{field} {n:g} of {own or 'the draft'} (the tools report {sorted(reported) or 'no count for it'})")
    if unbound:
        errors.append(f"numbers that are not the count of what they sit next to, nor a reported total: {unbound}")
    text = normalize("\n".join(t for t, _ in texts))
    if unknown := sorted(_cited(text) - set(statuses)):
        errors.append(f"controls that do not exist: {unknown}")
    if m := FORBIDDEN.search(text):
        errors.append(f"forbidden claim {m.group(0)!r}: a scan shows violations or their absence, never compliance")
    for obj, _ in objects:
        keys = _cited(str(obj.get("key", "")))
        if len(keys) == 1 and "status" in obj and (key := keys.pop()) in statuses and obj["status"] != statuses[key]:
            errors.append(f"{key}: draft says {obj['status']!r}, status is {statuses[key]!r}")
    for segment in SEGMENT.split(text):
        keys = _cited(segment) & set(statuses)
        if len(keys) == 1 and (wrong := sorted({s for s in STATUS.findall(segment) if s != statuses[next(iter(keys))]})):
            errors.append(f"{next(iter(keys))}: draft says {wrong} in {segment.strip()[:80]!r}, status is {statuses[next(iter(keys))]!r}")
    return errors


def run_workflow(workflow: Workflow, provider: Provider, out: Path, limits: Limits, now: datetime | None = None) -> Json:
    """Run a workflow over `out`, write its run record (and its draft, when valid) under `out/agent/`."""
    try:
        outputs_run = json.loads((out / "run.json").read_text(encoding="utf-8"))["run_id"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        raise AgentError(f"no readable {out / 'run.json'}: run `grc run` first") from e
    try:
        mapping = read_mapping(out / "mapping.json")
    except FileNotFoundError as e:
        raise AgentError(f"no {out / 'mapping.json'}: run `grc run` first") from e
    now = now or datetime.now(UTC)
    started = time.monotonic()
    transcript = provider(workflow, out, limits)
    problems = validate(workflow, transcript, mapping)
    attempts: list[Json] = []
    remaining = limits.budget_usd - transcript["cost_usd"]
    if problems and transcript["output"] is not None and remaining > 0:
        # One correction round: the model sees why its draft was rejected, on what is left of the budget.
        attempts.append({"transcript": transcript, "problems": problems})
        retry = replace(workflow, task=workflow.task + CORRECTION.format(
            problems="\n".join(f"- {p}" for p in problems), draft=json.dumps(transcript["output"], indent=1)))
        transcript = provider(retry, out, replace(limits, budget_usd=remaining))
        problems = validate(retry, transcript, mapping)
    name = f"{workflow.name}-{now.strftime('%Y%m%dT%H%M%SZ')}"
    folder = out / "agent"
    folder.mkdir(parents=True, exist_ok=True)
    draft = None
    if not problems and transcript["output"] is not None:
        draft = folder / f"{name}.md"
        draft.write_text(workflow.render(transcript["output"]), encoding="utf-8")
    prompt_hash = hashlib.sha256(f"{workflow.version}\n{workflow.prompt}\n{workflow.task}".encode()).hexdigest()
    record = {
        "workflow": workflow.name, "workflow_version": workflow.version, "prompt_sha256": prompt_hash,
        "engine": version("grc-evidence"), "outputs_run_id": outputs_run, "started": now.isoformat(timespec="seconds"),
        "duration_s": round(time.monotonic() - started, 1), "transcript": transcript,
        "validation": {"passed": not problems, "problems": problems}, "draft": draft.name if draft else None,
        "rejected_attempts": attempts,
    }
    (folder / f"{name}.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    # Agent runs keep their own ledger: the report's LLM line counts only the report's narration.
    with (folder / "usage.jsonl").open("a", encoding="utf-8") as ledger:
        for t in [a["transcript"] for a in attempts] + [transcript]:
            ledger.write(json.dumps({
                "ts": now.isoformat(timespec="seconds"), "run_id": outputs_run, "task": f"agent:{workflow.name}",
                "mode": t["provider"], "model": t["model"], "prompt_hash": prompt_hash, **t["usage"],
                "batch": False, "billed": t["billed"], "cost_usd": t["cost_usd"],
            }) + "\n")
    return record


def _workflows() -> dict[str, Workflow]:
    from grc_evidence.agents.posture import (
        POSTURE,  # imported here: workflow modules import this one
    )

    return {w.name: w for w in (POSTURE,)}


WORKFLOWS: dict[str, Workflow] = {}  # filled on first use by _workflows()
PROVIDERS: dict[str, Provider] = {"claude-cli": run_claude, "anthropic": run_anthropic, "replay": run_replay}


def main(argv: list[str] | None = None) -> None:
    if not WORKFLOWS:
        WORKFLOWS.update(_workflows())
    parser = argparse.ArgumentParser(prog="grc agent", description=__doc__)
    parser.add_argument("workflow", help=f"one of: {', '.join(sorted(WORKFLOWS)) or '(none yet)'}")
    parser.add_argument("--out", type=Path, default=Path("out"), help="where `grc run` wrote its outputs")
    args = parser.parse_args(argv)
    if args.workflow not in WORKFLOWS:
        raise AgentError(f"no workflow {args.workflow!r}; one of: {', '.join(sorted(WORKFLOWS)) or '(none yet)'}")
    mode = os.environ.get("LLM_MODE", "replay")
    if mode not in PROVIDERS:
        raise AgentError(f"LLM_MODE={mode!r} cannot run agents; one of: {', '.join(sorted(PROVIDERS))}")
    record = run_workflow(WORKFLOWS[args.workflow], PROVIDERS[mode], args.out, Limits.from_env())
    t = record["transcript"]
    cost = t["cost_usd"] + sum(a["transcript"]["cost_usd"] for a in record["rejected_attempts"])
    retried = f", after {len(record['rejected_attempts'])} rejected draft(s)" if record["rejected_attempts"] else ""
    print(f"agent {record['workflow']}: {t['turns']} turn(s), {len(t['tool_calls'])} tool call(s), denied {t['denials'] or 'none'}, "
          f"${cost:.4f} ({'billed' if t['billed'] else 'not billed'}){retried}")
    if not record["validation"]["passed"]:
        raise AgentError("draft rejected: " + "; ".join(record["validation"]["problems"]))
    print(f"agent: wrote {args.out / 'agent' / record['draft']}")
