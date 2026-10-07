"""Review intervals (Spec J §4.3): a person's verification stays valid for an interval; grc check warns, then fails."""

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from grc_evidence.config import Config
from grc_evidence.okf_lib import load_bundle
from grc_evidence.review import add_duration, due_date, review

REVIEW = Config(review_default="1y", review_by_type=(("Stack Component", "90d"), ("Crosswalk", "6m")))


def _bundle(tmp_path: Path, **concepts: str) -> Path:
    (tmp_path / "index.md").write_text('---\nokf_version: "0.2"\n---\n# Bundle\n')
    for name, frontmatter in concepts.items():
        (tmp_path / f"{name}.md").write_text(f"---\n{frontmatter}---\n# Intent\nx\n")
    return tmp_path


def _verified(day: str, by: str = "human:r") -> str:
    return f'verified:\n  - by: "{by}"\n    at: "{day}T10:00:00-07:00"\n'


@pytest.mark.parametrize(("start", "duration", "due"), [
    (date(2026, 9, 29), "90d", date(2026, 12, 28)),
    (date(2026, 10, 6), "6m", date(2027, 4, 6)),
    (date(2026, 8, 31), "6m", date(2027, 2, 28)),  # calendar months: clamped to the month's last day
    (date(2028, 2, 29), "1y", date(2029, 2, 28)),
])
def test_add_duration_uses_calendar_months(start: date, duration: str, due: date) -> None:
    assert add_duration(start, duration) == due


def test_due_from_latest_human_verification(tmp_path: Path) -> None:
    fm = "type: Stack Component\n" + _verified("2026-09-29") + '  - by: "human:r"\n    at: "2026-10-05T09:00:00-07:00"\n  - by: "bot"\n    at: "2026-12-01T00:00:00Z"\n'
    c = load_bundle(_bundle(tmp_path, a=fm)).concepts["a"]
    assert due_date(c, REVIEW) == date(2027, 1, 3)  # 2026-10-05 + 90d; a bot's stamp does not count


def test_explicit_stale_after_earlier_wins(tmp_path: Path) -> None:
    b = load_bundle(_bundle(tmp_path, a="type: Reference\nstale_after: 2026-12-01\n" + _verified("2026-10-01"),
                            b="type: Reference\nstale_after: 2030-01-01\n" + _verified("2026-10-01")))
    assert due_date(b.concepts["a"], REVIEW) == date(2026, 12, 1)
    assert due_date(b.concepts["b"], REVIEW) == date(2027, 10, 1)


def test_no_review_section_only_stale_after_counts(tmp_path: Path) -> None:
    b = load_bundle(_bundle(tmp_path, a="type: Reference\n" + _verified("2020-01-01"),
                            b="type: Reference\nstale_after: 2026-01-01\n" + _verified("2020-01-01")))
    assert due_date(b.concepts["a"], Config()) is None
    assert due_date(b.concepts["b"], Config()) == date(2026, 1, 1)


def test_warns_within_warn_before_and_fails_after(tmp_path: Path) -> None:
    bundle = load_bundle(_bundle(tmp_path, a="type: Stack Component\n" + _verified("2026-09-29")))  # due 2026-12-28
    config = replace(REVIEW, review_by_type=(("Stack Component", "90d"),))
    assert review(bundle, config, set(), date(2026, 11, 27)) == ([], [])
    assert review(bundle, config, set(), date(2026, 11, 28)) == ([], ["knowledge/a.md: review due 2026-12-28"])
    assert review(bundle, config, set(), date(2026, 12, 28)) == ([], ["knowledge/a.md: review due 2026-12-28"])
    assert review(bundle, config, set(), date(2026, 12, 29)) == (["knowledge/a.md: review due 2026-12-28: verify it again"], [])
    assert review(bundle, replace(config, review_warn_before="7d"), set(), date(2026, 11, 28)) == ([], [])


def test_overdue_base_copy_warns_unless_base_fail(tmp_path: Path) -> None:
    bundle = load_bundle(_bundle(tmp_path, a="type: Crosswalk\n" + _verified("2026-01-01")))  # due 2026-07-01
    config, later = replace(REVIEW, review_by_type=(("Crosswalk", "6m"),)), date(2026, 10, 6)
    assert review(bundle, config, {"a.md"}, later) == (
        [], ["knowledge/a.md: review due 2026-07-01, overdue in the engine; upgrade when a release re-verifies it"])
    assert review(bundle, replace(config, review_base="fail"), {"a.md"}, later)[0] == [
        "knowledge/a.md: review due 2026-07-01: verify it again"]
    assert review(bundle, config, set(), later)[0] == ["knowledge/a.md: review due 2026-07-01: verify it again"]


def test_suppressions_and_unverified_concepts_are_not_reviewed(tmp_path: Path) -> None:
    suppression = ('type: Suppression\nkind: false-positive\nfinding: {tool: t, rule_id: r, target: x}\nowner: human:r\n'
                   'approved: "2020-01-01"\nexpires: "2020-02-01"\n' + _verified("2020-01-01"))
    (tmp_path / "s.md").write_text(f"---\n{suppression}---\n# Reason\n\nReviewed.\n")
    bundle = load_bundle(_bundle(tmp_path, a="type: Reference\n"))
    assert review(bundle, replace(REVIEW, review_by_type=()), set(), date(2026, 10, 6)) == ([], [])  # 'not verified' is grc check's own problem


def test_unknown_type_in_by_type_is_a_problem(tmp_path: Path) -> None:
    bundle = load_bundle(_bundle(tmp_path, a="type: Reference\n" + _verified("2026-10-01")))
    config = replace(REVIEW, review_by_type=(("Stak Component", "90d"),))
    assert review(bundle, config, set(), date(2026, 10, 6))[0] == [
        "grc.yaml: review.by_type names 'Stak Component', which no concept in knowledge has"]
