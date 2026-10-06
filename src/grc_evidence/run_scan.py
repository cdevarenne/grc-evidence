"""Run Semgrep, Trivy, Checkov and Conftest against a target and write normalized findings."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib.resources.abc import Traversable
from pathlib import Path, PurePosixPath
from typing import Any

from grc_evidence.config import Config, load_config
from grc_evidence.data import SCHEMA_VERSION
from grc_evidence.errors import GrcError

Finding = dict[str, Any]
SEVERITIES = ("critical", "high", "medium", "low", "info", "unknown")
_SEMGREP_SEVERITY = {"ERROR": "high", "WARNING": "medium", "INFO": "low"}


class ScanError(GrcError, RuntimeError):
    """A scanner is missing, crashed, or produced unreadable output."""


def _finding(tool: str, rule_id: str, severity: str, target: str, message: str, tags: Sequence[str] = ()) -> Finding:
    """One normalized finding. The target is a repo-relative POSIX path with no `./`, whichever scanner
    reported it, because suppressions match it exactly (target `.` would otherwise yield `./Dockerfile`)."""
    level = severity.lower() if severity.lower() in SEVERITIES else "unknown"
    path = PurePosixPath(target).as_posix()
    return {"tool": tool, "rule_id": rule_id, "severity": level, "target": path, "message": message, "tags": list(tags)}


def normalize_semgrep(doc: dict[str, Any], target_dir: str) -> list[Finding]:
    """Semgrep --json; paths are already repo-relative. Rule ids drop the config-path prefix.

    Semgrep reports rule and parse errors in `errors` while still exiting 0/1, so any error fails the scan.
    """
    if errors := doc.get("errors"):
        raise ScanError(f"semgrep: {len(errors)} error(s), first: {errors[0].get('message', errors[0])}")
    return [
        _finding(
            "semgrep",
            r["check_id"].rsplit(".", 1)[-1],
            _SEMGREP_SEVERITY.get(r["extra"]["severity"], r["extra"]["severity"]),
            r["path"],
            r["extra"]["message"],
        )
        for r in doc["results"]
    ]


def normalize_trivy(doc: dict[str, Any], target_dir: str) -> list[Finding]:
    """Trivy config/fs --format json; targets are relative to the scanned directory."""
    findings = []
    for result in doc.get("Results", []):
        target = f"{target_dir}/{result['Target']}"
        for m in result.get("Misconfigurations") or []:
            if m["Status"] == "FAIL":
                findings.append(_finding("trivy", m["ID"], m["Severity"], target, f"{m['Title']}: {m['Message']}"))
        for v in result.get("Vulnerabilities") or []:
            message = f"{v['PkgName']} {v['InstalledVersion']}: {v['Title']}"
            findings.append(_finding("trivy", v["VulnerabilityID"], v["Severity"], target, message, ["vulnerability"]))
    return findings


def normalize_checkov(doc: dict[str, Any] | list[dict[str, Any]], target_dir: str) -> list[Finding]:
    """Checkov -o json (one object per framework); run with cwd=target so paths are target-relative.

    A framework with nothing to scan is a bare summary dict without `results`; it contributes no findings.
    """
    reports = doc if isinstance(doc, list) else [doc]
    return [
        _finding(
            "checkov",
            c["check_id"],
            c.get("severity") or "unknown",
            f"{target_dir}/{c['file_path'].lstrip('/')}",
            f"{c['check_name']} ({c['resource']})",
        )
        for report in reports
        for c in report.get("results", {}).get("failed_checks", [])
    ]


def normalize_conftest(doc: list[dict[str, Any]], target_dir: str) -> list[Finding]:
    """Conftest -o json; the policy package (namespace) is the rule id. Deny rules block, so severity is high."""
    return [
        _finding("conftest", r["namespace"], "high", r["filename"], f["msg"])
        for r in doc
        for f in r.get("failures") or []
    ]


def dedupe(findings: list[Finding]) -> list[Finding]:
    """Collapse identical findings, sorted by tool, rule id, target, and message.

    The message is part of the key: one rule can fire on several resources in one file.
    Sorting makes the output independent of the order a scanner reports in.
    """
    seen: dict[tuple[str, str, str, str], Finding] = {}
    for f in findings:
        seen.setdefault((f["tool"], f["rule_id"], f["target"], f["message"]), f)
    return [seen[key] for key in sorted(seen)]


def run_tool(tool: str, argv: list[str], cwd: Path, tools: Path | None = None, timeout: int | None = None) -> Any:
    """Run a scanner and parse its JSON stdout. Exit 0/1 means clean/issues found; anything else fails.

    `tools` is the `.tools` directory `grc bootstrap` fills: its `bin/` copy of a scanner is used before
    one on PATH, and Trivy keeps its database in its `trivy-cache/` unless TRIVY_CACHE_DIR is set.
    """
    local = tools / "bin" / argv[0] if tools else None
    exe = str(local) if local and local.is_file() else shutil.which(argv[0])
    if exe is None:
        raise ScanError(f"{tool}: '{argv[0]}' not found in .tools/bin or on PATH; run `grc bootstrap`")
    env = os.environ | ({"TRIVY_CACHE_DIR": str(tools / "trivy-cache")} if tools and "TRIVY_CACHE_DIR" not in os.environ else {})
    try:
        proc = subprocess.run(
            [exe, *argv[1:]], cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", check=False, timeout=timeout
        )
    except subprocess.TimeoutExpired as e:  # the scanner is killed; name it rather than hang the run
        raise ScanError(f"{tool}: no result after {timeout}s; stopped (scanner_timeout in grc.yaml)") from e
    if proc.returncode not in (0, 1):
        raise ScanError(f"{tool}: exit {proc.returncode}: {proc.stderr.strip()[-500:]}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise ScanError(f"{tool}: unreadable JSON output: {e}") from e


def _check_target(repo: Path, target_dir: str) -> None:
    """Refuse option-like targets and targets that resolve outside the repo root."""
    if target_dir.startswith("-") or not (repo / target_dir).resolve().is_relative_to(repo.resolve()):
        raise ScanError(f"--target {target_dir!r} must be a directory inside the repo root {repo}")


@dataclass(frozen=True)
class ScannerRun:
    """One scanner invocation. The assessment plan reads these, so it cannot drift from what runs."""

    tool: str
    title: str
    argv: tuple[str, ...]
    in_target: bool  # run with cwd = the scan target; otherwise the repo root
    pin: str  # the tools.lock key holding this scanner's version
    normalize: Callable[[Any, str], list[Finding]]


def tools_not_run(config: Config) -> list[str]:
    """Scanners the layout turns off: an explicit empty `conftest.inputs` skips Conftest (#71)."""
    return [] if config.conftest_inputs else ["conftest"]


def scanner_runs(config: Config, conftest_inputs: Sequence[str]) -> list[ScannerRun]:
    """The scanner runs over `config.target`, in execution order; Conftest only when it has inputs to check."""
    target_dir = config.target
    semgrep_configs = [arg for c in config.semgrep_configs for arg in ("--config", c)]
    frameworks = ("--framework", *config.checkov_frameworks)
    skip_paths = [arg for p in (*config.skip_paths, *config.checkov_skip_paths) for arg in ("--skip-path", p)]
    skip_dirs = [arg for p in config.skip_paths for arg in ("--skip-dirs", p)]
    rego = [arg for r in config.rego for arg in ("-p", r)]
    runs = [
        ScannerRun("semgrep", "Semgrep code scan", ("semgrep", "scan", *semgrep_configs, "--metrics=off", "--json", "--quiet", target_dir), False, "SEMGREP_VERSION", normalize_semgrep),
        ScannerRun("trivy", "Trivy misconfiguration scan", ("trivy", "config", "--quiet", "--format", "json", *skip_dirs, target_dir), False, "TRIVY_VERSION", normalize_trivy),
        ScannerRun("trivy", "Trivy dependency vulnerability scan", ("trivy", "fs", "--quiet", "--scanners", "vuln", "--format", "json", *skip_dirs, target_dir), False, "TRIVY_VERSION", normalize_trivy),
        ScannerRun("checkov", "Checkov infrastructure-as-code scan", ("checkov", "-d", ".", *frameworks, *skip_paths, "-o", "json", "--quiet", "--compact"), True, "CHECKOV_VERSION", normalize_checkov),
        ScannerRun("conftest", "Conftest policy check", ("conftest", "test", "--all-namespaces", "--no-color", "-o", "json", *rego, *conftest_inputs), False, "CONFTEST_VERSION", normalize_conftest),
    ]
    return [run for run in runs if run.tool not in tools_not_run(config)]


def load_pins(lock: Traversable) -> dict[str, str]:
    """`KEY=value` lines of tools.lock; comments and blank lines are skipped."""
    lines = [ln for ln in lock.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    return dict(ln.split("=", 1) for ln in lines)


def conftest_inputs(repo: Path, config: Config) -> list[str]:
    """The files Conftest checks: `conftest.inputs` globs from the target, repo-relative and sorted.

    Patterns that match nothing are an error: Conftest given no files prints its usage instead of JSON. An explicit
    empty `conftest.inputs` returns none, and Conftest does not run. A match that leaves the repo is an error; so is
    one that is a symlink out of it, unless `allow_external_symlinks` is set.
    """
    root, patterns = repo.absolute(), config.conftest_inputs
    if not patterns:
        return []
    found: set[str] = set()
    for pattern in patterns:
        for match in (root / config.target).glob(pattern):
            path = Path(os.path.normpath(match))
            if not path.is_relative_to(root):
                raise ScanError(f"conftest.inputs {pattern!r} reaches {path}, outside the repo")
            rel = path.relative_to(root).as_posix()
            if not path.resolve().is_relative_to(root.resolve()) and not config.allow_external_symlinks:
                raise ScanError(f"conftest input {rel} is a symlink out of the repo; set allow_external_symlinks: true to accept it")
            found.add(rel)
    inputs = sorted(found)
    if not inputs:
        raise ScanError(f"conftest: no files under {config.target!r} match conftest.inputs ({', '.join(patterns)})")
    return inputs


def scan(repo: Path, config: Config) -> list[Finding]:
    """Run all four scanners over `repo/config.target` and return deduplicated findings."""
    _check_target(repo, config.target)
    # A missing path would not fail loudly: Semgrep reads a name like `p/python` as a registry ruleset.
    for key, paths in (("semgrep.configs", config.semgrep_configs), ("rego", config.rego)):
        if missing := [rel for rel in paths if not (repo / rel).exists()]:
            raise ScanError(f"{key}: {missing} do not exist")
    target = repo / config.target
    findings: list[Finding] = []
    for run in scanner_runs(config, conftest_inputs(repo, config)):
        findings += run.normalize(run_tool(run.tool, list(run.argv), target if run.in_target else repo, repo / ".tools", config.scanner_timeout), config.target)
    return dedupe(findings)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None, help="scan layout (default: grc.yaml if present)")
    parser.add_argument("--target", default=None, help="scan target, relative to the repo root (overrides the config)")
    parser.add_argument("--out", type=Path, default=Path("out"))
    args = parser.parse_args(argv)
    repo = Path.cwd()
    findings = scan(repo, load_config(repo, args.config, target=args.target))
    args.out.mkdir(parents=True, exist_ok=True)
    doc = {"schema_version": SCHEMA_VERSION, "findings": findings}
    (args.out / "findings.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
