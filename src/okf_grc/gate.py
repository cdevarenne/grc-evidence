"""`grc gate`: fail a pipeline when compliance gets worse than a committed baseline of control statuses and findings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from okf_grc.contract import read_mapping

Json = dict[str, Any]
BASELINE = Path("expected/control-status.json")
FAILING = "not-satisfied"
RANKED = ("critical", "high", "medium", "low", "info")  # --fail-on levels for vulnerabilities; `unknown` reaches none
VULNERABILITY = "vulnerability"  # the tag run_scan puts on a dependency advisory (CVE, GHSA, GO, ...)


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
    """
    statuses = baseline["controls"]
    found = [
        f"{key}: {statuses.get(key, 'not in the baseline')} -> {FAILING}"
        for key, status in control_status(mapping).items()
        if status == FAILING and statuses.get(key) != FAILING
    ]
    if "findings" in baseline:
        known, levels = _counts(baseline), RANKED[: RANKED.index(fail_on) + 1]
        for fid, fs in _new(mapping, baseline).items():
            count = f"{known.get(fid, 0)} -> {len(fs)}"
            if not any(VULNERABILITY in f["tags"] for f in fs):
                found.append(f"new finding: {fid} ({count})")
            elif worst := next((level for level in levels if any(f["severity"] == level for f in fs)), None):
                found.append(f"new {worst} vulnerability: {fid} ({count})")
    found += [f"suppression {sid} expired" for sid in mapping.get("expired_suppressions", [])]
    return found


def summary(mapping: Json, baseline: Json) -> str:
    """A Markdown table of each control's baseline and current status, changes marked."""
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
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as f:
            f.write(summary(mapping, baseline))
    if found := problems(mapping, baseline, args.fail_on):
        raise SystemExit("grc gate: failed\n" + "\n".join(f"  {p}" for p in found))
    print("gate: passed")


if __name__ == "__main__":
    main()
