"""The grounding gate: findings reach a control only through a declared rule."""

import json
from pathlib import Path

import pytest

from okf_grc.map_findings import map_findings
from okf_grc.okf_lib import load_bundle

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def mapping() -> dict:
    findings = json.loads((FIXTURES / "findings.json").read_text())
    return map_findings(load_bundle(FIXTURES / "bundle"), findings)


def _rules(findings: list[dict]) -> list[str]:
    return [f["rule_id"] for f in findings]


def test_every_bundle_control_is_reported(mapping: dict) -> None:
    assert sorted(mapping["controls"]) == ["soc2:cc6.1", "soc2:cc7.1", "soc2:cc7.2", "soc2:cc8.1"]


def test_declared_rules_map_to_their_control(mapping: dict) -> None:
    assert _rules(mapping["controls"]["soc2:cc6.1"]["findings"]) == ["require_non_root", "CKV_TEST_1"]


def test_glob_rule_maps_cve(mapping: dict) -> None:
    assert _rules(mapping["controls"]["soc2:cc7.1"]["findings"]) == ["CVE-2024-0001"]


def test_undeclared_rule_is_a_gap_not_a_mapping(mapping: dict) -> None:
    gaps = {g["finding"]["rule_id"]: g["reason"] for g in mapping["unmapped"]}
    assert gaps["CKV_TEST_99"] == "no-rule-match"
    assert all("CKV_TEST_99" not in _rules(c["findings"]) for c in mapping["controls"].values())


def test_control_missing_from_bundle_is_a_gap(mapping: dict) -> None:
    gaps = {g["finding"]["rule_id"]: g["reason"] for g in mapping["unmapped"]}
    assert gaps["orphan_rule"] == "control-not-in-bundle"
    assert "soc2:cc9.9" not in mapping["controls"]


def test_statuses(mapping: dict) -> None:
    status = {code: c["status"] for code, c in mapping["controls"].items()}
    assert status == {
        "soc2:cc6.1": "not-satisfied",
        "soc2:cc7.1": "not-satisfied",
        "soc2:cc7.2": "not-assessed",
        "soc2:cc8.1": "no-violations-detected",
    }


def test_evidence_links(mapping: dict) -> None:
    assert mapping["controls"]["soc2:cc7.1"]["evidenced_by"] == ["scanners/trivy"]
    assert mapping["controls"]["soc2:cc8.1"]["satisfied_by"] == ["policies/deny-latest-tag"]


def _write(root: Path, rel: str, frontmatter: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}\n---\n", encoding="utf-8")


def test_evidence_comes_from_declarations_not_hand_tags(tmp_path: Path) -> None:
    _write(tmp_path, "controls/cc6.1.md", "type: SOC 2 Control\ntags: [cc6.1]")
    _write(tmp_path, "controls/cc7.2.md", "type: SOC 2 Control\ntags: [cc7.2]")
    _write(tmp_path, "scanners/checkov.md", "type: Scanner\ntags: [cc6.1, cc7.2]")
    _write(tmp_path, "scanners/semgrep.md", "type: Scanner\ntags: [sast]")
    _write(tmp_path, "policies/p.md", 'type: Rego Policy\ntags: [cc6.1]\nrule_ids: ["checkov:CKV_1"]')
    controls = map_findings(load_bundle(tmp_path), [])["controls"]
    assert controls["soc2:cc7.2"] == {
        "status": "not-assessed", "findings": [], "evidenced_by": [], "satisfied_by": []
    }
    assert controls["soc2:cc6.1"]["evidenced_by"] == ["scanners/checkov"]
    assert controls["soc2:cc6.1"]["satisfied_by"] == ["policies/p"]
    assert controls["soc2:cc6.1"]["status"] == "no-violations-detected"
