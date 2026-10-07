"""okflib sits on the reader's path only: its LLM and MCP modules, which reach the network, are never imported."""

import subprocess
import sys

import pytest


@pytest.mark.parametrize("module", ["grc_evidence.cli", "grc_evidence.okf_lib"])
def test_okflib_llm_and_mcp_are_not_imported(module: str) -> None:
    code = f"import sys, {module}; print(sorted(m for m in sys.modules if m.startswith('okflib')))"
    loaded = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert "okflib.llm" not in loaded and "okflib.mcp" not in loaded and "okflib.cli" not in loaded
