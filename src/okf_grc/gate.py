"""`grc gate`: fail a pipeline when compliance gets worse than a committed baseline of control statuses."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

Json = dict[str, Any]
BASELINE = Path("expected/control-status.json")
FAILING = "not-satisfied"


def control_status(mapping: Json) -> dict[str, str]:
    """Each control's status, by key."""
    return {key: entry["status"] for key, entry in sorted(mapping["controls"].items())}


def problems(mapping: Json, baseline: dict[str, str]) -> list[str]:
    """Why the gate fails: a control newly `not-satisfied`, or an expired suppression. Empty means it passes.

    A control already `not-satisfied` in the baseline does not fail again; improvements never fail.
    """
    found = [
        f"{key}: {baseline.get(key, 'not in the baseline')} -> {FAILING}"
        for key, status in control_status(mapping).items()
        if status == FAILING and baseline.get(key) != FAILING
    ]
    found += [f"suppression {sid} expired" for sid in mapping.get("expired_suppressions", [])]
    return found


def summary(mapping: Json, baseline: dict[str, str]) -> str:
    """A Markdown table of each control's baseline and current status, changes marked."""
    lines = ["## Compliance gate", "", "| Control | Baseline | Now | |", "|---|---|---|---|"]
    for key, status in control_status(mapping).items():
        before = baseline.get(key, "-")
        mark = "" if before == status else ("regressed" if status == FAILING else "changed")
        lines.append(f"| `{key}` | {before} | {status} | {mark} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="grc gate", description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("out"), help="where `grc run` wrote mapping.json")
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--write-baseline", action="store_true", help="record the current statuses as the baseline")
    parser.add_argument("--summary", type=Path, default=None, help="append the status table to this file (CI job summary)")
    args = parser.parse_args(argv)
    mapping = json.loads((args.out / "mapping.json").read_text(encoding="utf-8"))
    if args.write_baseline:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(json.dumps({"controls": control_status(mapping)}, indent=2) + "\n", encoding="utf-8")
        print(f"gate: wrote {args.baseline}")
        return
    if not args.baseline.is_file():
        raise SystemExit(f"grc gate: no baseline at {args.baseline}; create it with `grc gate --write-baseline`")
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))["controls"]
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as f:
            f.write(summary(mapping, baseline))
    if found := problems(mapping, baseline):
        raise SystemExit("grc gate: failed\n" + "\n".join(f"  {p}" for p in found))
    print("gate: passed")


if __name__ == "__main__":
    main()
