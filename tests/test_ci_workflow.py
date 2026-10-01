"""CI runs every test on each push to main and each pull request, with pinned actions and a read-only token."""

import re
from pathlib import Path
from typing import Any

import yaml

WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml"


def _workflow() -> dict[Any, Any]:
    return yaml.safe_load(WORKFLOW.read_text())


def test_runs_on_pushes_to_main_and_pull_requests() -> None:
    wf = _workflow()
    triggers = wf.get("on", wf.get(True))  # PyYAML reads a bare `on:` key as True
    assert set(triggers) == {"push", "pull_request"}
    assert triggers["push"] == {"branches": ["main"]}


def test_actions_are_pinned_to_commits() -> None:
    uses = re.findall(r"uses:\s*(\S+)", WORKFLOW.read_text())
    assert uses and all(re.search(r"@[0-9a-f]{40}$", action) for action in uses)


def test_token_is_read_only() -> None:
    assert _workflow()["permissions"] == {"contents": "read"}


def test_runs_bootstrap_then_unit_then_integration_tests() -> None:
    steps = [s["run"] for s in _workflow()["jobs"]["test"]["steps"] if "run" in s and "GITHUB_OUTPUT" not in s["run"]]
    assert steps == ["make bootstrap", "make audit", "make test", "make test-integration"]


def test_trivy_database_cache_is_keyed_on_the_pins_and_the_day() -> None:
    (cache,) = [s for s in _workflow()["jobs"]["test"]["steps"] if "actions/cache" in s.get("uses", "")]
    assert cache["with"]["path"] == ".tools/trivy-cache"
    assert "hashFiles('src/okf_grc/data/tools.lock')" in cache["with"]["key"] and "steps.day.outputs.day" in cache["with"]["key"]


def test_checkout_does_not_persist_credentials() -> None:
    (checkout,) = [s for s in _workflow()["jobs"]["test"]["steps"] if "actions/checkout" in s.get("uses", "")]
    assert checkout["with"]["persist-credentials"] is False


def test_job_has_a_timeout() -> None:
    assert _workflow()["jobs"]["test"]["timeout-minutes"] == 30
