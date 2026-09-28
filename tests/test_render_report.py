import json
from pathlib import Path

from map_findings import map_findings
from okf_lib import load_bundle
from render_report import render_report

FIXTURES = Path(__file__).parent / "fixtures"


def test_report_matches_golden() -> None:
    bundle = load_bundle(FIXTURES / "bundle")
    mapping = map_findings(bundle, json.loads((FIXTURES / "findings.json").read_text()))
    report = render_report(bundle, mapping, "2026-09-25T12:00:00+00:00")
    assert report == (FIXTURES / "report.golden.md").read_text()


def test_remediation_line_is_omitted_without_remediation_text(tmp_path: Path) -> None:
    for rel, fm in {
        "controls/cc6.1.md": "type: SOC 2 Control\ntitle: CC6.1\ntags: [cc6.1]",
        "policies/p.md": 'type: Rego Policy\ntitle: P\ntags: [cc6.1]\nrule_ids: ["conftest:p"]',
    }.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(f"---\n{fm}\n---\n", encoding="utf-8")
    bundle = load_bundle(tmp_path)
    finding = {"tool": "conftest", "rule_id": "p", "severity": "high", "target": "t", "message": "m", "tags": []}
    report = render_report(bundle, map_findings(bundle, [finding]), "2026-09-25T12:00:00+00:00")
    assert "Open findings" in report and "Remediation" not in report


def _ai_report() -> str:
    bundle = load_bundle(FIXTURES / "ai_bundle")
    findings = json.loads((FIXTURES / "ai_findings.json").read_text())
    mapping = map_findings(bundle, findings, {"risk_tier": "limited"})
    return render_report(bundle, mapping, "2026-09-25T12:00:00+00:00")


def test_one_section_per_framework_in_order() -> None:
    headings = [ln for ln in _ai_report().splitlines() if ln.startswith("## ")]
    assert headings == [
        "## Risk posture", "## Summary", "## SOC 2", "## ISO/IEC 42001", "## EU AI Act",
        "## Crosswalk", "## Coverage gaps", "## Not assessed", "## Not applicable",
    ]


def test_crosswalk_row_shows_each_side_status() -> None:
    assert (
        "| iso42001:a.7 | not-satisfied | eu-ai-act:art-12 | not-applicable | "
        "[ISO/IEC 42001 ↔ EU AI Act](../knowledge/crosswalk/iso42001-ai-act.md) |"
    ) in _ai_report()


def test_not_applicable_is_counted_apart_and_keeps_its_findings() -> None:
    report = _ai_report()
    assert "3 open findings across 3 of 4 controls: 3 high." in report
    summary = report.split("## Summary", 1)[1].split("## SOC 2", 1)[0]
    assert [ln.split(" | ")[0] for ln in summary.splitlines() if ln.startswith("| ") and ":" in ln] == [
        "| soc2:cc6.1", "| iso42001:a.6", "| iso42001:a.7", "| eu-ai-act:art-12", "| eu-ai-act:art-50",
    ]
    assert "1 control shows no violations. 0 not assessed. 1 not applicable. 1 coverage gap to triage." in report
    na = report.split("## Not applicable", 1)[1]
    assert "- Art. 12 — Record-keeping" in na and "`llm-prompt-logged`" in na
