"""`grc.yaml`: the scan layout, validated; no file means the v1.0 layout."""

import json
import os
import re
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from grc_evidence.config import Config, ConfigError, RepoSpec, load_config
from grc_evidence.run_scan import (
    ScanError,
    conftest_inputs,
    scan,
    scanner_runs,
    tools_not_run,
)


def _repo(tmp_path: Path, config: str | None = None) -> Path:
    if config is not None:
        (tmp_path / "grc.yaml").write_text(config, encoding="utf-8")
    return tmp_path


def _argv(runs: list, tool: str, title_word: str = "") -> tuple[str, ...]:
    (run,) = [r for r in runs if r.tool == tool and title_word in r.title]
    return run.argv


def test_defaults_are_the_v1_layout(tmp_path: Path) -> None:
    assert load_config(_repo(tmp_path)) == Config(
        target="app",
        knowledge="knowledge",
        inventory="ai-inventory.yaml",
        conftest_inputs=("k8s/**/*.yaml", "k8s/**/*.yml", "infra/**/*.tf", "ai-inventory.yaml"),
        checkov_frameworks=("terraform", "kubernetes", "dockerfile"),
        checkov_skip_paths=(),
        semgrep_configs=("policies/semgrep",),
        rego=("policies/rego",),
        scanner_timeout=900,
    )


def test_default_argv_is_unchanged_from_v1() -> None:
    runs = scanner_runs(Config(), ["app/k8s/deployment.yaml"])
    assert _argv(runs, "semgrep") == (
        "semgrep", "scan", "--config", "policies/semgrep", "--metrics=off", "--json", "--quiet", "app",
    )
    assert _argv(runs, "checkov") == (
        "checkov", "-d", ".", "--framework", "terraform", "kubernetes", "dockerfile", "-o", "json", "--quiet", "--compact",
    )
    assert _argv(runs, "conftest") == (
        "conftest", "test", "--all-namespaces", "--no-color", "-o", "json", "-p", "policies/rego", "app/k8s/deployment.yaml",
    )


def test_file_overrides_defaults_and_flags_override_the_file(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "target: svc\nknowledge: kb\nsemgrep:\n  configs: [rules/a, rules/b]\n")
    config = load_config(repo)
    assert (config.target, config.knowledge, config.semgrep_configs) == ("svc", "kb", ("rules/a", "rules/b"))
    assert config.rego == ("policies/rego",)
    assert load_config(repo, target="other", knowledge=None).target == "other"


def test_an_explicit_config_file_must_exist(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="no such config file"):
        load_config(tmp_path, Path("missing.yaml"))


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("targt: app\n", "unknown key 'targt'"),
        ("checkov:\n  skip: [x]\n", "unknown key 'checkov.skip'"),
        ("rego: policies/rego\n", "'rego' must be a list of strings"),
        ("conftest:\n  inputs: [1]\n", "'conftest.inputs' must be a list of strings"),
        ("target: [app]\n", "'target' must be a string"),
        ("checkov: [terraform]\n", "checkov must be a mapping"),
        ("- app\n", "grc.yaml must be a mapping"),
        ("semgrep:\n  configs: [--dangerous]\n", "'semgrep.configs': a value may not start with '-'"),
        ("target: ../elsewhere\n", "target '../elsewhere' leaves the repo root"),
        ("rego: [../rules]\n", "rego '../rules' leaves the repo root"),
        ("conftest:\n  inputs: ['/etc/*.yaml']\n", "conftest.inputs '/etc/\\*.yaml' must be relative to the target"),
        ("allow_external_symlinks: 'yes'\n", "'allow_external_symlinks' must be true or false"),
        ("skip_paths: [../up]\n", "skip_paths '../up' must stay under the target"),
        ("checkov:\n  skip_paths: [/etc]\n", "checkov.skip_paths '/etc' must stay under the target"),
        ("scanner_timeout: '60'\n", "'scanner_timeout' must be a positive whole number of seconds"),
        ("scanner_timeout: true\n", "'scanner_timeout' must be a positive whole number of seconds"),
        ("scanner_timeout: 0\n", "'scanner_timeout' must be a positive whole number of seconds"),
    ],
)
def test_malformed_configs_are_rejected(tmp_path: Path, text: str, error: str) -> None:
    with pytest.raises(ConfigError, match=error):
        load_config(_repo(tmp_path, text))


def test_flags_are_validated_like_the_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="leaves the repo root"):
        load_config(tmp_path, target="../elsewhere")


def test_a_custom_layout_drives_every_scanner(tmp_path: Path) -> None:
    for rel in ("deploy/api.yaml", "deploy/web.yaml", "terraform/main.tf", "helm-chart/values.yaml"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("x\n", encoding="utf-8")
    config = load_config(_repo(tmp_path, (
        "target: .\n"
        "conftest:\n  inputs: ['deploy/*.yaml', 'deploy/api.yaml', 'terraform/*.tf']\n"
        "checkov:\n  frameworks: [terraform, kubernetes]\n  skip_paths: [helm-chart]\n"
        "semgrep:\n  configs: [rules/python, rules/ai]\n"
        "rego: [policies/rego, local/rego]\n"
    )))
    inputs = conftest_inputs(tmp_path, config)
    assert inputs == ["deploy/api.yaml", "deploy/web.yaml", "terraform/main.tf"]  # overlapping globs, one entry each
    runs = scanner_runs(config, inputs)
    assert _argv(runs, "semgrep")[2:6] == ("--config", "rules/python", "--config", "rules/ai")
    assert _argv(runs, "checkov")[3:8] == ("--framework", "terraform", "kubernetes", "--skip-path", "helm-chart")
    assert _argv(runs, "conftest")[6:] == ("-p", "policies/rego", "-p", "local/rego", *inputs)


def test_scan_refuses_policy_paths_that_do_not_exist(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    with pytest.raises(ScanError, match=r"semgrep.configs: \['p/python'\] do not exist"):
        scan(tmp_path, Config(semgrep_configs=("p/python",)))


@pytest.mark.integration
def test_real_scanners_honor_a_custom_layout(tmp_path: Path) -> None:
    """Checkov skips the skipped path and Conftest reads only the configured inputs."""
    root = Path(__file__).parent.parent
    config = tmp_path / "grc.yaml"
    config.write_text("checkov:\n  skip_paths: [Dockerfile]\nconftest:\n  inputs: ['k8s/*.yaml']\n", encoding="utf-8")
    env = os.environ | {"PATH": f"{root / '.tools' / 'bin'}{os.pathsep}{os.environ['PATH']}",
                        "TRIVY_CACHE_DIR": str(root / ".tools" / "trivy-cache")}
    subprocess.run(["uv", "run", "grc", "scan", "--config", str(config), "--out", str(tmp_path)], cwd=root, env=env, check=True)
    findings = json.loads((tmp_path / "findings.json").read_text())["findings"]
    by_tool = {tool: {f["target"] for f in findings if f["tool"] == tool} for tool in ("checkov", "conftest")}
    assert by_tool["checkov"] and "app/Dockerfile" not in by_tool["checkov"]
    assert by_tool["conftest"] and all(t.startswith("app/k8s/") for t in by_tool["conftest"])


def _beside_layout(tmp_path: Path) -> Path:
    """A repo whose target is a vendored directory; the inventory sits beside it, as for a submodule."""
    (tmp_path / "upstream" / "k8s").mkdir(parents=True)
    (tmp_path / "upstream" / "k8s" / "app.yaml").write_text("kind: Deployment\n")
    (tmp_path / "ai-inventory.yaml").write_text("systems: []\n")
    return tmp_path


def test_conftest_reads_an_input_beside_the_target(tmp_path: Path) -> None:
    repo = _beside_layout(tmp_path)
    config = Config(target="upstream", conftest_inputs=("k8s/*.yaml", "../ai-inventory.yaml"))
    assert conftest_inputs(repo, config) == ["ai-inventory.yaml", "upstream/k8s/app.yaml"]


def test_conftest_inputs_may_not_leave_the_repo(tmp_path: Path) -> None:
    repo = _beside_layout(tmp_path / "repo")
    (tmp_path / "secret.yaml").write_text("x: 1\n")
    with pytest.raises(ScanError, match="outside the repo"):
        conftest_inputs(repo, Config(target="upstream", conftest_inputs=("../../secret.yaml",)))


def test_a_symlink_out_of_the_repo_needs_the_opt_in(tmp_path: Path) -> None:
    """#70: adopter repos are trusted, but a symlink out of the repo is accepted only on request."""
    repo = _beside_layout(tmp_path / "repo")
    (tmp_path / "outside.yaml").write_text("x: 1\n")
    (repo / "upstream" / "k8s" / "link.yaml").symlink_to(tmp_path / "outside.yaml")
    with pytest.raises(ScanError, match="upstream/k8s/link.yaml is a symlink out of the repo"):
        conftest_inputs(repo, Config(target="upstream", conftest_inputs=("k8s/*.yaml",)))
    allowed = Config(target="upstream", conftest_inputs=("k8s/*.yaml",), allow_external_symlinks=True)
    assert conftest_inputs(repo, allowed) == ["upstream/k8s/app.yaml", "upstream/k8s/link.yaml"]


def test_skip_paths_apply_to_trivy_and_checkov(tmp_path: Path) -> None:
    """E3: templated or duplicate directories (a Helm chart, release bundles) are skipped by both IaC scanners."""
    config = load_config(_repo(tmp_path, "skip_paths: [helm-chart, release]\ncheckov:\n  skip_paths: [docs]\n"))
    runs = scanner_runs(config, ["app/k8s/a.yaml"])
    for word in ("config", "fs"):
        argv = _argv(runs, "trivy", "misconfiguration" if word == "config" else "dependency")
        assert argv[argv.index("--skip-dirs"):][:4] == ("--skip-dirs", "helm-chart", "--skip-dirs", "release")
    checkov = _argv(runs, "checkov")
    assert [checkov[i + 1] for i, a in enumerate(checkov) if a == "--skip-path"] == ["helm-chart", "release", "docs"]


def test_an_explicit_empty_conftest_inputs_skips_conftest(tmp_path: Path) -> None:
    """#71: `conftest.inputs: []` turns Conftest off; patterns that match nothing are still an error."""
    config = load_config(_repo(tmp_path, "conftest:\n  inputs: []\n"))
    assert config.conftest_inputs == () and tools_not_run(config) == ["conftest"]
    assert conftest_inputs(tmp_path, config) == []
    assert [r.tool for r in scanner_runs(config, [])] == ["semgrep", "trivy", "trivy", "checkov"]
    with pytest.raises(ScanError, match="conftest.inputs"):
        conftest_inputs(tmp_path, Config(conftest_inputs=("k8s/*.yaml",)))


WINDOW = "window: {start: 2026-06-01, end: 2026-08-31}\n"


def test_github_repos_from_yaml(tmp_path: Path) -> None:
    repo = _repo(tmp_path, WINDOW + "github:\n  repos:\n    - {name: acme/api, tier: in-scope, collect: [scm, changes]}\n")
    c = load_config(repo)
    assert c.github_repos == (RepoSpec("acme/api", "in-scope", ("scm", "changes")),)
    assert (c.window_start, c.window_end, c.window_max_gap_days) == (date(2026, 6, 1), date(2026, 8, 31), 7)
    assert c.bounds() == (datetime(2026, 6, 1, tzinfo=UTC), datetime(2026, 9, 1, tzinfo=UTC))


def test_evidence_settings_from_yaml(tmp_path: Path) -> None:
    c = load_config(_repo(tmp_path, (
        "window: {start: '2026-06-01', end: '2026-08-31', max_gap_days: 3}\n"
        "ledger: audit/ledger.jsonl\npeople: pseudonymous\npeople_salt_env: DEMO_SALT\n"
        "github:\n  branches: [release]\n  scanner_jobs: [semgrep, trivy]\n"
        "  repos:\n    - {name: acme/lib, tier: library}\n"
    )))
    assert (c.window_start, c.window_max_gap_days, c.ledger) == (date(2026, 6, 1), 3, "audit/ledger.jsonl")
    assert (c.people, c.people_salt_env) == ("pseudonymous", "DEMO_SALT")
    assert (c.github_branches, c.github_scanner_jobs) == (("release",), ("semgrep", "trivy"))
    assert c.github_repos == (RepoSpec("acme/lib", "library", ()),)


def test_repos_file_joins_the_repo_list(tmp_path: Path) -> None:
    (tmp_path / "repos.yaml").write_text("- {name: acme/web, tier: dormant}\n")
    c = load_config(_repo(tmp_path, "github:\n  repos_file: repos.yaml\n  repos:\n    - {name: acme/api, tier: in-scope}\n"))
    assert [r.name for r in c.github_repos] == ["acme/api", "acme/web"]


def test_no_window_has_no_bounds(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="no window in grc.yaml"):
        load_config(_repo(tmp_path)).bounds()


@pytest.mark.parametrize(("yaml_text", "key"), [
    ("window: {start: 2026-08-31, end: 2026-06-01}\n", "window.end"),
    ("window: {start: 2026-06-01}\n", "window.end"),
    ("window: {start: 2026-06-01, end: 2026-08-31, max_gap_days: 0}\n", "window.max_gap_days"),
    ("window: {start: June, end: 2026-08-31}\n", "window.start"),
    ("github:\n  repos:\n    - {name: acme/api, tier: prod}\n", "github.repos[0].tier"),
    ("github:\n  repos:\n    - {name: acme/api, tier: in-scope, collect: [scan]}\n", "github.repos[0].collect"),
    ("github:\n  repos:\n    - {name: acme/api, tier: in-scope}\n    - {name: Acme/API, tier: library}\n", "github.repos[1].name"),
    ("github:\n  repos:\n    - {name: api, tier: in-scope}\n", "github.repos[0].name"),
    ("github:\n  repos:\n    - {name: acme/api, tier: in-scope, owner: me}\n", "github.repos[0]"),
    ("github:\n  colour: blue\n", "github.colour"),
    ("people: anonymous\n", "people"),
    ("people_salt_env: 'my salt'\n", "people_salt_env"),
    ("ledger: ../ledger.jsonl\n", "ledger"),
    ("github:\n  repos_file: ../repos.yaml\n", "github.repos_file"),
])
def test_evidence_settings_are_checked(tmp_path: Path, yaml_text: str, key: str) -> None:
    with pytest.raises(ConfigError, match=re.escape(key)):
        load_config(_repo(tmp_path, yaml_text))
