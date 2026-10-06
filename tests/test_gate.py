"""grc gate: compliance may not get worse than the committed baseline."""

import json
from pathlib import Path

import pytest

from grc_evidence import cli
from grc_evidence.data import SCHEMA_VERSION
from grc_evidence.gate import baseline_doc, problems, summary

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
    assert json.loads(baseline.read_text()) == {"controls": dict(sorted(BASE.items())), "findings": {}}
    cli.main(["gate", "--out", str(out), "--baseline", str(baseline), "--summary", str(job_summary)])
    assert job_summary.read_text().startswith("## Compliance gate")
    (out / "mapping.json").write_text(json.dumps(_mapping(BASE | {"soc2:cc7.1": "not-satisfied"})))
    with pytest.raises(SystemExit, match="soc2:cc7.1: no-violations-detected -> not-satisfied"):
        cli.main(["gate", "--out", str(out), "--baseline", str(baseline)])


def test_cli_without_a_baseline_says_how_to_create_it(tmp_path: Path) -> None:
    (tmp_path / "mapping.json").write_text(json.dumps(_mapping(BASE)))
    with pytest.raises(SystemExit, match="grc gate --write-baseline"):
        cli.main(["gate", "--out", str(tmp_path), "--baseline", str(tmp_path / "none.json")])


def _f(rule: str, severity: str, target: str = "k8s/a.yaml", message: str = "m", **extra: str) -> dict:
    """A finding; a CVE-, GHSA- or GO- rule is tagged a vulnerability, as run_scan tags Trivy's advisories."""
    tags = ["vulnerability"] if rule.startswith(("CVE-", "GHSA-", "GO-")) else []
    return {"tool": "trivy", "rule_id": rule, "severity": severity, "target": target, "message": message, "tags": tags} | extra


OLD = [_f("KSV-0012", "high")]
WITH_FINDINGS = {"controls": BASE, "findings": {"trivy:KSV-0012 k8s/a.yaml": 1}}


def test_a_new_code_finding_fails_at_any_severity_in_a_control_already_failing() -> None:
    """#113: a code or configuration finding can only come from a change, so `unknown` fails too."""
    new = [*OLD, _f("CKV_K8S_21", "unknown"), _f("KSV-0020", "low")]
    assert problems(_mapping(BASE, findings=new), WITH_FINDINGS, "critical") == [
        "new finding: trivy:CKV_K8S_21 k8s/a.yaml (0 -> 1)",
        "new finding: trivy:KSV-0020 k8s/a.yaml (0 -> 1)",
    ]


def test_a_new_vulnerability_fails_only_at_or_above_the_level() -> None:
    """#91, #113: a new advisory can appear with no change, so vulnerabilities keep the --fail-on threshold."""
    new = [*OLD, _f("CVE-2026-1", "critical", "go.mod"), _f("GHSA-x", "medium", "go.mod")]
    assert problems(_mapping(BASE, findings=new), WITH_FINDINGS) == ["new critical vulnerability: trivy:CVE-2026-1 go.mod (0 -> 1)"]
    assert problems(_mapping(BASE, findings=new), WITH_FINDINGS, "medium")[1] == "new medium vulnerability: trivy:GHSA-x go.mod (0 -> 1)"
    assert problems(_mapping(BASE, findings=[*OLD, _f("CVE-2026-2", "unknown", "go.mod")]), WITH_FINDINGS, "info") == []


def test_another_instance_of_a_known_identity_fails() -> None:
    """#113: one rule on a second resource of the same file is a new finding, not the known one."""
    second = [*OLD, _f("KSV-0012", "high", message="another resource")]
    assert problems(_mapping(BASE, findings=second), WITH_FINDINGS) == ["new finding: trivy:KSV-0012 k8s/a.yaml (1 -> 2)"]


def test_known_reworded_and_accepted_findings_pass() -> None:
    """Identity omits the message; an accepted risk is not a regression."""
    findings = [_f("KSV-0012", "high", message="a newer message"), _f("CVE-2026-2", "critical", "go.mod", accepted="suppressions/accepted")]
    assert problems(_mapping(BASE, findings=findings), WITH_FINDINGS, "info") == []


def test_a_new_coverage_gap_fails() -> None:
    """#113: a finding no control claims still comes from the change; gaps are counted like mapped findings."""
    mapping = _mapping(BASE, findings=OLD) | {"unmapped": [{"finding": _f("DS-0029", "high", "Dockerfile"), "reason": "no-rule-match"}]}
    assert problems(mapping, WITH_FINDINGS) == ["new finding: trivy:DS-0029 Dockerfile (0 -> 1)"]


def test_baseline_counts_each_finding_once_and_reads_a_list_baseline() -> None:
    """A finding on two controls counts once; a 1.3-1.5 baseline (a list) records each identity once."""
    mapping = _mapping(BASE, findings=[*OLD, _f("KSV-0012", "high", message="two")])
    mapping["controls"]["soc2:cc7.1"]["findings"] = list(OLD)  # the same finding, crosswalked to a second control
    assert baseline_doc(mapping)["findings"] == {"trivy:KSV-0012 k8s/a.yaml": 2}
    assert problems(mapping, {"controls": BASE, "findings": ["trivy:KSV-0012 k8s/a.yaml"]}) == ["new finding: trivy:KSV-0012 k8s/a.yaml (1 -> 2)"]


def test_a_baseline_without_findings_checks_statuses_only() -> None:
    assert problems(_mapping(BASE, findings=[_f("CVE-2026-1", "critical")]), DOC) == []


def test_summary_counts_findings_not_in_the_baseline() -> None:
    table = summary(_mapping(BASE, findings=[*OLD, _f("KSV-0012", "high", message="two"), _f("KSV-0020", "low")]), WITH_FINDINGS)
    assert table.endswith("Findings not in the baseline (any kind and severity): 2\n")
