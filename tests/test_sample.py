"""`grc sample`: per-change evidence for the changes an auditor sampled (Spec H §6); a gap is never a pass."""

import csv
import json
from pathlib import Path

import pytest

from grc_evidence import cli
from grc_evidence.errors import GrcError
from grc_evidence.sample import COLUMNS, read_sample_list, sample_evidence


def _change(number: int, checks: list[list[str]], flags: str = "", repo: str = "acme/api") -> dict:
    return {"repo": repo, "number": number, "merged_at": "2026-07-02T00:00:00Z", "approvers": "p-1234567890",
            "flags": flags, "checks": checks}


DOC = {"summary": {}, "changes": [
    _change(1, [["semgrep", "SUCCESS"], ["ci/build", "SUCCESS"]]),
    _change(2, [["semgrep", "SKIPPED"], ["ci/build", "NEUTRAL"]]),
    _change(3, []),
    _change(4, [["ci/build", "SUCCESS"]]),
    _change(5, [["semgrep", "FAILURE"], ["ci/build", "SUCCESS"]]),
    _change(6, [["semgrep", "SUCCESS"]], flags="checks_incomplete"),
    _change(7, [["Semgrep scan", "PENDING"]]),
]}


def _row(number: int, repo: str = "acme/api") -> dict:
    (row,) = sample_evidence(DOC, [(repo, number)], ("semgrep",))
    return row


def test_columns_match_the_spec() -> None:
    assert COLUMNS == ("repo", "number", "merged_at", "approvers", "ci_conclusion", "scanner_checks", "missing")
    assert list(_row(1)) == list(COLUMNS)


def test_all_checks_passed() -> None:
    row = _row(1)
    assert (row["ci_conclusion"], row["scanner_checks"], row["missing"]) == ("success", "semgrep=SUCCESS", "")
    assert (row["merged_at"], row["approvers"]) == ("2026-07-02T00:00:00Z", "p-1234567890")


def test_skipped_counts_as_success() -> None:
    assert _row(2)["ci_conclusion"] == "success"


def test_no_checks_is_none_not_success() -> None:
    row = _row(3)
    assert row["ci_conclusion"] == "none" and row["missing"] == "no-checks;no-scanner-check"


def test_no_scanner_check_is_missing() -> None:
    assert _row(4)["missing"] == "no-scanner-check"


def test_a_failed_or_pending_check_is_a_failure() -> None:
    assert _row(5)["ci_conclusion"] == "failure" and _row(5)["scanner_checks"] == "semgrep=FAILURE"
    assert _row(7)["ci_conclusion"] == "failure" and _row(7)["scanner_checks"] == "Semgrep scan=PENDING"


def test_incomplete_checks_are_never_a_success() -> None:
    row = _row(6)
    assert row["ci_conclusion"] == "incomplete" and row["missing"] == "checks-incomplete"


def test_not_in_population_is_missing() -> None:
    row = _row(99)
    assert (row["ci_conclusion"], row["missing"], row["merged_at"]) == ("none", "not-in-population", "")
    assert _row(1, repo="ACME/API")["missing"] == ""  # GitHub names do not depend on case


def test_bad_sample_header_raises(tmp_path: Path) -> None:
    (tmp_path / "s.csv").write_text("repository,pr\nacme/api,1\n")
    with pytest.raises(GrcError, match="repo,number"):
        read_sample_list(tmp_path / "s.csv")
    (tmp_path / "s.csv").write_text("repo,number\nacme/api,one\n")
    with pytest.raises(GrcError, match="line 2"):
        read_sample_list(tmp_path / "s.csv")


def test_extra_sample_columns_are_ignored(tmp_path: Path) -> None:
    (tmp_path / "s.csv").write_text("number,repo,note\n1,acme/api,picked by the auditor\n")
    assert read_sample_list(tmp_path / "s.csv") == [("acme/api", 1)]


def test_grc_sample_writes_the_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "grc.yaml").write_text("github:\n  scanner_jobs: [semgrep]\n")
    (tmp_path / "out" / "collect").mkdir(parents=True)
    (tmp_path / "out" / "collect" / "changes.json").write_text(json.dumps(DOC))
    (tmp_path / "sample.csv").write_text("repo,number\nacme/api,1\n=evil(),3\n")
    cli.main(["sample", "--list", "sample.csv"])
    rows = list(csv.reader((tmp_path / "out" / "collect" / "sample-evidence.csv").open()))
    assert rows[0] == list(COLUMNS) and rows[1][:2] == ["acme/api", "1"]
    assert rows[2][0] == "'=evil()" and rows[2][6] == "not-in-population"  # an untrusted cell cannot start a formula
    assert "2 sampled changes, 1 with missing evidence" in capsys.readouterr().out


def test_grc_sample_needs_a_population(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sample.csv").write_text("repo,number\nacme/api,1\n")
    with pytest.raises(SystemExit, match="grc collect changes"):
        cli.main(["sample", "--list", "sample.csv"])
