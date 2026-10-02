"""make audit: the engine's own dependencies and workflows, with reviewed, expiring exceptions only."""

import re
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
IGNORES = yaml.safe_load((ROOT / "audit-ignore.yaml").read_text())["vulnerabilities"]


def _recipe() -> str:
    makefile = (ROOT / "Makefile").read_text()
    match = re.search(r"^audit:\n((?:\t.*\n|  .*\n)+)", makefile, re.MULTILINE)
    assert match is not None
    return match.group(1)


def test_audit_fails_on_fixable_high_and_critical_and_skips_the_sample_app() -> None:
    recipe = _recipe()
    for flag in ("--ignore-unfixed", "--severity HIGH,CRITICAL", "--exit-code 1", "--ignorefile audit-ignore.yaml", "--skip-dirs app"):
        assert flag in recipe, flag
    assert "zizmor --no-progress .github\n" in recipe  # workflows and dependabot.yml (#105)


def test_each_exception_is_exact_explained_and_expiring() -> None:
    for entry in IGNORES:
        assert re.fullmatch(r"CVE-\d{4}-\d+", entry["id"])
        assert entry["paths"] and all(p.startswith("src/okf_grc/data/locks/") for p in entry["paths"])
        assert entry["statement"].strip()
        assert isinstance(entry["expired_at"], date)
