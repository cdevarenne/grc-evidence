"""The evidence ledger: append-only JSON Lines with a hash chain (Spec H §3.2)."""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from grc_evidence import cli
from grc_evidence.ledger import (
    LEDGER_SCHEMA,
    LedgerError,
    append,
    canonical,
    first_problem,
    make_entry,
    read,
    verify,
)

NOW = "2026-10-05T12:00:00+00:00"


def _entry(collector: str) -> dict:
    return make_entry(
        collector, None if collector == "run" else "acme/api", {"start": "2026-06-01", "end": "2026-08-31"},
        {"branch": "main"}, {"collect/population.csv": "ab" * 32}, {"in_population": 3}, {"cost": 1, "remaining": 4999},
        NOW, "2.0.0",
    )


def test_chain(tmp_path: Path) -> None:
    p = tmp_path / "evidence" / "l.jsonl"
    a = append(p, _entry("scm"))
    b = append(p, _entry("changes"))
    assert a["prev_id"] is None and b["prev_id"] == a["entry_id"]
    assert a["schema_version"] == LEDGER_SCHEMA == "1.0"
    assert read(p) == [a, b]
    assert verify(p) is None


def test_entry_fields_match_the_spec() -> None:
    assert set(_entry("scm")) == {
        "recorded_at", "engine_version", "collector", "repo", "window", "inputs", "outputs", "summary", "rate_limit",
        "supersedes",
    }


def test_edit_fails(tmp_path: Path) -> None:
    p = tmp_path / "l.jsonl"
    append(p, _entry("scm"))
    append(p, _entry("changes"))
    lines = p.read_text().splitlines()
    lines[0] = lines[0].replace('"scm"', '"run"')
    p.write_text("\n".join(lines) + "\n")
    assert verify(p) == 1


def test_deleted_line_breaks_chain(tmp_path: Path) -> None:
    p = tmp_path / "l.jsonl"
    for collector in ("scm", "changes", "run"):
        append(p, _entry(collector))
    p.write_text("".join(p.read_text().splitlines(keepends=True)[1:]))
    assert verify(p) == 1  # the new first line still names a prev_id


@pytest.mark.parametrize("rewrite", [
    lambda line: line.replace('"collector":"scm"', '"collector":"scm","collector":"run"', 1),  # duplicate key
    lambda line: line.replace('","', '", "', 1),  # not canonical spacing
    lambda line: line[:-1] + ',"extra":NaN}',  # NaN is not JSON
])
def test_a_line_must_be_its_canonical_form(tmp_path: Path, rewrite: Callable[[str], str]) -> None:
    """Another JSON reader must see exactly what was hashed: duplicate keys, spacing and NaN fail."""
    p = tmp_path / "l.jsonl"
    append(p, _entry("scm"))
    line = p.read_text().rstrip("\n")
    p.write_text(rewrite(line) + "\n")
    assert first_problem(p) == (1, "not canonical")


def test_nan_is_never_written(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        append(tmp_path / "l.jsonl", {**_entry("scm"), "summary": {"x": float("nan")}})


def test_entry_id_excludes_itself(tmp_path: Path) -> None:
    stored = append(tmp_path / "l.jsonl", _entry("scm"))
    rest = {k: v for k, v in stored.items() if k != "entry_id"}
    assert stored["entry_id"] == hashlib.sha256(canonical(rest)).hexdigest()


def test_lines_are_canonical_json(tmp_path: Path) -> None:
    p = tmp_path / "l.jsonl"
    stored = append(p, _entry("scm"))
    assert p.read_bytes() == canonical(stored) + b"\n"


def test_missing_and_empty_ledgers_are_valid(tmp_path: Path) -> None:
    assert read(tmp_path / "none.jsonl") == [] and verify(tmp_path / "none.jsonl") is None
    (tmp_path / "empty.jsonl").write_text("")  # the demo's ledger branch starts with an empty file
    assert verify(tmp_path / "empty.jsonl") is None
    assert append(tmp_path / "empty.jsonl", _entry("scm"))["prev_id"] is None


def test_cli_verify_exit_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "evidence" / "ledger.jsonl"
    append(p, _entry("scm"))
    append(p, _entry("changes"))
    cli.main(["ledger", "verify"])
    assert "2 entries" in capsys.readouterr().out
    lines = p.read_text().splitlines()
    second = json.loads(lines[1])
    second["prev_id"] = "0" * 64
    second["entry_id"] = hashlib.sha256(canonical({k: v for k, v in second.items() if k != "entry_id"})).hexdigest()
    p.write_text(lines[0] + "\n" + canonical(second).decode() + "\n")
    with pytest.raises(SystemExit, match="ledger line 2: broken chain"):
        cli.main(["ledger", "verify", "--ledger", "evidence/ledger.jsonl"])
    p.write_text(lines[0].replace('"scm"', '"run"') + "\n")
    with pytest.raises(SystemExit, match="ledger line 1: hash mismatch"):
        cli.main(["ledger", "verify"])


def _at(entry: dict, recorded_at: str) -> dict:
    return {**entry, "recorded_at": recorded_at}


def test_a_back_dated_entry_fails(tmp_path: Path) -> None:
    """The chain proves no line changed; time must also never go back, or an appended line could fill a past gap."""
    p = tmp_path / "l.jsonl"
    append(p, _at(_entry("run"), "2026-06-20T06:00:00+00:00"))
    with pytest.raises(LedgerError, match="before the line before"):
        append(p, _at(_entry("run"), "2026-06-10T06:00:00+00:00"))
    first = p.read_text()
    second = json.loads(first)
    second = {k: v for k, v in second.items() if k not in ("entry_id", "schema_version", "prev_id")}
    stored = {**_at(second, "2026-06-10T06:00:00+00:00"), "schema_version": LEDGER_SCHEMA, "prev_id": json.loads(first)["entry_id"]}
    stored["entry_id"] = hashlib.sha256(canonical(stored)).hexdigest()
    p.write_text(first + canonical(stored).decode() + "\n")  # chained correctly, but back-dated
    assert first_problem(p) == (2, "recorded before the line before")


def test_a_future_entry_fails(tmp_path: Path) -> None:
    p = tmp_path / "l.jsonl"
    append(p, _at(_entry("run"), "2026-06-20T06:00:00+00:00"))
    assert first_problem(p, now=datetime(2026, 6, 20, 6, 4, tzinfo=UTC)) is None  # within the clock slack
    assert first_problem(p, now=datetime(2026, 6, 20, 5, 0, tzinfo=UTC)) == (1, "recorded in the future")


def test_a_missing_recorded_at_fails(tmp_path: Path) -> None:
    p = tmp_path / "l.jsonl"
    append(p, {k: v for k, v in _entry("run").items() if k != "recorded_at"})
    assert first_problem(p) == (1, "no valid recorded_at")
