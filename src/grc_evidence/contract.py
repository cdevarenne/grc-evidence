"""Readers of the output contract's JSON files: each checks the schema's major version before use."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from grc_evidence.data import SCHEMA_VERSION
from grc_evidence.errors import GrcError

Json = dict[str, Any]


class ContractError(GrcError, ValueError):
    """An output file that is not written under this engine's schema major version."""


def _read(path: Path, kind: str, rerun: str) -> Json:
    doc = json.loads(path.read_text(encoding="utf-8"))
    major = SCHEMA_VERSION.split(".")[0]
    if not isinstance(doc, dict) or str(doc.get("schema_version", "")).split(".")[0] != major:
        raise ContractError(f"{path}: not a schema {major}.x {kind} file; rerun `{rerun}`")
    return doc


def read_findings(path: Path) -> list[Json]:
    """The findings list of a `findings.json` written under schema 1.x; anything else is an error."""
    return _read(path, "findings", "grc scan")["findings"]


def read_mapping(path: Path) -> Json:
    """A `mapping.json` written under schema 1.x; anything else is an error."""
    return _read(path, "mapping", "grc map")
