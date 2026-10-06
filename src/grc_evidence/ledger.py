"""The evidence ledger: one JSON object per line, only appended, each line chained to the one before (Spec H §3.2).

`entry_id` is the sha256 of the canonical JSON of the entry without `entry_id`; `prev_id` is the `entry_id`
of the line before, or null on the first line. An edited, deleted or reordered line fails `verify`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from grc_evidence.config import load_config
from grc_evidence.errors import GrcError

LEDGER_SCHEMA = "1.0"
Entry = dict[str, Any]


class LedgerError(GrcError, ValueError):
    """The ledger is not a valid hash chain."""


def canonical(obj: Entry) -> bytes:
    """Keys sorted, no spaces, UTF-8, no NaN or Infinity: the bytes that are hashed and written."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _entry_id(entry: Entry) -> str:
    return hashlib.sha256(canonical({k: v for k, v in entry.items() if k != "entry_id"})).hexdigest()


def make_entry(
    collector: str, repo: str | None, window: dict | None, inputs: dict, outputs: dict[str, str], summary: dict,
    rate_limit: dict | None, now: str, engine_version: str, supersedes: str | None = None,
) -> Entry:
    """An entry before `append` adds `schema_version`, `prev_id` and `entry_id`."""
    return {
        "recorded_at": now, "engine_version": engine_version, "collector": collector, "repo": repo, "window": window,
        "inputs": inputs, "outputs": outputs, "summary": summary, "rate_limit": rate_limit, "supersedes": supersedes,
    }


def read(path: Path) -> list[Entry]:
    """Every entry, in order; no entries when the file does not exist."""
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def append(path: Path, entry: Entry) -> Entry:
    """Chain `entry` to the last line and append it; returns the stored entry."""
    entries = read(path)
    stored = {**entry, "schema_version": LEDGER_SCHEMA, "prev_id": entries[-1]["entry_id"] if entries else None}
    stored["entry_id"] = _entry_id(stored)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as f:
        f.write(canonical(stored) + b"\n")
    return stored


def first_problem(path: Path) -> tuple[int, str] | None:
    """The 1-based number of the first bad line and why, or None for a valid chain."""
    if not path.is_file():
        return None
    prev = None
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            return number, "not JSON"
        # A line must be exactly what was hashed, so every JSON reader sees the same entry: this rejects
        # duplicate keys, other spacing or key order, and NaN or Infinity.
        if not isinstance(entry, dict) or not _is_canonical(line, entry):
            return number, "not canonical"
        if entry.get("entry_id") != _entry_id(entry):
            return number, "hash mismatch"
        if entry.get("prev_id") != prev:
            return number, "broken chain"
        prev = entry["entry_id"]
    return None


def _is_canonical(line: str, entry: Entry) -> bool:
    try:
        return canonical(entry) == line.encode()
    except ValueError:  # NaN or Infinity
        return False


def verify(path: Path) -> int | None:
    """The 1-based number of the first bad line, or None."""
    problem = first_problem(path)
    return problem[0] if problem else None


def main(argv: list[str]) -> None:
    """`grc ledger verify`: check every entry_id and the prev_id chain."""
    parser = argparse.ArgumentParser(prog="grc ledger", description=main.__doc__)
    parser.add_argument("action", choices=("verify",))
    parser.add_argument("--config", help="grc.yaml to read the ledger path from (default: grc.yaml if present)")
    parser.add_argument("--ledger", help="ledger file (overrides the config)")
    args = parser.parse_args(argv)
    path = Path(args.ledger or load_config(Path.cwd(), Path(args.config) if args.config else None).ledger)
    if problem := first_problem(path):
        raise LedgerError(f"ledger line {problem[0]}: {problem[1]}")
    print(f"ok: {path}: {len(read(path))} entries, chain intact")
