"""Scan layout from an optional `grc.yaml`: what each scanner reads and which policies it applies.

Scan inputs (`inventory`, `conftest.inputs`, `checkov.skip_paths`) are relative to the target;
`target`, `knowledge`, `semgrep.configs`, and `rego` are relative to the repo root. With no file,
the defaults are the v1.0 layout.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

CONFIG_FILE = "grc.yaml"
# Accepted keys: a type for a leaf, a nested dict for a section.
_SHAPE: dict[str, Any] = {
    "target": str,
    "knowledge": str,
    "inventory": str,
    "rego": list,
    "scanner_timeout": int,
    "conftest": {"inputs": list},
    "checkov": {"frameworks": list, "skip_paths": list},
    "semgrep": {"configs": list},
}


class ConfigError(ValueError):
    """`grc.yaml` or a command-line override is malformed or points outside the repo."""


@dataclass(frozen=True)
class Config:
    """The resolved scan layout; field names are the YAML keys with `.` as `_`."""

    target: str = "app"
    knowledge: str = "knowledge"
    inventory: str = "ai-inventory.yaml"
    conftest_inputs: tuple[str, ...] = ("k8s/**/*.yaml", "k8s/**/*.yml", "infra/**/*.tf", "ai-inventory.yaml")
    checkov_frameworks: tuple[str, ...] = ("terraform", "kubernetes", "dockerfile")
    checkov_skip_paths: tuple[str, ...] = ()
    semgrep_configs: tuple[str, ...] = ("policies/semgrep",)
    rego: tuple[str, ...] = ("policies/rego",)
    scanner_timeout: int = 900  # seconds per scanner; a hung scanner stops the scan with its name


def load_config(repo: Path, path: Path | None = None, **overrides: str | None) -> Config:
    """`grc.yaml` (or `path`) over the defaults, then the non-None `overrides` (command-line flags), checked."""
    file = repo / (path or CONFIG_FILE)
    if path is not None and not file.is_file():
        raise ConfigError(f"{path}: no such config file")
    raw = (yaml.safe_load(file.read_text(encoding="utf-8")) or {}) if file.is_file() else {}
    config = replace(Config(), **_fields(raw, _SHAPE, ""))
    config = replace(config, **_fields({k: v for k, v in overrides.items() if v is not None}, _SHAPE, ""))
    _check_paths(repo, config)
    return config


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
    inside(f"{config.target}/{config.inventory}", "inventory")
    for rel in config.semgrep_configs:
        inside(rel, "semgrep.configs")
    for rel in config.rego:
        inside(rel, "rego")
    for key, patterns in (("conftest.inputs", config.conftest_inputs), ("checkov.skip_paths", config.checkov_skip_paths)):
        for pattern in patterns:
            if PurePosixPath(pattern).is_absolute() or ".." in PurePosixPath(pattern).parts:
                raise ConfigError(f"{key} {pattern!r} must stay under the target")
