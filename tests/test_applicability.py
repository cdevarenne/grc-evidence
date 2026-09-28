"""`applies_when` + the AI inventory decide which controls are in scope; `not-applicable` is never a pass."""

import json
from pathlib import Path

import pytest

from map_findings import load_context, map_findings
from okf_lib import applies, load_bundle

FIXTURES = Path(__file__).parent / "fixtures"
AI = load_bundle(FIXTURES / "ai_bundle")
FINDINGS = json.loads((FIXTURES / "ai_findings.json").read_text())


@pytest.mark.parametrize(
    ("context", "expected"),
    [({"risk_tier": "limited"}, False), ({"risk_tier": "high"}, True), ({}, True)],
)
def test_applies_reads_the_risk_tier(context: dict, expected: bool) -> None:
    assert applies(AI.control("eu-ai-act:art-12"), context) is expected


def test_control_without_applies_when_always_applies() -> None:
    assert applies(AI.control("eu-ai-act:art-50"), {"risk_tier": "minimal"})


def test_limited_tier_marks_high_risk_article_not_applicable() -> None:
    entry = map_findings(AI, FINDINGS, {"risk_tier": "limited"})["controls"]["eu-ai-act:art-12"]
    assert entry["status"] == "not-applicable"
    assert entry["reason"] == "control-not-applicable"
    assert [f["rule_id"] for f in entry["findings"]] == ["llm-prompt-logged"]


def test_same_finding_still_counts_on_an_applicable_control() -> None:
    controls = map_findings(AI, FINDINGS, {"risk_tier": "limited"})["controls"]
    assert controls["iso42001:a.7"]["status"] == "not-satisfied"


def test_high_tier_assesses_the_article() -> None:
    entry = map_findings(AI, FINDINGS, {"risk_tier": "high"})["controls"]["eu-ai-act:art-12"]
    assert entry["status"] == "not-satisfied"
    assert "reason" not in entry


def test_no_inventory_means_assess_everything() -> None:
    statuses = {e["status"] for e in map_findings(AI, FINDINGS)["controls"].values()}
    assert "not-applicable" not in statuses


def test_not_applicable_is_never_a_gap_or_a_clean_result() -> None:
    mapping = map_findings(AI, [], {"risk_tier": "limited"})
    assert mapping["controls"]["eu-ai-act:art-12"]["status"] == "not-applicable"
    assert mapping["unmapped"] == []


def test_load_context(tmp_path: Path) -> None:
    inventory = tmp_path / "ai-inventory.yaml"
    assert load_context(inventory) == {}
    inventory.write_text("risk_tier: limited\nsystems: []\n", encoding="utf-8")
    assert load_context(inventory) == {"risk_tier": "limited"}
