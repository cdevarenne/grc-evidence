"""Dependabot updates the engine's actions and Python lock only; never app/ or the scanner locks."""

from pathlib import Path

import yaml

CONFIG = yaml.safe_load((Path(__file__).parent.parent / ".github" / "dependabot.yml").read_text())


def test_updates_actions_and_uv_at_the_root_only() -> None:
    assert {(u["package-ecosystem"], u["directory"]) for u in CONFIG["updates"]} == {("github-actions", "/"), ("uv", "/")}
