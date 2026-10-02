"""grc agent (#118): the runner core and the Claude Code provider, from real recorded streams."""

import io
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from okf_grc import agent, cli
from okf_grc.agent import AgentError, Limits, Provider, Transcript, Workflow

STREAMS = Path(__file__).parent / "fixtures" / "agent" / "streams"
WORKFLOW = Workflow(
    name="probe", version="1", prompt="Answer from tool results only.", task="List the gaps.",
    tools=("gaps", "control_status"), schema={"type": "object", "properties": {"summary": {"type": "string"}}, "additionalProperties": False},
    render=lambda draft: f"# Probe\n\n{draft['summary']}\n",
)
NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


def _lines(name: str) -> list[str]:
    return (STREAMS / name).read_text().splitlines()


def _transcript(**changes: Any) -> Transcript:
    base: Transcript = {
        "provider": "replay", "model": "claude-haiku-4-5", "tool_calls": [], "denials": [], "turns": 2,
        "usage": {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        "cost_usd": 0.01, "billed": False, "output": {"summary": "The gaps are listed."}, "stopped": None,
    }
    return base | changes  # type: ignore[return-value]


def _out(tmp_path: Path) -> Path:
    return _api_out(tmp_path)


def test_claude_runs_isolated_with_only_the_workflows_tools() -> None:
    """No built-in tools, only our MCP server, no user settings (hooks, plugins, CLAUDE.md), no skills, a budget."""
    argv = agent.claude_argv(WORKFLOW, Limits(model="m", budget_usd=0.25), Path("/tmp/mcp.json"))
    pairs = {argv[i]: argv[i + 1] for i in range(len(argv) - 1) if argv[i].startswith("--")}
    assert argv[:2] == ["claude", "-p"]
    assert pairs["--tools"] == "" and pairs["--setting-sources"] == "" and pairs["--mcp-config"] == "/tmp/mcp.json"
    assert pairs["--max-budget-usd"] == "0.25" and pairs["--system-prompt"] == WORKFLOW.prompt and pairs["--model"] == "m"
    assert {"--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"} <= set(argv)
    assert argv[argv.index("--allowedTools") + 1 :] == ["mcp__okf-grc__gaps", "mcp__okf-grc__control_status"]


def test_a_recorded_stream_becomes_a_transcript() -> None:
    """A real run (gaps, on the demo repo, on the plan): the tool call and its full result, not billed."""
    transcript, early = agent.read_stream(_lines("gaps-success.jsonl"), "claude-haiku-4-5", max_turns=8)
    assert not early and transcript["stopped"] is None and transcript["provider"] == "claude-cli"
    (call,) = transcript["tool_calls"]
    assert call["name"] == "gaps" and call["arguments"] == {} and '"rule":"checkov:CKV_GCP_21"' in call["result"]
    assert transcript["denials"] == [] and not transcript["billed"] and transcript["turns"] >= 2
    assert transcript["usage"]["output_tokens"] > 0 and transcript["cost_usd"] > 0


def test_the_budget_stop_is_recorded() -> None:
    """A real run stopped by --max-budget-usd: no draft, the reason kept."""
    transcript, _ = agent.read_stream(_lines("budget-stopped.jsonl"), "claude-haiku-4-5", max_turns=8)
    assert transcript["stopped"] == "budget" and transcript["output"] is None


def test_the_turn_cap_stops_the_run() -> None:
    transcript, early = agent.read_stream(_lines("gaps-success.jsonl"), "claude-haiku-4-5", max_turns=1)
    assert early and transcript["stopped"] == "max_turns" and transcript["output"] is None


def test_a_denied_tool_is_recorded_as_a_denial_not_a_call() -> None:
    """As the recorded posture run showed: the model asks for gate, Claude Code refuses, the run goes on."""
    events = [
        {"type": "assistant", "message": {"id": "m1", "content": [{"type": "tool_use", "id": "t1", "name": "mcp__okf-grc__scan", "input": {}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": True,
                                                  "content": "Claude requested permissions to use mcp__okf-grc__scan, but you haven't granted it yet."}]}},
        {"type": "result", "subtype": "success", "is_error": False, "structured_output": {"summary": "x"},
         "permission_denials": [{"tool_name": "mcp__okf-grc__scan", "tool_input": {}}]},
    ]
    transcript, _ = agent.read_stream([json.dumps(e) for e in events], "m", max_turns=8)
    assert transcript["denials"] == ["scan"] and transcript["tool_calls"] == [] and transcript["output"] == {"summary": "x"}


class FakeProcess:
    """Stands in for the `claude` process: replays a stream on stdout."""

    def __init__(self, argv: list[str], lines: list[str], **kwargs: Any) -> None:
        self.argv, self.stdin, self.stderr = argv, io.StringIO(), io.StringIO("")
        self.stdout, self.returncode, self.terminated = iter(f"{ln}\n" for ln in lines), 0, False
        self.mcp = json.loads(Path(argv[argv.index("--mcp-config") + 1]).read_text())

    def terminate(self) -> None:
        self.terminated = True

    def wait(self) -> int:
        return self.returncode


def test_run_claude_points_the_cli_at_this_engines_server_and_stops_at_the_cap(tmp_path: Path) -> None:
    started: list[FakeProcess] = []

    def popen(argv: list[str], **kwargs: Any) -> FakeProcess:
        started.append(FakeProcess(argv, _lines("gaps-success.jsonl")))
        return started[0]

    transcript = agent.run_claude(WORKFLOW, tmp_path / "out", Limits(max_turns=1), popen)
    (proc,) = started
    server = proc.mcp["mcpServers"]["okf-grc"]
    assert server["command"] == sys.executable and server["args"][:3] == ["-m", "okf_grc.cli", "mcp"]
    assert server["args"][-1] == str((tmp_path / "out").absolute())
    assert transcript["stopped"] == "max_turns" and proc.terminated


def test_run_claude_without_the_cli_says_so(tmp_path: Path) -> None:
    def missing(argv: list[str], **kwargs: Any) -> Any:
        raise FileNotFoundError("claude")

    with pytest.raises(AgentError, match="claude not found on PATH"):
        agent.run_claude(WORKFLOW, tmp_path, Limits(), missing)


def test_a_run_writes_its_record_draft_and_ledger_line_and_nothing_else(tmp_path: Path) -> None:
    out = _out(tmp_path)
    record = agent.run_workflow(WORKFLOW, lambda w, o, lim: _transcript(), out, Limits(), NOW)
    folder = out / "agent"
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == ["mapping.json", "probe-20261002T120000Z.json", "probe-20261002T120000Z.md", "run.json", "usage.jsonl"]
    assert (folder / "probe-20261002T120000Z.md").read_text() == "# Probe\n\nThe gaps are listed.\n"
    assert record["validation"] == {"passed": True, "problems": []} and record["outputs_run_id"] == "run-1"
    assert json.loads((folder / "probe-20261002T120000Z.json").read_text()) == record
    line = json.loads((folder / "usage.jsonl").read_text())
    assert (line["task"], line["run_id"], line["billed"]) == ("agent:probe", "run-1", False)


def test_a_stopped_run_writes_no_draft(tmp_path: Path) -> None:
    out = _out(tmp_path)
    record = agent.run_workflow(WORKFLOW, lambda w, o, lim: _transcript(stopped="budget", output=None), out, Limits(), NOW)
    assert record["draft"] is None and record["validation"] == {"passed": False, "problems": ["the run stopped: budget"]}
    assert not (out / "agent" / "probe-20261002T120000Z.md").exists()


def test_a_run_needs_the_outputs(tmp_path: Path) -> None:
    with pytest.raises(AgentError, match="run `grc run` first"):
        agent.run_workflow(WORKFLOW, lambda w, o, lim: _transcript(), tmp_path, Limits(), NOW)


def test_replay_reads_a_recording_and_names_a_missing_one(tmp_path: Path) -> None:
    (tmp_path / "probe.json").write_text(json.dumps(_transcript()))
    assert agent.run_replay(WORKFLOW, tmp_path, Limits(), fixtures=tmp_path)["output"] == {"summary": "The gaps are listed."}
    with pytest.raises(AgentError, match="no recorded run"):
        agent.run_replay(WORKFLOW, tmp_path, Limits(), fixtures=tmp_path / "none")


def test_cli_runs_a_workflow_and_fails_on_a_rejected_draft(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    out = _out(tmp_path)
    monkeypatch.setitem(agent.WORKFLOWS, "probe", WORKFLOW)
    monkeypatch.setitem(agent.PROVIDERS, "replay", lambda w, o, lim: _transcript())
    cli.main(["agent", "probe", "--out", str(out)])
    assert "agent: wrote" in capsys.readouterr().out
    monkeypatch.setitem(agent.PROVIDERS, "replay", lambda w, o, lim: _transcript(stopped="max_turns", output=None))
    with pytest.raises(SystemExit, match="grc agent: draft rejected: the run stopped: max_turns"):
        cli.main(["agent", "probe", "--out", str(out)])
    monkeypatch.setenv("LLM_MODE", "batch")
    with pytest.raises(SystemExit, match="LLM_MODE='batch' cannot run agents"):
        cli.main(["agent", "probe", "--out", str(out)])


def test_the_draft_return_is_not_a_tool_call() -> None:
    """Claude Code returns the --json-schema draft through its own StructuredOutput tool; any other tool is kept."""
    events = [{"type": "assistant", "message": {"id": "m1", "content": [
        {"type": "tool_use", "id": "t1", "name": "StructuredOutput", "input": {"summary": "x"}},
        {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "ls"}}]}}]
    transcript, _ = agent.read_stream([json.dumps(e) for e in events], "m", max_turns=8)
    assert [c["name"] for c in transcript["tool_calls"]] == ["Bash"]


def _api_out(tmp_path: Path) -> Path:
    """Outputs the in-process MCP server reads: the fixture bundle's mapping."""
    from okf_grc.data import SCHEMA_VERSION
    from okf_grc.map_findings import map_findings
    from okf_grc.okf_lib import load_bundle

    fixtures = Path(__file__).parent / "fixtures"
    mapping = map_findings(load_bundle(fixtures / "bundle"), json.loads((fixtures / "findings.json").read_text()))
    out = tmp_path / "out"
    out.mkdir()
    (out / "mapping.json").write_text(json.dumps({"schema_version": SCHEMA_VERSION, **mapping}))
    (out / "run.json").write_text(json.dumps({"run_id": "run-1"}))
    return out


def _api(replies: list[dict]) -> tuple[Any, list[dict]]:
    """A fake Messages API: canned replies in order (the last repeats); every request body is kept."""
    import httpx2

    requests: list[dict] = []

    def open_objects(schema: Any) -> bool:
        """The real API's rule: every object in output_config's schema sets additionalProperties to false."""
        if isinstance(schema, dict):
            if schema.get("type") == "object" and schema.get("additionalProperties") is not False:
                return True
            return any(open_objects(v) for v in schema.values())
        return isinstance(schema, list) and any(open_objects(v) for v in schema)

    def handle(request: Any) -> Any:
        requests.append(json.loads(request.content))
        if open_objects(requests[-1].get("output_config", {}).get("format", {}).get("schema")):
            return httpx2.Response(400, json={"type": "error", "error": {"type": "invalid_request_error", "message":
                "output_config.format.schema: For 'object' type, 'additionalProperties' must be explicitly set to false"}})
        reply = replies[min(len(requests), len(replies)) - 1]
        return httpx2.Response(200, json={"id": f"msg_{len(requests)}", "type": "message", "role": "assistant",
                                          "model": "claude-haiku-4-5", "stop_sequence": None, **reply})

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handle)), requests


TOOL_USE = {"content": [{"type": "tool_use", "id": "toolu_1", "name": "gaps", "input": {}}], "stop_reason": "tool_use",
            "usage": {"input_tokens": 1000, "output_tokens": 100}}
FINAL = {"content": [{"type": "text", "text": '{"summary": "Two gaps."}'}], "stop_reason": "end_turn",
         "usage": {"input_tokens": 1500, "output_tokens": 50}}


@pytest.fixture
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


@pytest.mark.usefixtures("_api_key")
def test_the_api_sees_only_the_workflows_tools_and_they_run_against_the_server(tmp_path: Path) -> None:
    """#119: the SDK's tool runner and MCP helper, our in-process server; only the API's replies are canned."""
    http, requests = _api([TOOL_USE, FINAL])
    transcript = agent.run_anthropic(WORKFLOW, _api_out(tmp_path), Limits(), http_client=http)
    assert sorted(t["name"] for t in requests[0]["tools"]) == ["control_status", "gaps"]  # not scan, findings, ...
    assert requests[0]["output_config"]["format"]["type"] == "json_schema" and requests[0]["system"] == WORKFLOW.prompt
    (call,) = transcript["tool_calls"]
    assert call["name"] == "gaps" and "checkov:CKV_TEST_99" in call["result"] and not call["is_error"]
    assert "checkov:CKV_TEST_99" in json.dumps(requests[1]["messages"])  # the real result went back to the model
    assert transcript["output"] == {"summary": "Two gaps."} and transcript["stopped"] is None
    assert transcript["billed"] and transcript["turns"] == 2 and transcript["denials"] == []
    assert transcript["usage"]["input_tokens"] == 2500 and transcript["cost_usd"] == pytest.approx((2500 * 1 + 150 * 5) / 1e6)


@pytest.mark.usefixtures("_api_key")
def test_the_budget_stops_the_loop_before_the_next_call(tmp_path: Path) -> None:
    http, requests = _api([TOOL_USE, FINAL])
    transcript = agent.run_anthropic(WORKFLOW, _api_out(tmp_path), Limits(budget_usd=0.0001), http_client=http)
    assert transcript["stopped"] == "budget" and transcript["output"] is None and len(requests) == 1


@pytest.mark.usefixtures("_api_key")
def test_the_turn_cap_stops_a_model_that_keeps_calling_tools(tmp_path: Path) -> None:
    http, requests = _api([TOOL_USE])
    transcript = agent.run_anthropic(WORKFLOW, _api_out(tmp_path), Limits(max_turns=2), http_client=http)
    assert transcript["stopped"] == "max_turns" and transcript["turns"] == 2 and len(requests) == 2


@pytest.mark.usefixtures("_api_key")
def test_a_final_reply_that_is_not_json_is_stopped(tmp_path: Path) -> None:
    http, _ = _api([{**FINAL, "content": [{"type": "text", "text": "Two gaps, I think."}]}])
    transcript = agent.run_anthropic(WORKFLOW, _api_out(tmp_path), Limits(), http_client=http)
    assert transcript["stopped"] == "the model's final reply was not JSON" and transcript["output"] is None


def test_an_unpriced_model_cannot_be_budgeted(tmp_path: Path) -> None:
    with pytest.raises(AgentError, match="no price for 'claude-mystery'"):
        agent.run_anthropic(WORKFLOW, tmp_path, Limits(model="claude-mystery"))


STATUS_RESULT = json.dumps({"run_id": "run-1", "by_status": {"not-satisfied": 2}, "controls": [
    {"key": "soc2:cc6.1", "status": "not-satisfied", "findings": 2}, {"key": "soc2:cc7.1", "status": "not-satisfied", "findings": 1}]})
SCHEMA = {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}


def _check(draft: dict, results: tuple[str, ...] = (STATUS_RESULT,)) -> list[str]:
    """Validate a draft against the fixture mapping, as if the tools had returned `results`."""
    from okf_grc.contract import read_mapping

    mapping = read_mapping(_api_out(Path(tempfile.mkdtemp())) / "mapping.json")
    calls = [{"name": "control_status", "arguments": {}, "result": r, "is_error": False} for r in results]
    return agent.validate(WORKFLOW.__class__(**{**WORKFLOW.__dict__, "schema": SCHEMA}), _transcript(output=draft, tool_calls=calls), mapping)


def _unbound(problems: list[str]) -> list[int]:
    """The numbers a validation found not bound to what they count."""
    found = [p for p in problems if p.startswith("numbers that are not the count")]
    return [int(item.split()[0]) if item[0].isdigit() else int(item.split()[1]) for item in eval(found[0].split(": ", 1)[1])] if found else []


def test_an_invented_total_is_rejected() -> None:
    """#120, the prototype's failure: right controls, right counts, and a sum no tool returned (here 4; really 3)."""
    assert _unbound(_check({"summary": "cc6.1 (2 findings) and cc7.1 (1 finding) are not-satisfied, totaling 4 findings."})) == [4]
    assert _check({"summary": "cc6.1 (2 findings) and cc7.1 (1 finding) are not-satisfied."}) == []


def test_a_reported_number_next_to_the_wrong_thing_is_rejected() -> None:
    """#124, the demo repo's 1.7.0 draft: 11 is a count the tools reported (here, cc8.1's), but not of what it sits
    next to. Validation in 1.7 passed it; binding does not."""
    findings = json.dumps({"run_id": "run-1", "total": 8, "by_rule": {"trivy:CVE-1": 4, "trivy:CVE-2": 4}})
    other = json.dumps({"run_id": "run-1", "controls": [{"key": "soc2:cc8.1", "status": "not-satisfied", "findings": 11}]})
    draft = {"summary": "soc2:cc7.1: trivy:CVE-1 (4), plus 11 additional CVEs at 4 findings each."}
    assert _unbound(_check(draft, (findings, other))) == [11]
    assert _check({"summary": "soc2:cc7.1: trivy:CVE-1 (4), trivy:CVE-2 (4); soc2:cc8.1 has 11 findings."}, (findings, other)) == []


def test_a_count_in_a_field_must_be_its_controls_or_rules() -> None:
    assert _unbound(_check({"summary": "See below.", "controls": [{"key": "soc2:cc6.1", "findings": 3}]})) == [3]
    assert _check({"summary": "See below.", "controls": [{"key": "soc2:cc6.1", "findings": 2}]}) == []
    assert _unbound(_check({"summary": "Two controls.", "count": 9})) == [9]  # any other number: a reported total
    assert _check({"summary": "Two controls.", "count": 2}) == []


def test_text_inside_an_object_may_cite_its_own_count() -> None:
    """As posture writes "Six rules with 1 finding each" for a control with 6 findings."""
    result = json.dumps({"run_id": "run-1", "controls": [{"key": "soc2:cc6.1", "status": "not-satisfied", "findings": 6}],
                         "by_rule": {"checkov:CKV_GCP_12": 1}})
    draft = {"summary": "See below.", "groups": [{"key": "soc2:cc6.1", "findings": 6, "note": "Six rules with 1 finding each: checkov:CKV_GCP_12."}]}
    assert _check(draft, (result,)) == []


def test_a_control_that_does_not_exist_is_rejected() -> None:
    assert "controls that do not exist: ['soc2:cc9.9']" in _check({"summary": "Also cc9.9 needs work."})


def test_a_status_must_be_the_controls_own() -> None:
    """In a field next to the key, and in a sentence that names one control; "not satisfied" in plain words counts."""
    wrong = _check({"summary": "See below.", "controls": [{"key": "soc2:cc6.1", "status": "no-violations-detected"}]})
    assert wrong == ["soc2:cc6.1: draft says 'no-violations-detected', status is 'not-satisfied'"]
    assert _check({"summary": "cc6.1 shows no-violations-detected."})[0].startswith("soc2:cc6.1: draft says ['no-violations-detected']")
    assert _check({"summary": "cc6.1 is not satisfied. CC7.1 is not-satisfied too."}) == []


def test_a_compliance_claim_is_rejected() -> None:
    assert _check({"summary": "cc6.1 is compliant."})[0].startswith("forbidden claim 'compliant'")
    assert _check({"summary": "cc6.1 is not satisfied."}) == []  # plain words for the status, not a claim


def test_a_missing_field_is_rejected() -> None:
    assert _check({"note": "x"}) == ["missing field 'summary'"]


def test_names_with_digits_are_not_counts() -> None:
    """Run ids, dates the tools reported (and their years), ids they returned verbatim, and framework names."""
    result = json.dumps({"run_id": "82a46f28-3485-5abe-b1dc-2442fb88399b", "controls": [{"key": "soc2:cc6.1", "status": "not-satisfied", "findings": 2}],
                         "applied": [{"suppression": "suppressions/django-cve-2023-31047", "expires": "2026-12-30"}]})
    draft = {"summary": "Run 82a46f28-3485-5abe-b1dc-2442fb88399b: cc6.1 has 2 findings under SOC 2 and ISO/IEC 42001. "
                        "suppressions/django-cve-2023-31047 expires 2026-12-30, in 2026."}
    assert _check(draft, (result,)) == []
    assert _unbound(_check({"summary": "28 controls fail."}, (result,))) == [28]


def test_numbers_written_as_words_are_checked_too() -> None:
    """The trial posture run wrote "Seven controls": a spelled-out number must be bound like any other."""
    assert _check({"summary": "Two controls are not-satisfied."}) == []  # by_status reports 2
    assert _unbound(_check({"summary": "Six controls are not-satisfied."})) == [6]


def test_a_result_the_validator_cannot_read_binds_nothing() -> None:
    """Claude Code saved a 57.7 KB result to a file and gave the model a preview: nothing in it can be checked."""
    preview = "<persisted-output>\nOutput too large (57.7KB). Full output saved to: (a local file)\n{\"by_rule\": {\"checkov:CKV_K8S_21\": 41"
    assert _unbound(_check({"summary": "checkov:CKV_K8S_21 has 41 findings."}, (STATUS_RESULT, preview))) == [41]


def _two_drafts(first: dict, second: dict) -> tuple[Provider, list[str]]:
    """A provider whose first run drafts `first` and second run `second`; it keeps the tasks it was given."""
    tasks: list[str] = []
    calls = [{"name": "control_status", "arguments": {}, "result": STATUS_RESULT, "is_error": False}]

    def provider(workflow: Workflow, out: Path, limits: Limits) -> Transcript:
        tasks.append(workflow.task)
        return _transcript(output=first if len(tasks) == 1 else second, tool_calls=calls)

    return provider, tasks


def test_a_rejected_draft_gets_one_correction_round(tmp_path: Path) -> None:
    """#124: the model sees why, and its corrected draft is the one written; both attempts are recorded and billed."""
    out = _out(tmp_path)
    provider, tasks = _two_drafts({"summary": "There are 12 findings."}, {"summary": "cc6.1 has 2 findings."})
    record = agent.run_workflow(WORKFLOW, provider, out, Limits(), NOW)
    assert record["validation"] == {"passed": True, "problems": []} and record["draft"]
    (attempt,) = record["rejected_attempts"]
    assert _unbound(attempt["problems"]) == [12] and attempt["transcript"]["output"] == {"summary": "There are 12 findings."}
    assert "rejected for these reasons" in tasks[1] and "There are 12 findings." in tasks[1]
    assert len((out / "agent" / "usage.jsonl").read_text().splitlines()) == 2


def test_a_draft_rejected_twice_is_not_written(tmp_path: Path) -> None:
    out = _out(tmp_path)
    provider, tasks = _two_drafts({"summary": "There are 12 findings."}, {"summary": "There are 13 findings."})
    record = agent.run_workflow(WORKFLOW, provider, out, Limits(), NOW)
    assert not record["validation"]["passed"] and _unbound(record["validation"]["problems"]) == [13] and len(tasks) == 2
    assert record["draft"] is None and not list((out / "agent").glob("*.md"))


def test_no_correction_round_without_budget_or_after_a_stop(tmp_path: Path) -> None:
    provider, tasks = _two_drafts({"summary": "There are 12 findings."}, {"summary": "cc6.1 has 2 findings."})
    record = agent.run_workflow(WORKFLOW, provider, _out(tmp_path), Limits(budget_usd=0.01), NOW)  # the first run cost 0.01
    assert len(tasks) == 1 and record["rejected_attempts"] == [] and not record["validation"]["passed"]
    (tmp_path / "s").mkdir()
    stopped = agent.run_workflow(WORKFLOW, lambda w, o, lim: _transcript(stopped="max_turns", output=None), _out(tmp_path / "s"), Limits(), NOW)
    assert stopped["rejected_attempts"] == []


@pytest.mark.usefixtures("_api_key")
def test_an_api_refusal_is_a_one_line_error(tmp_path: Path) -> None:
    """The real API refused posture's first schema; a refusal is an AgentError, not a traceback."""
    open_schema = WORKFLOW.__class__(**{**WORKFLOW.__dict__, "schema": {"type": "object", "properties": {}}})
    http, _ = _api([FINAL])
    with pytest.raises(AgentError, match="the API refused the request: .*additionalProperties"):
        agent.run_anthropic(open_schema, _api_out(tmp_path), Limits(), http_client=http)


def test_a_number_beside_an_identifier_binds_to_it_not_to_a_total() -> None:
    """#125, the demo run with 1.8.0: "and 7 more CVEs" sat beside a CVE (4) and passed because 7 was also a reported
    total. A number that close to an identifier is that identifier's count or nothing."""
    findings = json.dumps({"run_id": "run-1", "total": 8, "by_rule": {"trivy:CVE-1": 4, "trivy:CVE-2": 4}})
    totals = json.dumps({"run_id": "run-1", "by_status": {"not-satisfied": 7}, "findings_by_status": {"not-satisfied": 417},
                         "controls": [{"key": "soc2:cc6.1", "status": "not-satisfied", "findings": 188}]})
    assert _unbound(_check({"summary": "soc2:cc7.1: trivy:CVE-1 (4), and 7 more CVEs at 4 findings each."}, (findings, totals))) == [7]
    assert _check({"summary": "Seven controls are not-satisfied with 417 total findings: soc2:cc6.1 (188 findings)."}, (findings, totals)) == []


def test_a_reported_date_written_in_words_is_a_name() -> None:
    """The same run: "active through December 30" for an expiry the tools reported as 2026-12-30."""
    result = json.dumps({"run_id": "run-1", "controls": [{"key": "soc2:cc6.1", "status": "not-satisfied", "findings": 2}],
                         "counts": {"applied": 1}, "applied": [{"suppression": "suppressions/s1", "expires": "2026-12-30"}]})
    assert _check({"summary": "One suppression is active through December 30."}, (result,)) == []
    assert _unbound(_check({"summary": "One suppression is active through December 31."}, (result,))) == [31]
