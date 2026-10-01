"""grc gate: compliance may not get worse than the committed baseline."""

import json
from pathlib import Path

import pytest

from okf_grc import cli
from okf_grc.gate import problems, summary

BASE = {"soc2:cc6.1": "not-satisfied", "soc2:cc7.1": "no-violations-detected", "soc2:cc8.1": "not-assessed"}


def _mapping(statuses: dict[str, str], expired: list[str] | None = None) -> dict:
    mapping = {"controls": {k: {"status": s} for k, s in statuses.items()}, "unmapped": []}
    return mapping | ({"expired_suppressions": expired} if expired is not None else {})


def test_unchanged_statuses_pass() -> None:
    assert problems(_mapping(BASE), BASE) == []


def test_a_control_newly_not_satisfied_fails() -> None:
    assert problems(_mapping(BASE | {"soc2:cc7.1": "not-satisfied"}), BASE) == [
        "soc2:cc7.1: no-violations-detected -> not-satisfied"
    ]


def test_already_not_satisfied_and_improvements_do_not_fail() -> None:
    assert problems(_mapping(BASE | {"soc2:cc8.1": "no-violations-detected"}), BASE) == []


def test_a_new_control_that_is_not_satisfied_fails() -> None:
    assert problems(_mapping(BASE | {"soc2:cc6.6": "not-satisfied"}), BASE) == ["soc2:cc6.6: not in the baseline -> not-satisfied"]


def test_an_expired_suppression_fails() -> None:
    assert problems(_mapping(BASE, expired=["suppressions/fp"]), BASE) == ["suppression suppressions/fp expired"]


def test_summary_marks_changes() -> None:
    table = summary(_mapping(BASE | {"soc2:cc7.1": "not-satisfied", "soc2:cc8.1": "no-violations-detected"}), BASE)
    assert "| `soc2:cc7.1` | no-violations-detected | not-satisfied | regressed |" in table
    assert "| `soc2:cc8.1` | not-assessed | no-violations-detected | changed |" in table
    assert "| `soc2:cc6.1` | not-satisfied | not-satisfied |  |" in table


def test_cli_writes_a_baseline_then_gates_against_it(tmp_path: Path) -> None:
    out, baseline, job_summary = tmp_path / "out", tmp_path / "expected" / "control-status.json", tmp_path / "summary.md"
    out.mkdir()
    (out / "mapping.json").write_text(json.dumps(_mapping(BASE)))
    cli.main(["gate", "--out", str(out), "--baseline", str(baseline), "--write-baseline"])
    assert json.loads(baseline.read_text()) == {"controls": dict(sorted(BASE.items()))}
    cli.main(["gate", "--out", str(out), "--baseline", str(baseline), "--summary", str(job_summary)])
    assert job_summary.read_text().startswith("## Compliance gate")
    (out / "mapping.json").write_text(json.dumps(_mapping(BASE | {"soc2:cc7.1": "not-satisfied"})))
    with pytest.raises(SystemExit, match="soc2:cc7.1: no-violations-detected -> not-satisfied"):
        cli.main(["gate", "--out", str(out), "--baseline", str(baseline)])


def test_cli_without_a_baseline_says_how_to_create_it(tmp_path: Path) -> None:
    (tmp_path / "mapping.json").write_text(json.dumps(_mapping(BASE)))
    with pytest.raises(SystemExit, match="grc gate --write-baseline"):
        cli.main(["gate", "--out", str(tmp_path), "--baseline", str(tmp_path / "none.json")])
