"""grc gate: compliance may not get worse than the committed baseline."""

import json
from pathlib import Path

import pytest

from okf_grc import cli
from okf_grc.data import SCHEMA_VERSION
from okf_grc.gate import problems, summary

BASE = {"soc2:cc6.1": "not-satisfied", "soc2:cc7.1": "no-violations-detected", "soc2:cc8.1": "not-assessed"}
DOC = {"controls": BASE}  # a 1.2.x baseline: statuses only


def _mapping(statuses: dict[str, str], expired: list[str] | None = None, findings: list[dict] | None = None) -> dict:
    """`findings` all land on soc2:cc6.1."""
    mapping = {"controls": {k: {"status": s, "findings": (findings or []) if k == "soc2:cc6.1" else []} for k, s in statuses.items()}, "unmapped": [], "schema_version": SCHEMA_VERSION}
    return mapping | ({"expired_suppressions": expired} if expired is not None else {})


def test_unchanged_statuses_pass() -> None:
    assert problems(_mapping(BASE), DOC) == []


def test_a_control_newly_not_satisfied_fails() -> None:
    assert problems(_mapping(BASE | {"soc2:cc7.1": "not-satisfied"}), DOC) == [
        "soc2:cc7.1: no-violations-detected -> not-satisfied"
    ]


def test_already_not_satisfied_and_improvements_do_not_fail() -> None:
    assert problems(_mapping(BASE | {"soc2:cc8.1": "no-violations-detected"}), DOC) == []


def test_a_new_control_that_is_not_satisfied_fails() -> None:
    assert problems(_mapping(BASE | {"soc2:cc6.6": "not-satisfied"}), DOC) == ["soc2:cc6.6: not in the baseline -> not-satisfied"]


def test_an_expired_suppression_fails() -> None:
    assert problems(_mapping(BASE, expired=["suppressions/fp"]), DOC) == ["suppression suppressions/fp expired"]


def test_summary_marks_changes() -> None:
    table = summary(_mapping(BASE | {"soc2:cc7.1": "not-satisfied", "soc2:cc8.1": "no-violations-detected"}), DOC)
    assert "| `soc2:cc7.1` | no-violations-detected | not-satisfied | regressed |" in table
    assert "| `soc2:cc8.1` | not-assessed | no-violations-detected | changed |" in table
    assert "| `soc2:cc6.1` | not-satisfied | not-satisfied |  |" in table


def test_cli_writes_a_baseline_then_gates_against_it(tmp_path: Path) -> None:
    out, baseline, job_summary = tmp_path / "out", tmp_path / "expected" / "control-status.json", tmp_path / "summary.md"
    out.mkdir()
    (out / "mapping.json").write_text(json.dumps(_mapping(BASE)))
    cli.main(["gate", "--out", str(out), "--baseline", str(baseline), "--write-baseline"])
    assert json.loads(baseline.read_text()) == {"controls": dict(sorted(BASE.items())), "findings": []}
    cli.main(["gate", "--out", str(out), "--baseline", str(baseline), "--summary", str(job_summary)])
    assert job_summary.read_text().startswith("## Compliance gate")
    (out / "mapping.json").write_text(json.dumps(_mapping(BASE | {"soc2:cc7.1": "not-satisfied"})))
    with pytest.raises(SystemExit, match="soc2:cc7.1: no-violations-detected -> not-satisfied"):
        cli.main(["gate", "--out", str(out), "--baseline", str(baseline)])


def test_cli_without_a_baseline_says_how_to_create_it(tmp_path: Path) -> None:
    (tmp_path / "mapping.json").write_text(json.dumps(_mapping(BASE)))
    with pytest.raises(SystemExit, match="grc gate --write-baseline"):
        cli.main(["gate", "--out", str(tmp_path), "--baseline", str(tmp_path / "none.json")])


def _f(rule: str, severity: str, target: str = "k8s/a.yaml", **extra: str) -> dict:
    return {"tool": "trivy", "rule_id": rule, "severity": severity, "target": target, "message": "m", "tags": []} | extra


OLD = [_f("KSV-0012", "high")]
WITH_FINDINGS = {"controls": BASE, "findings": ["trivy:KSV-0012 k8s/a.yaml"]}


def test_a_new_finding_at_or_above_the_level_fails_in_a_control_already_failing() -> None:
    """#91: cc6.1 is already not-satisfied, yet a new high finding in it fails the gate."""
    new = [*OLD, _f("CVE-2026-1", "critical", "go.mod"), _f("KSV-0020", "medium")]
    assert problems(_mapping(BASE, findings=new), WITH_FINDINGS) == ["new critical finding: trivy:CVE-2026-1 go.mod"]
    assert problems(_mapping(BASE, findings=new), WITH_FINDINGS, "medium") == [
        "new critical finding: trivy:CVE-2026-1 go.mod",
        "new medium finding: trivy:KSV-0020 k8s/a.yaml",
    ]


def test_known_unknown_severity_and_accepted_findings_pass() -> None:
    """Identity omits the message; `unknown` never reaches a level; an accepted risk is not a regression."""
    findings = [_f("KSV-0012", "high") | {"message": "a newer message"}, _f("CKV_K8S_21", "unknown"),
                _f("CVE-2026-2", "critical", "go.mod", accepted="suppressions/accepted")]
    assert problems(_mapping(BASE, findings=findings), WITH_FINDINGS, "info") == []


def test_a_baseline_without_findings_checks_statuses_only() -> None:
    assert problems(_mapping(BASE, findings=[_f("CVE-2026-1", "critical")]), DOC) == []


def test_summary_counts_findings_not_in_the_baseline() -> None:
    table = summary(_mapping(BASE, findings=[*OLD, _f("KSV-0020", "low")]), WITH_FINDINGS)
    assert table.endswith("Findings not in the baseline (any severity): 1\n")
