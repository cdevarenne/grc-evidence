"""`grc gate`: fail a pipeline when compliance gets worse than a committed baseline of control statuses and findings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

Json = dict[str, Any]
BASELINE = Path("expected/control-status.json")
FAILING = "not-satisfied"
RANKED = ("critical", "high", "medium", "low", "info")  # `unknown` is unranked: it never reaches a --fail-on level


def control_status(mapping: Json) -> dict[str, str]:
    """Each control's status, by key."""
    return {key: entry["status"] for key, entry in sorted(mapping["controls"].items())}


def findings(mapping: Json) -> dict[str, Json]:
    """Each mapped finding by identity (`tool:rule_id target`), accepted risks left out.

    The message is not part of the identity: a version bump on a still-vulnerable package is not a new finding.
    """
    return {
        f"{f['tool']}:{f['rule_id']} {f['target']}": f
        for entry in mapping["controls"].values()
        for f in entry["findings"]
        if not f.get("accepted")
    }


def baseline_doc(mapping: Json) -> Json:
    """What `--write-baseline` records: control statuses and finding identities."""
    return {"controls": control_status(mapping), "findings": sorted(findings(mapping))}


def problems(mapping: Json, baseline: Json, fail_on: str = "high") -> list[str]:
    """Why the gate fails: a control newly `not-satisfied`, a new finding at or above `fail_on`, or an expired
    suppression. Empty means it passes.

    A control already `not-satisfied` in the baseline does not fail again; improvements never fail. A baseline
    without `findings` (written before they were recorded) skips the finding check.
    """
    statuses = baseline["controls"]
    found = [
        f"{key}: {statuses.get(key, 'not in the baseline')} -> {FAILING}"
        for key, status in control_status(mapping).items()
        if status == FAILING and statuses.get(key) != FAILING
    ]
    if "findings" in baseline:
        known, levels = set(baseline["findings"]), RANKED[: RANKED.index(fail_on) + 1]
        found += [
            f"new {f['severity']} finding: {fid}"
            for fid, f in sorted(findings(mapping).items())
            if fid not in known and f["severity"] in levels
        ]
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
        new = sorted(set(findings(mapping)) - set(baseline["findings"]))
        lines += ["", f"Findings not in the baseline (any severity): {len(new)}"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="grc gate", description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("out"), help="where `grc run` wrote mapping.json")
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--write-baseline", action="store_true", help="record the current statuses and findings as the baseline")
    parser.add_argument("--fail-on", choices=RANKED, default="high", help="fail on a new finding at or above this severity")
    parser.add_argument("--summary", type=Path, default=None, help="append the status table to this file (CI job summary)")
    args = parser.parse_args(argv)
    mapping = json.loads((args.out / "mapping.json").read_text(encoding="utf-8"))
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
