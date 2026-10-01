"""`grc`: run the compliance pipeline (scan, map, OSCAL, report) without the Makefile or an agent."""

from __future__ import annotations

import argparse
import subprocess
from datetime import UTC, datetime
from importlib.metadata import version
from importlib.resources import as_file
from pathlib import Path
from types import ModuleType

from okf_grc import data, manifest, map_findings, render_report, run_scan, to_oscal
from okf_grc.config import load_config

# Each step's own options pass through unchanged: `grc scan --target app` is `run_scan.py --target app`.
STEPS: dict[str, ModuleType] = {
    "scan": run_scan, "map": map_findings, "oscal": to_oscal, "report": render_report, "manifest": manifest,
}


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
    args = parser.parse_args(argv)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    config = load_config(Path.cwd(), Path(args.config) if args.config else None, target=args.target, knowledge=args.knowledge)
    stamp = ["--now", now, "--run-id", manifest.run_id(Path.cwd(), config, now)]
    common = [*_flag(args, "config"), "--out", args.out]
    layout = [*_flag(args, "knowledge"), *_flag(args, "target"), *common]
    STEPS["scan"].main([*_flag(args, "target"), *common])
    STEPS["map"].main(layout)
    STEPS["oscal"].main([*layout, *stamp])
    STEPS["report"].main([*_flag(args, "knowledge"), *common, "--now", now])
    STEPS["manifest"].main([*layout, *stamp])


def _flag(args: argparse.Namespace, name: str) -> list[str]:
    """`--name value` when the flag was given; passing nothing lets the config decide."""
    value = getattr(args, name)
    return [f"--{name}", value] if value is not None else []


def main(argv: list[str] | None = None) -> None:
    """Entry point of the `grc` command."""
    parser = argparse.ArgumentParser(prog="grc", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('okf-grc')}")
    parser.add_argument("command", choices=["bootstrap", "run", *STEPS], help="step to run")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="options for that step (see `grc <command> -h`)")
    args = parser.parse_args(argv)
    if args.command == "bootstrap":
        bootstrap()
    elif args.command == "run":
        run(args.args)
    else:
        STEPS[args.command].main(args.args)


if __name__ == "__main__":
    main()
