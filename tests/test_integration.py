"""End-to-end: `make scan` finds every seeded issue and maps it exactly as SEEDED.yaml expects."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from oscal_schema import validate

from grc_evidence import data
from grc_evidence.to_oscal import PROP_NS

ROOT = Path(__file__).parent.parent
OUT = ROOT / "out"
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def mapping() -> dict:
    subprocess.run(["make", "scan"], cwd=ROOT, check=True)
    return json.loads((OUT / "mapping.json").read_text())


def _located(mapping: dict, tool: str, rule_id: str, file: str) -> set[str]:
    """Where a finding landed: control codes, or 'gap:<reason>'."""
    hits = {
        code
        for code, entry in mapping["controls"].items()
        for f in entry["findings"]
        if (f["tool"], f["rule_id"], f["target"]) == (tool, rule_id, file)
    }
    hits |= {
        f"gap:{u['reason']}"
        for u in mapping["unmapped"]
        if (u["finding"]["tool"], u["finding"]["rule_id"], u["finding"]["target"]) == (tool, rule_id, file)
    }
    hits |= {
        f"suppressed:{s['kind']}"
        for s in mapping.get("suppressed", [])
        if s["kind"] == "false-positive"
        and (s["finding"]["tool"], s["finding"]["rule_id"], s["finding"]["target"]) == (tool, rule_id, file)
    }
    return hits


SEEDED = yaml.safe_load((ROOT / "app" / "SEEDED.yaml").read_text())


def _expected(seed: dict, mapping: dict) -> set[str]:
    """Where a seed's findings must land today; an expired suppression lands them as if it did not exist."""
    expect = seed["expect"]
    if "suppressed" in expect:
        if expect["suppression"] in mapping.get("expired_suppressions", []):
            expect = expect["unsuppressed"]
        else:
            return {f"suppressed:{expect['suppressed']}"}
    return set(expect.get("controls", [])) or {f"gap:{expect['gap']}"}


@pytest.mark.parametrize("seed", SEEDED, ids=lambda s: s["id"])
def test_seeded_issue_lands_where_expected(mapping: dict, seed: dict) -> None:
    for detector in seed["detected_by"]:
        tool, rule_id = detector.split(":", 1)
        assert _located(mapping, tool, rule_id, seed["file"]) == _expected(seed, mapping), f"{seed['id']} {detector}"


@pytest.mark.parametrize("seed", [s for s in SEEDED if "accepted" in s["expect"]], ids=lambda s: s["id"])
def test_accepted_risk_is_marked_while_in_force(mapping: dict, seed: dict) -> None:
    sid = seed["expect"]["accepted"]
    marks = {
        f.get("accepted")
        for entry in mapping["controls"].values()
        for f in entry["findings"]
        if (f["tool"], f["rule_id"], f["target"]) == (*seed["detected_by"][0].split(":", 1), seed["file"])
    }
    assert marks == ({None} if sid in mapping.get("expired_suppressions", []) else {sid})


def test_every_finding_target_is_under_the_scan_target(mapping: dict) -> None:
    findings = json.loads((OUT / "findings.json").read_text())["findings"]
    assert [f["target"] for f in findings if not f["target"].startswith("app/")] == []


def test_outputs_follow_the_contract_and_the_manifest_matches_them(mapping: dict) -> None:
    for name in ("findings", "mapping", "run"):
        doc = json.loads((OUT / f"{name}.json").read_text())
        schema = json.loads(data.path(f"schemas/{name}.schema.json").read_text())
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(doc)
    run = json.loads((OUT / "run.json").read_text())
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    assert run["repository"]["commit"] == head
    assert run["outputs"] == {rel: hashlib.sha256((OUT / rel).read_bytes()).hexdigest() for rel in run["outputs"]}
    results = json.loads((OUT / "oscal" / "assessment-results.json").read_text())["assessment-results"]["results"][0]
    assert {"name": "run-id", "ns": PROP_NS, "value": run["run_id"]} in results["props"]


def test_no_suppression_is_unused(mapping: dict) -> None:
    assert mapping.get("unused_suppressions", []) == []


def test_outputs_exist_and_oscal_validates(mapping: dict) -> None:
    assert (OUT / "report.md").read_text().startswith("# Compliance Scan Report")
    validate(json.loads((OUT / "oscal" / "component-definition.json").read_text()), "oscal_component_schema.json")
    validate(json.loads((OUT / "oscal" / "assessment-plan.json").read_text()), "oscal_assessment-plan_schema.json")
    results = json.loads((OUT / "oscal" / "assessment-results.json").read_text())
    validate(results, "oscal_assessment-results_schema.json")
    assert (OUT / "oscal" / results["assessment-results"]["import-ap"]["href"]).is_file()


def test_plan_names_the_monitoring_control_the_results_leave_unassessed(mapping: dict) -> None:
    plan = json.loads((OUT / "oscal" / "assessment-plan.json").read_text())["assessment-plan"]
    planned = {c["control-id"] for s in plan["reviewed-controls"]["control-selections"] for c in s["include-controls"]}
    assert "cc7.2" in planned and "art-12" not in planned


def test_monitoring_control_has_only_a_configuration_check(mapping: dict) -> None:
    """CC7.2's one rule checks GKE flow logging; the sample has no cluster, so nothing fires (#87)."""
    entry = mapping["controls"]["soc2:cc7.2"]
    assert entry["status"] == "no-violations-detected" and entry["satisfied_by"] == ["policies/network-flow-logs"]


def test_high_risk_articles_are_not_applicable_at_limited_tier(mapping: dict) -> None:
    high_risk = [f"eu-ai-act:art-{n}" for n in (9, 10, 12, 13, 14, 15)]
    assert {mapping["controls"][k]["status"] for k in high_risk} == {"not-applicable"}
    assert mapping["controls"]["eu-ai-act:art-50"]["status"] == "not-satisfied"


def test_not_applicable_article_keeps_its_finding(mapping: dict) -> None:
    entry = mapping["controls"]["eu-ai-act:art-12"]
    assert [f["rule_id"] for f in entry["findings"]] == ["llm-prompt-logged"]
    assert entry["reason"] == "control-not-applicable"


def test_report_has_a_section_per_framework_and_a_crosswalk(mapping: dict) -> None:
    report = (OUT / "report.md").read_text()
    for heading in ("## SOC 2", "## ISO/IEC 42001", "## EU AI Act", "## Crosswalk", "## Not applicable"):
        assert f"\n{heading}\n" in report, heading


def test_oscal_has_one_source_per_framework(mapping: dict) -> None:
    doc = json.loads((OUT / "oscal" / "component-definition.json").read_text())
    titles = [r["title"] for r in doc["component-definition"]["back-matter"]["resources"]]
    assert [t.split(" ")[0] for t in titles] == ["AICPA", "ISO/IEC", "Regulation"]
