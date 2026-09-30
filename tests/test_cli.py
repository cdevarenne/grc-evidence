"""`grc`: one entry point for the pipeline; each step keeps its own options."""

import json
import os
import subprocess
from importlib.metadata import version
from pathlib import Path

import pytest

from okf_grc import cli, data

ROOT = Path(__file__).parent.parent


def _record(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[str] | None]]:
    calls: list[tuple[str, list[str] | None]] = []
    for name, module in cli.STEPS.items():
        monkeypatch.setattr(module, "main", lambda argv, name=name: calls.append((name, argv)))
    return calls


def test_version_is_the_package_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert capsys.readouterr().out.strip() == f"grc {version('okf-grc')}"


def test_unknown_command_is_rejected() -> None:
    with pytest.raises(SystemExit):
        cli.main(["deploy"])


def test_a_step_gets_its_own_options(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _record(monkeypatch)
    cli.main(["scan", "--target", "svc", "--out", "o"])
    assert calls == [("scan", ["--target", "svc", "--out", "o"])]


def test_run_calls_the_four_steps_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _record(monkeypatch)
    cli.main(["run", "--target", "svc", "--knowledge", "kb", "--out", "o"])
    assert calls == [
        ("scan", ["--target", "svc", "--out", "o"]),
        ("map", ["--knowledge", "kb", "--target", "svc", "--out", "o"]),
        ("oscal", ["--knowledge", "kb", "--target", "svc", "--out", "o"]),
        ("report", ["--knowledge", "kb", "--out", "o"]),
    ]


def test_packaged_data_is_found() -> None:
    assert "TRIVY_VERSION=" in data.path("tools.lock").read_text()
    assert 'source "$(dirname "$0")/tools.lock"' in data.path("bootstrap.sh").read_text()


def test_bootstrap_runs_the_packaged_script_in_the_current_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ran: list[tuple[list[str], Path]] = []
    monkeypatch.setattr(cli.subprocess, "run", lambda argv, cwd, check: ran.append((argv, cwd)))
    monkeypatch.chdir(tmp_path)
    cli.main(["bootstrap"])
    ((argv, cwd),) = ran
    assert argv[0] == "bash" and argv[1].endswith("bootstrap.sh") and cwd == tmp_path


@pytest.mark.integration
def test_installed_tool_runs_the_pipeline(tmp_path: Path) -> None:
    """Install the package as a tool, as an adopter would, and scan this repo with it."""
    env = os.environ | {"UV_TOOL_DIR": str(tmp_path / "tools"), "UV_TOOL_BIN_DIR": str(tmp_path / "bin")}
    subprocess.run(["uv", "tool", "install", "--quiet", str(ROOT)], env=env, check=True)
    grc = tmp_path / "bin" / "grc"
    assert subprocess.run([grc, "--version"], capture_output=True, text=True, check=True).stdout.strip() == "grc 1.1.0"
    env["PATH"] = f"{ROOT / '.tools' / 'bin'}{os.pathsep}{env['PATH']}"
    env["TRIVY_CACHE_DIR"] = str(ROOT / ".tools" / "trivy-cache")
    out = tmp_path / "out"
    subprocess.run([grc, "run", "--target", "app", "--out", str(out)], cwd=ROOT, env=env, check=True)
    assert json.loads((out / "mapping.json").read_text())["controls"]["soc2:cc6.1"]["status"] == "not-satisfied"
