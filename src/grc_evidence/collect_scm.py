"""SCM posture (Spec H §4): the default branch's rules and the CI scanner jobs of one repo, read-only.

Rules are read as the Part A spike recorded (`docs/limits.md`, "Repository settings"): rulesets first, then
classic branch protection. They are readable only when both reads succeed; a 404 on classic protection counts
as "no protection" only with GitHub's message "Branch not protected". Unreadable rules give the finding
`scm-rules-unreadable`, never a pass. A posture is the state on the day it is read, not history (§3.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import yaml

from grc_evidence.config import RepoSpec
from grc_evidence.github_api import NotFound, Transport
from grc_evidence.github_queries import DEFAULT_BRANCH, WORKFLOWS
from grc_evidence.run_scan import Finding, _finding

NOT_PROTECTED = "Branch not protected"
WORKFLOW_SUFFIXES = (".yml", ".yaml")


@dataclass(frozen=True)
class Posture:
    """The posture of one repo's default branch. Rule fields are None when the rules are not readable."""

    repo: str
    branch: str
    readable: bool
    required_reviews: int | None
    dismiss_stale: bool | None
    required_checks: tuple[str, ...]
    admin_bypass: bool | None  # admins, ruleset bypass actors, or classic review bypass allowances
    scanner_jobs: dict[str, dict[str, bool]]
    workflow_errors: tuple[str, ...]


@dataclass(frozen=True)
class _Rules:
    required_reviews: int
    dismiss_stale: bool
    required_checks: tuple[str, ...]
    admin_bypass: bool


def read_posture(t: Transport, repo: RepoSpec, scanner_jobs: tuple[str, ...]) -> Posture:
    """Read the rules and the workflows of `repo`'s default branch."""
    owner, name = repo.name.split("/")
    branch = t.graphql(DEFAULT_BRANCH, {"owner": owner, "name": name})["repository"]["defaultBranchRef"]["name"]
    rules = _read_rules(t, repo.name, branch)
    workflows, unreadable = _read_workflows(t, owner, name)
    jobs, errors = scanner_job_status(workflows, scanner_jobs)
    return Posture(
        repo=repo.name, branch=branch, readable=rules is not None,
        required_reviews=rules.required_reviews if rules else None,
        dismiss_stale=rules.dismiss_stale if rules else None,
        required_checks=rules.required_checks if rules else (),
        admin_bypass=rules.admin_bypass if rules else None,
        scanner_jobs=jobs, workflow_errors=tuple(sorted((*unreadable, *errors))),
    )


def _read_rules(t: Transport, repo: str, branch: str) -> _Rules | None:
    """Rulesets and classic protection combined, or None when either cannot be read."""
    quoted = quote(branch, safe="")
    rulesets = t.rest(f"/repos/{repo}/rules/branches/{quoted}")
    try:
        classic = t.rest(f"/repos/{repo}/branches/{quoted}/protection")
    except NotFound as e:
        if e.reason != NOT_PROTECTED:
            return None
        classic = {}
    if not isinstance(rulesets, list) or not isinstance(classic, dict):
        return None
    reviews, stale, checks, bypass = [0], False, set[str](), False
    if classic:
        if prr := classic.get("required_pull_request_reviews"):
            reviews.append(prr.get("required_approving_review_count", 0))
            stale |= bool(prr.get("dismiss_stale_reviews"))
            # Named users, teams or apps may merge without the required reviews.
            bypass |= any((prr.get("bypass_pull_request_allowances") or {}).values())
        if rsc := classic.get("required_status_checks"):
            checks |= set(rsc.get("contexts") or []) | {c["context"] for c in rsc.get("checks") or []}
        bypass |= not (classic.get("enforce_admins") or {}).get("enabled", False)
    for rule in rulesets:
        params = rule.get("parameters") or {}
        if rule.get("type") == "pull_request":
            reviews.append(params.get("required_approving_review_count", 0))
            stale |= bool(params.get("dismiss_stale_reviews_on_push"))
        elif rule.get("type") == "required_status_checks":
            checks |= {c["context"] for c in params.get("required_status_checks") or []}
    for ruleset_id in sorted({r["ruleset_id"] for r in rulesets if "ruleset_id" in r}):
        try:
            detail = t.rest(f"/repos/{repo}/rulesets/{ruleset_id}")
        except NotFound:
            return None
        if not isinstance(detail, dict) or "bypass_actors" not in detail:  # the list needs administration read
            return None
        # Every mode is a bypass: `pull_request` actors can merge without the required reviews, `exempt` skips the rules.
        bypass |= bool(detail["bypass_actors"])
    return _Rules(max(reviews), stale, tuple(sorted(checks)), bypass)


def _read_workflows(t: Transport, owner: str, name: str) -> tuple[dict[str, str], list[str]]:
    """The workflow files at the default branch head, and the names of those that could not be read whole."""
    tree = t.graphql(WORKFLOWS, {"owner": owner, "name": name, "expr": "HEAD:.github/workflows"})["repository"]["object"]
    files: dict[str, str] = {}
    unreadable: list[str] = []
    for entry in (tree or {}).get("entries") or []:
        if entry.get("type") != "blob" or not entry["name"].endswith(WORKFLOW_SUFFIXES):
            continue
        blob = entry.get("object") or {}
        if blob.get("isTruncated") or blob.get("text") is None:
            unreadable.append(entry["name"])
        else:
            files[entry["name"]] = blob["text"]
    return files, unreadable


def scanner_job_status(
    workflows: dict[str, str], patterns: tuple[str, ...]
) -> tuple[dict[str, dict[str, bool]], tuple[str, ...]]:
    """For each pattern, whether a CI job matches it and whether a matching job or step can fail without
    failing the build; and the workflow files that do not parse (their jobs count as not present)."""
    jobs: list[tuple[str, str, bool]] = []
    errors: list[str] = []
    for file, text in sorted(workflows.items()):
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError:
            errors.append(file)
            continue
        file_jobs = doc.get("jobs") if isinstance(doc, dict) else None
        if not isinstance(file_jobs, dict):
            errors.append(file)
            continue
        jobs += [
            (str(i), str(j.get("name", "")), _can_fail(j))
            for i, j in file_jobs.items()
            if isinstance(j, dict) and j.get("if") is not False  # a job with `if: false` never runs
        ]
    status = {}
    for pattern in patterns:
        p = pattern.lower()
        matched = [can_fail for job_id, name, can_fail in jobs if p in job_id.lower() or p in name.lower()]
        status[pattern] = {"present": bool(matched), "can_fail": any(matched)}
    return status, tuple(errors)


def _can_fail(job: dict[str, Any]) -> bool:
    """`continue-on-error` on the job or a step. An expression counts: it may be true when the job runs."""
    steps = [s for s in job.get("steps") or [] if isinstance(s, dict)]
    return any(x.get("continue-on-error") not in (None, False) for x in (job, *steps))


def posture_findings(p: Posture) -> list[Finding]:
    """Findings in the existing contract: tool `github`, target `github:<owner>/<name>`."""
    target, found = f"github:{p.repo}", []
    if not p.readable:
        found.append(("scm-rules-unreadable", "unknown", f"the rules of branch {p.branch} cannot be read with this token"))
    else:
        if (p.required_reviews or 0) < 1:
            found.append(("scm-no-required-review", "high", f"branch {p.branch} requires no approving review"))
        if not p.required_checks:
            found.append(("scm-no-required-checks", "medium", f"branch {p.branch} requires no status check"))
        if p.admin_bypass:
            found.append(("scm-admin-bypass", "medium", f"the rules of branch {p.branch} can be bypassed"))
    errors = f" (workflow files not read: {', '.join(p.workflow_errors)})" if p.workflow_errors else ""
    for pattern, job in p.scanner_jobs.items():
        if not job["present"]:
            found.append(("scm-scanner-job-missing", "medium", f"no CI job matches scanner job {pattern!r}{errors}"))
        elif job["can_fail"]:
            found.append(("scm-scanner-job-can-fail", "medium", f"a CI job for {pattern!r} has continue-on-error"))
    return [_finding("github", rule, severity, target, message) for rule, severity, message in found]


def posture_summary(p: Posture) -> dict[str, Any]:
    """The ledger summary of one repo's posture (spec §4.3)."""
    return {
        "required_reviews": p.required_reviews, "required_checks": list(p.required_checks),
        "admin_bypass": p.admin_bypass, "readable": p.readable,
    }
