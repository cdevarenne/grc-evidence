"""`grc`: one entry point for the pipeline; each step keeps its own options."""

import json
import os
import subprocess
from importlib.metadata import version
from pathlib import Path

import pytest

from okf_grc import cli, data, manifest

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


def _record_writing(monkeypatch: pytest.MonkeyPatch, fail_at: str | None = None) -> list[tuple[str, list[str]]]:
    """Fake steps that record their argv; `manifest` writes every output into its --out, as the real ones do."""
    calls: list[tuple[str, list[str]]] = []

    def step(name: str):
        def main(argv: list[str]) -> None:
            calls.append((name, argv))
            if name == fail_at:
                raise RuntimeError(f"{name} failed")
            if name == "manifest":
                staging = Path(argv[argv.index("--out") + 1])
                for rel in (*manifest.OUTPUTS, "run.json"):
                    (staging / rel).parent.mkdir(parents=True, exist_ok=True)
                    (staging / rel).write_text(f"new {rel}")
        return main

    for name, module in cli.STEPS.items():
        monkeypatch.setattr(module, "main", step(name))
    return calls


def test_run_calls_every_step_in_order_with_one_time_and_run_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = _record_writing(monkeypatch)
    out = tmp_path / "o"
    cli.main(["run", "--target", "app", "--knowledge", "knowledge", "--out", str(out)])
    steps = dict(calls)
    assert [name for name, _ in calls] == ["scan", "map", "oscal", "report", "manifest"]
    staging = steps["scan"][-1]
    assert Path(staging).parent == out and Path(staging).name.startswith(".grc-run-")
    layout = ["--knowledge", "knowledge", "--target", "app", "--out", staging]
    assert steps["scan"] == ["--target", "app", "--out", staging]
    assert steps["map"] == layout
    now, run_id = steps["oscal"][-3], steps["oscal"][-1]
    assert steps["oscal"] == [*layout, "--now", now, "--run-id", run_id]
    assert steps["manifest"] == [*layout, "--now", now, "--run-id", run_id, "--exclude", str(out)]
    assert steps["report"] == ["--knowledge", "knowledge", "--out", staging, "--now", now]
    assert (out / "run.json").read_text() == "new run.json" and not Path(staging).exists()


def test_a_failed_run_leaves_the_previous_outputs_untouched(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    out = tmp_path / "o"
    (out / "oscal").mkdir(parents=True)
    for rel in (*manifest.OUTPUTS, "run.json"):
        (out / rel).write_text(f"old {rel}")
    _record_writing(monkeypatch, fail_at="oscal")
    with pytest.raises(RuntimeError, match="oscal failed"):
        cli.main(["run", "--out", str(out)])
    assert all((out / rel).read_text() == f"old {rel}" for rel in (*manifest.OUTPUTS, "run.json"))
    assert not [p for p in out.iterdir() if p.name.startswith(".grc-run-")]


def test_run_hands_the_report_its_narratives_and_ledger(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    out = tmp_path / "o"
    out.mkdir()
    (out / "narratives.json").write_text("{}")
    seen: list[str] = []
    calls = _record_writing(monkeypatch)
    report = cli.STEPS["report"].main
    monkeypatch.setattr(cli.STEPS["report"], "main", lambda argv: (seen.extend(
        p.name for p in Path(argv[argv.index("--out") + 1]).iterdir()), report(argv)))
    cli.main(["run", "--out", str(out)])
    assert "narratives.json" in seen and calls


def test_require_clean_refuses_untracked_inputs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _git_repo(tmp_path)
    (tmp_path / "app" / "new.yaml").write_text("x: 1\n")
    monkeypatch.chdir(tmp_path)
    calls = _record_writing(monkeypatch)
    with pytest.raises(SystemExit, match="untracked scan inputs: app/new.yaml"):
        cli.main(["run", "--require-clean"])
    assert calls == []


def _git_repo(path: Path) -> None:
    (path / "app").mkdir()
    (path / "app" / "main.py").write_text("x = 1\n")
    (path / ".gitignore").write_text("out/\n")
    for argv in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "c"]):
        subprocess.run(["git", *argv], cwd=path, check=True)


def test_repo_state_lists_untracked_inputs_under_the_target_only(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    assert manifest.repo_state(tmp_path, "app") == {"commit": manifest._git(tmp_path, "rev-parse", "HEAD"), "dirty": False, "untracked": []}
    (tmp_path / "app" / "new file.yaml").write_text("x: 1\n")
    (tmp_path / "notes.txt").write_text("outside the target\n")
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "report.md").write_text("ignored\n")
    (tmp_path / "app" / "run").mkdir()
    (tmp_path / "app" / "run" / "x.json").write_text("{}\n")
    state = manifest.repo_state(tmp_path, "app", (tmp_path / "app" / "run",))
    assert state["dirty"] is True and state["untracked"] == ["app/new file.yaml"]


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


def _record_narrate(monkeypatch: pytest.MonkeyPatch, calls: list) -> None:
    monkeypatch.setattr(cli.narrate, "main", lambda argv: calls.append(("narrate", argv)))


def test_narrate_rewrites_the_report_and_the_manifest_with_the_run_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _record(monkeypatch)
    _record_narrate(monkeypatch, calls)
    run = {"run_id": "rid", "generated": "2026-10-01T12:00:00+00:00", "config": {"resolved": {"target": "svc"}}}
    (tmp_path / "run.json").write_text(json.dumps(run))
    cli.main(["narrate", "--out", str(tmp_path)])
    assert calls == [
        ("narrate", ["--knowledge", "knowledge", "--out", str(tmp_path)]),
        ("report", ["--out", str(tmp_path), "--now", run["generated"]]),
        ("manifest", ["--out", str(tmp_path), "--target", "svc", "--now", run["generated"], "--run-id", "rid", "--keep-repository"]),
    ]


def test_narrate_without_a_manifest_only_rewrites_the_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = _record(monkeypatch)
    _record_narrate(monkeypatch, calls)
    cli.main(["narrate", "--out", str(tmp_path)])
    assert [name for name, _ in calls] == ["narrate", "report"]


def test_triage_gets_its_own_options(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _record(monkeypatch)
    cli.main(["triage", "--batch", "--out", "o"])
    assert calls == [("triage", ["--batch", "--out", "o"])]
