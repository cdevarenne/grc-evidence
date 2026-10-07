"""Scan layout from an optional `grc.yaml`: what each scanner reads and which policies it applies.

Scan inputs (`inventory`, `conftest.inputs`, `checkov.skip_paths`) are relative to the target;
`target`, `knowledge`, `semgrep.configs`, `rego`, `ledger` and `github.repos_file` are relative to the
repo root. With no file, the defaults are the v1.0 layout. The evidence keys (`window`, `ledger`,
`people`, `people_salt_env`, `github`) configure the Type 2 collectors (Spec H); `review` sets how long a
person's verification of a concept stays valid (Spec J).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from grc_evidence.errors import GrcError
from grc_evidence.window import Bounds, utc_bounds

CONFIG_FILE = "grc.yaml"
# Accepted keys: a type for a leaf, a nested dict for a section.
_SHAPE: dict[str, Any] = {
    "target": str,
    "knowledge": str,
    "inventory": str,
    "skip_paths": list,
    "rego": list,
    "scanner_timeout": int,
    "allow_external_symlinks": bool,
    "conftest": {"inputs": list},
    "checkov": {"frameworks": list, "skip_paths": list},
    "semgrep": {"configs": list},
    "ledger": str,
    "people": str,
    "people_salt_env": str,
}
TIERS = ("in-scope", "library", "deferred", "dormant")
COLLECTORS = ("scm", "changes")
_REPO_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+")
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_DURATION = re.compile(r"[1-9][0-9]*[dmy]")  # days, calendar months, calendar years
REVIEW_BASE = ("warn", "fail")


class ConfigError(GrcError, ValueError):
    """`grc.yaml` or a command-line override is malformed or points outside the repo."""


@dataclass(frozen=True)
class RepoSpec:
    """One target repo: `owner/name`, its tier, and the collectors that read it."""

    name: str
    tier: str
    collect: tuple[str, ...] = ()


@dataclass(frozen=True)
class AcceptedBot:
    """A bot whose review approvals count, with the team's reason, for an auditor to accept or reject."""

    login: str  # lower case, without GitHub's `[bot]` suffix
    reason: str


@dataclass(frozen=True)
class Config:
    """The resolved scan layout; field names are the YAML keys with `.` as `_`."""

    target: str = "app"
    knowledge: str = "knowledge"
    inventory: str = "ai-inventory.yaml"
    conftest_inputs: tuple[str, ...] = ("k8s/**/*.yaml", "k8s/**/*.yml", "infra/**/*.tf", "ai-inventory.yaml")
    checkov_frameworks: tuple[str, ...] = ("terraform", "kubernetes", "dockerfile")
    checkov_skip_paths: tuple[str, ...] = ()
    skip_paths: tuple[str, ...] = ()  # target-relative directories Trivy and Checkov skip (templated or duplicate files)
    semgrep_configs: tuple[str, ...] = ("policies/semgrep",)
    rego: tuple[str, ...] = ("policies/rego",)
    scanner_timeout: int = 900  # seconds per scanner; a hung scanner stops the scan with its name
    allow_external_symlinks: bool = False  # accept a Conftest input that is a symlink out of the repo
    window_start: date | None = None
    window_end: date | None = None
    window_max_gap_days: int = 7  # a longer silence in the ledger is a gap in the window report
    ledger: str = "evidence/ledger.jsonl"
    people: str = "real"  # or pseudonymous: logins in outputs become p-<HMAC>
    people_salt_env: str = "GRC_PEOPLE_SALT"
    github_repos: tuple[RepoSpec, ...] = ()
    github_branches: tuple[str, ...] = ()  # production branches beside each repo's default branch
    github_scanner_jobs: tuple[str, ...] = ()  # CI job names that must run a scanner and fail the build
    github_accepted_bots: tuple[AcceptedBot, ...] = ()  # bot reviewers whose approvals count; none by default
    review_default: str | None = None  # without a `review:` section, only a concept's own stale_after counts
    review_by_type: tuple[tuple[str, str], ...] = ()  # (concept type, interval)
    review_warn_before: str = "30d"
    review_base: str = "warn"  # an overdue base-bundle copy: warn (adopters) or fail (the engine's own repo)

    def bounds(self) -> Bounds:
        """The window as UTC bounds; an error when `grc.yaml` has no window."""
        if self.window_start is None or self.window_end is None:
            raise ConfigError("no window in grc.yaml")
        return utc_bounds(self.window_start, self.window_end)


def load_config(repo: Path, path: Path | None = None, **overrides: str | None) -> Config:
    """`grc.yaml` (or `path`) over the defaults, then the non-None `overrides` (command-line flags), checked."""
    file = repo / (path or CONFIG_FILE)
    if path is not None and not file.is_file():
        raise ConfigError(f"{path}: no such config file")
    raw = (yaml.safe_load(file.read_text(encoding="utf-8")) or {}) if file.is_file() else {}
    evidence = _evidence(repo, raw)
    config = replace(Config(), **_fields(raw, _SHAPE, ""), **evidence)
    config = replace(config, **_fields({k: v for k, v in overrides.items() if v is not None}, _SHAPE, ""))
    _check_paths(repo, config)
    _check_people(config)
    return config


def _evidence(repo: Path, raw: Any) -> dict[str, Any]:
    """Config fields from the nested evidence keys `window` and `github`, removed from `raw`."""
    if not isinstance(raw, dict):
        return {}
    fields: dict[str, Any] = {}
    if "window" in raw:
        fields |= _window(raw.pop("window"))
    if "github" in raw:
        fields |= _github(repo, raw.pop("github"))
    if "review" in raw:
        fields |= _review(raw.pop("review"))
    return fields


def _review(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ConfigError("'review' must be a mapping with default, by_type, warn_before and base")
    if unknown := sorted(raw.keys() - {"default", "by_type", "warn_before", "base"}):
        raise ConfigError(f"unknown key 'review.{unknown[0]}'")
    by_type = raw.get("by_type", {})
    if not isinstance(by_type, dict):
        raise ConfigError("'review.by_type' must map a concept type to an interval")
    fields: dict[str, Any] = {
        "review_by_type": tuple((str(t), _duration(v, f"review.by_type.{t}")) for t, v in by_type.items()),
    }
    if "default" in raw:
        fields["review_default"] = _duration(raw["default"], "review.default")
    if "warn_before" in raw:
        fields["review_warn_before"] = _duration(raw["warn_before"], "review.warn_before")
    if "base" in raw:
        if raw["base"] not in REVIEW_BASE:
            raise ConfigError(f"'review.base' must be one of {', '.join(REVIEW_BASE)}")
        fields["review_base"] = raw["base"]
    return fields


def _duration(value: Any, key: str) -> str:
    if not isinstance(value, str) or not _DURATION.fullmatch(value):
        raise ConfigError(f"'{key}' must be a number of days, months or years, such as 90d, 6m or 1y")
    return value


def _window(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ConfigError("'window' must be a mapping with start and end")
    if unknown := sorted(raw.keys() - {"start", "end", "max_gap_days"}):
        raise ConfigError(f"unknown key 'window.{unknown[0]}'")
    start, end = _date(raw.get("start"), "window.start"), _date(raw.get("end"), "window.end")
    if end < start:
        raise ConfigError(f"'window.end' {end} is before 'window.start' {start}")
    gap = raw.get("max_gap_days", 7)
    if isinstance(gap, bool) or not isinstance(gap, int) or gap <= 0:
        raise ConfigError("'window.max_gap_days' must be a positive whole number of days")
    return {"window_start": start, "window_end": end, "window_max_gap_days": gap}


def _date(value: Any, key: str) -> date:
    """A YAML date, or a string in `YYYY-MM-DD` form."""
    if type(value) is date:
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ConfigError(f"'{key}' must be a date (YYYY-MM-DD)")


def _github(repo: Path, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ConfigError("'github' must be a mapping")
    if unknown := sorted(raw.keys() - {"repos", "repos_file", "branches", "scanner_jobs", "accepted_bots"}):
        raise ConfigError(f"unknown key 'github.{unknown[0]}'")
    lists = {k: raw[k] for k in ("branches", "scanner_jobs") if k in raw}
    items = raw.get("repos", [])
    if not isinstance(items, list):
        raise ConfigError("'github.repos' must be a list of repos")
    labeled = [(f"github.repos[{i}]", item) for i, item in enumerate(items)]
    if "repos_file" in raw:
        labeled += _repos_file(repo, raw["repos_file"])
    return {
        "github_repos": _repos(labeled), "github_accepted_bots": _accepted_bots(raw.get("accepted_bots", [])),
        **_fields(lists, {"branches": list, "scanner_jobs": list}, "github."),
    }


def _accepted_bots(items: Any) -> tuple[AcceptedBot, ...]:
    if not isinstance(items, list):
        raise ConfigError("'github.accepted_bots' must be a list of {login, reason}")
    bots = []
    for i, item in enumerate(items):
        key = f"github.accepted_bots[{i}]"
        if not isinstance(item, dict) or item.keys() != {"login", "reason"}:
            raise ConfigError(f"'{key}' must be a mapping with login and reason")
        if not isinstance(item["login"], str) or not item["login"].strip():
            raise ConfigError(f"'{key}.login' must be a bot login")
        if not isinstance(item["reason"], str) or not item["reason"].strip():
            raise ConfigError(f"'{key}.reason' must say why this bot's approvals are accepted")
        bots.append(AcceptedBot(item["login"].strip().lower().removesuffix("[bot]"), item["reason"].strip()))
    return tuple(bots)


def _repos_file(repo: Path, rel: Any) -> list[tuple[str, Any]]:
    """The items of `github.repos_file`, a YAML list in the same shape as `github.repos`."""
    if not isinstance(rel, str) or not rel:
        raise ConfigError("'github.repos_file' must be a string")
    path = repo / rel
    if not path.resolve().is_relative_to(repo.resolve()):
        raise ConfigError(f"github.repos_file {rel!r} leaves the repo root")
    if not path.is_file():
        raise ConfigError(f"github.repos_file {rel!r}: no such file")
    items = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(items, list):
        raise ConfigError(f"github.repos_file {rel!r} must hold a list of repos")
    return [(f"{rel}[{i}]", item) for i, item in enumerate(items)]


def _repos(labeled: list[tuple[str, Any]]) -> tuple[RepoSpec, ...]:
    specs: list[RepoSpec] = []
    seen: set[str] = set()
    for key, item in labeled:
        if not isinstance(item, dict) or not {"name", "tier"} <= item.keys() <= {"name", "tier", "collect"}:
            raise ConfigError(f"'{key}' must be a mapping with name, tier and an optional collect list")
        name, tier, collect = item["name"], item["tier"], item.get("collect", [])
        if not isinstance(name, str) or not _REPO_NAME.fullmatch(name):
            raise ConfigError(f"'{key}.name' {name!r} must be owner/name")
        if name.lower() in seen:  # GitHub names do not depend on case
            raise ConfigError(f"'{key}.name' {name!r} is listed twice")
        if tier not in TIERS:
            raise ConfigError(f"'{key}.tier' {tier!r} must be one of {', '.join(TIERS)}")
        if not isinstance(collect, list) or any(c not in COLLECTORS for c in collect):
            raise ConfigError(f"'{key}.collect' must be a list of {', '.join(COLLECTORS)}")
        seen.add(name.lower())
        specs.append(RepoSpec(name, tier, tuple(collect)))
    return tuple(specs)


def _check_people(config: Config) -> None:
    if config.people not in ("real", "pseudonymous"):
        raise ConfigError(f"'people' must be real or pseudonymous, not {config.people!r}")
    if not _ENV_NAME.fullmatch(config.people_salt_env):
        raise ConfigError(f"'people_salt_env' {config.people_salt_env!r} must be an environment variable name")


def _fields(raw: Any, shape: dict[str, Any], prefix: str) -> dict[str, Any]:
    """Validate `raw` against `shape` and flatten it to Config field names."""
    if not isinstance(raw, dict):
        raise ConfigError(f"{prefix.rstrip('.') or CONFIG_FILE} must be a mapping")
    fields: dict[str, Any] = {}
    for key, value in raw.items():
        name = f"{prefix}{key}"
        kind = shape.get(key)
        if kind is None:
            raise ConfigError(f"unknown key {name!r}")
        if isinstance(kind, dict):
            fields |= _fields(value, kind, f"{name}.")
            continue
        if kind is bool:
            if not isinstance(value, bool):
                raise ConfigError(f"{name!r} must be true or false")
            fields[name] = value
            continue
        if kind is int:
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ConfigError(f"{name!r} must be a positive whole number of seconds")
            fields[name] = value
            continue
        values = value if kind is list else [value]
        if (kind is list and not isinstance(value, list)) or not all(isinstance(v, str) and v for v in values):
            raise ConfigError(f"{name!r} must be {'a list of strings' if kind is list else 'a string'}")
        if any(v.startswith("-") for v in values):
            raise ConfigError(f"{name!r}: a value may not start with '-'")
        fields[name.replace(".", "_")] = tuple(value) if kind is list else value
    return fields


def _check_paths(repo: Path, config: Config) -> None:
    root = repo.resolve()

    def inside(rel: str, key: str) -> None:
        if not (repo / rel).resolve().is_relative_to(root):
            raise ConfigError(f"{key} {rel!r} leaves the repo root")

    inside(config.target, "target")
    inside(config.knowledge, "knowledge")
    inside(config.ledger, "ledger")
    inside(f"{config.target}/{config.inventory}", "inventory")
    for rel in config.semgrep_configs:
        inside(rel, "semgrep.configs")
    for rel in config.rego:
        inside(rel, "rego")
    # Conftest inputs may reach beside the target (an inventory next to a submodule); the scan checks that
    # every file they match stays inside the repo.
    for pattern in config.conftest_inputs:
        if PurePosixPath(pattern).is_absolute():
            raise ConfigError(f"conftest.inputs {pattern!r} must be relative to the target")
    for key, patterns in (("skip_paths", config.skip_paths), ("checkov.skip_paths", config.checkov_skip_paths)):
        for pattern in patterns:
            if PurePosixPath(pattern).is_absolute() or ".." in PurePosixPath(pattern).parts:
                raise ConfigError(f"{key} {pattern!r} must stay under the target")
