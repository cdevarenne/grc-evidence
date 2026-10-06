"""`grc init` sets up a repo from the engine's base bundle; `grc check` reports drift from it and unreviewed concepts;
`grc sync-base` updates the repo's copies to the installed engine's base."""

from __future__ import annotations

import argparse
import os
import re
from collections.abc import Iterable
from importlib.metadata import version
from importlib.resources import as_file
from pathlib import Path

from grc_evidence import data
from grc_evidence.config import CONFIG_FILE, Config, load_config
from grc_evidence.manifest import recorded_base_version
from grc_evidence.okf_lib import BundleError, load_bundle

ROOT_INDEX = """---
okf_version: "0.2"
base_version: "{version}"
---
# Knowledge Bundle

Grounds grc-evidence scans of this repository. A finding reaches a control only
through a `rule_ids` declaration here; a finding with none is a coverage gap.
Controls, crosswalks, scanners, and generic policies are copies of the grc-evidence
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
SKILL = Path(".claude/skills/grc-continuous-compliance/SKILL.md")  # where Claude Code finds a project skill
GITIGNORED = (".tools/", "out/")  # scanners and run outputs: local, never committed
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
INVENTORY = """# AI system inventory read by grc-evidence. A person fills this in.
# risk_tier is the EU AI Act risk class: minimal, limited, or high. Left unset,
# every tier-gated control is assessed; set it only with a recorded reason.
# risk_tier: limited
components: []  # each component: {path: <dir>, kind: <api | assistant | ...>}
systems: []  # each AI system: {path (its component's), name, owner, provider, sdk, purpose}; sdk: anthropic, langchain, ...
"""


def starter_config(d: Config) -> str:
    """A `grc.yaml` naming every key with its value in `d`."""
    return (
        "# grc-evidence scan layout. Scan inputs (inventory, conftest.inputs, checkov.skip_paths) are\n"
        "# relative to the target; the other paths are relative to the repo root.\n"
        f"target: {d.target}\nknowledge: {d.knowledge}\ninventory: {d.inventory}\n"
        f"conftest:\n  inputs: {_flow(repr(p) for p in d.conftest_inputs)}  # [] turns Conftest off\n"
        f"skip_paths: {_flow(d.skip_paths)}  # directories Trivy and Checkov skip, e.g. helm-chart\n"
        f"checkov:\n  frameworks: {_flow(d.checkov_frameworks)}\n  skip_paths: {_flow(d.checkov_skip_paths)}\n"
        f"semgrep:\n  configs: {_flow(d.semgrep_configs)}\n"
        f"rego: {_flow(d.rego)}\n"
        f"scanner_timeout: {d.scanner_timeout}  # seconds per scanner\n"
        f"allow_external_symlinks: false  # accept a Conftest input that is a symlink out of the repo\n"
    )


def init_files(repo: Path, target: str) -> dict[Path, str]:
    """Every file `grc init` writes, repo-relative, with its content."""
    config = _starter(repo, target)
    knowledge, files = Path(config.knowledge), {}
    with as_file(data.path("base")) as base, as_file(data.path("policies")) as policies:
        for src in _tree(base):
            if src != Path("index.md"):
                files[knowledge / src] = (base / src).read_text(encoding="utf-8")
        for src in _tree(policies):
            files[Path("policies") / src] = (policies / src).read_text(encoding="utf-8")
    files[knowledge / "index.md"] = ROOT_INDEX.format(version=version("grc-evidence"))
    components = sorted(p for p in (repo / target / "src").glob("*/") if p.is_dir())
    entries = ""
    for component in components:
        stub = knowledge / "stack" / f"{component.name}.md"
        resource = Path(os.path.relpath(component, repo / stub.parent)).as_posix() + "/"
        files[stub] = STUB.format(name=component.name, resource=resource)
        entries += f"* [{component.name}]({component.name}.md)\n"
    files[knowledge / "stack" / "index.md"] = STACK_INDEX.format(entries=entries)
    files[knowledge / "suppressions" / "index.md"] = SUPPRESSIONS_INDEX
    files[Path(CONFIG_FILE)] = starter_config(config)
    files[Path(os.path.normpath(Path(target) / config.inventory))] = INVENTORY
    return files


def _starter(repo: Path, target: str) -> Config:
    """The starter layout. A target that is its own git repository (a submodule) is someone else's code:
    the inventory goes to the repo root, beside it, and Conftest reads it there."""
    defaults = Config(target=target)
    if not (repo / target / ".git").exists():
        return defaults
    inventory = Path(os.path.relpath(repo / "ai-inventory.yaml", repo / target)).as_posix()
    inputs = tuple(inventory if p == defaults.inventory else p for p in defaults.conftest_inputs)
    return Config(target=target, inventory=inventory, conftest_inputs=inputs)


def init(repo: Path, target: str = ".") -> list[Path]:
    """Write the starter files; refuse, writing nothing, if any already exists. Ignores `.tools/` and `out/` in git."""
    files = init_files(repo, target)
    if conflicts := sorted(rel for rel in files if (repo / rel).exists()):
        raise FileExistsError(f"grc init writes nothing: {len(conflicts)} file(s) exist, e.g. {conflicts[0]}")
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    return sorted([*files, *_ignore(repo, GITIGNORED)])


def _ignore(repo: Path, entries: tuple[str, ...]) -> list[Path]:
    """Append the entries `.gitignore` lacks (the one file `grc init` may change); the paths it touched."""
    gitignore = repo / ".gitignore"
    present = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.is_file() else []
    if not (missing := [e for e in entries if e not in present]):
        return []
    prefix = "" if not present or gitignore.read_text(encoding="utf-8").endswith("\n") else "\n"
    with gitignore.open("a", encoding="utf-8") as f:
        f.write(prefix + "\n".join(missing) + "\n")
    return [Path(".gitignore")]


def check(repo: Path, config: Config) -> list[str]:
    """Problems: base copies that drifted or are missing, a stale base_version, and unverified concepts."""
    knowledge, installed, problems = repo / config.knowledge, version("grc-evidence"), []
    if (recorded := recorded_base_version(knowledge)) != installed:
        problems.append(f"{config.knowledge}/index.md: base_version {recorded!r}, installed engine {installed!r}")
    with as_file(data.path("base")) as base, as_file(data.path("policies")) as policies, as_file(data.path("skill")) as skill:
        for source, copy in _copies(repo, config, base, policies, skill):
            if copy.name == "index.md":
                continue
            if not copy.is_file():
                problems.append(f"{copy.relative_to(repo)}: missing (base {installed})")
            elif copy.read_bytes() != source.read_bytes():
                problems.append(f"{copy.relative_to(repo)}: differs from base {installed}")
    try:
        bundle = load_bundle(knowledge)
    except BundleError as e:
        return [*problems, f"{config.knowledge}/{e}"]
    for concept in sorted(bundle.concepts.values(), key=lambda c: c.id):
        if not any(str(e.get("by", "")).startswith("human:") for e in concept.frontmatter.get("verified") or []):
            problems.append(f"{config.knowledge}/{concept.path}: not verified by a person")
    return problems


def sync_base(repo: Path, config: Config) -> list[str]:
    """Overwrite the repo's base copies with the installed engine's and set `base_version`; what changed.

    An `index.md` with a line the base lacks (the repo's own entries) is kept and reported for a person to merge;
    one whose lines all appear in the base's is overwritten. A file the base no longer has is left in place.
    """
    installed, changes = version("grc-evidence"), []
    with as_file(data.path("base")) as base, as_file(data.path("policies")) as policies, as_file(data.path("skill")) as skill:
        for source, copy in _copies(repo, config, base, policies, skill):
            rel = copy.relative_to(repo).as_posix()
            if copy.is_file() and copy.read_bytes() == source.read_bytes():
                continue
            if copy.name == "index.md" and copy.is_file() and not _lines(copy) <= _lines(source):
                changes.append(f"kept {rel}: differs from base {installed}; merge its new entries by hand")
                continue
            changes.append(f"{'updated' if copy.is_file() else 'added'} {rel}")
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(source.read_bytes())
    index = repo / config.knowledge / "index.md"
    text = index.read_text(encoding="utf-8")
    # Only the value changes: a comment after it stays.
    synced = re.sub(r'^(base_version:\s*)("[^"]*"|[^\s#]+)', rf'\g<1>"{installed}"', text, count=1, flags=re.MULTILINE)
    if synced != text:
        index.write_text(synced, encoding="utf-8")
        changes.append(f"updated {index.relative_to(repo).as_posix()}: base_version {installed}")
    return changes


def _lines(path: Path) -> set[str]:
    return set(path.read_text(encoding="utf-8").splitlines())


def _copies(repo: Path, config: Config, base: Path, policies: Path, skill: Path) -> list[tuple[Path, Path]]:
    """Each base file and where the repo keeps its copy; the base's root `index.md` is the repo's own.

    The agent skill counts only once `grc install-skill` has put it in the repo.
    """
    pairs = [(base / rel, repo / config.knowledge / rel) for rel in _tree(base) if rel != Path("index.md")]
    pairs += [(policies / rel, repo / "policies" / rel) for rel in _tree(policies)]
    return pairs + ([(skill / SKILL.name, repo / SKILL)] if (repo / SKILL).is_file() else [])


def install_skill(repo: Path) -> str:
    """Write the engine's agent skill where Claude Code finds it; what happened."""
    dest, installed = repo / SKILL, version("grc-evidence")
    with as_file(data.path("skill")) as skill:
        text = (skill / SKILL.name).read_bytes()
    if dest.is_file() and dest.read_bytes() == text:
        return f"ok: {SKILL.as_posix()} already matches {installed}"
    verb = "updated" if dest.is_file() else "added"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(text)
    return f"{verb} {SKILL.as_posix()} ({installed}); grc sync-base keeps it current"


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
    print(f"ok: copies match base {version('grc-evidence')}; every concept is verified")


def install_skill_main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(prog="grc install-skill", description="Install the engine's agent skill for Claude Code.").parse_args(argv)
    print(install_skill(Path.cwd()))


def sync_base_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="grc sync-base", description="Update this repo's base copies to the installed engine's base.")
    parser.add_argument("--config", type=Path, default=None, help="scan layout (default: grc.yaml if present)")
    args = parser.parse_args(argv)
    repo = Path.cwd()
    changes = sync_base(repo, load_config(repo, args.config))
    print("\n".join(changes) if changes else f"ok: copies already match base {version('grc-evidence')}")
