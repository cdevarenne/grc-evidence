"""`grc sample` (Spec H §6): the evidence for each change an auditor sampled from the population.

Reads `out/collect/changes.json` and writes `out/collect/sample-evidence.csv`. A sampled change that is not in
the population, has no checks, has no scanner check, or has a cut-off check list is listed in `missing`; it is
never reported as passing.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
from typing import Any

from grc_evidence.collect_changes import csv_cell
from grc_evidence.config import load_config
from grc_evidence.errors import GrcError

COLUMNS = ("repo", "number", "merged_at", "approvers", "ci_conclusion", "scanner_checks", "missing")
PASSING = ("SUCCESS", "NEUTRAL", "SKIPPED")
OUTPUT = "collect/sample-evidence.csv"


def read_sample_list(path: Path) -> list[tuple[str, int]]:
    """The auditor's sample: a CSV with the columns `repo` and `number` (other columns are ignored)."""
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not {"repo", "number"} <= set(reader.fieldnames or ()):
            raise GrcError(f"{path}: the header must name the columns repo,number")
        rows = []
        for line, row in enumerate(reader, 2):
            try:
                rows.append((row["repo"], int(row["number"])))
            except (TypeError, ValueError):
                raise GrcError(f"{path} line {line}: number {row['number']!r} is not a whole number") from None
    return rows


def _evidence(change: dict[str, Any], scanner_jobs: tuple[str, ...]) -> tuple[str, str, list[str]]:
    """The CI conclusion, the scanner checks, and what is missing for one change in the population."""
    checks = [(name, conclusion.upper()) for name, conclusion in change["checks"]]
    scanners = [(n, c) for n, c in checks if any(p.lower() in n.lower() for p in scanner_jobs)]
    missing = [] if checks else ["no-checks"]
    if not scanners:
        missing.append("no-scanner-check")
    if "checks_incomplete" in change["flags"].split(";"):
        missing.append("checks-incomplete")
        conclusion = "incomplete"
    elif not checks:
        conclusion = "none"
    else:
        conclusion = "success" if all(c in PASSING for _, c in checks) else "failure"
    return conclusion, ";".join(f"{n}={c}" for n, c in scanners), missing


def sample_evidence(changes_doc: dict, rows: list[tuple[str, int]], scanner_jobs: tuple[str, ...]) -> list[dict[str, Any]]:
    """One row per sampled change, with the columns of spec §6."""
    population = {(c["repo"].lower(), c["number"]): c for c in changes_doc["changes"]}
    out = []
    for repo, number in rows:
        change = population.get((repo.lower(), number))
        if change is None:
            out.append(dict(zip(COLUMNS, (repo, number, "", "", "none", "", "not-in-population"), strict=True)))
            continue
        conclusion, scanners, missing = _evidence(change, scanner_jobs)
        values = (repo, number, change["merged_at"], change["approvers"], conclusion, scanners, ";".join(missing))
        out.append(dict(zip(COLUMNS, values, strict=True)))
    return out


def main(argv: list[str]) -> None:
    """`grc sample --list FILE`: write out/collect/sample-evidence.csv for the sampled changes."""
    parser = argparse.ArgumentParser(prog="grc sample", description=main.__doc__)
    parser.add_argument("--list", required=True, type=Path, help="the auditor's sample: a CSV with columns repo,number")
    parser.add_argument("--config", help="grc.yaml to read github.scanner_jobs from (default: grc.yaml if present)")
    parser.add_argument("--out", type=Path, default=Path("out"))
    args = parser.parse_args(argv)
    population = args.out / "collect" / "changes.json"
    if not population.is_file():
        raise GrcError(f"{population}: no change population; run `grc run` or `grc collect changes` first")
    config = load_config(Path.cwd(), Path(args.config) if args.config else None)
    rows = sample_evidence(json.loads(population.read_text(encoding="utf-8")), read_sample_list(args.list), config.github_scanner_jobs)
    text = io.StringIO()
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(COLUMNS)
    writer.writerows([csv_cell(v) for v in row.values()] for row in rows)
    (args.out / OUTPUT).write_text(text.getvalue(), encoding="utf-8")
    print(f"{len(rows)} sampled changes, {sum(bool(r['missing']) for r in rows)} with missing evidence: {args.out / OUTPUT}")
