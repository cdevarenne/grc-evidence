import json
from pathlib import Path

import pytest

from okf_grc.config import Config
from okf_grc.map_findings import map_findings
from okf_grc.okf_lib import Bundle, load_bundle
from oscal_schema import validate
from okf_grc.run_scan import conftest_inputs, load_pins, scanner_runs
from okf_grc.to_oscal import AP_HREF, NO_SSP_HREF, PROP_NS, assessment_plan, assessment_results, component_definition

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).parent.parent
NOW = "2026-09-25T12:00:00+00:00"
PINS = load_pins(Path(__file__).parent.parent / "src" / "okf_grc" / "data" / "tools.lock")


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


def test_results_import_the_plan_next_to_them(bundle: Bundle, mapping: dict) -> None:
    assert assessment_results(bundle, mapping, NOW)["assessment-results"]["import-ap"] == {"href": AP_HREF}
    assert AP_HREF == "assessment-plan.json"


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


def _severities(item: dict) -> list[str]:
    return [p["value"] for p in item.get("props", []) if (p["name"], p.get("ns")) == ("severity", PROP_NS)]


def test_severity_is_a_structured_prop(bundle: Bundle) -> None:
    base = {"tool": "conftest", "rule_id": "require_non_root", "target": "app/k8s/deployment.yaml", "tags": []}
    findings = [{**base, "severity": sev, "message": sev} for sev in ("low", "critical")]
    doc = assessment_results(bundle, map_findings(bundle, findings), NOW)
    validate(doc, "oscal_assessment-results_schema.json")
    (result,) = doc["assessment-results"]["results"]
    assert sorted(s for o in result["observations"] for s in _severities(o)) == ["critical", "low"]
    (finding,) = result["findings"]
    assert _severities(finding) == ["critical"]  # the highest among its observations


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


def _plan(bundle: Bundle, mapping: dict) -> dict:
    return assessment_plan(bundle, mapping, NOW, PINS)["assessment-plan"]


def _codes(selections: list[dict]) -> list[str]:
    return [c["control-id"] for s in selections for c in s["include-controls"]]


def test_assessment_plan_is_schema_valid(bundle: Bundle, mapping: dict) -> None:
    validate(assessment_plan(bundle, mapping, NOW, PINS), "oscal_assessment-plan_schema.json")
    ai, ai_mapping = _ai()
    validate(assessment_plan(ai, ai_mapping, NOW, PINS), "oscal_assessment-plan_schema.json")


def test_assessment_plan_is_deterministic(bundle: Bundle, mapping: dict) -> None:
    assert assessment_plan(bundle, mapping, NOW, PINS) == assessment_plan(bundle, mapping, NOW, PINS)
    assert _plan(bundle, mapping)["uuid"] != assessment_plan(bundle, mapping, "2026-09-26T12:00:00+00:00", PINS)[
        "assessment-plan"
    ]["uuid"]


def test_plan_imports_the_ssp_placeholder(bundle: Bundle, mapping: dict) -> None:
    assert _plan(bundle, mapping)["import-ssp"]["href"] == NO_SSP_HREF == "#system-security-plan-not-modeled"


def test_plan_scopes_every_applicable_control_including_unevidenced(bundle: Bundle, mapping: dict) -> None:
    planned = _codes(_plan(bundle, mapping)["reviewed-controls"]["control-selections"])
    assert planned == ["cc6.1", "cc7.1", "cc7.2", "cc8.1"]  # cc7.2 has no scanner: planned, not assessed


def test_results_review_a_subset_of_the_plan() -> None:
    for b, m in ((load_bundle(FIXTURES / "bundle"), None), _ai()):
        m = m or map_findings(b, json.loads((FIXTURES / "findings.json").read_text()))
        (result,) = assessment_results(b, m, NOW)["assessment-results"]["results"]
        reviewed = set(_codes(result["reviewed-controls"]["control-selections"]))
        assert reviewed <= set(_codes(_plan(b, m)["reviewed-controls"]["control-selections"]))


def test_plan_excludes_not_applicable_controls() -> None:
    ai, mapping = _ai()
    reviewed = _plan(ai, mapping)["reviewed-controls"]
    assert "art-12" not in _codes(reviewed["control-selections"])
    assert "art-50" in _codes(reviewed["control-selections"])
    assert reviewed["remarks"] == "Not applicable at the declared AI risk tier: eu-ai-act:art-12"


def test_plan_components_share_uuids_with_the_component_definition(bundle: Bundle, mapping: dict) -> None:
    plan = _plan(bundle, mapping)
    cd = component_definition(bundle, NOW)["component-definition"]["components"]
    planned = [c["uuid"] for c in plan["local-definitions"]["components"]]
    assert planned == [c["uuid"] for c in cd]
    (subjects,) = plan["assessment-subjects"]
    assert [s["subject-uuid"] for s in subjects["include-subjects"]] == planned


def test_plan_has_one_activity_per_scanner_run_with_its_pinned_version(bundle: Bundle, mapping: dict) -> None:
    activities = _plan(bundle, mapping)["local-definitions"]["activities"]
    versions = [next(p["value"] for p in a["props"] if p["name"] == "tool-version") for a in activities]
    pins = [PINS[k] for k in ("SEMGREP_VERSION", "TRIVY_VERSION", "TRIVY_VERSION", "CHECKOV_VERSION", "CONFTEST_VERSION")]
    assert versions == pins
    assert activities[0]["steps"][0]["description"].startswith("`semgrep scan --config policies/semgrep")
    assert len({a["uuid"] for a in activities}) == 5


def test_activity_related_controls_come_from_rule_declarations(bundle: Bundle, mapping: dict) -> None:
    by_title = {a["title"]: a for a in _plan(bundle, mapping)["local-definitions"]["activities"]}
    related = {t: _codes(a.get("related-controls", {}).get("control-selections", [])) for t, a in by_title.items()}
    declared = {
        tool: sorted({k.partition(":")[2] for c in bundle.concepts.values() for e in c.rule_ids
                      if e.startswith(f"{tool}:") for k in c.control_keys if bundle.control(k)})
        for tool in ("semgrep", "trivy", "checkov", "conftest")
    }
    assert related["Semgrep code scan"] == declared["semgrep"]
    assert related["Checkov infrastructure-as-code scan"] == declared["checkov"]
    assert "cc7.2" not in {c for codes in related.values() for c in codes}


def test_plan_states_the_suppression_policy_and_grounding_rule(bundle: Bundle, mapping: dict) -> None:
    parts = {p["title"]: p["prose"] for p in _plan(bundle, mapping)["terms-and-conditions"]["parts"]}
    assert "exactly" in parts["Suppression policy"] and "90 days" in parts["Suppression policy"]
    assert "human owner" in parts["Suppression policy"] and "`verified`" in parts["Suppression policy"]
    assert "coverage gap" in parts["Grounding rule"]


def test_one_task_runs_every_activity_against_every_subject(bundle: Bundle, mapping: dict) -> None:
    plan = _plan(bundle, mapping)
    (task,) = plan["tasks"]
    assert task["type"] == "action"
    assert [a["activity-uuid"] for a in task["associated-activities"]] == [
        a["uuid"] for a in plan["local-definitions"]["activities"]
    ]
    assert task["subjects"] == plan["assessment-subjects"]


def test_platform_uses_one_component_per_pinned_tool(bundle: Bundle, mapping: dict) -> None:
    assets = _plan(bundle, mapping)["assessment-assets"]
    assert [c["title"] for c in assets["components"]] == [
        f"semgrep {PINS['SEMGREP_VERSION']}", f"trivy {PINS['TRIVY_VERSION']}",
        f"checkov {PINS['CHECKOV_VERSION']}", f"conftest {PINS['CONFTEST_VERSION']}",
    ]
    (platform,) = assets["assessment-platforms"]
    assert [u["component-uuid"] for u in platform["uses-components"]] == [c["uuid"] for c in assets["components"]]


def test_plan_without_components_selects_all_subjects(tmp_path: Path) -> None:
    (tmp_path / "controls").mkdir()
    (tmp_path / "controls/cc6.1.md").write_text("---\ntype: SOC 2 Control\ntags: [cc6.1]\n---\n", encoding="utf-8")
    b = load_bundle(tmp_path)
    doc = assessment_plan(b, map_findings(b, []), NOW, PINS)
    validate(doc, "oscal_assessment-plan_schema.json")
    assert doc["assessment-plan"]["assessment-subjects"][0]["include-all"] == {}


def test_plan_records_the_files_conftest_checks(bundle: Bundle, mapping: dict) -> None:
    plan = assessment_plan(bundle, mapping, NOW, PINS, Config(), ROOT)["assessment-plan"]
    (activity,) = [a for a in plan["local-definitions"]["activities"] if a["title"] == "Conftest policy check"]
    (run,) = [r for r in scanner_runs(Config(), conftest_inputs(ROOT, Config())) if r.tool == "conftest"]
    assert f"`{' '.join(run.argv)}`" in activity["steps"][0]["description"]
    assert "*" not in activity["steps"][0]["description"]
