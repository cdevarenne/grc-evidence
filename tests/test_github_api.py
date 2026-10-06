"""The read-only GitHub transport: recorded responses for tests, HTTPS for real runs, and named rate limits."""

import email.message
import http.client
import io
import json
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from grc_evidence import github_queries
from grc_evidence.github_api import (
    GitHubError,
    HttpTransport,
    NotFound,
    RecordedTransport,
    RecordingTransport,
    graphql_key,
    rate_limit,
    rest_key,
    token_from_env,
)

QUERY = "query($owner: String!) {\n  repository(owner: $owner) { name }\n}"


def _raise_http(status: int, headers: dict[str, str] | None = None, body: bytes = b"{}") -> Callable[..., Any]:
    def urlopen(request: urllib.request.Request, timeout: float) -> Any:
        hdrs = email.message.Message()
        for k, v in (headers or {}).items():
            hdrs[k] = v
        raise urllib.error.HTTPError(request.full_url, status, "error", hdrs, io.BytesIO(body))
    return urlopen


class _Response(io.BytesIO):
    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _reply(body: object, seen: list[urllib.request.Request]) -> Callable[..., Any]:
    def urlopen(request: urllib.request.Request, timeout: float) -> Any:
        seen.append(request)
        return _Response(json.dumps(body).encode())
    return urlopen


def test_recorded_graphql_roundtrip(tmp_path: Path) -> None:
    (tmp_path / graphql_key(QUERY, {"owner": "acme"})).write_text(json.dumps({"data": {"repository": {"name": "api"}}}))
    assert RecordedTransport(tmp_path).graphql(QUERY, {"owner": "acme"}) == {"repository": {"name": "api"}}


def test_missing_fixture_names_key(tmp_path: Path) -> None:
    with pytest.raises(GitHubError, match=graphql_key(QUERY, {"owner": "acme"})) as e:
        RecordedTransport(tmp_path).graphql(QUERY, {"owner": "acme"})
    assert "query($owner: String!) {" in str(e.value)


def test_recorded_403_is_none_and_404_names_its_message(tmp_path: Path) -> None:
    (tmp_path / rest_key("/repos/acme/api/rules/branches/main")).write_text('{"status": 403}')
    assert RecordedTransport(tmp_path).rest("/repos/acme/api/rules/branches/main") is None
    (tmp_path / rest_key("/repos/acme/api/branches/main/protection")).write_text('{"status": 404, "message": "Branch not protected"}')
    with pytest.raises(NotFound) as e:
        RecordedTransport(tmp_path).rest("/repos/acme/api/branches/main/protection")
    assert e.value.reason == "Branch not protected"


def test_http_404_names_its_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """The spike: classic protection answers 404 "Branch not protected" when there is none, "Branch not found" otherwise."""
    monkeypatch.setattr(urllib.request, "urlopen", _raise_http(404, body=b'{"message": "Branch not protected", "status": "404"}'))
    with pytest.raises(NotFound) as e:
        HttpTransport("tok").rest("/repos/acme/api/branches/main/protection")
    assert e.value.reason == "Branch not protected"
    monkeypatch.setattr(urllib.request, "urlopen", _raise_http(404, body=b"not json"))
    with pytest.raises(NotFound) as e:
        HttpTransport("tok").rest("/repos/acme/api/branches/main/protection")
    assert e.value.reason == ""


def test_graphql_errors_raise(tmp_path: Path) -> None:
    (tmp_path / graphql_key(QUERY, {})).write_text('{"errors": [{"message": "x"}]}')
    with pytest.raises(GitHubError, match="x"):
        RecordedTransport(tmp_path).graphql(QUERY, {})


def test_http_reads_send_the_token_and_only_read(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[urllib.request.Request] = []
    monkeypatch.setattr(urllib.request, "urlopen", _reply({"data": {"ok": 1}}, seen))
    assert HttpTransport("tok").graphql(QUERY, {"owner": "acme"}) == {"ok": 1}
    monkeypatch.setattr(urllib.request, "urlopen", _reply([{"id": 1}], seen))
    assert HttpTransport("tok").rest("/repos/acme/api/rules/branches/main") == [{"id": 1}]
    graphql, rest = seen
    assert (graphql.get_method(), graphql.full_url) == ("POST", "https://api.github.com/graphql")
    assert (rest.get_method(), rest.full_url) == ("GET", "https://api.github.com/repos/acme/api/rules/branches/main")
    assert graphql.get_header("Authorization") == "Bearer tok" and graphql.get_header("User-agent") == "grc-evidence"


@pytest.mark.parametrize("path", ["repos/acme/api", "//evil.example/x", "/repos/../x", "https://evil.example/x"])
def test_rest_path_stays_on_the_api(path: str) -> None:
    with pytest.raises(GitHubError, match="path"):
        HttpTransport("tok").rest(path)


def test_token_never_in_error(monkeypatch: pytest.MonkeyPatch) -> None:
    t = HttpTransport("ghp_SECRET123")
    monkeypatch.setattr(urllib.request, "urlopen", _raise_http(401))
    with pytest.raises(GitHubError) as e:
        t.graphql("query{viewer{login}}", {})
    assert "ghp_SECRET123" not in str(e.value) and "ghp_SECRET123" not in repr(t)


def test_rest_403_permission_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", _raise_http(403, {"x-ratelimit-remaining": "4000"}))
    assert HttpTransport("tok").rest("/repos/acme/api/branches/main/protection") is None


def test_rest_403_rate_limited_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", _raise_http(403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1791374400"}))
    with pytest.raises(GitHubError, match="rate limit; resets at 2026-10-07T12:00:00Z"):
        HttpTransport("tok").rest("/repos/acme/api/rules/branches/main")


def test_secondary_rate_limit_names_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def urlopen(request: urllib.request.Request, timeout: float) -> Any:
        calls.append(1)
        return _raise_http(403, {"retry-after": "60"})(request, timeout)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(GitHubError, match="secondary rate limit; retry after 60 s"):
        HttpTransport("tok").graphql(QUERY, {})
    assert calls == [1]  # no retry


def test_429_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", _raise_http(429, {"retry-after": "5"}))
    with pytest.raises(GitHubError, match="rate limit"):
        HttpTransport("tok").rest("/repos/acme/api")


def test_token_from_env() -> None:
    assert token_from_env({"GH_TOKEN": "b"}) == "b"
    assert token_from_env({"GITHUB_TOKEN": "a", "GH_TOKEN": "b"}) == "a"
    with pytest.raises(GitHubError, match="set GITHUB_TOKEN or GH_TOKEN"):
        token_from_env({})


def test_rate_limit() -> None:
    assert rate_limit({"rateLimit": {"cost": 1, "remaining": 4999}, "repository": {}}) == {"cost": 1, "remaining": 4999}
    assert rate_limit({"repository": {}}) is None


class _Upper:
    def name(self, login: str | None) -> str:
        return "ghost" if login is None else f"p-{login.upper()}"


def test_recording_names_every_login_and_replays(tmp_path: Path) -> None:
    class _Inner:
        def graphql(self, query: str, variables: dict) -> dict:
            return {"pr": {"title": "Merge from alice/fix", "author": {"login": "alice"}, "reviews": [{"author": {"login": "bob"}, "body": "alice"}]}}

        def rest(self, path: str) -> dict | list | None:
            if path.endswith("/protection"):
                raise NotFound("GitHub API 404", "Branch not protected")
            return None

    recording = RecordingTransport(_Inner(), tmp_path, _Upper())
    recording.graphql(QUERY, {"owner": "acme"})
    assert recording.rest("/repos/acme/api/rules/branches/main") is None
    replay = RecordedTransport(tmp_path)
    assert replay.graphql(QUERY, {"owner": "acme"}) == {
        "pr": {"title": "", "author": {"login": "p-ALICE"}, "reviews": [{"author": {"login": "p-BOB"}, "body": "alice"}]}
    }
    assert replay.rest("/repos/acme/api/rules/branches/main") is None
    with pytest.raises(NotFound, match="404"):
        recording.rest("/repos/acme/api/branches/main/protection")
    with pytest.raises(NotFound) as e:
        replay.rest("/repos/acme/api/branches/main/protection")
    assert e.value.reason == "Branch not protected"


def test_only_reads() -> None:
    for name in dir(github_queries):
        value = getattr(github_queries, name)
        if isinstance(value, str) and not name.startswith("_"):
            assert "mutation" not in value, name
    assert {"MERGED_PRS", "WORKFLOWS", "DEFAULT_BRANCH"} <= set(dir(github_queries))


def test_network_failure_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    def urlopen(request: urllib.request.Request, timeout: float) -> Any:
        raise urllib.error.URLError("no route")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(GitHubError, match="GitHub API unreachable on graphql: no route"):
        HttpTransport("tok").graphql(QUERY, {})


def test_token_is_not_sent_on_a_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    """urllib follows redirects and copies normal headers to the new URL, even on another host."""
    seen: list[urllib.request.Request] = []
    monkeypatch.setattr(urllib.request, "urlopen", _reply({"id": 1}, seen))
    HttpTransport("tok").rest("/repos/acme/api")
    (request,) = seen
    redirected = urllib.request.HTTPRedirectHandler().redirect_request(request, io.BytesIO(), 302, "Found", http.client.HTTPMessage(), "https://evil.example/x")
    assert redirected is not None and "Authorization" not in redirected.headers
    assert request.unredirected_hdrs["Authorization"] == "Bearer tok"
