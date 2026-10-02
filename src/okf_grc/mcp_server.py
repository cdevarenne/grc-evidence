"""`grc mcp`: an MCP server over the engine's outputs, so any MCP-capable agent can read a run without shell access.

Read-mostly by design: a tool reads the contracted outputs in `out/` and never changes the repository. Tool results
are typed, so each tool advertises an output schema and returns structured content.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TypedDict

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from okf_grc.contract import read_mapping
from okf_grc.errors import GrcError

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)


class Control(TypedDict):
    """One control's result: never "satisfied"; `not-satisfied`, `no-violations-detected`, `not-assessed`, or
    `not-applicable`, with the reason when there is one."""

    key: str
    status: str
    reason: str | None
    findings: int
    evidenced_by: list[str]
    satisfied_by: list[str]


class ControlStatus(TypedDict):
    run_id: str
    controls: list[Control]


def _mapping(out: Path) -> dict:
    """`mapping.json`, version-checked; a missing or stale file is a tool error that names the step to run."""
    try:
        return read_mapping(out / "mapping.json")
    except FileNotFoundError as e:
        raise ToolError(f"no {out / 'mapping.json'}: run `grc run` first") from e
    except GrcError as e:
        raise ToolError(str(e)) from e


def _run_id(out: Path) -> str:
    """The run the outputs belong to, so an agent can tell two runs apart."""
    try:
        return json.loads((out / "run.json").read_text(encoding="utf-8"))["run_id"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        raise ToolError(f"no readable {out / 'run.json'}: run `grc run` first") from e


def build_server(out: Path) -> MCPServer:
    """The server over one repository's outputs in `out`."""
    server = MCPServer("okf-grc", instructions=(
        "Reads okf-grc compliance results. Statuses and counts come from the engine and are never 'satisfied'; "
        "a finding maps to a control only through a reviewed rule_ids declaration."
    ))

    @server.tool(annotations=READ_ONLY)
    def control_status(control: str | None = None) -> ControlStatus:
        """Each control's status from the latest run, or one control's (a key such as `soc2:cc6.1`, or a bare SOC 2
        code such as `cc6.1`)."""
        controls = _mapping(out)["controls"]
        if control is not None:
            key = control if control in controls else f"soc2:{control}"
            if key not in controls:
                raise ToolError(f"no control {control!r}; call control_status without arguments for the keys")
            controls = {key: controls[key]}
        return {
            "run_id": _run_id(out),
            "controls": [
                {
                    "key": key,
                    "status": entry["status"],
                    "reason": entry.get("reason"),
                    "findings": len(entry["findings"]),
                    "evidenced_by": entry["evidenced_by"],
                    "satisfied_by": entry["satisfied_by"],
                }
                for key, entry in sorted(controls.items())
            ],
        }

    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="grc mcp", description="Serve this repository's okf-grc results over MCP (stdio).")
    parser.add_argument("--out", type=Path, default=Path("out"), help="where `grc run` writes its outputs")
    args = parser.parse_args(argv)
    build_server(args.out.absolute()).run()
