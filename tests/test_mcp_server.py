"""grc mcp (#108): the server over a run's outputs, through the SDK's own client."""

import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

from okf_grc import cli
from okf_grc.data import SCHEMA_VERSION
from okf_grc.map_findings import map_findings
from okf_grc.mcp_server import build_server
from okf_grc.okf_lib import load_bundle

FIXTURES = Path(__file__).parent / "fixtures"
MAPPING = map_findings(load_bundle(FIXTURES / "bundle"), json.loads((FIXTURES / "findings.json").read_text()))


def _out(tmp_path: Path, mapping: dict | None = None) -> Path:
    out = tmp_path / "out"
    out.mkdir()
    (out / "mapping.json").write_text(json.dumps(mapping or {"schema_version": SCHEMA_VERSION, **MAPPING}))
    (out / "run.json").write_text(json.dumps({"run_id": "run-1"}))
    return out


def _with_client(server: Any, use: Callable[[Client], Awaitable[Any]]) -> Any:
    async def go() -> Any:
        async with Client(server) as client:
            return await use(client)

    return asyncio.run(go())


def test_control_status_is_a_typed_read_only_tool(tmp_path: Path) -> None:
    async def use(client: Client) -> Any:
        return (await client.list_tools()).tools

    (tool,) = _with_client(build_server(_out(tmp_path)), use)
    assert tool.name == "control_status"
    assert tool.annotations and tool.annotations.read_only_hint and not tool.annotations.destructive_hint
    assert tool.output_schema and set(tool.output_schema["properties"]) == {"run_id", "controls"}


def test_control_status_reports_every_control_from_the_mapping(tmp_path: Path) -> None:
    async def use(client: Client) -> Any:
        return await client.call_tool("control_status", {})

    result = _with_client(build_server(_out(tmp_path)), use)
    assert not result.is_error and result.structured_content["run_id"] == "run-1"
    got = {c["key"]: (c["status"], c["findings"]) for c in result.structured_content["controls"]}
    assert got == {key: (entry["status"], len(entry["findings"])) for key, entry in MAPPING["controls"].items()}


@pytest.mark.parametrize("control", ["soc2:cc6.1", "cc6.1"])
def test_control_status_for_one_control(tmp_path: Path, control: str) -> None:
    async def use(client: Client) -> Any:
        return await client.call_tool("control_status", {"control": control})

    (entry,) = _with_client(build_server(_out(tmp_path)), use).structured_content["controls"]
    assert entry["key"] == "soc2:cc6.1" and entry["status"] == MAPPING["controls"]["soc2:cc6.1"]["status"]


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        (lambda tmp: _out(tmp), "no control 'soc2:cc9.9'"),
        (lambda tmp: tmp / "missing", "run `grc run` first"),
        (lambda tmp: _out(tmp, {"controls": {}, "unmapped": []}), "rerun `grc map`"),
    ],
    ids=["unknown-control", "no-outputs", "unversioned-mapping"],
)
def test_problems_are_named_tool_errors(tmp_path: Path, setup: Callable[[Path], Path], message: str) -> None:
    async def use(client: Client) -> Any:
        return await client.call_tool("control_status", {"control": "soc2:cc9.9"})

    result = _with_client(build_server(setup(tmp_path)), use)
    assert result.is_error and message in result.content[0].text


def test_reading_changes_no_file(tmp_path: Path) -> None:
    out = _out(tmp_path)
    before = {p: p.read_bytes() for p in out.iterdir()}

    async def use(client: Client) -> Any:
        return await client.call_tool("control_status", {})

    _with_client(build_server(out), use)
    assert {p: p.read_bytes() for p in out.iterdir()} == before


def test_grc_mcp_serves_over_stdio(tmp_path: Path) -> None:
    """The real transport an agent uses: `grc mcp` as a subprocess."""
    out = _out(tmp_path)
    params = StdioServerParameters(command=sys.executable, args=["-m", "okf_grc.cli", "mcp", "--out", str(out)], cwd=tmp_path)

    async def use(client: Client) -> Any:
        return await client.call_tool("control_status", {"control": "cc6.1"})

    assert _with_client(params, use).structured_content["run_id"] == "run-1"


def test_grc_mcp_without_the_extra_says_how_to_install_it(monkeypatch: pytest.MonkeyPatch) -> None:
    import okf_grc

    for name in [m for m in sys.modules if m == "mcp" or m.startswith("mcp.")]:
        monkeypatch.setitem(sys.modules, name, None)  # as if the extra were not installed: importing mcp fails
    monkeypatch.delitem(sys.modules, "okf_grc.mcp_server")
    monkeypatch.delattr(okf_grc, "mcp_server")
    with pytest.raises(SystemExit, match=r"grc mcp needs the mcp extra: uv tool install 'okf-grc\[mcp\]"):
        cli.main(["mcp"])
