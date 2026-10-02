"""`applies_when` + the AI inventory decide which controls are in scope; `not-applicable` is never a pass."""

import json
import shutil
import sys
from pathlib import Path

import pytest

from okf_grc import map_findings as map_findings_module
from okf_grc.map_findings import load_context, map_findings
from okf_grc.okf_lib import applies, load_bundle

FIXTURES = Path(__file__).parent / "fixtures"
AI = load_bundle(FIXTURES / "ai_bundle")
FINDINGS = json.loads((FIXTURES / "ai_findings.json").read_text())


@pytest.mark.parametrize(
    ("context", "expected"),
    [({"risk_tier": "limited"}, False), ({"risk_tier": "high"}, True), ({}, True)],
)
def test_applies_reads_the_risk_tier(context: dict, expected: bool) -> None:
    assert (control := AI.control("eu-ai-act:art-12"))
    assert applies(control, context) is expected


def test_control_without_applies_when_always_applies() -> None:
    assert (control := AI.control("eu-ai-act:art-50"))
    assert applies(control, {"risk_tier": "minimal"})


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


@pytest.mark.parametrize("tier", ["hgih", "HIGH", "null", "[high]"])
def test_load_context_rejects_an_unknown_risk_tier(tmp_path: Path, tier: str) -> None:
    inventory = tmp_path / "ai-inventory.yaml"
    inventory.write_text(f"risk_tier: {tier}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="risk_tier"):
        load_context(inventory)


def test_main_reads_the_inventory_of_the_scan_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target, out = tmp_path / "svc", tmp_path / "out"
    target.mkdir()
    out.mkdir()
    shutil.copytree(FIXTURES / "ai_bundle", tmp_path / "kb")
    (target / "ai-inventory.yaml").write_text("risk_tier: high\n", encoding="utf-8")  # app/ declares limited
    (out / "findings.json").write_text(json.dumps({"schema_version": "1.0", "findings": FINDINGS}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["map_findings", "--knowledge", "kb", "--target", "svc", "--out", "out"])
    map_findings_module.main()
    mapping = json.loads((out / "mapping.json").read_text())
    assert mapping["controls"]["eu-ai-act:art-12"]["status"] == "not-satisfied"
