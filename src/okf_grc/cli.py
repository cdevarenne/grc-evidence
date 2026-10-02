"""`grc`: run the compliance pipeline (scan, map, OSCAL, report) without the Makefile or an agent."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from importlib.metadata import version
from importlib.resources import as_file
from pathlib import Path
from types import ModuleType

from okf_grc import (
    adopt,
    data,
    gate,
    manifest,
    map_findings,
    narrate,
    render_report,
    run_scan,
    to_oscal,
    triage,
)
from okf_grc.config import load_config

# Each step's own options pass through unchanged: `grc scan --target app` is `run_scan.py --target app`.
STEPS: dict[str, ModuleType] = {
    "scan": run_scan, "map": map_findings, "oscal": to_oscal, "report": render_report, "manifest": manifest,
    "triage": triage, "gate": gate,
}
COMMANDS = ("bootstrap", "init", "check", "sync-base", "run", "narrate", *STEPS)


def bootstrap() -> None:
    """Install the pinned scanners into ./.tools of the current directory."""
    with as_file(data.path("bootstrap.sh")) as script:
        subprocess.run(["bash", str(script)], cwd=Path.cwd(), check=True)


def run(argv: list[str]) -> None:
    """All steps over one target, as `make scan` runs them, ending with the run manifest."""
    parser = argparse.ArgumentParser(prog="grc run", description=run.__doc__)
    parser.add_argument("--config", help="scan layout (default: grc.yaml if present)")
    parser.add_argument("--target", help="scan target, relative to the repo root (overrides the config)")
    parser.add_argument("--knowledge", help="knowledge bundle (overrides the config)")
    parser.add_argument("--out", default="out")
    parser.add_argument("--require-clean", action="store_true", help="fail if the scan inputs differ from the commit (CI)")
    args = parser.parse_args(argv)
    repo, out = Path.cwd(), Path(args.out)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    config = load_config(repo, Path(args.config) if args.config else None, target=args.target, knowledge=args.knowledge)
    if args.require_clean and (problem := _unclean(manifest.repo_state(repo, manifest.scan_inputs(config), (out,)))):
        raise SystemExit(f"grc run --require-clean: {problem}")
    stamp = ["--now", now, "--run-id", manifest.run_id(repo, config, now)]
    # Steps write into a staging directory; out/ changes only once the manifest exists, so a failed run
    # leaves the previous run whole. The narratives and the LLM ledger are report inputs, not outputs.
    out.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".grc-run-", dir=out))
    try:
        for keep in ("narratives.json", "llm-usage.jsonl"):
            if (out / keep).is_file():
                shutil.copy2(out / keep, staging / keep)
        common = [*_flag(args, "config"), "--out", str(staging)]
        layout = [*_flag(args, "knowledge"), *_flag(args, "target"), *common]
        STEPS["scan"].main([*_flag(args, "target"), *common])
        STEPS["map"].main(layout)
        STEPS["oscal"].main([*layout, *stamp])
        STEPS["report"].main([*_flag(args, "knowledge"), *common, "--now", now])
        STEPS["manifest"].main([*layout, *stamp, "--exclude", str(out)])
        for rel in (*manifest.OUTPUTS, "run.json"):
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging / rel, out / rel)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _unclean(state: dict) -> str | None:
    """Why the scan inputs are not exactly a commit, or None when they are."""
    if state["commit"] is None:
        return "not a git repository"
    if not state["dirty"]:
        return None
    if untracked := state["untracked"]:
        more = f" and {len(untracked) - 5} more" if len(untracked) > 5 else ""
        return f"untracked scan inputs: {', '.join(untracked[:5])}{more}"
    return "tracked files differ from the commit"


def narrate_run(argv: list[str]) -> None:
    """LLM prose per control, validated; then the report, and the run manifest that hashes it, are rewritten."""
    parser = argparse.ArgumentParser(prog="grc narrate", description=narrate_run.__doc__)
    parser.add_argument("--config", help="scan layout (default: grc.yaml if present)")
    parser.add_argument("--knowledge", help="knowledge bundle (overrides the config)")
    parser.add_argument("--out", default="out")
    args = parser.parse_args(argv)
    config = load_config(Path.cwd(), Path(args.config) if args.config else None, knowledge=args.knowledge)
    common = [*_flag(args, "config"), *_flag(args, "knowledge"), "--out", args.out]
    narrate.main(["--knowledge", config.knowledge, "--out", args.out])
    run_json = Path(args.out) / "run.json"
    if not run_json.is_file():  # steps run one by one: there is no manifest to keep in step
        STEPS["report"].main(common)
        return
    run = json.loads(run_json.read_text(encoding="utf-8"))
    STEPS["report"].main([*common, "--now", run["generated"]])
    target = ["--target", run["config"]["resolved"]["target"]]  # the layout the run hashed, overrides included
    # The scan's inputs did not change: keep the repository state it recorded rather than reading the tree now.
    STEPS["manifest"].main([*common, *target, "--now", run["generated"], "--run-id", run["run_id"], "--keep-repository"])


def _flag(args: argparse.Namespace, name: str) -> list[str]:
    """`--name value` when the flag was given; passing nothing lets the config decide."""
    value = getattr(args, name)
    return [f"--{name}", value] if value is not None else []


def main(argv: list[str] | None = None) -> None:
    """Entry point of the `grc` command."""
    parser = argparse.ArgumentParser(prog="grc", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('okf-grc')}")
    parser.add_argument("command", choices=COMMANDS, help="step to run")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="options for that step (see `grc <command> -h`)")
    args = parser.parse_args(argv)
    if args.command == "bootstrap":
        bootstrap()
    elif args.command == "init":
        adopt.init_main(args.args)
    elif args.command == "check":
        adopt.check_main(args.args)
    elif args.command == "sync-base":
        adopt.sync_base_main(args.args)
    elif args.command == "narrate":
        narrate_run(args.args)
    elif args.command == "run":
        run(args.args)
    else:
        STEPS[args.command].main(args.args)


if __name__ == "__main__":
    main()
