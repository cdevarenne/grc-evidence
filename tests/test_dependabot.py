"""Dependabot updates the engine's actions and Python lock only; never app/ or the scanner locks."""

from pathlib import Path

import yaml

CONFIG = yaml.safe_load((Path(__file__).parent.parent / ".github" / "dependabot.yml").read_text())


def test_updates_actions_and_uv_at_the_root_only() -> None:
    assert {(u["package-ecosystem"], u["directory"]) for u in CONFIG["updates"]} == {("github-actions", "/"), ("uv", "/")}


def test_python_updates_never_touch_the_sample_app_or_the_scanner_locks() -> None:
    """The uv ecosystem also finds app/requirements.txt; its old versions are seeded issues (PR #74 bumped them)."""
    (uv,) = [u for u in CONFIG["updates"] if u["package-ecosystem"] == "uv"]
    assert set(uv["exclude-paths"]) >= {"app/**", "src/okf_grc/data/locks/**"}
