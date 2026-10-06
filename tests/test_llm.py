"""The LLM interface: offline replay, response cache, usage ledger, budget guard. No test touches the network."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from grc_evidence.llm import (
    LLM,
    REQUEST_TIMEOUT_S,
    BudgetExceeded,
    LLMError,
    Request,
    cost_usd,
    worst_case_usd,
)

SCHEMA = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"], "additionalProperties": False}
REQ = Request(task="t", system="stable bundle digest", user="per-run digest", schema=SCHEMA, max_tokens=100)
USAGE = {"input_tokens": 1000, "output_tokens": 200, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}


class FakeClient:
    """Stands in for anthropic.Anthropic: records params, returns one canned message."""

    def __init__(self, text: str = '{"x": 1}', stop_reason: str = "end_turn") -> None:
        self.calls: list[dict[str, Any]] = []
        self.message = SimpleNamespace(
            stop_reason=stop_reason,
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(**USAGE),
        )
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **params: Any) -> SimpleNamespace:
        self.calls.append(params)
        return self.message


def _llm(tmp_path: Path, **kw: Any) -> LLM:
    return LLM(fixtures=tmp_path / "fx", cache=tmp_path / "cache", ledger=tmp_path / "usage.jsonl", **kw)


def _ledger(tmp_path: Path) -> list[dict]:
    return [json.loads(ln) for ln in (tmp_path / "usage.jsonl").read_text().splitlines()]


def test_cost_from_usage() -> None:
    assert cost_usd("claude-haiku-4-5", USAGE) == pytest.approx(0.002)
    cached = {"input_tokens": 0, "cache_read_input_tokens": 1000, "output_tokens": 0}
    assert cost_usd("claude-haiku-4-5", cached) == pytest.approx(0.0001)
    assert cost_usd("claude-haiku-4-5", USAGE, batch=True) == pytest.approx(0.001)


def test_key_is_stable_and_input_sensitive() -> None:
    assert REQ.key("m") == REQ.key("m")
    assert REQ.key("m") != REQ.key("other")
    assert REQ.key("m") != Request("t", "stable bundle digest", "changed", SCHEMA, 100).key("m")


def test_replay_reads_the_fixture_and_bills_nothing(tmp_path: Path) -> None:
    llm = _llm(tmp_path)
    fixture = tmp_path / "fx" / f"{REQ.key(llm.model)}.json"
    fixture.parent.mkdir()
    fixture.write_text(json.dumps({"output": {"x": 7}, "usage": USAGE}))
    assert llm.complete(REQ) == {"x": 7}
    (entry,) = _ledger(tmp_path)
    assert (entry["mode"], entry["billed"], entry["cost_usd"], entry["input_tokens"]) == ("replay", False, 0.0, 1000)


def test_replay_without_fixture_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(LLMError, match="LLM_MODE=record"):
        _llm(tmp_path).complete(REQ)


def test_api_call_uses_cache_control_bounds_and_structured_output(tmp_path: Path) -> None:
    client = FakeClient()
    assert _llm(tmp_path, mode="anthropic", client=client).complete(REQ) == {"x": 1}
    (params,) = client.calls
    assert params["model"] == "claude-haiku-4-5" and params["max_tokens"] == 100
    assert params["timeout"] == REQUEST_TIMEOUT_S
    assert params["system"] == [{"type": "text", "text": "stable bundle digest", "cache_control": {"type": "ephemeral"}}]
    assert params["output_config"] == {"format": {"type": "json_schema", "schema": SCHEMA}}
    (entry,) = _ledger(tmp_path)
    assert entry["billed"] and entry["cost_usd"] == pytest.approx(0.002)


def test_second_identical_call_is_a_cache_hit(tmp_path: Path) -> None:
    client = FakeClient()
    llm = _llm(tmp_path, mode="anthropic", client=client)
    llm.complete(REQ)
    llm.complete(REQ)
    assert len(client.calls) == 1
    assert [e["billed"] for e in _ledger(tmp_path)] == [True, False]


def test_record_mode_writes_a_replayable_fixture(tmp_path: Path) -> None:
    _llm(tmp_path, mode="record", client=FakeClient()).complete(REQ)
    assert _llm(tmp_path).complete(REQ) == {"x": 1}


@pytest.mark.parametrize("stop_reason", ["max_tokens", "refusal"])
def test_truncated_or_refused_output_is_rejected(tmp_path: Path, stop_reason: str) -> None:
    with pytest.raises(LLMError, match=stop_reason):
        _llm(tmp_path, mode="anthropic", client=FakeClient(stop_reason=stop_reason)).complete(REQ)


def test_budget_guard_stops_before_the_call(tmp_path: Path) -> None:
    client = FakeClient()
    llm = _llm(tmp_path, mode="anthropic", client=client, budget_usd=worst_case_usd("claude-haiku-4-5", REQ) / 2)
    with pytest.raises(BudgetExceeded, match="no call made"):
        llm.complete(REQ)
    assert client.calls == []


def test_budget_counts_only_this_run(tmp_path: Path) -> None:
    old = {"run_id": "earlier", "cost_usd": 5.0}
    (tmp_path / "usage.jsonl").write_text(json.dumps(old) + "\n")
    _llm(tmp_path, mode="anthropic", client=FakeClient(), budget_usd=0.5).complete(REQ)


def test_unknown_mode_or_unpriced_model_is_refused(tmp_path: Path) -> None:
    with pytest.raises(LLMError, match="LLM_MODE"):
        _llm(tmp_path, mode="openai")
    with pytest.raises(LLMError, match="PRICES"):
        _llm(tmp_path, model="claude-unknown")


def test_claude_cli_mode_runs_headless_claude(tmp_path: Path) -> None:
    seen: list[list[str]] = []

    def runner(argv: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        assert kw["input"] == "per-run digest"
        out = {"result": '{"x": 3}', "usage": {"input_tokens": 10, "output_tokens": 2}}
        return subprocess.CompletedProcess(argv, 0, json.dumps(out), "")

    assert _llm(tmp_path, mode="claude-cli", runner=runner).complete(REQ) == {"x": 3}
    assert seen[0][:4] == ["claude", "-p", "--output-format", "json"]
    (entry,) = _ledger(tmp_path)
    assert entry["mode"] == "claude-cli" and entry["cost_usd"] == 0.0


class FakeBatches:
    """Stands in for client.messages.batches: ends at once and returns one canned result per request."""

    def __init__(self, message: SimpleNamespace) -> None:
        self.message = message
        self.created: list[dict[str, Any]] = []

    def create(self, requests: list[dict[str, Any]]) -> SimpleNamespace:
        self.created = requests
        return SimpleNamespace(id="batch_1")

    def retrieve(self, batch_id: str) -> SimpleNamespace:
        return SimpleNamespace(id=batch_id, processing_status="ended")

    def results(self, batch_id: str) -> list[SimpleNamespace]:
        ok = SimpleNamespace(type="succeeded", message=self.message)
        return [SimpleNamespace(custom_id=r["custom_id"], result=ok) for r in reversed(self.created)]


def test_batch_bounds_each_request_and_bills_half(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    client = FakeClient()
    client.messages.batches = FakeBatches(client.message)
    other = Request(task="t", system="stable bundle digest", user="another digest", schema=SCHEMA, max_tokens=100)
    outputs = _llm(tmp_path, mode="anthropic", client=client).complete_batch({"a": REQ, "b": other})
    assert outputs == {"a": {"x": 1}, "b": {"x": 1}}
    assert [r["params"]["max_tokens"] for r in client.messages.batches.created] == [100, 100]
    assert [e["cost_usd"] for e in _ledger(tmp_path)] == [pytest.approx(0.001)] * 2
    assert "llm: batch batch_1 submitted (2 requests)" in capsys.readouterr().err


@pytest.mark.parametrize("custom_id", ["baseline/tune/chunk-0", "", "x" * 65, "a b"])
def test_batch_custom_ids_are_checked_before_any_call(tmp_path: Path, custom_id: str) -> None:
    client = FakeClient()
    with pytest.raises(LLMError, match="custom_id"):
        _llm(tmp_path, mode="anthropic", client=client).complete_batch({custom_id: REQ})
    assert client.calls == []


def test_sonnet_runs_without_thinking_and_haiku_is_unchanged(tmp_path: Path) -> None:
    sonnet, haiku = FakeClient(), FakeClient()
    _llm(tmp_path / "s", mode="anthropic", model="claude-sonnet-5", client=sonnet).complete(REQ)
    _llm(tmp_path / "h", mode="anthropic", client=haiku).complete(REQ)
    assert sonnet.calls[0]["thinking"] == {"type": "disabled"}
    assert "thinking" not in haiku.calls[0]


def test_from_env_default_model_yields_to_llm_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert LLM.from_env(tmp_path, default_model="claude-sonnet-5").model == "claude-sonnet-5"
    assert LLM.from_env(tmp_path).model == "claude-haiku-4-5"
    monkeypatch.setenv("LLM_MODEL", "claude-haiku-4-5")
    assert LLM.from_env(tmp_path, default_model="claude-sonnet-5").model == "claude-haiku-4-5"


def test_batch_budget_guard_sums_the_whole_batch(tmp_path: Path) -> None:
    client = FakeClient()
    client.messages.batches = FakeBatches(client.message)
    one = worst_case_usd("claude-haiku-4-5", REQ) * 0.5  # batch price
    reqs = {f"r{i}": Request("t", "s", f"user {i}", SCHEMA, 100) for i in range(4)}
    llm = _llm(tmp_path, mode="anthropic", client=client, budget_usd=one * 2.5)  # each fits alone; four do not
    with pytest.raises(BudgetExceeded, match="batch of 4"):
        llm.complete_batch(reqs)
    assert client.messages.batches.created == []


def test_no_cache_always_calls_and_leaves_the_cache_alone(tmp_path: Path) -> None:
    client = FakeClient()
    llm = _llm(tmp_path, mode="anthropic", client=client, use_cache=False)
    llm.complete(REQ)
    llm.complete(REQ)
    assert len(client.calls) == 2
    assert not (tmp_path / "cache").exists()


@pytest.mark.parametrize(
    ("content", "error"),
    [([], "StopIteration"), ([SimpleNamespace(type="text", text="not json")], "JSONDecodeError")],
    ids=["no-text-block", "not-json"],
)
def test_a_malformed_api_response_is_an_llm_error(tmp_path: Path, content: list, error: str) -> None:
    """#67: callers catch LLMError and fall back; any other exception would crash the run."""
    client = FakeClient()
    client.message.content = content
    with pytest.raises(LLMError, match=error):
        _llm(tmp_path, mode="anthropic", client=client).complete(REQ)


@pytest.mark.parametrize("stdout", ["not json", '{"usage": {}}', '{"result": "not json"}'], ids=["stdout", "no-result", "result"])
def test_a_malformed_claude_cli_response_is_an_llm_error(tmp_path: Path, stdout: str) -> None:
    def runner(argv: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    with pytest.raises(LLMError, match="no JSON result"):
        _llm(tmp_path, mode="claude-cli", runner=runner).complete(REQ)


def test_a_stalled_batch_stops_after_the_deadline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """#94: polling has a limit and names the batch, instead of looping forever."""
    client = FakeClient()
    client.messages.batches = FakeBatches(client.message)
    monkeypatch.setattr(client.messages.batches, "retrieve", lambda batch_id: SimpleNamespace(id=batch_id, processing_status="in_progress", request_counts={}))
    clock = iter(range(0, 10_000, 1800))
    monkeypatch.setattr("grc_evidence.llm.time.monotonic", lambda: next(clock))
    monkeypatch.setattr("grc_evidence.llm.time.sleep", lambda s: None)
    with pytest.raises(LLMError, match="batch batch_1: not ended after 3600 s"):
        _llm(tmp_path, mode="anthropic", client=client).complete_batch({"a": REQ})
