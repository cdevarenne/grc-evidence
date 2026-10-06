"""`grc collect` and the collect step of `grc run` (Spec H): read GitHub, write `out/collect/`, return ledger entries.

Every repo is read before anything is written, so a failed collection writes no output and appends no ledger
entry. The ledger is written only when `grc.yaml` has a `window`: that is how a repo opts into Type 2 evidence.
`grc collect` alone appends its `scm` and `changes` entries but no `run` entry; control status, and so the
window report, comes only from `grc run`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

from grc_evidence import ledger
from grc_evidence.collect_changes import (
    change_findings,
    collect_changes,
    write_population,
)
from grc_evidence.collect_scm import posture_findings, posture_summary, read_posture
from grc_evidence.config import COLLECTORS, Config, load_config
from grc_evidence.contract import read_mapping
from grc_evidence.data import SCHEMA_VERSION
from grc_evidence.errors import GrcError
from grc_evidence.github_api import (
    HttpTransport,
    RecordedTransport,
    RecordingTransport,
    Transport,
    rate_limit,
    token_from_env,
)
from grc_evidence.github_queries import DEFAULT_BRANCH
from grc_evidence.people import namer_from_config

# Rule-id prefixes each collector produces: a collector no repo lists did not run, so its rules are not a pass.
COLLECTOR_RULES = {"scm": "github:scm-", "changes": "github:change-"}
FINDINGS = "collect/github-findings.json"
POSTURE = "collect/scm-posture.json"
FIXTURES_ENV = "GRC_GITHUB_FIXTURES"  # tests and offline examples only: read recorded responses from this folder


def collectors_not_run(config: Config) -> list[str]:
    """`github` when no repo lists a collector, else the rule prefixes of the collectors none lists."""
    listed = {c for repo in config.github_repos for c in repo.collect}
    if not listed:
        return ["github"]
    return [prefix for collector, prefix in COLLECTOR_RULES.items() if collector not in listed]


def transport_from_env() -> Transport:
    if fixtures := os.environ.get(FIXTURES_ENV):
        return RecordedTransport(Path(fixtures))
    return HttpTransport(token_from_env())


class _Metered:
    """Passes reads through and keeps what the ledger records: the query hashes and the rate-limit cost."""

    def __init__(self, inner: Transport) -> None:
        self._inner, self._queries, self._cost, self._remaining = inner, set[str](), 0, None

    def graphql(self, query: str, variables: dict) -> dict:
        data = self._inner.graphql(query, variables)
        self._queries.add(hashlib.sha256(query.encode()).hexdigest())
        if rl := rate_limit(data):
            self._cost, self._remaining = self._cost + rl["cost"], rl["remaining"]
        return data

    def rest(self, path: str) -> dict | list | None:
        return self._inner.rest(path)

    def queries(self) -> list[str]:
        return sorted(self._queries)

    def rate_limit(self) -> dict | None:
        return {"cost": self._cost, "remaining": self._remaining} if self._remaining is not None else None


def run_collect(
    config: Config, out: Path, transport: Transport, now: str, collectors: tuple[str, ...] = COLLECTORS
) -> list[dict[str, Any]]:
    """Read every listed repo, then write `out/collect/`; returns the ledger entries for the caller to append."""
    wanted = [(repo, c) for repo in config.github_repos for c in repo.collect if c in collectors]
    if not wanted:
        return []
    with_changes = any(c == "changes" for _, c in wanted)
    bounds = config.bounds() if with_changes else None
    namer = namer_from_config(config) if with_changes else None
    window = {"start": config.window_start.isoformat(), "end": config.window_end.isoformat()} if config.window_start and config.window_end else None
    past = ledger.read(Path(config.ledger))
    bots = frozenset(b.login for b in config.github_accepted_bots)
    findings: list[dict] = []
    postures: list[dict] = []
    changes: list = []
    summaries: dict[str, dict] = {}
    pending = []
    outputs: tuple[str, ...]
    for repo, collector in wanted:
        metered = _Metered(transport)
        if collector == "scm":
            posture = read_posture(metered, repo, config.github_scanner_jobs)
            findings += posture_findings(posture)
            postures.append(asdict(posture))
            branch, summary, outputs = posture.branch, posture_summary(posture), (FINDINGS, POSTURE)
        else:
            assert bounds is not None and namer is not None
            owner, name = repo.name.split("/")
            branch = metered.graphql(DEFAULT_BRANCH, {"owner": owner, "name": name})["repository"]["defaultBranchRef"]["name"]
            found, summary = collect_changes(metered, repo, bounds, config.github_branches, branch, past, namer, bots)
            changes += found
            findings += change_findings(found)
            summaries[repo.name] = summary
            outputs = (FINDINGS, "collect/population.csv", "collect/changes.json")
        inputs = {"query_sha256": metered.queries(), "branch": branch}
        pending.append((collector, repo.name, inputs, summary, metered.rate_limit(), outputs))
    hashes = _write(out, findings, postures, changes, summaries)
    engine = version("grc-evidence")
    return [
        ledger.make_entry(c, repo, window, inputs, {rel: hashes[rel] for rel in outputs}, summary, rl, now, engine)
        for c, repo, inputs, summary, rl, outputs in pending
    ]


def _write(out: Path, findings: list[dict], postures: list[dict], changes: list, summaries: dict) -> dict[str, str]:
    files = {FINDINGS: json.dumps({"schema_version": SCHEMA_VERSION, "findings": findings}, indent=2) + "\n"}
    if postures:
        files[POSTURE] = json.dumps({"repos": postures}, indent=2) + "\n"
    (out / "collect").mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        (out / rel).write_text(text, encoding="utf-8")
    hashes = {rel: hashlib.sha256(text.encode()).hexdigest() for rel, text in files.items()}
    if summaries:
        hashes |= write_population(out, changes, summaries)
    return hashes


def run_step(config: Config, out: Path, now: str) -> list[dict[str, Any]]:
    """The collect step of `grc run`: nothing, and no token needed, when no repo lists a collector."""
    if not any(repo.collect for repo in config.github_repos):
        return []
    return run_collect(config, out, transport_from_env(), now)


def append_run(config: Config, entries: list[dict[str, Any]], out: Path, now: str) -> None:
    """After `grc run` replaced its outputs: the collect entries, then one `run` entry with every control's status."""
    if config.window_start is None or config.window_end is None:
        return
    path = Path(config.ledger)
    for entry in entries:
        ledger.append(path, entry)
    run_json = (out / "run.json").read_bytes()
    statuses = {key: c["status"] for key, c in read_mapping(out / "mapping.json")["controls"].items()}
    window = {"start": config.window_start.isoformat(), "end": config.window_end.isoformat()}
    ledger.append(path, ledger.make_entry(
        "run", None, window, {"run_id": json.loads(run_json)["run_id"]},
        {"run.json": hashlib.sha256(run_json).hexdigest()}, statuses, None, now, version("grc-evidence"),
    ))


def main(argv: list[str]) -> None:
    """`grc collect {scm,changes,all}`: read GitHub into out/collect/ and append the entries (no `run` entry)."""
    parser = argparse.ArgumentParser(prog="grc collect", description=main.__doc__)
    parser.add_argument("collector", choices=(*COLLECTORS, "all"))
    parser.add_argument("--config", help="grc.yaml to use (default: grc.yaml if present)")
    parser.add_argument("--out", default="out")
    parser.add_argument("--record", help="also save each response, logins named, into this folder (test fixtures); "
                                         "appends nothing to the ledger")
    args = parser.parse_args(argv)
    config = load_config(Path.cwd(), Path(args.config) if args.config else None)
    transport = transport_from_env()
    if args.record:
        transport = RecordingTransport(transport, Path(args.record), namer_from_config(config))
    collectors = COLLECTORS if args.collector == "all" else (args.collector,)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    entries = run_collect(config, Path(args.out), transport, now, collectors)
    if not entries:
        raise GrcError(f"no repo in grc.yaml lists the {args.collector} collector")
    if not args.record and config.window_start is not None:
        for entry in entries:
            ledger.append(Path(config.ledger), entry)
    print(f"collected {len(entries)} entries into {Path(args.out) / 'collect'}")
