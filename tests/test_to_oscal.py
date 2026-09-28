import json
from pathlib import Path

import pytest

from map_findings import map_findings
from okf_lib import Bundle, load_bundle
from oscal_schema import validate
from to_oscal import assessment_results, component_definition

FIXTURES = Path(__file__).parent / "fixtures"
NOW = "2026-09-25T12:00:00+00:00"


@pytest.fixture
def bundle() -> Bundle:
    return load_bundle(FIXTURES / "bundle")


@pytest.fixture
def mapping(bundle: Bundle) -> dict:
    return map_findings(bundle, json.loads((FIXTURES / "findings.json").read_text()))


def test_component_definition_is_schema_valid(bundle: Bundle) -> None:
    validate(component_definition(bundle, NOW), "oscal_component_schema.json")


def test_component_lists_only_in_bundle_controls(bundle: Bundle) -> None:
    (comp,) = component_definition(bundle, NOW)["component-definition"]["components"]
    reqs = comp["control-implementations"][0]["implemented-requirements"]
    assert [r["control-id"] for r in reqs] == ["cc6.1", "cc7.1"]


def test_assessment_results_is_schema_valid(bundle: Bundle, mapping: dict) -> None:
    validate(assessment_results(bundle, mapping, NOW), "oscal_assessment-results_schema.json")


def test_findings_only_for_violated_controls(bundle: Bundle, mapping: dict) -> None:
    (result,) = assessment_results(bundle, mapping, NOW)["assessment-results"]["results"]
    states = {f["target"]["target-id"]: f["target"]["status"]["state"] for f in result["findings"]}
    assert states == {"cc6.1": "not-satisfied", "cc7.1": "not-satisfied"}


def test_clean_controls_are_never_attested(bundle: Bundle, mapping: dict) -> None:
    (result,) = assessment_results(bundle, mapping, NOW)["assessment-results"]["results"]
    assert "satisfied" not in {f["target"]["status"]["state"] for f in result["findings"]}
    assert "not a control attestation): soc2:cc8.1" in result["remarks"]
    assert "Not assessed (no in-bundle scanner or policy): soc2:cc7.2" in result["remarks"]
    reviewed = result["reviewed-controls"]["control-selections"][0]["include-controls"]
    assert [c["control-id"] for c in reviewed] == ["cc6.1", "cc7.1", "cc8.1"]


def test_coverage_gaps_are_risks_not_findings(bundle: Bundle, mapping: dict) -> None:
    (result,) = assessment_results(bundle, mapping, NOW)["assessment-results"]["results"]
    assert sorted(r["title"] for r in result["risks"]) == [
        "Coverage gap: checkov CKV_TEST_99",
        "Coverage gap: conftest orphan_rule",
    ]
    gap_obs = {o["observation-uuid"] for r in result["risks"] for o in r["related-observations"]}
    finding_obs = {o["observation-uuid"] for f in result["findings"] for o in f.get("related-observations", [])}
    assert gap_obs and not gap_obs & finding_obs


def test_output_is_deterministic(bundle: Bundle, mapping: dict) -> None:
    assert assessment_results(bundle, mapping, NOW) == assessment_results(bundle, mapping, NOW)
    assert component_definition(bundle, NOW) == component_definition(bundle, NOW)


def test_validator_rejects_missing_required_field(bundle: Bundle, mapping: dict) -> None:
    from jsonschema import ValidationError

    doc = assessment_results(bundle, mapping, NOW)
    del doc["assessment-results"]["import-ap"]
    with pytest.raises(ValidationError, match="import-ap"):
        validate(doc, "oscal_assessment-results_schema.json")


def test_validator_rejects_bad_token(bundle: Bundle) -> None:
    from jsonschema import ValidationError

    doc = component_definition(bundle, NOW)
    reqs = doc["component-definition"]["components"][0]["control-implementations"][0]["implemented-requirements"]
    reqs[0]["control-id"] = "9 not a token"
    with pytest.raises(ValidationError):
        validate(doc, "oscal_component_schema.json")


def test_per_resource_findings_keep_separate_observations(bundle: Bundle) -> None:
    base = {"tool": "conftest", "rule_id": "require_non_root", "severity": "high",
            "target": "app/k8s/deployment.yaml", "tags": []}
    findings = [{**base, "message": "container a"}, {**base, "message": "container b"}]
    (result,) = assessment_results(bundle, map_findings(bundle, findings), NOW)["assessment-results"]["results"]
    assert len(result["observations"]) == 2
    (finding,) = result["findings"]
    assert len({o["observation-uuid"] for o in finding["related-observations"]}) == 2


def test_component_claims_only_controls_with_declared_rules(tmp_path: Path) -> None:
    files = {
        "controls/cc6.1.md": "type: SOC 2 Control\ntags: [cc6.1]",
        "controls/cc7.2.md": "type: SOC 2 Control\ntags: [cc7.2]",
        "scanners/checkov.md": "type: Scanner\ntags: [cc7.2]",
        "policies/p.md": 'type: Rego Policy\ntags: [cc6.1]\nrule_ids: ["checkov:CKV_1"]',
    }
    for rel, fm in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(f"---\n{fm}\n---\n", encoding="utf-8")
    (tmp_path / "app.md").write_text(
        "---\ntype: Stack Component\n---\n[a](controls/cc6.1.md) [b](controls/cc7.2.md)\n", encoding="utf-8"
    )
    (comp,) = component_definition(load_bundle(tmp_path), NOW)["component-definition"]["components"]
    reqs = comp["control-implementations"][0]["implemented-requirements"]
    assert [r["control-id"] for r in reqs] == ["cc6.1"]


def test_assessment_results_uuid_changes_per_run(bundle: Bundle, mapping: dict) -> None:
    def doc_uuid(now: str) -> str:
        return assessment_results(bundle, mapping, now)["assessment-results"]["uuid"]

    assert doc_uuid(NOW) == doc_uuid(NOW)
    assert doc_uuid(NOW) != doc_uuid("2026-09-26T12:00:00+00:00")


AI_BUNDLE = FIXTURES / "ai_bundle"


def _ai() -> tuple[Bundle, dict]:
    ai = load_bundle(AI_BUNDLE)
    findings = json.loads((FIXTURES / "ai_findings.json").read_text())
    return ai, map_findings(ai, findings, {"risk_tier": "limited"})


def test_one_control_implementation_per_framework_source() -> None:
    ai, _ = _ai()
    doc = component_definition(ai, NOW)
    validate(doc, "oscal_component_schema.json")
    (comp,) = doc["component-definition"]["components"]
    resources = {f"#{r['uuid']}": r["title"] for r in doc["component-definition"]["back-matter"]["resources"]}
    by_source = {
        resources[ci["source"]].split(" ")[0]: [r["control-id"] for r in ci["implemented-requirements"]]
        for ci in comp["control-implementations"]
    }
    assert by_source == {"AICPA": ["cc6.1"], "ISO/IEC": ["a.6", "a.7"], "Regulation": ["art-50"]}


def test_iso42001_source_is_a_declared_placeholder() -> None:
    ai, _ = _ai()
    resources = component_definition(ai, NOW)["component-definition"]["back-matter"]["resources"]
    (iso,) = [r for r in resources if r["title"].startswith("ISO/IEC 42001")]
    assert "placeholder" in iso["title"] and "rlinks" not in iso
    (act,) = [r for r in resources if r["title"].startswith("Regulation (EU) 2024/1689")]
    assert act["rlinks"] == [{"href": "https://eur-lex.europa.eu/eli/reg/2024/1689/oj"}]


def test_not_applicable_controls_are_neither_reviewed_nor_findings() -> None:
    ai, mapping = _ai()
    doc = assessment_results(ai, mapping, NOW)
    validate(doc, "oscal_assessment-results_schema.json")
    (result,) = doc["assessment-results"]["results"]
    reviewed = [
        c["control-id"] for s in result["reviewed-controls"]["control-selections"] for c in s["include-controls"]
    ]
    assert "art-12" not in reviewed
    assert "art-12" not in {f["target"]["target-id"] for f in result["findings"]}
    assert "Not applicable at the declared AI risk tier: eu-ai-act:art-12" in result["remarks"]


def test_reviewed_controls_are_grouped_by_framework() -> None:
    ai, mapping = _ai()
    (result,) = assessment_results(ai, mapping, NOW)["assessment-results"]["results"]
    selections = result["reviewed-controls"]["control-selections"]
    assert [s["description"].split(" ")[0] for s in selections] == ["AICPA", "ISO/IEC", "Regulation"]
