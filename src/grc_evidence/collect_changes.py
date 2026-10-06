"""The change population (Spec H §5): every change merged into a production branch in the window, with who
wrote, approved and merged it, and the count of all merged changes beside it (a zero needs a denominator).

Code decides each flag. Logins pass through the `Namer` here, so no real login leaves this module when
`people: pseudonymous`. Rules that compare people (self-merge, the author's own review) use the raw logins.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from grc_evidence.config import RepoSpec
from grc_evidence.github_api import GitHubError, Transport
from grc_evidence.github_queries import MERGED_PRS
from grc_evidence.people import Namer
from grc_evidence.run_scan import Finding, _finding
from grc_evidence.window import Bounds, in_window, near_boundary, parse_ts

FLAGS = (
    "no_approval", "self_merge_without_review", "merged_before_rule", "rule_not_evidenced", "near_boundary",
    "reviews_incomplete", "checks_incomplete",
)
COUNTED_STATES = ("APPROVED", "CHANGES_REQUESTED", "DISMISSED")  # a COMMENTED review does not withdraw an approval
CSV_HEADER = ("repo", "number", "title", "author", "merged_by", "merged_at", "merge_sha", "base", "approvers", "flags")
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


@dataclass(frozen=True)
class Change:
    """One merged change. Logins are already named: `ghost` for a missing login."""

    repo: str
    number: int
    title: str
    author: str
    merged_by: str
    merged_at: datetime
    merge_sha: str
    base: str
    approvers: tuple[str, ...]
    flags: tuple[str, ...]
    checks: tuple[tuple[str, str], ...]  # (name, conclusion) on the merge commit


def fetch_merged(t: Transport, repo: str, bounds: Bounds) -> Iterator[dict]:
    """Merged pull requests, newest update first, up to the page that reaches before the window start.

    A change merged in the window was updated at or after its merge, so it comes before that page ends.
    """
    owner, name = repo.split("/")
    cursor: str | None = None
    seen: set[str] = set()
    while True:
        prs = t.graphql(MERGED_PRS, {"owner": owner, "name": name, "cursor": cursor})["repository"]["pullRequests"]
        nodes = prs["nodes"]
        yield from nodes
        if not nodes or parse_ts(nodes[-1]["updatedAt"]) < bounds[0] or not prs["pageInfo"]["hasNextPage"]:
            return
        cursor = prs["pageInfo"]["endCursor"]
        if cursor is None or cursor in seen:
            raise GitHubError(f"{repo}: pagination did not advance")
        seen.add(cursor)


def _login(actor: dict | None) -> str | None:
    return (actor or {}).get("login")


def approvers(reviews: list[dict], author: str | None, merged_at: datetime) -> tuple[str, ...]:
    """Raw logins whose latest counted review before the merge is APPROVED, the author excluded."""
    latest: dict[str, tuple[str, str]] = {}
    for review in sorted((r for r in reviews if r.get("submittedAt")), key=lambda r: parse_ts(r["submittedAt"])):
        login = _login(review.get("author"))
        if not login or (author and login.lower() == author.lower()) or review.get("state") not in COUNTED_STATES:
            continue
        if parse_ts(review["submittedAt"]) >= merged_at:
            continue
        latest[login.lower()] = (login, review["state"])
    return tuple(sorted(login for login, state in latest.values() if state == "APPROVED"))


def rule_state(entries: list[dict], repo: str, at: datetime) -> str:
    """Required reviews at `at`, from the last `scm` ledger entry for `repo` recorded on or before it:
    "on", "off", or "unknown" when there is no such entry or its rules were not readable."""
    before = [
        e for e in entries
        if e.get("collector") == "scm" and str(e.get("repo", "")).lower() == repo.lower() and parse_ts(e["recorded_at"]) <= at
    ]
    summary = (before[-1].get("summary") or {}) if before else {}
    if not summary.get("readable") or summary.get("required_reviews") is None:
        return "unknown"
    return "on" if summary["required_reviews"] >= 1 else "off"


def to_change(pr: dict, repo: str, bounds: Bounds, entries: list[dict], namer: Namer) -> Change:
    merged_at = parse_ts(pr["mergedAt"])
    author, merged_by = _login(pr.get("author")), _login(pr.get("mergedBy"))
    reviews = pr.get("reviews") or {"totalCount": 0, "nodes": []}
    commit = pr.get("mergeCommit") or {}
    contexts = (commit.get("statusCheckRollup") or {}).get("contexts") or {"totalCount": 0, "nodes": []}
    flags: set[str] = set()
    if reviews["totalCount"] > len(reviews["nodes"]):  # fail closed: a later dismissal may be cut off
        flags.add("reviews_incomplete")
        approved: tuple[str, ...] = ()
    else:
        approved = approvers(reviews["nodes"], author, merged_at)
    if contexts["totalCount"] > len(contexts["nodes"]):
        flags.add("checks_incomplete")
    if not approved:
        flags.add("no_approval")
        if author and merged_by and author.lower() == merged_by.lower():
            flags.add("self_merge_without_review")
    state = rule_state(entries, repo, merged_at)
    if state == "off":
        flags.add("merged_before_rule")
    elif state == "unknown":
        flags.add("rule_not_evidenced")
    if near_boundary(merged_at, bounds):
        flags.add("near_boundary")
    checks = tuple(
        (str(n.get("name") or n.get("context")), str(n.get("conclusion") or n.get("state") or "PENDING"))
        for n in contexts["nodes"]
    )
    return Change(
        repo=repo, number=pr["number"], title=pr.get("title") or "", author=namer.name(author),
        merged_by=namer.name(merged_by), merged_at=merged_at, merge_sha=commit.get("oid") or "",
        base=pr["baseRefName"], approvers=tuple(sorted(namer.name(a) for a in approved)),
        flags=tuple(f for f in FLAGS if f in flags), checks=checks,
    )


def collect_changes(
    t: Transport, repo: RepoSpec, bounds: Bounds, branches: tuple[str, ...], default_branch: str,
    entries: list[dict], namer: Namer,
) -> tuple[list[Change], dict[str, Any]]:
    """The population of `repo` (merged into the default branch or a listed branch in the window) and its
    summary: `in_population`, `merged_all_branches` (the denominator) and a count per flag."""
    merged: dict[int, dict] = {}
    for pr in fetch_merged(t, repo.name, bounds):
        if pr.get("mergedAt") and in_window(parse_ts(pr["mergedAt"]), bounds):
            merged.setdefault(pr["number"], pr)  # a change updated during paging can appear twice
    production = {default_branch, *branches}
    changes = sorted(
        (to_change(pr, repo.name, bounds, entries, namer) for pr in merged.values() if pr["baseRefName"] in production),
        key=lambda c: c.number,
    )
    summary = {
        "in_population": len(changes), "merged_all_branches": len(merged),
        "flags": {flag: sum(flag in c.flags for c in changes) for flag in FLAGS},
    }
    return changes, summary


def change_findings(changes: list[Change]) -> list[Finding]:
    """`change-*` findings, one target per change so a suppression can name one change."""
    findings = []
    for c in changes:
        target, day = f"github:{c.repo}#{c.number}", c.merged_at.date().isoformat()
        if "no_approval" in c.flags:
            findings.append(_finding("github", "change-no-approval", "high", target, f"#{c.number} merged on {day} with no independent approval"))
        if "self_merge_without_review" in c.flags:
            findings.append(_finding("github", "change-self-merge-without-review", "high", target, f"#{c.number} merged on {day} by its author with no approval"))
    return findings


def _utc(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _row(c: Change) -> dict[str, Any]:
    return {
        "repo": c.repo, "number": c.number, "title": c.title, "author": c.author, "merged_by": c.merged_by,
        "merged_at": _utc(c.merged_at), "merge_sha": c.merge_sha, "base": c.base,
        "approvers": ";".join(c.approvers), "flags": ";".join(c.flags),
    }


def _cell(value: Any) -> Any:
    """A text cell that a spreadsheet would read as a formula gets a leading quote; titles are not trusted."""
    return f"'{value}" if isinstance(value, str) and value.startswith(_FORMULA_START) else value


def write_population(out: Path, changes: list[Change], summary: dict[str, Any]) -> dict[str, str]:
    """Write `collect/population.csv` and `collect/changes.json` (the rows plus the checks, and `summary`);
    returns each path, relative to `out`, with its sha256."""
    text = io.StringIO()
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    writer.writerows([_cell(v) for v in _row(c).values()] for c in changes)
    doc = {"summary": summary, "changes": [{**_row(c), "checks": [list(check) for check in c.checks]} for c in changes]}
    files = {"collect/population.csv": text.getvalue(), "collect/changes.json": json.dumps(doc, indent=1) + "\n"}
    (out / "collect").mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        (out / rel).write_text(content, encoding="utf-8")
    return {rel: hashlib.sha256(content.encode()).hexdigest() for rel, content in files.items()}
