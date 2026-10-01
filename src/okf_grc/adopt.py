"""`grc init` sets up a repo from the engine's base bundle; `grc check` reports drift from it and unreviewed concepts."""

from __future__ import annotations

import argparse
import os
from collections.abc import Iterable
from importlib.metadata import version
from importlib.resources import as_file
from pathlib import Path

from okf_grc import data
from okf_grc.config import CONFIG_FILE, Config, load_config
from okf_grc.manifest import recorded_base_version
from okf_grc.okf_lib import BundleError, load_bundle

ROOT_INDEX = """---
okf_version: "0.2"
base_version: "{version}"
---
# Knowledge Bundle

Grounds okf-grc scans of this repository. A finding reaches a control only
through a `rule_ids` declaration here; a finding with none is a coverage gap.
Controls, crosswalks, scanners, and generic policies are copies of the okf-grc
base bundle (`grc check` reports drift); the stack and the suppressions are
this repository's own.

# Map

* [Controls](controls/) - SOC 2 criteria (mapped to NIST SP 800-53), ISO/IEC 42001 Annex A, and EU AI Act articles
* [Crosswalk](crosswalk/) - navigation links between frameworks; never a mapping
* [Stack](stack/) - this repository's components; each links the controls it implements
* [Policies](policies/) - guardrails (Rego, Semgrep) and the scanner rules that detect each
* [Scanners](scanners/) - DevSecOps tools and the controls they evidence
* [Suppressions](suppressions/) - reviewed, expiring false positives and accepted risks; never hidden
* [OSCAL output](oscal/component-definition.md) - the machine-readable output target
"""
STACK_INDEX = "# Stack\n\nThis repository's components. Each one links the controls it implements.\n\n{entries}"
SUPPRESSIONS_INDEX = "# Suppressions\n\nOne concept per reviewed decision about one exact finding, with an owner, a reason, and an expiry.\n"
STUB = """---
type: Stack Component
title: {name}
description: Replace with what this component is and does.
resource: {resource}
tags: []
---
# Implements

Link each control this component implements, for example
`- [CC6.1 — Logical Access](../controls/cc6.1.md)`. The OSCAL component
definition lists a control for a component only through these links.
"""
INVENTORY = """# AI system inventory read by okf-grc. A person fills this in.
# risk_tier is the EU AI Act risk class: minimal, limited, or high. Left unset,
# every tier-gated control is assessed; set it only with a recorded reason.
# risk_tier: limited
components: []  # each component: {path: <dir>, kind: <api | assistant | ...>}
systems: []  # each AI system: {name, owner, provider, purpose}
"""


def starter_config(target: str) -> str:
    """A `grc.yaml` naming every key with its default, for the given target."""
    d = Config(target=target)
    return (
        "# okf-grc scan layout. Scan inputs (inventory, conftest.inputs, checkov.skip_paths) are\n"
        "# relative to the target; the other paths are relative to the repo root.\n"
        f"target: {d.target}\nknowledge: {d.knowledge}\ninventory: {d.inventory}\n"
        f"conftest:\n  inputs: {_flow(repr(p) for p in d.conftest_inputs)}\n"
        f"checkov:\n  frameworks: {_flow(d.checkov_frameworks)}\n  skip_paths: {_flow(d.checkov_skip_paths)}\n"
        f"semgrep:\n  configs: {_flow(d.semgrep_configs)}\n"
        f"rego: {_flow(d.rego)}\n"
    )


def init_files(repo: Path, target: str) -> dict[Path, str]:
    """Every file `grc init` writes, repo-relative, with its content."""
    config = Config(target=target)
    knowledge, files = Path(config.knowledge), {}
    with as_file(data.path("base")) as base, as_file(data.path("policies")) as policies:
        for src in _tree(base):
            if src != Path("index.md"):
                files[knowledge / src] = (base / src).read_text(encoding="utf-8")
        for src in _tree(policies):
            files[Path("policies") / src] = (policies / src).read_text(encoding="utf-8")
    files[knowledge / "index.md"] = ROOT_INDEX.format(version=version("okf-grc"))
    components = sorted(p for p in (repo / target / "src").glob("*/") if p.is_dir())
    entries = ""
    for component in components:
        stub = knowledge / "stack" / f"{component.name}.md"
        resource = Path(os.path.relpath(component, repo / stub.parent)).as_posix() + "/"
        files[stub] = STUB.format(name=component.name, resource=resource)
        entries += f"* [{component.name}]({component.name}.md)\n"
    files[knowledge / "stack" / "index.md"] = STACK_INDEX.format(entries=entries)
    files[knowledge / "suppressions" / "index.md"] = SUPPRESSIONS_INDEX
    files[Path(CONFIG_FILE)] = starter_config(target)
    files[Path(target) / config.inventory] = INVENTORY
    return files


def init(repo: Path, target: str = ".") -> list[Path]:
    """Write the starter files; refuse, writing nothing, if any already exists."""
    files = init_files(repo, target)
    if conflicts := sorted(rel for rel in files if (repo / rel).exists()):
        raise FileExistsError(f"grc init writes nothing: {len(conflicts)} file(s) exist, e.g. {conflicts[0]}")
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    return sorted(files)


def check(repo: Path, config: Config) -> list[str]:
    """Problems: base copies that drifted or are missing, a stale base_version, and unverified concepts."""
    knowledge, installed, problems = repo / config.knowledge, version("okf-grc"), []
    if (recorded := recorded_base_version(knowledge)) != installed:
        problems.append(f"{config.knowledge}/index.md: base_version {recorded!r}, installed engine {installed!r}")
    with as_file(data.path("base")) as base, as_file(data.path("policies")) as policies:
        copies = [(base, knowledge, rel) for rel in _tree(base) if rel.name != "index.md"]
        copies += [(policies, repo / "policies", rel) for rel in _tree(policies)]
        for source, dest, rel in copies:
            copy = dest / rel
            if not copy.is_file():
                problems.append(f"{copy.relative_to(repo)}: missing (base {installed})")
            elif copy.read_bytes() != (source / rel).read_bytes():
                problems.append(f"{copy.relative_to(repo)}: differs from base {installed}")
    try:
        bundle = load_bundle(knowledge)
    except BundleError as e:
        return [*problems, f"{config.knowledge}/{e}"]
    for concept in sorted(bundle.concepts.values(), key=lambda c: c.id):
        if not any(str(e.get("by", "")).startswith("human:") for e in concept.frontmatter.get("verified") or []):
            problems.append(f"{config.knowledge}/{concept.path}: not verified by a person")
    return problems


def _flow(values: Iterable[str]) -> str:
    """A YAML flow sequence: `[a, b]`."""
    return "[" + ", ".join(values) + "]"


def _tree(root: Path) -> list[Path]:
    """Files under `root`, relative, skipping caches and hidden files."""
    return sorted(
        p.relative_to(root) for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and not any(s.startswith(".") for s in p.relative_to(root).parts)
    )


def init_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="grc init", description="Set up this repo from the engine's base bundle.")
    parser.add_argument("--target", default=".", help="scan target, relative to the repo root")
    args = parser.parse_args(argv)
    try:
        written = init(Path.cwd(), args.target)
    except FileExistsError as e:
        raise SystemExit(str(e)) from e
    for rel in written:
        print(f"wrote {rel}")


def check_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="grc check", description="Report drift from the base bundle and unreviewed concepts.")
    parser.add_argument("--config", type=Path, default=None, help="scan layout (default: grc.yaml if present)")
    args = parser.parse_args(argv)
    repo = Path.cwd()
    if problems := check(repo, load_config(repo, args.config)):
        print("\n".join(problems))
        raise SystemExit(1)
    print(f"ok: copies match base {version('okf-grc')}; every concept is verified")
