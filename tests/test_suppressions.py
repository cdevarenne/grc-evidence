"""Suppressions (Spec C): reviewed, expiring, exact; they change how a finding counts, never whether it shows."""

import json
import shutil
from datetime import date
from pathlib import Path

import pytest
from oscal_schema import validate

from grc_evidence.digest import scan_digest
from grc_evidence.map_findings import map_findings
from grc_evidence.okf_lib import BundleError, load_bundle
from grc_evidence.render_report import render_report
from grc_evidence.to_oscal import assessment_results

FIXTURES = Path(__file__).parent / "fixtures"
FINDINGS = json.loads((FIXTURES / "findings.json").read_text())
IN_FORCE = date(2026, 10, 1)
NOW = "2026-10-01T12:00:00+00:00"


def _suppression(kind: str, tool: str, rule_id: str, target: str, *, approved: str = "2026-09-28",
                 expires: str = "2026-12-27", owner: str = "human:reviewer", extra: str = "",
                 reason: str = "Reviewed: does not apply here.") -> str:
    return (
        f"---\ntype: Suppression\ntitle: t\nkind: {kind}\n"
        f"finding:\n  tool: {tool}\n  rule_id: {rule_id}\n  target: {target}\n{extra}"
        f"owner: {owner}\napproved: \"{approved}\"\nexpires: \"{expires}\"\ntags: [suppression]\n---\n"
        f"# Reason\n\n{reason}\n"
    )


FALSE_POSITIVE = _suppression("false-positive", "checkov", "CKV_TEST_99", "app/Dockerfile")
ACCEPTED = _suppression("accepted-risk", "trivy", "CVE-2024-0001", "app/requirements.txt")


def _bundle(tmp_path: Path, **suppressions: str):
    root = tmp_path / "bundle"
    shutil.copytree(FIXTURES / "bundle", root)
    for name, text in suppressions.items():
        (root / "suppressions").mkdir(exist_ok=True)
        (root / "suppressions" / f"{name}.md").write_text(text, encoding="utf-8")
    return load_bundle(root)


# -- validation ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "error"),
    [
        (_suppression("wontfix", "checkov", "CKV_TEST_99", "app/Dockerfile"), "kind"),
        (_suppression("false-positive", "checkov", "CKV_*", "app/Dockerfile"), "wildcards"),
        (_suppression("false-positive", "checkov", "", "app/Dockerfile"), "tool, rule_id, and target"),
        (_suppression("false-positive", "checkov", "CKV_TEST_99", "app/Dockerfile", owner="team-a"), "owner"),
        (_suppression("false-positive", "checkov", "CKV_TEST_99", "app/Dockerfile", expires="2026-12-28"), "90 days"),
        (_suppression("false-positive", "checkov", "CKV_TEST_99", "app/Dockerfile", expires="2026-09-28"), "90 days"),
        (_suppression("false-positive", "checkov", "CKV_TEST_99", "app/Dockerfile", approved="soon"), "ISO date"),
        (_suppression("false-positive", "checkov", "CKV_TEST_99", "app/Dockerfile", reason=""), "Reason"),
        (_suppression("accepted-risk", "checkov", "CKV_TEST_99", "app/Dockerfile"), "is a gap"),
    ],
)
def test_malformed_suppressions_are_rejected(tmp_path: Path, text: str, error: str) -> None:
    with pytest.raises(BundleError, match=error):
        _bundle(tmp_path, bad=text)


def test_suppressions_load_as_typed_records(tmp_path: Path) -> None:
    (s,) = _bundle(tmp_path, fp=FALSE_POSITIVE).suppressions()
    assert (s.id, s.kind, s.rule_id, s.owner, s.expires) == (
        "suppressions/fp", "false-positive", "CKV_TEST_99", "human:reviewer", date(2026, 12, 27)
    )
    assert s.reason == "Reviewed: does not apply here."


def _mapping(tmp_path: Path, today: date = IN_FORCE, **suppressions: str) -> dict:
    return map_findings(_bundle(tmp_path, **suppressions), FINDINGS, today=today)


# -- mapping ------------------------------------------------------------------------------------------


def test_false_positive_leaves_the_gap_list_but_stays_visible(tmp_path: Path) -> None:
    m = _mapping(tmp_path, fp=FALSE_POSITIVE)
    assert "CKV_TEST_99" not in [u["finding"]["rule_id"] for u in m["unmapped"]]
    (entry,) = m["suppressed"]
    assert (entry["kind"], entry["suppression"], entry["finding"]["rule_id"]) == (
        "false-positive", "suppressions/fp", "CKV_TEST_99"
    )


def test_accepted_risk_stays_on_its_control_and_keeps_the_status(tmp_path: Path) -> None:
    m = _mapping(tmp_path, accepted=ACCEPTED)
    entry = m["controls"]["soc2:cc7.1"]
    assert entry["status"] == "not-satisfied"
    assert [f.get("accepted") for f in entry["findings"]] == ["suppressions/accepted"]
    assert m["suppressed"][0]["controls"] == ["soc2:cc7.1"]


def test_a_false_positive_can_clear_a_control(tmp_path: Path) -> None:
    fp = _suppression("false-positive", "trivy", "CVE-2024-0001", "app/requirements.txt")
    assert _mapping(tmp_path, fp=fp)["controls"]["soc2:cc7.1"]["status"] == "no-violations-detected"


@pytest.mark.parametrize(
    ("today", "applies"),
    [(date(2026, 9, 28), True), (date(2026, 12, 27), True), (date(2026, 12, 28), False)],
)
def test_suppression_applies_from_approval_through_expiry(tmp_path: Path, today: date, applies: bool) -> None:
    m = _mapping(tmp_path, today=today, fp=FALSE_POSITIVE)
    assert bool(m["suppressed"]) is applies
    assert ("suppressions/fp" in m["expired_suppressions"]) is (today > date(2026, 12, 27))


def test_suppression_approved_after_today_is_pending_and_listed(tmp_path: Path) -> None:
    """#69: not an error, not silently ignored: not applied, and listed with its approval date."""
    m = _mapping(tmp_path, today=date(2026, 9, 27), fp=FALSE_POSITIVE)
    assert m["pending_suppressions"] == [{"id": "suppressions/fp", "approved": "2026-09-28"}]
    assert m["suppressed"] == [] and "suppressions/fp" not in m["unused_suppressions"]
    assert "CKV_TEST_99" in [u["finding"]["rule_id"] for u in m["unmapped"]]
    report = render_report(_bundle(tmp_path / "r", fp=FALSE_POSITIVE), m, NOW)
    assert "## Pending suppressions" in report and "- `suppressions/fp` approved 2026-09-28" in report


def test_expired_suppression_puts_the_finding_back(tmp_path: Path) -> None:
    m = _mapping(tmp_path, today=date(2026, 12, 28), fp=FALSE_POSITIVE)
    assert "CKV_TEST_99" in [u["finding"]["rule_id"] for u in m["unmapped"]]
    assert m["expired_suppressions"] == ["suppressions/fp"]


def test_unused_suppression_is_reported(tmp_path: Path) -> None:
    stale = _suppression("false-positive", "checkov", "CKV_GONE", "app/Dockerfile")
    assert _mapping(tmp_path, stale=stale)["unused_suppressions"] == ["suppressions/stale"]


def test_message_contains_narrows_the_match(tmp_path: Path) -> None:
    narrow = _suppression("false-positive", "checkov", "CKV_TEST_99", "app/Dockerfile",
                          extra="  message_contains: \"something else\"\n")
    m = _mapping(tmp_path, fp=narrow)
    assert m["suppressed"] == [] and m["unused_suppressions"] == ["suppressions/fp"]


def test_no_suppressions_means_no_new_keys() -> None:
    m = map_findings(load_bundle(FIXTURES / "bundle"), FINDINGS, today=IN_FORCE)
    assert set(m) == {"controls", "unmapped"}


# -- outputs ------------------------------------------------------------------------------------------


def test_oscal_records_accepted_risk_as_deviation_approved(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path, accepted=ACCEPTED, fp=FALSE_POSITIVE)
    m = map_findings(bundle, FINDINGS, today=IN_FORCE)
    doc = assessment_results(bundle, m, NOW)
    validate(doc, "oscal_assessment-results_schema.json")
    (result,) = doc["assessment-results"]["results"]
    (accepted,) = [r for r in result["risks"] if r["status"] == "deviation-approved"]
    assert accepted["title"] == "Accepted risk: trivy CVE-2024-0001"
    (cc71,) = [f for f in result["findings"] if f["target"]["target-id"] == "cc7.1"]
    assert cc71["description"] == "0 open finding(s), 1 accepted risk(s)."
    assert "Suppressed as false positives (reviewed; see the bundle): suppressions/fp" in result["remarks"]
    assert any(o["title"] == "checkov CKV_TEST_99" for o in result["observations"])
    assert not any(r["title"] == "Coverage gap: checkov CKV_TEST_99" for r in result["risks"])


def test_report_marks_accepted_findings_and_lists_suppressions(tmp_path: Path) -> None:
    stale = _suppression("false-positive", "checkov", "CKV_GONE", "app/Dockerfile")
    bundle = _bundle(tmp_path, accepted=ACCEPTED, fp=FALSE_POSITIVE, stale=stale)
    report = render_report(bundle, map_findings(bundle, FINDINGS, today=IN_FORCE), NOW)
    assert "— **accepted risk** (`suppressions/accepted`)" in report
    assert "1 accepted risk and 1 false positive suppressed after review." in report
    assert "2 open findings across 1 of 4 controls" in report
    assert "| false-positive | `checkov` `CKV_TEST_99` — `app/Dockerfile` | human:reviewer | 2026-12-27 |" in report
    assert "## Unused suppressions" in report and "## Expired suppressions" not in report


def test_reason_renders_as_one_plain_table_cell(tmp_path: Path) -> None:
    fp = _suppression("false-positive", "checkov", "CKV_TEST_99", "app/Dockerfile",
                      reason="See [CC7.1](../controls/cc7.1.md) | and\nmore.")
    bundle = _bundle(tmp_path, fp=fp)
    report = render_report(bundle, map_findings(bundle, FINDINGS, today=IN_FORCE), NOW)
    assert "| See CC7.1 \\| and more. |" in report


def test_digest_counts_accepted_and_false_positives_apart(tmp_path: Path) -> None:
    m = _mapping(tmp_path, accepted=ACCEPTED, fp=FALSE_POSITIVE)
    d = scan_digest(m)
    assert d["controls"]["soc2:cc7.1"] == {"status": "not-satisfied", "findings": 0, "by_severity": {},
                                           "accepted_risks": 1}
    assert d["suppressed_false_positives"] == 1
    assert "accepted_risks" not in d["controls"]["soc2:cc6.1"]


@pytest.mark.parametrize(
    ("today", "expiring"),
    [(date(2026, 12, 12), False), (date(2026, 12, 13), True), (date(2026, 12, 27), True), (date(2026, 12, 28), False)],
)
def test_suppressions_near_expiry_are_flagged(tmp_path: Path, today: date, expiring: bool) -> None:
    m = _mapping(tmp_path, today=today, fp=FALSE_POSITIVE)
    assert (m["expiring_suppressions"] == [{"id": "suppressions/fp", "expires": "2026-12-27"}]) is expiring


def test_report_lists_suppressions_expiring_soon(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path, fp=FALSE_POSITIVE)
    report = render_report(bundle, map_findings(bundle, FINDINGS, today=date(2026, 12, 20)), NOW)
    assert "## Expiring soon" in report and "- `suppressions/fp` expires 2026-12-27" in report
    quiet = render_report(bundle, map_findings(bundle, FINDINGS, today=IN_FORCE), NOW)
    assert "## Expiring soon" not in quiet
