import json
import re
from datetime import date
from pathlib import Path

from grc_evidence.map_findings import map_findings
from grc_evidence.okf_lib import load_bundle
from grc_evidence.render_report import render_report

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


def test_narrative_is_inserted_under_its_control_and_counts_stay_put() -> None:
    bundle = load_bundle(FIXTURES / "bundle")
    mapping = map_findings(bundle, json.loads((FIXTURES / "findings.json").read_text()))
    narratives = {"soc2:cc7.1": {"summary": "One critical CVE.", "auditor_note": "Check the upgrade ticket."}}
    base = render_report(bundle, mapping, "2026-09-25T12:00:00+00:00")
    report = render_report(bundle, mapping, "2026-09-25T12:00:00+00:00", narratives)
    section = report.split("### CC7.1", 1)[1].split("###", 1)[0]
    assert "**Summary (LLM):** One critical CVE." in section
    assert "**Auditor note (LLM):** Check the upgrade ticket." in section
    stripped = [ln for ln in report.splitlines() if "(LLM)" not in ln]
    assert [ln for ln in stripped if ln] == [ln for ln in base.splitlines() if ln]


def test_footer_reports_the_llm_run_cost() -> None:
    bundle = load_bundle(FIXTURES / "bundle")
    mapping = map_findings(bundle, [])
    usage = [
        {"model": "claude-haiku-4-5", "mode": "anthropic", "billed": True, "input_tokens": 900,
         "output_tokens": 400, "cache_read_input_tokens": 3000, "cost_usd": 0.0032},
        {"model": "claude-haiku-4-5", "mode": "anthropic", "billed": False, "input_tokens": 900,
         "output_tokens": 400, "cache_read_input_tokens": 0, "cost_usd": 0.0},
    ]
    footer = render_report(bundle, mapping, "2026-09-25T12:00:00+00:00", usage=usage).splitlines()[-1]
    assert footer.startswith("LLM step: 2 call(s), 1 billed, model claude-haiku-4-5, mode anthropic.")
    assert "Tokens: 1800 in, 800 out, 3000 cache read. Cost $0.0032." in footer


def test_posture_counts_a_control_whose_only_findings_are_accepted_risks() -> None:
    """#65: every applicable control appears once in the summary, accepted-only ones included."""
    bundle = load_bundle(Path(__file__).parent.parent / "knowledge")
    s = next(s for s in bundle.suppressions() if s.kind == "accepted-risk")
    finding = {"tool": s.tool, "rule_id": s.rule_id, "severity": "high", "target": s.target,
               "message": s.message_contains or "m", "tags": []}
    mapping = map_findings(bundle, [finding], {"risk_tier": "limited"}, today=date(2026, 10, 1))
    report = render_report(bundle, mapping, "2026-10-01T12:00:00+00:00")
    assert "1 control has only accepted risks." in report
    head = re.search(r"across (\d+) of (\d+) controls", report)
    rest = re.search(r"(\d+) controls? shows? no violations\. (\d+) controls? ha(?:s|ve) only accepted risks\. (\d+) not assessed", report)
    assert head and rest
    assert int(head[1]) + sum(int(n) for n in rest.groups()) == int(head[2])
