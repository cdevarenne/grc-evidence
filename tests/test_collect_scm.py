"""The SCM posture collector (Spec H §4): branch rules and scanner jobs, read-only; unreadable is never a pass."""

from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest

from grc_evidence import data
from grc_evidence.collect_scm import (
    posture_findings,
    posture_summary,
    read_posture,
    scanner_job_status,
)
from grc_evidence.config import RepoSpec
from grc_evidence.github_api import NotFound
from grc_evidence.github_queries import DEFAULT_BRANCH, WORKFLOWS
from grc_evidence.okf_lib import load_bundle

SCANNER = """jobs:
  scan:
    name: Semgrep scan
    runs-on: ubuntu-latest
    steps: [{run: semgrep scan}]
"""
SOFT = """jobs:
  semgrep:
    runs-on: ubuntu-latest
    continue-on-error: true
    steps: [{run: semgrep scan}]
"""
SOFT_STEP = """jobs:
  semgrep:
    runs-on: ubuntu-latest
    steps:
      - run: semgrep scan
        continue-on-error: ${{ github.event_name == 'pull_request' }}
"""
REVIEWS: dict[str, Any] = {"required_approving_review_count": 1, "dismiss_stale_reviews": True}
PROTECTED: dict[str, Any] = {
    "required_pull_request_reviews": REVIEWS,
    "required_status_checks": {"contexts": ["ci"], "checks": [{"context": "ci"}, {"context": "semgrep"}]},
    "enforce_admins": {"enabled": True},
}
NOT_PROTECTED = NotFound("GitHub API 404", "Branch not protected")


class FakeGitHub:
    """Answers the collector's reads for synthetic repos."""

    def __init__(self, repos: dict[str, dict[str, Any]]) -> None:
        self.repos = repos

    def graphql(self, query: str, variables: dict) -> dict:
        repo = self.repos[f"{variables['owner']}/{variables['name']}"]
        if query == DEFAULT_BRANCH:
            return {"repository": {"defaultBranchRef": {"name": repo.get("branch", "main")}}}
        assert query == WORKFLOWS and variables["expr"] == "HEAD:.github/workflows"
        files = repo.get("workflows")
        entries = [{"name": n, "type": "blob", "object": {"text": t, "isTruncated": False}} for n, t in (files or {}).items()]
        return {"repository": {"object": {"entries": entries} if files is not None else None}}

    def rest(self, path: str) -> dict | list | None:
        _, _, owner, name, *rest = path.split("/")
        repo, tail = self.repos[f"{owner}/{name}"], "/".join(rest)
        branch = quote(repo.get("branch", "main"), safe="")
        answer = {
            f"rules/branches/{branch}": repo.get("rulesets", []),
            f"branches/{branch}/protection": repo.get("classic", NOT_PROTECTED),
            **{f"rulesets/{i}": d for i, d in repo.get("details", {}).items()},
        }[tail]
        if isinstance(answer, Exception):
            raise answer
        return answer


def _read(repos: dict[str, dict[str, Any]], name: str = "acme/api", jobs: tuple[str, ...] = ("semgrep",)) -> Any:
    return read_posture(FakeGitHub(repos), RepoSpec(name, "in-scope", ("scm",)), jobs)


def _rules(p: Any) -> list[str]:
    return [f["rule_id"] for f in posture_findings(p)]


def test_protected_repo_has_no_findings() -> None:
    p = _read({"acme/api": {"classic": PROTECTED, "workflows": {"ci.yml": SCANNER}}})
    assert (p.readable, p.required_reviews, p.dismiss_stale, p.admin_bypass) == (True, 1, True, False)
    assert p.required_checks == ("ci", "semgrep")
    assert _rules(p) == []


def test_unprotected_repo() -> None:
    """The owner's own repos (spec §10): no rules and no scanner job."""
    p = _read({"acme/lib": {"workflows": {}}}, "acme/lib")
    assert p.readable and p.required_reviews == 0
    assert _rules(p) == ["scm-no-required-review", "scm-no-required-checks", "scm-scanner-job-missing"]
    findings = {f["rule_id"]: f for f in posture_findings(p)}
    assert findings["scm-no-required-review"]["severity"] == "high"
    assert findings["scm-no-required-checks"]["severity"] == "medium"
    assert findings["scm-no-required-review"]["target"] == "github:acme/lib"
    assert findings["scm-no-required-review"]["tool"] == "github"


def test_unreadable_is_not_a_pass() -> None:
    p = _read({"acme/locked": {"classic": None, "workflows": {"ci.yml": SCANNER}}}, "acme/locked")
    assert not p.readable and p.required_reviews is None and p.admin_bypass is None
    assert _rules(p) == ["scm-rules-unreadable"]
    assert posture_findings(p)[0]["severity"] == "unknown"


def test_unreadable_rulesets_are_not_a_pass() -> None:
    p = _read({"acme/api": {"rulesets": None, "classic": PROTECTED, "workflows": {"ci.yml": SCANNER}}})
    assert _rules(p) == ["scm-rules-unreadable"]


def test_a_404_other_than_not_protected_is_unreadable() -> None:
    p = _read({"acme/api": {"classic": NotFound("GitHub API 404", "Branch not found"), "workflows": {"ci.yml": SCANNER}}})
    assert _rules(p) == ["scm-rules-unreadable"]


def test_admin_bypass_from_classic_protection() -> None:
    classic = {**PROTECTED, "enforce_admins": {"enabled": False}}
    p = _read({"acme/api": {"classic": classic, "workflows": {"ci.yml": SCANNER}}})
    assert p.admin_bypass is True and _rules(p) == ["scm-admin-bypass"]


def test_rulesets_give_reviews_checks_and_bypass() -> None:
    rulesets = [
        {"type": "pull_request", "ruleset_id": 7, "parameters": {"required_approving_review_count": 2, "dismiss_stale_reviews_on_push": True}},
        {"type": "required_status_checks", "ruleset_id": 7, "parameters": {"required_status_checks": [{"context": "semgrep"}]}},
    ]
    details = {7: {"id": 7, "bypass_actors": [{"actor_type": "RepositoryRole", "bypass_mode": "always"}]}}
    p = _read({"acme/api": {"rulesets": rulesets, "details": details, "workflows": {"ci.yml": SCANNER}}})
    assert (p.required_reviews, p.dismiss_stale, p.required_checks, p.admin_bypass) == (2, True, ("semgrep",), True)
    assert _rules(p) == ["scm-admin-bypass"]


@pytest.mark.parametrize("mode", ["always", "pull_request", "exempt"])
def test_every_ruleset_bypass_mode_is_a_bypass(mode: str) -> None:
    """Fail closed: a pull_request-mode actor can merge without the required reviews; exempt skips the rules."""
    rulesets = [{"type": "pull_request", "ruleset_id": 7, "parameters": {"required_approving_review_count": 1}},
                {"type": "required_status_checks", "ruleset_id": 7, "parameters": {"required_status_checks": [{"context": "ci"}]}}]
    details = {7: {"id": 7, "bypass_actors": [{"actor_type": "Team", "bypass_mode": mode}]}}
    p = _read({"acme/api": {"rulesets": rulesets, "details": details, "workflows": {"ci.yml": SCANNER}}})
    assert p.admin_bypass is True and _rules(p) == ["scm-admin-bypass"]


def test_ruleset_with_no_bypass_actor_is_not_a_bypass() -> None:
    rulesets = [{"type": "pull_request", "ruleset_id": 7, "parameters": {"required_approving_review_count": 1}},
                {"type": "required_status_checks", "ruleset_id": 7, "parameters": {"required_status_checks": [{"context": "ci"}]}}]
    p = _read({"acme/api": {"rulesets": rulesets, "details": {7: {"id": 7, "bypass_actors": []}}, "workflows": {"ci.yml": SCANNER}}})
    assert p.admin_bypass is False and _rules(p) == []


@pytest.mark.parametrize("kind", ["users", "teams", "apps"])
def test_classic_review_bypass_allowances_are_a_bypass(kind: str) -> None:
    """Classic protection can let named users, teams or apps merge without the required reviews."""
    reviews = {**REVIEWS, "bypass_pull_request_allowances": {kind: [{"login": "x"}]}}
    p = _read({"acme/api": {"classic": {**PROTECTED, "required_pull_request_reviews": reviews}, "workflows": {"ci.yml": SCANNER}}})
    assert p.admin_bypass is True and _rules(p) == ["scm-admin-bypass"]
    assert "can be bypassed" in posture_findings(p)[0]["message"]


def test_empty_bypass_allowances_are_not_a_bypass() -> None:
    reviews = {**REVIEWS, "bypass_pull_request_allowances": {"users": [], "teams": [], "apps": []}}
    p = _read({"acme/api": {"classic": {**PROTECTED, "required_pull_request_reviews": reviews}, "workflows": {"ci.yml": SCANNER}}})
    assert p.admin_bypass is False


def test_a_job_that_never_runs_is_not_present() -> None:
    disabled = SCANNER.replace("    runs-on: ubuntu-latest\n", "    runs-on: ubuntu-latest\n    if: false\n")
    status, _ = scanner_job_status({"ci.yml": disabled}, ("semgrep",))
    assert status == {"semgrep": {"present": False, "can_fail": False}}


def test_ruleset_without_readable_bypass_list_is_unreadable() -> None:
    rulesets = [{"type": "pull_request", "ruleset_id": 7, "parameters": {"required_approving_review_count": 1}}]
    p = _read({"acme/api": {"rulesets": rulesets, "details": {7: {"id": 7}}, "workflows": {"ci.yml": SCANNER}}})
    assert _rules(p) == ["scm-rules-unreadable"]


def test_job_level_and_step_level_continue_on_error() -> None:
    for text in (SOFT, SOFT_STEP):
        p = _read({"acme/api": {"classic": PROTECTED, "workflows": {"ci.yml": text}}})
        assert p.scanner_jobs == {"semgrep": {"present": True, "can_fail": True}}
        assert _rules(p) == ["scm-scanner-job-can-fail"]


def test_malformed_workflow_counts_as_missing() -> None:
    status, errors = scanner_job_status({"bad.yml": "jobs: [unclosed", "ci.yml": "on: push\n"}, ("semgrep",))
    assert status == {"semgrep": {"present": False, "can_fail": False}}
    assert errors == ("bad.yml", "ci.yml")


def test_no_workflows_directory() -> None:
    p = _read({"acme/api": {"classic": PROTECTED, "workflows": None}})
    assert _rules(p) == ["scm-scanner-job-missing"]


def test_pattern_matches_job_name_case_insensitive() -> None:
    status, _ = scanner_job_status({"ci.yml": SCANNER}, ("SEMGREP", "trivy"))
    assert status == {"SEMGREP": {"present": True, "can_fail": False}, "trivy": {"present": False, "can_fail": False}}


def test_branch_with_a_slash_is_quoted() -> None:
    p = _read({"acme/api": {"branch": "release/1", "classic": PROTECTED, "workflows": {"ci.yml": SCANNER}}})
    assert p.branch == "release/1" and p.readable


def test_summary_holds_the_ledger_fields() -> None:
    p = _read({"acme/api": {"classic": PROTECTED, "workflows": {"ci.yml": SCANNER}}})
    assert posture_summary(p) == {"required_reviews": 1, "required_checks": ["ci", "semgrep"], "admin_bypass": False, "readable": True}


@pytest.mark.parametrize("rule", ["scm-no-required-review", "scm-rules-unreadable", "change-no-approval"])
def test_base_bundle_maps_github_rules(rule: str) -> None:
    bundle = load_bundle(Path(str(data.path("base"))))
    assert any("soc2:cc8.1" in c.control_keys for c in bundle.by_rule("github", rule))
