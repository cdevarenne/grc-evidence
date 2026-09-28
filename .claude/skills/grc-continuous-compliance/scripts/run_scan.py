"""Run Semgrep, Trivy, Checkov and Conftest against a target and write normalized findings."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Finding = dict[str, Any]
SEVERITIES = ("critical", "high", "medium", "low", "info", "unknown")
_SEMGREP_SEVERITY = {"ERROR": "high", "WARNING": "medium", "INFO": "low"}
# Files Conftest checks, relative to the scan target.
CONFTEST_PATTERNS = ("k8s/**/*.yaml", "k8s/**/*.yml", "infra/**/*.tf", "ai-inventory.yaml")


class ScanError(RuntimeError):
    """A scanner is missing, crashed, or produced unreadable output."""


def _finding(tool: str, rule_id: str, severity: str, target: str, message: str) -> Finding:
    level = severity.lower() if severity.lower() in SEVERITIES else "unknown"
    return {"tool": tool, "rule_id": rule_id, "severity": level, "target": target, "message": message, "tags": []}


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
            findings.append(_finding("trivy", v["VulnerabilityID"], v["Severity"], target, message))
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
    """Collapse identical findings, keeping first-occurrence order.

    The message is part of the key: one rule can fire on several resources in one file.
    """
    seen: dict[tuple[str, str, str, str], Finding] = {}
    for f in findings:
        seen.setdefault((f["tool"], f["rule_id"], f["target"], f["message"]), f)
    return list(seen.values())


def run_tool(tool: str, argv: list[str], cwd: Path) -> Any:
    """Run a scanner and parse its JSON stdout. Exit 0/1 means clean/issues found; anything else fails."""
    if shutil.which(argv[0]) is None:
        raise ScanError(f"{tool}: '{argv[0]}' not found on PATH; run `make bootstrap`")
    proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=False)
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


def scanner_runs(target_dir: str, conftest_inputs: Sequence[str]) -> list[ScannerRun]:
    """The five scanner runs over `target_dir`, in execution order."""
    return [
        ScannerRun("semgrep", "Semgrep code scan", ("semgrep", "scan", "--config", "policies/semgrep", "--metrics=off", "--json", "--quiet", target_dir), False, "SEMGREP_VERSION", normalize_semgrep),
        ScannerRun("trivy", "Trivy misconfiguration scan", ("trivy", "config", "--quiet", "--format", "json", target_dir), False, "TRIVY_VERSION", normalize_trivy),
        ScannerRun("trivy", "Trivy dependency vulnerability scan", ("trivy", "fs", "--quiet", "--scanners", "vuln", "--format", "json", target_dir), False, "TRIVY_VERSION", normalize_trivy),
        ScannerRun("checkov", "Checkov infrastructure-as-code scan", ("checkov", "-d", ".", "--framework", "terraform", "kubernetes", "dockerfile", "-o", "json", "--quiet", "--compact"), True, "CHECKOV_VERSION", normalize_checkov),
        ScannerRun("conftest", "Conftest policy check", ("conftest", "test", "--all-namespaces", "--no-color", "-o", "json", "-p", "policies/rego", *conftest_inputs), False, "CONFTEST_VERSION", normalize_conftest),
    ]


def load_pins(lock: Path) -> dict[str, str]:
    """`KEY=value` lines of tools.lock; comments and blank lines are skipped."""
    lines = [ln for ln in lock.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    return dict(ln.split("=", 1) for ln in lines)


def scan(repo: Path, target_dir: str) -> list[Finding]:
    """Run all four scanners over `repo/target_dir` and return deduplicated findings."""
    _check_target(repo, target_dir)
    target = repo / target_dir
    conftest_inputs = sorted(
        p.relative_to(repo).as_posix() for pattern in CONFTEST_PATTERNS for p in target.glob(pattern)
    )
    findings: list[Finding] = []
    for run in scanner_runs(target_dir, conftest_inputs):
        findings += run.normalize(run_tool(run.tool, list(run.argv), target if run.in_target else repo), target_dir)
    return dedupe(findings)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default="app", help="scan target, relative to the repo root")
    parser.add_argument("--out", type=Path, default=Path("out"))
    args = parser.parse_args()
    findings = scan(Path.cwd(), args.target)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "findings.json").write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
