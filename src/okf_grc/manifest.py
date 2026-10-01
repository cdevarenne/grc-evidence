"""Write `out/run.json`: what produced a run's outputs, and the sha256 of each, so every result is traceable."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import yaml

from okf_grc import data
from okf_grc.config import CONFIG_FILE, Config, load_config
from okf_grc.run_scan import load_pins
from okf_grc.to_oscal import NAMESPACE

Json = dict[str, Any]
# Every output `grc run` writes, relative to the output directory; all must exist when the manifest is written.
OUTPUTS = (
    "findings.json",
    "mapping.json",
    "oscal/component-definition.json",
    "oscal/assessment-plan.json",
    "oscal/assessment-results.json",
    "report.md",
)
SCANNERS = ("semgrep", "trivy", "checkov", "conftest")


def config_sha256(config: Config) -> str:
    """Hash of the resolved layout (file, defaults, and flags together), not of the file's bytes."""
    return hashlib.sha256(json.dumps(asdict(config), sort_keys=True).encode()).hexdigest()


def run_id(repo: Path, config: Config, now: str) -> str:
    """Known before any output is written, so the OSCAL results can carry it."""
    return str(uuid.uuid5(NAMESPACE, f"run:{_git(repo, 'rev-parse', 'HEAD')}:{now}:{config_sha256(config)}"))


def build_manifest(repo: Path, out: Path, config: Config, run: str, now: str) -> Json:
    """The manifest document; raises FileNotFoundError if an output is missing."""
    pins = load_pins(data.path("tools.lock"))
    commit = _git(repo, "rev-parse", "HEAD")
    return {
        "schema_version": data.SCHEMA_VERSION,
        "run_id": run,
        "generated": now,
        "repository": {
            "commit": commit,
            "dirty": None if commit is None else bool(_git(repo, "status", "--porcelain", "--untracked-files=no")),
        },
        "engine": {"package": "okf-grc", "version": version("okf-grc")},
        "base_version": _base_version(repo / config.knowledge),
        "scanners": {tool: pins[f"{tool.upper()}_VERSION"] for tool in SCANNERS},
        "config": {
            "file": CONFIG_FILE if (repo / CONFIG_FILE).is_file() else None,
            "resolved": asdict(config),
            "sha256": config_sha256(config),
        },
        "outputs": {rel: hashlib.sha256((out / rel).read_bytes()).hexdigest() for rel in OUTPUTS},
    }


def _git(repo: Path, *args: str) -> str | None:
    """Stripped output of a git command, or None outside a git repository."""
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def _base_version(knowledge: Path) -> str | None:
    """`base_version` from the bundle's root index frontmatter, if recorded."""
    index = knowledge / "index.md"
    if not index.is_file() or not (text := index.read_text(encoding="utf-8")).startswith("---\n"):
        return None
    return (yaml.safe_load(text.split("---\n")[1]) or {}).get("base_version")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None, help="scan layout (default: grc.yaml if present)")
    parser.add_argument("--target", default=None, help="scan target (overrides the config)")
    parser.add_argument("--knowledge", default=None, help="knowledge bundle (overrides the config)")
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--now", default=datetime.now(UTC).isoformat(timespec="seconds"))
    parser.add_argument("--run-id", default=None, help="the id the OSCAL results carry (default: derived)")
    args = parser.parse_args(argv)
    repo = Path.cwd()
    config = load_config(repo, args.config, target=args.target, knowledge=args.knowledge)
    manifest = build_manifest(repo, args.out, config, args.run_id or run_id(repo, config, args.now), args.now)
    (args.out / "run.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
