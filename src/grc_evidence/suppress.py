"""`grc suppress draft`: write a pending suppression for findings of the last scan (Spec I Part A).

The draft has every field except the reason and `verified`. A person writes the reason, deletes the draft marker
lines and signs it; until then it is pending (never applied) and `grc check` fails on it.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from importlib.metadata import version
from pathlib import Path
from typing import Any

import yaml

from grc_evidence.config import load_config
from grc_evidence.contract import read_mapping
from grc_evidence.errors import GrcError
from grc_evidence.okf_lib import (
    DRAFT_MARKER,
    MAX_SUPPRESSION_DAYS,
    SUPPRESSION_KINDS,
    SUPPRESSION_TYPE,
    Bundle,
    load_bundle,
)

Json = dict[str, Any]
DEFAULT_DAYS = 30
ID_MAX = 100
_ID = re.compile(r"[a-z0-9][a-z0-9-]*")
_RESERVED = ("index", "log")  # the folder's own files
_OWNER = re.compile(r"human:[^\s<>]+")
MARKER_LINE = f"{DRAFT_MARKER}. Write this section, then delete this line. -->"


class DraftError(GrcError):
    """A draft the engine refuses to write."""


@dataclass(frozen=True)
class Request:
    """What the person asked for: one tool and rule id in one or more named files."""

    tool: str
    rule_id: str
    targets: tuple[str, ...]
    kind: str
    owner: str
    days: int = DEFAULT_DAYS
    id: str | None = None


def slug(*parts: str) -> str:
    """Lowercase, each run of other characters as one `-`, at most 100 characters."""
    return re.sub(r"[^a-z0-9]+", "-", "-".join(parts).lower()).strip("-")[:ID_MAX].rstrip("-")


def _facts(mapping: Json, req: Request) -> dict[str, list[tuple[Json, list[str]]]]:
    """Each target's findings in the last scan, each with the controls it is on (none: a coverage gap)."""
    on: dict[tuple[str, str, str], tuple[Json, list[str]]] = {}
    for key, entry in mapping["controls"].items():
        for f in entry["findings"]:
            on.setdefault((f["target"], f["message"], f["severity"]), (f, []))[1].append(key)
    for u in mapping["unmapped"]:
        on.setdefault((u["finding"]["target"], u["finding"]["message"], u["finding"]["severity"]), (u["finding"], []))
    facts: dict[str, list[tuple[Json, list[str]]]] = {t: [] for t in req.targets}
    for f, keys in on.values():
        if (f["tool"], f["rule_id"]) == (req.tool, req.rule_id) and f["target"] in facts:
            facts[f["target"]].append((f, sorted(keys)))
    return facts


def _check(bundle: Bundle, req: Request, facts: dict[str, list[tuple[Json, list[str]]]]) -> None:
    if not _OWNER.fullmatch(req.owner):
        hint = "replace <you> with your name" if "<" in req.owner else "human:<name>"
        raise DraftError(f"--owner must be a person ({hint})")
    if not 1 <= req.days <= MAX_SUPPRESSION_DAYS:
        raise DraftError(f"--days must be from 1 to {MAX_SUPPRESSION_DAYS}")
    if req.id is not None and not (_ID.fullmatch(req.id) and len(req.id) <= ID_MAX and req.id not in _RESERVED):
        raise DraftError(f"--id must be lowercase letters, digits and '-', at most {ID_MAX} characters, not index or log")
    for target, found in facts.items():
        if not found:
            raise DraftError(f"no {req.tool}:{req.rule_id} finding in {target} in the last scan")
        if req.kind == "accepted-risk" and not any(keys for _, keys in found):
            raise DraftError(f"{req.tool}:{req.rule_id} in {target} is a coverage gap; only false-positive applies")
    for s in bundle.suppressions():
        if (s.tool, s.rule_id) == (req.tool, req.rule_id) and (named := sorted(set(s.targets) & set(req.targets))):
            raise DraftError(f"{s.id}.md already names {', '.join(named)}; edit or remove it first")


def _body(req: Request, facts: dict[str, list[tuple[Json, list[str]]]]) -> str:
    lines = ["# Reason", "", MARKER_LINE, "", "From the last scan (scanner text, quoted as reported):", ""]
    for target, found in facts.items():
        for f, keys in found:
            where = f"controls: {', '.join(keys)}" if keys else "coverage gap"
            lines.append(f'- `{target}`: {f["severity"]}, "{" ".join(f["message"].split())}" ({where})')
    if req.kind == "accepted-risk":
        lines += ["", "# Compensating control", "", MARKER_LINE]
    return "\n".join(lines) + "\n"


def draft(bundle: Bundle, mapping: Json, req: Request, today: date, now: str) -> tuple[str, str]:
    """The new suppression's path in the bundle and its text; `DraftError` when the request is refused."""
    facts = _facts(mapping, req)
    _check(bundle, req, facts)
    target = req.targets[0] if len(req.targets) == 1 else None
    finding = {"tool": req.tool, "rule_id": req.rule_id} | ({"target": target} if target else {"targets": list(req.targets)})
    fm = {
        "type": SUPPRESSION_TYPE,
        "title": f"{req.rule_id} in {target or f'{len(req.targets)} files'}",
        "kind": req.kind,
        "finding": finding,
        "owner": req.owner,
        "approved": today.isoformat(),
        "expires": (today + timedelta(days=req.days)).isoformat(),
        "tags": ["suppression"],
        "generated": {"by": f"grc-evidence/{version('grc-evidence')}", "at": now},
    }
    sid = req.id or slug(req.tool, req.rule_id, *([target] if target else []))
    text = f"---\n{yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, width=1000)}---\n{_body(req, facts)}"
    return f"suppressions/{sid}.md", text


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="grc suppress", description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    p = actions.add_parser("draft", help="write a pending suppression for findings of the last scan")
    p.add_argument("--tool", required=True)
    p.add_argument("--rule-id", required=True)
    p.add_argument("--target", action="append", required=True, help="an exact file; repeat for one rule in several files")
    p.add_argument("--kind", choices=SUPPRESSION_KINDS, required=True)
    p.add_argument("--owner", required=True, help="the person accountable: human:<name>")
    p.add_argument("--days", type=int, default=DEFAULT_DAYS, help=f"until expiry, 1 to {MAX_SUPPRESSION_DAYS}")
    p.add_argument("--id", default=None, help="file name in suppressions/ (default: from the tool, rule id and target)")
    p.add_argument("--config", type=Path, default=None, help="scan layout (default: grc.yaml if present)")
    p.add_argument("--knowledge", default=None, help="knowledge bundle (overrides the config)")
    p.add_argument("--out", type=Path, default=Path("out"), help="where `grc run` wrote mapping.json")
    p.add_argument("--today", type=date.fromisoformat, default=None, help="approval date (default: today, UTC)")
    args = parser.parse_args(argv)
    knowledge = Path(load_config(Path.cwd(), args.config, knowledge=args.knowledge).knowledge)
    req = Request(args.tool, args.rule_id, tuple(sorted(set(args.target))), args.kind, args.owner, args.days, args.id)
    now = datetime.now(UTC)
    rel, text = draft(load_bundle(knowledge), read_mapping(args.out / "mapping.json"), req, args.today or now.date(),
                      now.isoformat(timespec="seconds"))
    path = knowledge / rel
    path.parent.mkdir(exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as f:
            f.write(text)
    except FileExistsError as e:
        raise DraftError(f"{path} exists; pass --id") from e
    print(f"suppress: wrote {path} (pending: not applied until a person signs it)\n"
          "Next: write each section, delete the draft marker lines, add `verified` with your human: name,\n"
          "then run `grc check` and the scan and gate.")


if __name__ == "__main__":
    main()
