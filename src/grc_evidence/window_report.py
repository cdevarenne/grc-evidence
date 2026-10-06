"""`grc window` (Spec H §6): each control's history over the audit window, from the ledger's `run` entries only.

A day's status is the last `run` entry recorded that day (UTC). A gap is a run of days in the window when the
control was not `no-violations-detected` (a control missing from a run counts too), or a silence with no run
longer than `window_max_gap_days`, for its whole length. While the window is open, it is read up to today.
The window report is never built from a ledger that fails `grc ledger verify`, and never back-fills a day.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from grc_evidence import ledger
from grc_evidence.config import load_config
from grc_evidence.window import Bounds, in_window, parse_ts

OK = "no-violations-detected"


def _days(bounds: Bounds, today: date, by_day: dict[date, dict]) -> list[date]:
    """The window's days, up to today while the window is open; today only once it has a run."""
    first, last = bounds[0].date(), min(bounds[1].date() - timedelta(days=1), today)
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    return days[:-1] if days and days[-1] == today and today not in by_day else days


def _by_day(entries: list[dict], bounds: Bounds) -> dict[date, dict]:
    """The summary of each day's latest `run` entry in the window, by its time, not its line."""
    latest: dict[date, tuple[datetime, dict]] = {}
    for e in entries:
        if e.get("collector") == "run" and in_window(ts := parse_ts(e["recorded_at"]), bounds):
            if ts.date() not in latest or ts >= latest[ts.date()][0]:
                latest[ts.date()] = (ts, e.get("summary") or {})
    return {day: summary for day, (_, summary) in latest.items()}


def _silent(days: list[date], by_day: dict[date, dict], max_gap_days: int) -> set[date]:
    """Days inside a run of days with no entry that is longer than `max_gap_days`."""
    silent: set[date] = set()
    quiet: list[date] = []
    for day in [*days, None]:
        if day is not None and day not in by_day:
            quiet.append(day)
            continue
        if len(quiet) > max_gap_days:
            silent.update(quiet)
        quiet = []
    return silent


def _spans(days: list[date]) -> list[list[str]]:
    """Consecutive days joined into [first, last] spans."""
    spans: list[list[date]] = []
    for day in sorted(days):
        if spans and day - spans[-1][1] == timedelta(days=1):
            spans[-1][1] = day
        else:
            spans.append([day, day])
    return [[a.isoformat(), b.isoformat()] for a, b in spans]


def silences(entries: list[dict], bounds: Bounds, max_gap_days: int, today: date | None = None) -> list[list[str]]:
    """The spans with no run that are longer than `max_gap_days`."""
    by_day = _by_day(entries, bounds)
    return _spans(list(_silent(_days(bounds, today or datetime.now(UTC).date(), by_day), by_day, max_gap_days)))


def window_status(entries: list[dict], bounds: Bounds, max_gap_days: int, today: date | None = None) -> dict[str, dict[str, Any]]:
    """Per control key: `first_satisfied`, `last_evidence` (dates `YYYY-MM-DD`, UTC) and `gaps` ([first, last] spans)."""
    by_day = _by_day(entries, bounds)
    days = _days(bounds, today or datetime.now(UTC).date(), by_day)
    silent = _silent(days, by_day, max_gap_days)
    status = {}
    for key in sorted({k for summary in by_day.values() for k in summary}):
        seen = [d for d in days if key in by_day.get(d, {})]
        satisfied = [d for d in seen if by_day[d][key] == OK]
        bad = [d for d in days if d in silent or (d in by_day and by_day[d].get(key) != OK)]
        status[key] = {
            "first_satisfied": satisfied[0].isoformat() if satisfied else None,
            "last_evidence": seen[-1].isoformat() if seen else None,
            "gaps": _spans(bad),
        }
    return status


def render_window(status: dict[str, dict[str, Any]], quiet: list[list[str]], bounds: Bounds, run_days: int) -> str:
    """The window report as Markdown: one row per control."""
    start, end = bounds[0].date().isoformat(), (bounds[1].date() - timedelta(days=1)).isoformat()
    lines = [
        "# Control history over the audit window", "",
        f"Window {start} to {end} (UTC): {run_days} days with a run in the evidence ledger.",
        ("A gap is a period when the control was not `no-violations-detected`, or a silence with no run longer than "
         "the allowed gap."), "",
    ]
    if quiet:
        lines += [f"Silences with no run: {', '.join(_span_text(s) for s in quiet)}.", ""]
    lines += ["| Control | First satisfied | Last evidence | Gaps |", "|---|---|---|---|"]
    for key, s in status.items():
        gaps = ", ".join(_span_text(g) for g in s["gaps"]) or "none"
        lines.append(f"| `{key}` | {s['first_satisfied'] or '—'} | {s['last_evidence'] or '—'} | {gaps} |")
    return "\n".join(lines) + "\n"


def _span_text(span: list[str]) -> str:
    return span[0] if span[0] == span[1] else f"{span[0]} to {span[1]}"


def main(argv: list[str]) -> None:
    """`grc window`: write out/window.json and out/window.md from the evidence ledger."""
    parser = argparse.ArgumentParser(prog="grc window", description=main.__doc__)
    parser.add_argument("--config", help="grc.yaml with the window (default: grc.yaml if present)")
    parser.add_argument("--out", type=Path, default=Path("out"))
    args = parser.parse_args(argv)
    config = load_config(Path.cwd(), Path(args.config) if args.config else None)
    bounds, path = config.bounds(), Path(config.ledger)
    if problem := ledger.first_problem(path):
        raise ledger.LedgerError(f"ledger line {problem[0]}: {problem[1]}; the window report needs a valid ledger")
    entries = ledger.read(path)
    today = datetime.now(UTC).date()
    status = window_status(entries, bounds, config.window_max_gap_days, today)
    quiet = silences(entries, bounds, config.window_max_gap_days, today)
    run_days = len(_by_day(entries, bounds))
    doc = {
        "window": {"start": bounds[0].date().isoformat(), "end": (bounds[1].date() - timedelta(days=1)).isoformat()},
        "max_gap_days": config.window_max_gap_days, "run_days": run_days, "silences": quiet, "controls": status,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "window.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    (args.out / "window.md").write_text(render_window(status, quiet, bounds, run_days), encoding="utf-8")
    print(f"window report: {len(status)} controls over {run_days} days with a run: {args.out / 'window.md'}")
