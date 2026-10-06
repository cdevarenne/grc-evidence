"""`grc window`: each control's history over the audit window, from the ledger's `run` entries only (Spec H §6)."""

import json
from datetime import date
from pathlib import Path

import pytest

from grc_evidence import cli, ledger
from grc_evidence.window import utc_bounds
from grc_evidence.window_report import render_window, silences, window_status

B = utc_bounds(date(2026, 6, 1), date(2026, 6, 30))
DONE = date(2026, 10, 1)  # the window is over
OK, BAD = "no-violations-detected", "not-satisfied"


def _run(day: str, status: str = OK, at: str = "06:00:00", key: str = "soc2:cc8.1") -> dict:
    return {"collector": "run", "repo": None, "recorded_at": f"{day}T{at}+00:00", "summary": {key: status}}


def _daily(first: int, last: int, status: str = OK) -> list[dict]:
    return [_run(f"2026-06-{d:02d}", status) for d in range(first, last + 1)]


def _cc81(entries: list[dict], today: date = DONE) -> dict:
    return window_status(entries, B, 7, today)["soc2:cc8.1"]


def test_every_day_satisfied_has_no_gap() -> None:
    assert _cc81(_daily(1, 30)) == {"first_satisfied": "2026-06-01", "last_evidence": "2026-06-30", "gaps": []}


def test_seeded_gap() -> None:
    entries = [*_daily(1, 10), _run("2026-06-11", BAD), *_daily(12, 30)]
    assert _cc81(entries)["gaps"] == [["2026-06-11", "2026-06-11"]]


def test_silence_longer_than_max_is_gap() -> None:
    entries = [_run("2026-06-01"), _run("2026-06-20"), *_daily(21, 30)]
    assert _cc81(entries)["gaps"] == [["2026-06-02", "2026-06-19"]]


def test_short_silence_is_not_a_gap() -> None:
    entries = [*_daily(1, 10), *_daily(18, 30)]  # 7 silent days, max 7
    assert _cc81(entries)["gaps"] == []


def test_silence_at_the_window_start_counts() -> None:
    assert _cc81(_daily(12, 30))["gaps"] == [["2026-06-01", "2026-06-11"]]


def test_no_entries_whole_window_gap() -> None:
    assert window_status([], B, 7, DONE) == {}
    assert silences([], B, 7, DONE) == [["2026-06-01", "2026-06-30"]]


def test_same_day_entries_last_wins() -> None:
    """Review focus 4: two runs on one day count once, and the later one decides."""
    entries = [*_daily(1, 30), _run("2026-06-15", BAD, at="23:00:00")]
    assert _cc81(entries)["gaps"] == [["2026-06-15", "2026-06-15"]]
    fixed = [*_daily(1, 14), _run("2026-06-15", BAD, at="05:00:00"), _run("2026-06-15", OK, at="06:00:00"), *_daily(16, 30)]
    assert _cc81(fixed)["gaps"] == []


def test_entries_outside_window_ignored() -> None:
    entries = [_run("2026-05-31", BAD, at="23:59:59"), *_daily(1, 30), _run("2026-07-01", BAD, at="00:00:00")]
    assert _cc81(entries)["gaps"] == []
    assert _cc81([*_daily(1, 30), {**_run("2026-06-10", BAD), "collector": "scm"}])["gaps"] == []  # only run entries


def test_an_open_window_ends_today() -> None:
    entries = _daily(1, 10)
    assert _cc81(entries, today=date(2026, 6, 15))["gaps"] == []  # 5 quiet days so far
    assert _cc81(entries, today=date(2026, 6, 25))["gaps"] == [["2026-06-11", "2026-06-24"]]  # a long silence is a gap now
    assert _cc81([*entries, _run("2026-06-25")], today=date(2026, 6, 25))["gaps"] == [["2026-06-11", "2026-06-24"]]
    assert _cc81(entries, today=date(2026, 6, 11))["gaps"] == []  # today has no run yet: not counted


def test_a_control_missing_from_a_run_is_not_a_pass() -> None:
    """A run entry holds every control; cc8.1 joins the bundle on 06-16."""
    entries = [{**_run(f"2026-06-{d:02d}", key="soc2:cc6.1"), "summary": {"soc2:cc6.1": OK, **({"soc2:cc8.1": OK} if d >= 16 else {})}}
               for d in range(1, 31)]
    status = window_status(entries, B, 7, DONE)
    assert status["soc2:cc8.1"]["gaps"] == [["2026-06-01", "2026-06-15"]] and status["soc2:cc8.1"]["first_satisfied"] == "2026-06-16"
    assert status["soc2:cc6.1"]["gaps"] == []


def test_render_window_is_a_table() -> None:
    entries = [*_daily(1, 10), _run("2026-06-11", BAD), *_daily(12, 30)]
    text = render_window(window_status(entries, B, 7, DONE), silences(entries, B, 7, DONE), B, 30)
    assert "| `soc2:cc8.1` | 2026-06-01 | 2026-06-30 | 2026-06-11 |" in text
    assert "2026-06-01 to 2026-06-30" in text and "30 days with a run" in text


def _repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entries: list[dict]) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "grc.yaml").write_text("window: {start: 2026-06-01, end: 2026-06-30}\n")
    for e in entries:
        ledger.append(tmp_path / "evidence" / "ledger.jsonl", {**e, "window": None, "inputs": {}, "outputs": {},
                                                               "rate_limit": None, "supersedes": None, "engine_version": "2.0.0"})
    return tmp_path


def test_grc_window_writes_json_and_markdown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path, monkeypatch, [*_daily(1, 10), _run("2026-06-11", BAD), *_daily(12, 30)])
    cli.main(["window"])
    doc = json.loads((repo / "out" / "window.json").read_text())
    assert doc["window"] == {"start": "2026-06-01", "end": "2026-06-30"} and doc["run_days"] == 30
    assert doc["controls"]["soc2:cc8.1"]["gaps"] == [["2026-06-11", "2026-06-11"]] and doc["silences"] == []
    assert "soc2:cc8.1" in (repo / "out" / "window.md").read_text()


def test_grc_window_refuses_a_broken_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path, monkeypatch, _daily(1, 3))
    path = repo / "evidence" / "ledger.jsonl"
    path.write_text(path.read_text().replace(OK, BAD, 1))
    with pytest.raises(SystemExit, match="ledger line 1: hash mismatch"):
        cli.main(["window"])
    assert not (repo / "out" / "window.json").exists()
