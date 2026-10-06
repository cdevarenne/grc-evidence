"""A control whose only rules cannot read the inventory's AI SDKs is not assessed, never clean."""

from pathlib import Path

import pytest

from grc_evidence.config import ConfigError
from grc_evidence.map_findings import SDK_GAP, load_context, map_findings
from grc_evidence.okf_lib import BundleError, load_bundle
from grc_evidence.render_report import render_report
from grc_evidence.to_oscal import assessment_results

ROOT = Path(__file__).parent.parent
BUNDLE = load_bundle(ROOT / "knowledge")  # art-50's only rule reads Anthropic; a.6 also has an SDK-agnostic rule
NOW = "2026-10-01T12:00:00+00:00"


def _inventory(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "ai-inventory.yaml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("systems", "expected"),
    [
        ("[{name: a, sdk: langchain}, {name: b, sdk: anthropic}]", ["anthropic", "langchain"]),
        ("[{name: a, sdk: langchain}, {name: b}]", None),  # one unknown SDK rules nothing out
        ("[]", None),
    ],
)
def test_load_context_reads_sdks_only_when_every_system_names_one(tmp_path: Path, systems: str, expected) -> None:
    context = load_context(_inventory(tmp_path, f"risk_tier: limited\nsystems: {systems}\n"))
    assert context.get("ai_sdks") == expected


def test_load_context_rejects_malformed_systems(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="systems must be a list of mappings"):
        load_context(_inventory(tmp_path, "systems: [langchain]\n"))


def _status(context: dict, findings: list | None = None) -> dict[str, tuple[str, str | None]]:
    controls = map_findings(BUNDLE, findings or [], context)["controls"]
    return {key: (c["status"], c.get("reason")) for key, c in controls.items()}


def test_uncovered_sdk_makes_a_clean_control_not_assessed() -> None:
    status = _status({"risk_tier": "limited", "ai_sdks": ["langchain"]})
    assert status["eu-ai-act:art-50"] == ("not-assessed", SDK_GAP)
    assert status["iso42001:a.6"] == ("no-violations-detected", None)  # its key rule reads any SDK


@pytest.mark.parametrize("context", [{"risk_tier": "limited", "ai_sdks": ["anthropic"]}, {"risk_tier": "limited"}])
def test_covered_or_unknown_sdk_leaves_the_status_alone(context: dict) -> None:
    assert _status(context)["eu-ai-act:art-50"] == ("no-violations-detected", None)


def test_a_finding_still_fails_the_control() -> None:
    finding = {"tool": "semgrep", "rule_id": "llm-no-ai-disclosure", "severity": "medium",
               "target": "svc/views.py", "message": "m", "tags": []}
    assert _status({"ai_sdks": ["langchain"]}, [finding])["eu-ai-act:art-50"] == ("not-satisfied", None)


def test_report_and_oscal_say_why() -> None:
    mapping = map_findings(BUNDLE, [], {"risk_tier": "limited", "ai_sdks": ["langchain"]})
    assert "its only rules do not read the AI SDKs the inventory declares." in render_report(BUNDLE, mapping, NOW)
    (result,) = assessment_results(BUNDLE, mapping, NOW)["assessment-results"]["results"]
    assert "Not assessed (its only rules do not read the AI SDKs the inventory declares): eu-ai-act:art-50" in result["remarks"]


def test_sdks_must_be_a_list(tmp_path: Path) -> None:
    (tmp_path / "rule.md").write_text("---\ntype: Semgrep Rule\nsdks: langchain\n---\n# Rule\n", encoding="utf-8")
    with pytest.raises(BundleError, match="'sdks' must be a YAML list"):
        load_bundle(tmp_path)
