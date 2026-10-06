"""Review focus 5: a recorded GitHub fixture in this public repo holds no real login and no title (Spec H §5.4)."""

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "github"


def _logins(value: Any) -> Iterator[str]:
    """Every `login` string, at any depth."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "login" and isinstance(item, str):
                yield item
            else:
                yield from _logins(item)
    elif isinstance(value, list):
        for item in value:
            yield from _logins(item)


def _titles(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield from [item] if key == "title" and isinstance(item, str) else _titles(item)
    elif isinstance(value, list):
        for item in value:
            yield from _titles(item)


def test_logins_are_found_at_any_depth() -> None:
    doc = {"data": {"nodes": [{"author": {"login": "a"}, "reviews": {"nodes": [{"author": {"login": "b"}}]}}]}}
    assert list(_logins(doc)) == ["a", "b"]


@pytest.mark.parametrize("path", sorted(FIXTURES.rglob("*.json")), ids=lambda p: str(p.relative_to(FIXTURES)))
def test_fixtures_pseudonymized(path: Path) -> None:
    for login in _logins(json.loads(path.read_text(encoding="utf-8"))):
        assert login == "ghost" or re.fullmatch(r"p-[0-9a-f]{10}", login), f"{path}: real login {login!r}"
    assert not any(_titles(json.loads(path.read_text(encoding="utf-8")))), f"{path}: a title can hold a login"
