"""The change population (Spec H §5): merged changes in the window, independent approval, and the denominator."""

import csv
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from grc_evidence.collect_changes import (
    FLAGS,
    approvers,
    change_findings,
    collect_changes,
    fetch_merged,
    rule_state,
    to_change,
    write_population,
)
from grc_evidence.config import RepoSpec
from grc_evidence.github_api import GitHubError
from grc_evidence.github_queries import MERGED_PRS
from grc_evidence.people import Namer, pseudonym
from grc_evidence.window import utc_bounds

B = utc_bounds(date(2026, 6, 1), date(2026, 8, 31))
REAL = Namer("real", None)
REPO = RepoSpec("acme/api", "in-scope", ("changes",))
HEAD = "a" * 40  # the final commit of every synthetic pull request
MERGED = datetime(2026, 7, 2, tzinfo=UTC)


def _review(login: str | None, state: str, at: str, *, push: bool | None = True, bot: bool = False, commit: str | None = HEAD) -> dict:
    return {"author": {"login": login, "__typename": "Bot" if bot else "User"} if login else None, "state": state,
            "submittedAt": at, "authorCanPushToRepository": push, "commit": {"oid": commit} if commit else None}


def _approved(reviews: list[dict], accepted: frozenset[str] = frozenset()) -> tuple[str, ...]:
    return approvers(reviews, "alice", MERGED, HEAD, accepted)[0]


def _pr(number: int, merged_at: str, *, author: str | None = "alice", merged_by: str | None = "bob",
        reviews: list[dict] | None = None, base: str = "main", updated_at: str | None = None,
        checks: list[dict] | None = None, review_total: int | None = None, check_total: int | None = None) -> dict:
    reviews = [_review("carol", "APPROVED", "2026-07-01T09:00:00Z")] if reviews is None else reviews
    checks = [{"__typename": "CheckRun", "name": "semgrep", "conclusion": "SUCCESS"},
              {"__typename": "StatusContext", "context": "ci/legacy", "state": "SUCCESS"}] if checks is None else checks
    return {
        "number": number, "title": f"Change {number}", "updatedAt": updated_at or merged_at, "mergedAt": merged_at,
        "baseRefName": base, "headRefOid": HEAD, "author": {"login": author} if author else None,
        "mergedBy": {"login": merged_by} if merged_by else None,
        "mergeCommit": {"oid": f"{number:040x}", "statusCheckRollup": {"contexts": {
            "totalCount": len(checks) if check_total is None else check_total, "nodes": checks}}},
        "reviews": {"totalCount": len(reviews) if review_total is None else review_total, "nodes": reviews},
    }


class FakeGitHub:
    """Serves MERGED_PRS pages: `pages[i]` answers cursor None for i == 0 and cursor f"c{i}" after."""

    def __init__(self, pages: list[list[dict]], repeat_cursor: bool = False) -> None:
        self.pages, self.repeat = pages, repeat_cursor
        self.requested: list[int] = []

    def graphql(self, query: str, variables: dict) -> dict:
        assert query == MERGED_PRS and (variables["owner"], variables["name"]) == ("acme", "api")
        i = 0 if variables["cursor"] is None else int(variables["cursor"][1:])
        self.requested.append(i)
        more = i + 1 < len(self.pages)
        cursor = "c1" if self.repeat else f"c{i + 1}"
        return {"rateLimit": {"cost": 1, "remaining": 4999}, "repository": {"pullRequests": {
            "pageInfo": {"hasNextPage": more, "endCursor": cursor if more else None}, "nodes": self.pages[i]}}}

    def rest(self, path: str) -> dict | list | None:
        raise AssertionError("the change collector reads only GraphQL")


def _change(pr: dict, entries: list[dict] | None = None, namer: Namer = REAL) -> Any:
    return to_change(pr, "acme/api", B, entries or [], namer)


def _scm(at: str, reviews: int, readable: bool = True) -> dict:
    return {"collector": "scm", "repo": "acme/api", "recorded_at": at,
            "summary": {"required_reviews": reviews if readable else None, "readable": readable}}


def test_last_second_in_first_second_out() -> None:
    t = FakeGitHub([[_pr(2, "2026-09-01T00:00:00Z"), _pr(1, "2026-08-31T23:59:59Z")]])
    changes, summary = collect_changes(t, REPO, B, (), "main", [], REAL)
    assert [c.number for c in changes] == [1] and summary["in_population"] == 1
    assert "near_boundary" in changes[0].flags


def test_independent_approval_has_no_flag() -> None:
    c = _change(_pr(1, "2026-07-02T00:00:00Z"), [_scm("2026-06-01T00:00:00+00:00", 1)])
    assert c.approvers == ("carol",) and c.flags == ()
    assert c.checks == (("semgrep", "SUCCESS"), ("ci/legacy", "SUCCESS"))


def test_self_merge_without_review() -> None:
    c = _change(_pr(1, "2026-07-02T00:00:00Z", author="alice", merged_by="Alice", reviews=[]))
    assert {"no_approval", "self_merge_without_review"} <= set(c.flags)
    findings = change_findings([c])
    assert [f["rule_id"] for f in findings] == ["change-no-approval", "change-self-merge-without-review"]
    assert all(f["severity"] == "high" and f["target"] == "github:acme/api#1" and f["tool"] == "github" for f in findings)


def test_dismissed_after_approval_not_approver() -> None:
    """GitHub turns the dismissed approval itself into a DISMISSED review."""
    assert _approved([_review("carol", "DISMISSED", "2026-07-01T09:00:00Z")]) == ()


def test_comment_after_approval_keeps_approver() -> None:
    reviews = [_review("carol", "APPROVED", "2026-07-01T09:00:00Z"), _review("carol", "COMMENTED", "2026-07-01T10:00:00Z")]
    assert _approved(reviews) == ("carol",)


def test_changes_requested_after_approval_not_approver() -> None:
    reviews = [_review("carol", "APPROVED", "2026-07-01T09:00:00Z"), _review("carol", "CHANGES_REQUESTED", "2026-07-01T10:00:00Z")]
    assert _approved(reviews) == ()


def test_review_after_merge_ignored() -> None:
    assert _approved([_review("carol", "APPROVED", "2026-07-02T00:00:00Z")]) == ()


def test_author_review_ignored() -> None:
    reviews = [_review("Alice", "APPROVED", "2026-07-01T09:00:00Z"), _review("dave", "APPROVED", "2026-07-01T09:00:00Z"),
               _review(None, "APPROVED", "2026-07-01T09:00:00Z")]
    assert _approved(reviews) == ("dave",)


def test_approval_without_write_access_does_not_count() -> None:
    """Anyone can approve a public pull request; GitHub ignores approvals from people who cannot push."""
    assert _approved([_review("eve", "APPROVED", "2026-07-01T09:00:00Z", push=False)]) == ()
    assert _approved([_review("eve", "APPROVED", "2026-07-01T09:00:00Z", push=None)]) == ()


def test_approval_of_an_earlier_commit_does_not_count() -> None:
    c = _change(_pr(1, "2026-07-02T00:00:00Z", reviews=[_review("carol", "APPROVED", "2026-07-01T09:00:00Z", commit="b" * 40)]))
    assert c.approvers == () and {"approval_not_on_final_commit", "no_approval"} <= set(c.flags)
    reapproved = [_review("carol", "APPROVED", "2026-07-01T09:00:00Z", commit="b" * 40), _review("carol", "APPROVED", "2026-07-01T11:00:00Z")]
    assert _approved(reapproved) == ("carol",)


def test_no_final_commit_fails_closed() -> None:
    pr = {**_pr(1, "2026-07-02T00:00:00Z"), "headRefOid": None}
    assert _change(pr).approvers == () and "approval_not_on_final_commit" in _change(pr).flags


def test_bot_review_is_ignored_unless_accepted() -> None:
    bot = [_review("coderabbitai", "APPROVED", "2026-07-01T09:00:00Z", push=False, bot=True)]
    assert _approved(bot) == ()
    assert approvers(bot, "alice", MERGED, HEAD, frozenset({"coderabbitai"})) == (("coderabbitai",), frozenset({"bot_approval"}))
    blocking = [*bot, _review("coderabbitai", "CHANGES_REQUESTED", "2026-07-01T10:00:00Z", bot=True)]
    assert _approved(blocking) == ()


def test_accepted_bot_approval_is_flagged_on_the_change() -> None:
    pr = _pr(1, "2026-07-02T00:00:00Z", reviews=[_review("coderabbitai", "APPROVED", "2026-07-01T09:00:00Z", push=False, bot=True)])
    c = to_change(pr, "acme/api", B, [], REAL, frozenset({"coderabbitai"}))
    assert c.approvers == ("coderabbitai",) and "bot_approval" in c.flags and "no_approval" not in c.flags
    assert "no_approval" in to_change(pr, "acme/api", B, [], REAL).flags


def test_rule_became_active_mid_window() -> None:
    entries = [_scm("2026-06-10T06:00:00+00:00", 0), _scm("2026-07-01T06:00:00+00:00", 1)]
    assert "merged_before_rule" in _change(_pr(1, "2026-06-20T00:00:00Z"), entries).flags
    after = _change(_pr(2, "2026-07-05T00:00:00Z"), entries).flags
    assert "merged_before_rule" not in after and "rule_not_evidenced" not in after
    assert rule_state(entries, "acme/api", datetime(2026, 6, 5, tzinfo=UTC)) == "unknown"


def test_no_scm_entry_is_rule_not_evidenced() -> None:
    flags = _change(_pr(1, "2026-07-02T00:00:00Z"), []).flags
    assert "rule_not_evidenced" in flags and "merged_before_rule" not in flags


def test_unreadable_scm_entry_is_rule_not_evidenced() -> None:
    entries = [_scm("2026-06-10T06:00:00+00:00", 1), _scm("2026-06-20T06:00:00+00:00", 1, readable=False)]
    assert rule_state(entries, "acme/api", datetime(2026, 7, 1, tzinfo=UTC)) == "unknown"
    other_repo = [{**_scm("2026-06-10T06:00:00+00:00", 1), "repo": "acme/lib"}]
    assert rule_state(other_repo, "acme/api", datetime(2026, 7, 1, tzinfo=UTC)) == "unknown"


def test_empty_population_keeps_denominator() -> None:
    page = [_pr(i, "2026-07-02T00:00:00Z", base="feature") for i in range(1, 5)]
    changes, summary = collect_changes(FakeGitHub([page]), REPO, B, (), "main", [], REAL)
    assert changes == [] and summary["in_population"] == 0 and summary["merged_all_branches"] == 4
    assert summary["flags"] == {flag: 0 for flag in FLAGS}


def test_listed_branches_join_the_population() -> None:
    page = [_pr(1, "2026-07-02T00:00:00Z", base="release"), _pr(2, "2026-07-02T00:00:00Z", base="feature")]
    changes, summary = collect_changes(FakeGitHub([page]), REPO, B, ("release",), "main", [], REAL)
    assert [c.number for c in changes] == [1] and summary["merged_all_branches"] == 2


def test_pagination_stops_before_window() -> None:
    pages = [
        [_pr(3, "2026-09-10T00:00:00Z"), _pr(2, "2026-07-02T00:00:00Z", updated_at="2026-09-05T00:00:00Z")],
        [_pr(1, "2026-07-01T00:00:00Z"), _pr(9, "2026-05-01T00:00:00Z", updated_at="2026-05-20T00:00:00Z")],
        [_pr(8, "2026-04-01T00:00:00Z")],
    ]
    t = FakeGitHub(pages)
    changes, summary = collect_changes(t, REPO, B, (), "main", [], REAL)
    assert t.requested == [0, 1]  # page 3 is never requested
    assert sorted(c.number for c in changes) == [1, 2] and summary["merged_all_branches"] == 2


def test_pagination_same_cursor_raises() -> None:
    pages = [[_pr(3, "2026-08-10T00:00:00Z")], [_pr(2, "2026-08-01T00:00:00Z")], [_pr(1, "2026-07-01T00:00:00Z")]]
    with pytest.raises(GitHubError, match="pagination did not advance"):
        list(fetch_merged(FakeGitHub(pages, repeat_cursor=True), "acme/api", B))


def test_truncated_reviews_give_no_approver() -> None:
    """Fail closed: a dismissal after the first 100 reviews would otherwise leave a stale approval."""
    c = _change(_pr(1, "2026-07-02T00:00:00Z", review_total=101))
    assert c.approvers == () and {"reviews_incomplete", "no_approval"} <= set(c.flags)
    assert "checks_incomplete" in _change(_pr(2, "2026-07-02T00:00:00Z", check_total=101)).flags


def test_ghost_author() -> None:
    c = _change(_pr(1, "2026-07-02T00:00:00Z", author=None))
    assert c.author == "ghost"


def test_ghost_author_and_merger_not_self_merge() -> None:
    c = _change(_pr(1, "2026-07-02T00:00:00Z", author=None, merged_by=None, reviews=[]))
    assert "self_merge_without_review" not in c.flags and "no_approval" in c.flags


def test_pseudonymous_no_raw_login_anywhere(tmp_path: Path) -> None:
    namer = Namer("pseudonymous", b"salt")
    page = [_pr(1, "2026-07-02T00:00:00Z", author="alice", merged_by="alice", reviews=[]), _pr(2, "2026-07-03T00:00:00Z")]
    changes, summary = collect_changes(FakeGitHub([page]), REPO, B, (), "main", [], namer)
    assert {c.author for c in changes} == {pseudonym("alice", b"salt")}
    assert "self_merge_without_review" in changes[0].flags  # compared on raw logins
    write_population(tmp_path, changes, {"acme/api": summary})
    text = json.dumps([f["message"] for f in change_findings(changes)]) + "".join(
        p.read_text() for p in (tmp_path / "collect").iterdir())
    for login in ("alice", "bob", "carol"):
        assert login not in text


def test_pseudonymous_drops_titles() -> None:
    """A title can hold a login ("Merge ... from alice/branch", "@alice"), so pseudonymous outputs carry none."""
    pr = {**_pr(1, "2026-07-02T00:00:00Z"), "title": "Merge pull request #1 from alice/fix, thanks @carol"}
    assert _change(pr, namer=Namer("pseudonymous", b"salt")).title == ""
    assert _change(pr).title == pr["title"]


def test_csv_header_and_utc_z(tmp_path: Path) -> None:
    changes = [_change(_pr(1, "2026-07-02T08:30:00+02:00"))]
    hashes = write_population(tmp_path, changes, {"acme/api": {"in_population": 1}})
    rows = list(csv.reader((tmp_path / "collect" / "population.csv").open()))
    assert rows[0] == ["repo", "number", "title", "author", "merged_by", "merged_at", "merge_sha", "base", "approvers", "flags"]
    assert rows[1][5] == "2026-07-02T06:30:00Z" and rows[1][8] == "carol"
    assert set(hashes) == {"collect/population.csv", "collect/changes.json"}
    doc = json.loads((tmp_path / "collect" / "changes.json").read_text())
    assert doc["summary"] == {"acme/api": {"in_population": 1}}
    assert doc["changes"][0]["checks"] == [["semgrep", "SUCCESS"], ["ci/legacy", "SUCCESS"]]


def test_csv_cells_cannot_start_a_formula(tmp_path: Path) -> None:
    """Titles come from anyone who opens a pull request; a spreadsheet would run `=...` as a formula."""
    pr = {**_pr(1, "2026-07-02T00:00:00Z"), "title": '=HYPERLINK("http://x","y")'}
    write_population(tmp_path, [_change(pr)], {})
    rows = list(csv.reader((tmp_path / "collect" / "population.csv").open()))
    assert rows[1][2] == "'=HYPERLINK(\"http://x\",\"y\")"
