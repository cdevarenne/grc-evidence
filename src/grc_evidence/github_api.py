"""Read-only access to the GitHub API: HTTPS for real runs, recorded responses for tests and offline examples.

No code path writes to GitHub. GraphQL reads use POST, which is the only POST. The token is sent only in the
Authorization header: it never appears in an error, a log line or an output. A rate limit stops the run at
once with the retry or reset time; there is no retry loop (the next scheduled run tries again).
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime
from email.message import Message
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from grc_evidence.errors import GrcError
from grc_evidence.ledger import canonical

API = "https://api.github.com"
TIMEOUT = 30  # seconds per request


class GitHubError(GrcError, RuntimeError):
    """A GitHub API call failed: HTTP error, GraphQL error, rate limit, or a missing recorded response."""


class _NotReadable(GitHubError):
    """HTTP 403 with no rate-limit signal, or 404: the token cannot read this resource."""


class Transport(Protocol):
    def graphql(self, query: str, variables: dict) -> dict:
        """The `data` of a GraphQL read; GitHubError on an HTTP error or a non-empty `errors` list."""
        ...

    def rest(self, path: str) -> dict | list | None:
        """A REST read, or None when the token cannot read it (403 with no rate-limit signal, or 404)."""
        ...


class Names(Protocol):
    def name(self, login: str | None) -> str: ...


def graphql_key(query: str, variables: dict) -> str:
    """The recorded-response file name of a GraphQL read."""
    return hashlib.sha256(canonical({"q": query, "v": variables})).hexdigest()[:16] + ".json"


def rest_key(path: str) -> str:
    """The recorded-response file name of a REST read."""
    return "rest" + path.replace("/", "__") + ".json"


def token_from_env(environ: Mapping[str, str] = os.environ) -> str:
    if token := environ.get("GITHUB_TOKEN") or environ.get("GH_TOKEN"):
        return token
    raise GitHubError("set GITHUB_TOKEN or GH_TOKEN")


def rate_limit(data: dict) -> dict | None:
    """`{cost, remaining}` from a query's `rateLimit` field, or None."""
    rl = data.get("rateLimit")
    return {"cost": rl["cost"], "remaining": rl["remaining"]} if rl else None


def _data(body: Any, where: str) -> dict:
    if errors := body.get("errors"):
        raise GitHubError(f"GitHub API error on {where}: {errors[0].get('message', 'unknown error')}")
    return body["data"]


class HttpTransport:
    """The GitHub API over HTTPS."""

    def __init__(self, token: str, api: str = API) -> None:
        self._token, self._api = token, api.rstrip("/")

    def __repr__(self) -> str:
        return f"HttpTransport(api={self._api!r})"

    def graphql(self, query: str, variables: dict) -> dict:
        payload = json.dumps({"query": query, "variables": variables}).encode()
        return _data(self._send(urllib.request.Request(f"{self._api}/graphql", data=payload, method="POST"), "graphql"), "graphql")

    def rest(self, path: str) -> dict | list | None:
        parts = PurePosixPath(path).parts
        if not path.startswith("/") or path.startswith("//") or ".." in parts:
            raise GitHubError(f"REST path {path!r} must be an absolute API path")
        try:
            body: dict | list = self._send(urllib.request.Request(f"{self._api}{path}", method="GET"), path)
        except _NotReadable:
            return None
        return body

    def _send(self, request: urllib.request.Request, where: str) -> Any:
        request.add_header("Authorization", f"Bearer {self._token}")
        request.add_header("User-Agent", "grc-evidence")
        request.add_header("Accept", "application/vnd.github+json")
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as e:
            raise _http_error(e.code, e.headers, where) from None
        except urllib.error.URLError as e:
            raise GitHubError(f"GitHub API unreachable on {where}: {e.reason}") from None


def _http_error(status: int, headers: Message, where: str) -> GitHubError:
    """A named rate limit, a not-readable resource, or a plain HTTP error."""
    if retry := headers.get("retry-after"):
        return GitHubError(f"GitHub API {status} on {where}: secondary rate limit; retry after {retry} s")
    if headers.get("x-ratelimit-remaining") == "0" or status == 429:
        reset = headers.get("x-ratelimit-reset")
        when = datetime.fromtimestamp(int(reset), UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if reset else "unknown"
        return GitHubError(f"GitHub API {status} on {where}: rate limit; resets at {when}")
    if status in (403, 404):
        return _NotReadable(f"GitHub API {status} on {where}")
    return GitHubError(f"GitHub API {status} on {where}")


class RecordedTransport:
    """Responses read from files: `<graphql_key>` holds a GraphQL body, `<rest_key>` a REST body or `{"status": 404}`."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def graphql(self, query: str, variables: dict) -> dict:
        return _data(self._load(graphql_key(query, variables), query.splitlines()[0]), "graphql")

    def rest(self, path: str) -> dict | list | None:
        body = self._load(rest_key(path), path)
        return None if body == {"status": 404} else body

    def _load(self, key: str, what: str) -> Any:
        file = self._root / key
        if not file.is_file():
            raise GitHubError(f"no recorded response {key} for {what}")
        return json.loads(file.read_text(encoding="utf-8"))


class RecordingTransport:
    """Reads through `inner` and writes each response for RecordedTransport, every `login` passed through `namer`.

    It returns the named response too, so a recording run and its offline replay give the same outputs.
    """

    def __init__(self, inner: Transport, root: Path, namer: Names) -> None:
        self._inner, self._root, self._namer = inner, root, namer

    def graphql(self, query: str, variables: dict) -> dict:
        data = _named(self._inner.graphql(query, variables), self._namer)
        self._write(graphql_key(query, variables), {"data": data})
        return data

    def rest(self, path: str) -> dict | list | None:
        body = self._inner.rest(path)
        named = None if body is None else _named(body, self._namer)
        self._write(rest_key(path), {"status": 404} if named is None else named)
        return named

    def _write(self, key: str, body: Any) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        (self._root / key).write_text(json.dumps(body, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _named(value: Any, namer: Names) -> Any:
    """`value` with every `login` string replaced by its name."""
    if isinstance(value, dict):
        return {k: namer.name(v) if k == "login" and isinstance(v, str) else _named(v, namer) for k, v in value.items()}
    if isinstance(value, list):
        return [_named(v, namer) for v in value]
    return value
