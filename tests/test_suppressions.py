"""Suppressions (Spec C): reviewed, expiring, exact; they change how a finding counts, never whether it shows."""

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from map_findings import map_findings
from okf_lib import BundleError, load_bundle

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
    [(date(2026, 9, 27), False), (date(2026, 9, 28), True), (date(2026, 12, 27), True), (date(2026, 12, 28), False)],
)
def test_suppression_applies_from_approval_through_expiry(tmp_path: Path, today: date, applies: bool) -> None:
    m = _mapping(tmp_path, today=today, fp=FALSE_POSITIVE)
    assert bool(m["suppressed"]) is applies
    assert ("suppressions/fp" in m["expired_suppressions"]) is (today > date(2026, 12, 27))


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
