"""`grc gate`: fail a pipeline when compliance gets worse than a committed baseline of control statuses and findings."""

from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path
from typing import Any

from grc_evidence.contract import read_mapping
from grc_evidence.suppress import DEFAULT_DAYS

Json = dict[str, Any]
BASELINE = Path("expected/control-status.json")
FAILING = "not-satisfied"
RANKED = ("critical", "high", "medium", "low", "info")  # --fail-on levels for vulnerabilities; `unknown` reaches none
VULNERABILITY = "vulnerability"  # the tag run_scan puts on a dependency advisory (CVE, GHSA, GO, ...)
DRAFT_NOTE = "Run one, write the reason, and sign it; nothing applies until a person signs."
OWNER_PLACEHOLDER = "human:<you>"  # printed quoted; `grc suppress draft` refuses it, so a person puts their name


def control_status(mapping: Json) -> dict[str, str]:
    """Each control's status, by key."""
    return {key: entry["status"] for key, entry in sorted(mapping["controls"].items())}


def findings(mapping: Json) -> dict[str, list[Json]]:
    """Each finding by identity (`tool:rule_id target`): those on controls and the coverage gaps, accepted risks left
    out, each finding once though it may sit on several controls.

    The message is not part of the identity: a version bump on a still-vulnerable package is not a new finding.
    Several findings can share one identity (one rule on several resources of a file); they are counted.
    """
    distinct = {
        (f["tool"], f["rule_id"], f["target"], f["message"]): f
        for f in [*(f for entry in mapping["controls"].values() for f in entry["findings"]), *(u["finding"] for u in mapping["unmapped"])]
        if not f.get("accepted")
    }
    grouped: dict[str, list[Json]] = {}
    for f in distinct.values():
        grouped.setdefault(f"{f['tool']}:{f['rule_id']} {f['target']}", []).append(f)
    return dict(sorted(grouped.items()))


def baseline_doc(mapping: Json) -> Json:
    """What `--write-baseline` records: control statuses, and how many findings each identity has."""
    return {"controls": control_status(mapping), "findings": {fid: len(fs) for fid, fs in findings(mapping).items()}}


def _counts(baseline: Json) -> dict[str, int]:
    """The baseline's finding counts; a list (written by 1.3 to 1.5) records each identity once."""
    recorded = baseline["findings"]
    return dict.fromkeys(recorded, 1) if isinstance(recorded, list) else recorded


def _new(mapping: Json, baseline: Json) -> dict[str, list[Json]]:
    """Identities with more findings than the baseline records."""
    known = _counts(baseline)
    return {fid: fs for fid, fs in findings(mapping).items() if len(fs) > known.get(fid, 0)}


def problems(mapping: Json, baseline: Json, fail_on: str = "high") -> list[str]:
    """Why the gate fails: a control newly `not-satisfied`, a new finding, or an expired suppression. Empty means it
    passes.

    A new code or configuration finding fails at any severity, `unknown` included: only a change to the repository
    produces one. A new vulnerability finding (tagged at scan time) fails at or above `fail_on`, because a new
    advisory can appear with no change at all. A control already `not-satisfied` in the baseline does not fail
    again; improvements never fail. A baseline without `findings` skips the finding check.

    A `change-*` finding (a change merged without an independent approval, Spec H) never fails the gate: it
    comes from a repo's merge history, with no change to this repository, and is evidence for the window. A
    new `scm-*` finding (a branch rule turned off) still fails.
    """
    statuses = baseline["controls"]
    found = [
        f"{key}: {statuses.get(key, 'not in the baseline')} -> {FAILING}"
        for key, status in control_status(mapping).items()
        if status == FAILING and statuses.get(key) != FAILING
    ]
    found += [line for line, _ in _failing(mapping, baseline, fail_on)]
    found += [f"suppression {sid} expired" for sid in mapping.get("expired_suppressions", [])]
    return found


def _failing(mapping: Json, baseline: Json, fail_on: str) -> list[tuple[str, list[Json]]]:
    """The new findings that fail the gate (see `problems`), each identity with its failure line."""
    if "findings" not in baseline:
        return []
    known, levels, failing = _counts(baseline), RANKED[: RANKED.index(fail_on) + 1], []
    for fid, fs in _new(mapping, baseline).items():
        if all(f["tool"] == "github" and f["rule_id"].startswith("change-") for f in fs):
            continue
        count = f"{known.get(fid, 0)} -> {len(fs)}"
        if not any(VULNERABILITY in f["tags"] for f in fs):
            failing.append((f"new finding: {fid} ({count})", fs))
        elif worst := next((level for level in levels if any(f["severity"] == level for f in fs)), None):
            failing.append((f"new {worst} vulnerability: {fid} ({count})", fs))
    return failing


def drafts(mapping: Json, baseline: Json, fail_on: str = "high") -> list[str]:
    """One `grc suppress draft` command per tool and rule id among the new findings the gate fails on, every value
    shell-quoted: rule ids and targets come from scanned files. A rule whose findings are coverage gaps gets
    `false-positive`, the only kind allowed there; any other, `accepted-risk`. A person reads and edits it."""
    gaps = {(u["finding"]["tool"], u["finding"]["rule_id"]) for u in mapping["unmapped"]}
    targets: dict[tuple[str, str], set[str]] = {}
    for _, fs in _failing(mapping, baseline, fail_on):
        for f in fs:
            targets.setdefault((f["tool"], f["rule_id"]), set()).add(f["target"])
    return [
        shlex.join([
            "grc", "suppress", "draft", "--tool", tool, "--rule-id", rule_id,
            *(word for target in sorted(files) for word in ("--target", target)),
            "--kind", "false-positive" if (tool, rule_id) in gaps else "accepted-risk",
            "--days", str(DEFAULT_DAYS), "--owner", OWNER_PLACEHOLDER,
        ])
        for (tool, rule_id), files in sorted(targets.items())
    ]


def summary(mapping: Json, baseline: Json, commands: list[str] | None = None) -> str:
    """A Markdown table of each control's baseline and current status, changes marked, then the draft commands."""
    statuses = baseline["controls"]
    lines = ["## Compliance gate", "", "| Control | Baseline | Now | |", "|---|---|---|---|"]
    for key, status in control_status(mapping).items():
        before = statuses.get(key, "-")
        mark = "" if before == status else ("regressed" if status == FAILING else "changed")
        lines.append(f"| `{key}` | {before} | {status} | {mark} |")
    if "findings" in baseline:
        known = _counts(baseline)
        new = sum(len(fs) - known.get(fid, 0) for fid, fs in _new(mapping, baseline).items())
        lines += ["", f"Findings not in the baseline (any kind and severity): {new}"]
    if commands:
        lines += ["", "### Draft suppressions", "", DRAFT_NOTE, "", "```sh", *commands, "```"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="grc gate", description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("out"), help="where `grc run` wrote mapping.json")
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--write-baseline", action="store_true", help="record the current statuses and findings as the baseline")
    parser.add_argument("--fail-on", choices=RANKED, default="high", help="fail on a new vulnerability at or above this severity; any other new finding always fails")
    parser.add_argument("--summary", type=Path, default=None, help="append the status table to this file (CI job summary)")
    args = parser.parse_args(argv)
    mapping = read_mapping(args.out / "mapping.json")
    if args.write_baseline:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(json.dumps(baseline_doc(mapping), indent=2) + "\n", encoding="utf-8")
        print(f"gate: wrote {args.baseline}")
        return
    if not args.baseline.is_file():
        raise SystemExit(f"grc gate: no baseline at {args.baseline}; create it with `grc gate --write-baseline`")
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    if "findings" not in baseline:
        print(f"gate: {args.baseline} records no findings, so new findings are not checked; rewrite it with --write-baseline")
    commands = drafts(mapping, baseline, args.fail_on)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as f:
            f.write(summary(mapping, baseline, commands))
    if found := problems(mapping, baseline, args.fail_on):
        lines = ["grc gate: failed", *(f"  {p}" for p in found)]
        if commands:
            lines += ["To draft a suppression for review (a person writes the reason and signs it):", *(f"  {c}" for c in commands)]
        raise SystemExit("\n".join(lines))
    print("gate: passed")


if __name__ == "__main__":
    main()
