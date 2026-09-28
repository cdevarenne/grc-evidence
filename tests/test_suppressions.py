"""Suppressions (Spec C): reviewed, expiring, exact; they change how a finding counts, never whether it shows."""

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

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
