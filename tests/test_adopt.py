"""`grc init` sets up a repo from the base bundle; `grc check` reports drift from it and unreviewed concepts."""

import json
import os
import shutil
import subprocess
from datetime import date
from importlib.metadata import version
from pathlib import Path

import pytest
import yaml

from grc_evidence import adopt, cli, data
from grc_evidence.config import Config, load_config
from grc_evidence.map_findings import load_context
from grc_evidence.okf_lib import load_bundle

ROOT = Path(__file__).parent.parent
BASE = Path(str(data.path("base")))


def _repo(tmp_path: Path, *components: str) -> Path:
    for name in components:
        (tmp_path / "src" / name).mkdir(parents=True)
    return tmp_path


def test_init_copies_the_base_and_writes_starters(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "cart", "web")
    written = adopt.init(repo)
    assert Path("grc.yaml") in written and Path("ai-inventory.yaml") in written
    assert (repo / "knowledge/controls/cc6.1.md").read_bytes() == (BASE / "controls/cc6.1.md").read_bytes()
    assert (repo / "policies/rego/require_non_root.rego").is_file()
    index = yaml.safe_load((repo / "knowledge/index.md").read_text().split("---\n")[1])
    assert index == {"okf_version": "0.2", "base_version": version("grc-evidence")}
    stubs = {c.id: c for c in load_bundle(repo / "knowledge").concepts.values() if c.id.startswith("stack/")}
    assert sorted(stubs) == ["stack/cart", "stack/web"]
    assert stubs["stack/cart"].frontmatter["resource"] == "../../src/cart/"
    assert load_config(repo) == Config(target=".")
    assert load_context(repo / "ai-inventory.yaml") == {}  # risk tier left to a person: every control is assessed


def test_init_ignores_tools_and_outputs_in_git(tmp_path: Path) -> None:
    assert Path(".gitignore") in adopt.init(tmp_path)
    assert (tmp_path / ".gitignore").read_text() == ".tools/\nout/\n"


def test_init_appends_only_missing_ignore_entries(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("node_modules/\nout/", encoding="utf-8")  # no trailing newline
    adopt.init(tmp_path)
    assert (tmp_path / ".gitignore").read_text() == "node_modules/\nout/\n.tools/\n"


def test_init_refuses_and_writes_nothing_when_a_file_exists(tmp_path: Path) -> None:
    (tmp_path / "grc.yaml").write_text("target: .\n")
    with pytest.raises(FileExistsError, match="writes nothing: 1 file"):
        adopt.init(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["grc.yaml"]


def test_check_flags_only_the_unreviewed_stubs_after_init(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "cart")
    adopt.init(repo)
    assert adopt.check(repo, load_config(repo)) == ["knowledge/stack/cart.md: not verified by a person"]


def test_check_passes_on_this_repo() -> None:
    assert adopt.check(ROOT, load_config(ROOT)) == []


def test_check_reports_drift(tmp_path: Path) -> None:
    adopt.init(tmp_path)
    concept = tmp_path / "knowledge/controls/cc6.1.md"
    concept.write_text(concept.read_text() + "A local edit.\n")
    (tmp_path / "policies/rego/deny_latest_tag.rego").unlink()
    index = tmp_path / "knowledge/index.md"
    index.write_text(index.read_text().replace(f'base_version: "{version("grc-evidence")}"', 'base_version: "1.0.0"'))
    assert adopt.check(tmp_path, load_config(tmp_path)) == [
        f"knowledge/index.md: base_version '1.0.0', installed engine '{version('grc-evidence')}'",
        f"knowledge/controls/cc6.1.md: differs from base {version('grc-evidence')}",
        f"policies/rego/deny_latest_tag.rego: missing (base {version('grc-evidence')})",
    ]


def test_sync_base_restores_the_base_and_reports_each_change(tmp_path: Path) -> None:
    """#86: drifted and missing copies are rewritten, base_version updated, a differing index kept for a person."""
    adopt.init(tmp_path)
    concept = tmp_path / "knowledge/controls/cc6.1.md"
    concept.write_text(concept.read_text() + "A local edit.\n")
    (tmp_path / "policies/rego/deny_latest_tag.rego").unlink()
    policies_index = tmp_path / "knowledge/policies/index.md"
    policies_index.write_text(policies_index.read_text() + "* [Local](local.md)\n")
    controls_index = tmp_path / "knowledge/controls/index.md"
    controls_index.write_text(controls_index.read_text().split("\n* ")[0] + "\n")  # an older base: fewer entries
    index = tmp_path / "knowledge/index.md"
    index.write_text(index.read_text().replace(f'base_version: "{version("grc-evidence")}"', 'base_version: "1.0.0"  # a note'))
    config = load_config(tmp_path)
    assert adopt.sync_base(tmp_path, config) == [
        "updated knowledge/controls/cc6.1.md",
        "updated knowledge/controls/index.md",
        f"kept knowledge/policies/index.md: differs from base {version('grc-evidence')}; merge its new entries by hand",
        "added policies/rego/deny_latest_tag.rego",
        f"updated knowledge/index.md: base_version {version('grc-evidence')}",
    ]
    assert policies_index.read_text().endswith("* [Local](local.md)\n")
    assert f'base_version: "{version("grc-evidence")}"  # a note\n' in index.read_text()
    assert adopt.check(tmp_path, config) == []
    assert adopt.sync_base(tmp_path, config) == [
        f"kept knowledge/policies/index.md: differs from base {version('grc-evidence')}; merge its new entries by hand"
    ]


def test_check_reports_a_malformed_concept_instead_of_crashing(tmp_path: Path) -> None:
    adopt.init(tmp_path)
    (tmp_path / "knowledge/stack/broken.md").write_text("no frontmatter\n")
    assert adopt.check(tmp_path, load_config(tmp_path)) == ["knowledge/stack/broken.md: missing YAML frontmatter"]


def test_cli_init_reports_a_conflict_without_a_traceback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "grc.yaml").write_text("target: .\n")
    with pytest.raises(SystemExit, match="grc init writes nothing"):
        cli.main(["init"])


def test_cli_check_exits_nonzero_on_problems(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(_repo(tmp_path, "cart"))
    cli.main(["init"])
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["check"])
    assert exit_info.value.code == 1


@pytest.mark.integration
def test_a_new_repo_goes_from_init_to_a_scan(tmp_path: Path) -> None:
    """The adopter path: a repo with only a Kubernetes manifest, `grc init`, then `grc run`."""
    (tmp_path / "k8s").mkdir()
    shutil.copy(ROOT / "app/k8s/deployment.yaml", tmp_path / "k8s/deployment.yaml")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    # No scanner on PATH: grc must find them in ./.tools itself (#59). The Makefile exports .tools/bin, so drop it.
    scanners = ("semgrep", "trivy", "checkov", "conftest")
    path = [p for p in os.environ["PATH"].split(os.pathsep) if not any((Path(p) / s).exists() for s in scanners)]
    env = os.environ | {"PATH": os.pathsep.join(path)}
    env.pop("TRIVY_CACHE_DIR", None)
    grc = ["uv", "run", "--project", str(ROOT), "grc"]
    subprocess.run([*grc, "init"], cwd=tmp_path, env=env, check=True, capture_output=True)
    (tmp_path / ".tools").symlink_to(ROOT / ".tools")  # stands in for `grc bootstrap`
    subprocess.run([*grc, "check"], cwd=tmp_path, env=env, check=True, capture_output=True)
    subprocess.run([*grc, "run"], cwd=tmp_path, env=env, check=True, capture_output=True)
    mapping = json.loads((tmp_path / "out/mapping.json").read_text())
    assert mapping["controls"]["soc2:cc6.1"]["status"] == "not-satisfied"  # the manifest runs as root
    assert json.loads((tmp_path / "out/run.json").read_text())["base_version"] == version("grc-evidence")


def test_init_never_writes_into_a_submodule(tmp_path: Path) -> None:
    """E2: a target with its own .git (a submodule) gets nothing written into it; the inventory goes beside it."""
    (tmp_path / "upstream" / "src" / "cart").mkdir(parents=True)
    (tmp_path / "upstream" / ".git").write_text("gitdir: ../.git/modules/upstream\n")
    before = sorted(p.relative_to(tmp_path) for p in (tmp_path / "upstream").rglob("*"))
    written = adopt.init(tmp_path, "upstream")
    assert sorted(p.relative_to(tmp_path) for p in (tmp_path / "upstream").rglob("*")) == before
    assert Path("ai-inventory.yaml") in written and not any(str(p).startswith("upstream") for p in written)
    config = load_config(tmp_path)
    assert config.inventory == "../ai-inventory.yaml" and "../ai-inventory.yaml" in config.conftest_inputs
    assert "stack/cart" in load_bundle(tmp_path / "knowledge").concepts


def test_starter_inventory_documents_the_path_that_ties_a_system_to_its_component() -> None:
    """ai_inventory_complete matches a system to its assistant component by `path`; the starter must say so."""
    assert "path (its component's)" in adopt.INVENTORY


def test_the_skill_installs_and_then_syncs_like_the_base(tmp_path: Path) -> None:
    """#106: no skill is fine; once installed, check reports drift and sync-base restores it."""
    adopt.init(tmp_path)
    (tmp_path / "knowledge/stack/index.md").write_text("# Stack\n")
    config = load_config(tmp_path)
    assert adopt.check(tmp_path, config) == [] and adopt.sync_base(tmp_path, config) == []
    assert adopt.install_skill(tmp_path).startswith("added .claude/skills/grc-continuous-compliance/SKILL.md")
    assert adopt.install_skill(tmp_path).startswith("ok: ")
    skill = tmp_path / adopt.SKILL
    assert skill.read_bytes() == (Path(str(data.path("skill"))) / "SKILL.md").read_bytes()
    skill.write_text(skill.read_text() + "A local edit.\n")
    assert adopt.check(tmp_path, config) == [f".claude/skills/grc-continuous-compliance/SKILL.md: differs from base {version('grc-evidence')}"]
    assert adopt.sync_base(tmp_path, config) == ["updated .claude/skills/grc-continuous-compliance/SKILL.md"]
    assert adopt.check(tmp_path, config) == []


def test_cli_installs_the_skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    cli.main(["install-skill"])
    assert "added .claude/skills/grc-continuous-compliance/SKILL.md" in capsys.readouterr().out


def test_check_warns_before_a_review_is_due_and_fails_after(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                            capsys: pytest.CaptureFixture[str]) -> None:
    """Spec J: a local concept due soon is a warning; overdue, grc check fails. Base copies only warn in an adopter."""
    adopt.init(tmp_path)
    for stub in (tmp_path / "knowledge/stack").glob("*.md"):
        if stub.name != "index.md":
            stub.unlink()
    (tmp_path / "knowledge/stack/app.md").write_text(
        '---\ntype: Stack Component\ntitle: App\ndescription: d\ntags: [app]\n'
        'verified:\n  - by: "human:r"\n    at: "2026-09-29T10:00:00-07:00"\n---\n# App\n')
    review = "review:\n  default: 1y\n  by_type:\n    Stack Component: 90d\n    Crosswalk: 1d\n"
    (tmp_path / "grc.yaml").write_text((tmp_path / "grc.yaml").read_text() + review)
    config = load_config(tmp_path)
    problems, warnings = adopt.check_report(tmp_path, config, date(2026, 12, 1))
    assert "knowledge/stack/app.md: review due 2026-12-28" in warnings and problems == []
    assert any("crosswalk" in w and "overdue in the engine" in w for w in warnings)  # base copies: 1d is long past
    assert adopt.check(tmp_path, config, date(2026, 12, 29)) == ["knowledge/stack/app.md: review due 2026-12-28: verify it again"]
    monkeypatch.chdir(tmp_path)
    adopt.check_main([])  # today: no problem, so no exit; the overdue base crosswalks are printed as warnings
    out = capsys.readouterr().out
    assert "warning: knowledge/crosswalk/" in out and "overdue in the engine" in out and out.rstrip().endswith("review date")
