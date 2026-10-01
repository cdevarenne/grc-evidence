"""`grc init` sets up a repo from the base bundle; `grc check` reports drift from it and unreviewed concepts."""

import json
import os
import shutil
import subprocess
from importlib.metadata import version
from pathlib import Path

import pytest
import yaml

from okf_grc import adopt, cli, data
from okf_grc.config import Config, load_config
from okf_grc.map_findings import load_context
from okf_grc.okf_lib import load_bundle

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
    assert index == {"okf_version": "0.2", "base_version": version("okf-grc")}
    stubs = {c.id: c for c in load_bundle(repo / "knowledge").concepts.values() if c.id.startswith("stack/")}
    assert sorted(stubs) == ["stack/cart", "stack/web"]
    assert stubs["stack/cart"].frontmatter["resource"] == "../../src/cart/"
    assert load_config(repo) == Config(target=".")
    assert load_context(repo / "ai-inventory.yaml") == {}  # risk tier left to a person: every control is assessed


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
    index.write_text(index.read_text().replace(f'base_version: "{version("okf-grc")}"', 'base_version: "1.0.0"'))
    assert adopt.check(tmp_path, load_config(tmp_path)) == [
        f"knowledge/index.md: base_version '1.0.0', installed engine '{version('okf-grc')}'",
        f"knowledge/controls/cc6.1.md: differs from base {version('okf-grc')}",
        f"policies/rego/deny_latest_tag.rego: missing (base {version('okf-grc')})",
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
    env = os.environ | {"PATH": f"{ROOT / '.tools' / 'bin'}{os.pathsep}{os.environ['PATH']}",
                        "TRIVY_CACHE_DIR": str(ROOT / ".tools" / "trivy-cache")}
    grc = ["uv", "run", "--project", str(ROOT), "grc"]
    subprocess.run([*grc, "init"], cwd=tmp_path, env=env, check=True, capture_output=True)
    subprocess.run([*grc, "check"], cwd=tmp_path, env=env, check=True, capture_output=True)
    subprocess.run([*grc, "run"], cwd=tmp_path, env=env, check=True, capture_output=True)
    mapping = json.loads((tmp_path / "out/mapping.json").read_text())
    assert mapping["controls"]["soc2:cc6.1"]["status"] == "not-satisfied"  # the manifest runs as root
    assert json.loads((tmp_path / "out/run.json").read_text())["base_version"] == version("okf-grc")
