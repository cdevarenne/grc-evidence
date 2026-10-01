"""Write `out/run.json`: what produced a run's outputs, and the sha256 of each, so every result is traceable."""

from __future__ import annotations

import argparse
import hashlib
import posixpath
import json
import subprocess
import uuid
from collections.abc import Iterable
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


def scan_inputs(config: Config) -> list[str]:
    """Every path whose content shapes a run: the target, the bundle, the policies, the inventory, `grc.yaml`."""
    inventory = posixpath.normpath(f"{config.target}/{config.inventory}")
    return [config.target, config.knowledge, *config.semgrep_configs, *config.rego, inventory, CONFIG_FILE]


def repo_state(repo: Path, inputs: Iterable[str], exclude: Iterable[Path] = ()) -> Json:
    """The scanned commit, whether the scan inputs differ from it, and the untracked files among them.

    Untracked, not-ignored files among `inputs` (see `scan_inputs`) are inputs the commit does not contain, so
    they make the run dirty; `.tools/` and the `exclude` paths (run outputs) are not inputs. Outside git: commit None.
    """
    commit = _git(repo, "rev-parse", "HEAD")
    if commit is None:
        return {"commit": None, "dirty": None, "untracked": []}
    root = repo.resolve()
    skip = [p.relative_to(root) for p in ((repo / q).resolve() for q in (".tools", *exclude)) if p.is_relative_to(root)]
    listed = (_git(repo, "ls-files", "-z", "--others", "--exclude-standard", "--", *inputs) or "").split("\0")
    untracked = sorted(f for f in listed if f and not any(Path(f).is_relative_to(s) for s in skip))
    modified = bool(_git(repo, "status", "--porcelain", "--untracked-files=no"))
    return {"commit": commit, "dirty": modified or bool(untracked), "untracked": untracked}


def build_manifest(
    repo: Path, out: Path, config: Config, run: str, now: str, exclude: Iterable[Path] = (), repository: Json | None = None
) -> Json:
    """The manifest document; raises FileNotFoundError if an output is missing.

    `repository` keeps the state a scan recorded when the manifest is rewritten later (after narration),
    since the inputs did not change; otherwise the state is read now.
    """
    pins = load_pins(data.path("tools.lock"))
    return {
        "schema_version": data.SCHEMA_VERSION,
        "run_id": run,
        "generated": now,
        "repository": repository or repo_state(repo, scan_inputs(config), (out, *exclude)),
        "engine": {"package": "okf-grc", "version": version("okf-grc")},
        "base_version": recorded_base_version(repo / config.knowledge),
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


def recorded_base_version(knowledge: Path) -> str | None:
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
    parser.add_argument("--exclude", type=Path, action="append", default=[], help="a run directory that is not a scan input")
    parser.add_argument("--keep-repository", action="store_true", help="keep the repository state of the existing run.json")
    args = parser.parse_args(argv)
    repo = Path.cwd()
    config = load_config(repo, args.config, target=args.target, knowledge=args.knowledge)
    kept = json.loads((args.out / "run.json").read_text(encoding="utf-8"))["repository"] if args.keep_repository else None
    manifest = build_manifest(repo, args.out, config, args.run_id or run_id(repo, config, args.now), args.now, args.exclude, kept)
    (args.out / "run.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
