"""A version tag releases only after every test passes and the tag equals the package version."""

import re
from pathlib import Path
from typing import Any

import yaml

WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "release.yml"


def _workflow() -> dict[Any, Any]:
    return yaml.safe_load(WORKFLOW.read_text())


def _steps() -> list[dict[str, Any]]:
    return _workflow()["jobs"]["release"]["steps"]


def test_runs_on_version_tags_only() -> None:
    wf = _workflow()
    assert wf.get("on", wf.get(True)) == {"push": {"tags": ["v*"]}}  # PyYAML reads a bare `on:` key as True


def test_only_the_job_can_write_and_only_contents() -> None:
    assert _workflow()["permissions"] == {}
    assert _workflow()["jobs"]["release"]["permissions"] == {"contents": "write"}


def test_actions_are_pinned_and_credentials_not_persisted() -> None:
    uses = re.findall(r"uses:\s*(\S+)", WORKFLOW.read_text())
    assert uses and all(re.search(r"@[0-9a-f]{40}$", action) for action in uses)
    (checkout,) = [s for s in _steps() if "actions/checkout" in s.get("uses", "")]
    assert checkout["with"]["persist-credentials"] is False


def test_no_dependency_cache_in_a_release() -> None:
    (setup,) = [s for s in _steps() if "setup-uv" in s.get("uses", "")]
    assert setup["with"]["enable-cache"] is False
    assert not [s for s in _steps() if "actions/cache" in s.get("uses", "")]


def test_checks_the_version_then_tests_then_releases() -> None:
    runs = [s["run"] for s in _steps() if "run" in s]
    assert runs[0] == 'test "$GITHUB_REF_NAME" = "v$(uv version --short)"'
    assert runs[1:4] == ["make bootstrap", "make test", "make test-integration"]
    assert runs[4].startswith('gh release create "$GITHUB_REF_NAME"') and "--verify-tag" in runs[4]


def test_no_expression_is_interpolated_into_a_shell_command() -> None:
    assert not [s["run"] for s in _steps() if "run" in s and "${{" in s["run"]]
