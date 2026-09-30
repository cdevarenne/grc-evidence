"""`grc.yaml`: the scan layout, validated; no file means the v1.0 layout."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from okf_grc.config import Config, ConfigError, load_config
from okf_grc.run_scan import ScanError, conftest_inputs, scan, scanner_runs


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
        ("conftest:\n  inputs: ['../x/*.yaml']\n", "conftest.inputs '../x/\\*.yaml' must stay under the target"),
        ("checkov:\n  skip_paths: [/etc]\n", "checkov.skip_paths '/etc' must stay under the target"),
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
    findings = json.loads((tmp_path / "findings.json").read_text())
    by_tool = {tool: {f["target"] for f in findings if f["tool"] == tool} for tool in ("checkov", "conftest")}
    assert by_tool["checkov"] and "app/Dockerfile" not in by_tool["checkov"]
    assert by_tool["conftest"] and all(t.startswith("app/k8s/") for t in by_tool["conftest"])
