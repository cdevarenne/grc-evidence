"""The posture workflow (#121): what it may call, what it asks for, and how a draft reads."""

import json
import shutil
from pathlib import Path

import pytest

from okf_grc import agent
from okf_grc.agents.posture import POSTURE, PROMPT, SCHEMA, render
from okf_grc.contract import read_mapping

DRAFT = {
    "summary": "The repository has 7 not-satisfied controls.",
    "not_satisfied": [{"key": "soc2:cc6.1", "status": "not-satisfied", "findings": 188, "largest_groups": "checkov:CKV_K8S_21: 41"}],
    "gaps": [{"rule": "trivy:DS-0029", "findings": 1}],
    "suppressions": "One accepted risk, expiring 2026-12-30.",
    "next_steps": ["Pin image digests in soc2:cc8.1."],
}


def test_posture_reads_results_and_never_scans_or_gates() -> None:
    assert POSTURE.tools == ("control_status", "findings", "gaps", "suppressions")
    assert set(SCHEMA["required"]) == {"summary", "not_satisfied", "gaps", "suppressions", "next_steps"}


def test_the_prompt_names_every_total_the_tools_report() -> None:
    """The validator rejects totals no tool reported, so the prompt points at the ones that exist."""
    for total in ("by_status", "findings_by_status", "rules", "by_rule", "counts", "untrusted"):
        assert f"`{total}`" in PROMPT, total


def test_a_draft_renders_for_a_person() -> None:
    text = render(DRAFT)
    assert text.startswith("# Compliance posture\n\nThe repository has 7 not-satisfied controls.\n")
    assert "| `soc2:cc6.1` | not-satisfied | 188 | checkov:CKV_K8S_21: 41 |" in text
    assert "- `trivy:DS-0029`: 1 finding(s)" in text and text.rstrip().endswith("a person reviews it._")


def test_an_empty_posture_says_none() -> None:
    text = render(DRAFT | {"not_satisfied": [], "gaps": []})
    assert "## Controls not satisfied\n\nNone." in text and "## Coverage gaps\n\nNone." in text


def test_grc_agent_knows_posture() -> None:
    assert agent._workflows() == {"posture": POSTURE}


def _open_objects(schema: object, path: str = "") -> list[str]:
    if isinstance(schema, dict):
        here = [path or "/"] if schema.get("type") == "object" and schema.get("additionalProperties") is not False else []
        return here + [p for k, v in schema.items() for p in _open_objects(v, f"{path}/{k}")]
    return [p for i, v in enumerate(schema) for p in _open_objects(v, f"{path}/{i}")] if isinstance(schema, list) else []


def test_every_workflow_schema_is_closed_as_the_api_requires() -> None:
    """The Messages API refused posture's first schema: every object must set additionalProperties to false."""
    assert {name: _open_objects(w.schema) for name, w in agent._workflows().items()} == {"posture": []}


RECORDED = Path(__file__).parent / "fixtures" / "agent"


@pytest.mark.parametrize(("recording", "outputs"), [("posture.json", "demo-out"), ("posture.anthropic.json", "sample-out")],
                         ids=["claude-cli-on-the-demo-repo", "api-on-the-sample-app"])
def test_a_recorded_run_replays_and_validates(tmp_path: Path, recording: str, outputs: str) -> None:
    """#121: real runs (the maintainer's plan, then the API) replay to a draft that passes validation."""
    out = tmp_path / "out"
    shutil.copytree(RECORDED / outputs, out)
    transcript = json.loads((RECORDED / recording).read_text())
    record = agent.run_workflow(POSTURE, lambda w, o, lim: transcript, out, agent.Limits())
    assert record["validation"] == {"passed": True, "problems": []}
    assert (out / "agent" / record["draft"]).read_text().startswith("# Compliance posture\n")
    assert {c["name"] for c in transcript["tool_calls"]} <= set(POSTURE.tools)


@pytest.mark.parametrize("recording", ["posture.json", "posture.anthropic.json"])
def test_a_recorded_draft_with_a_changed_number_is_rejected(tmp_path: Path, recording: str) -> None:
    transcript = json.loads((RECORDED / recording).read_text())
    transcript["output"]["summary"] += " In all, 9999 findings."
    mapping = read_mapping(RECORDED / ("demo-out" if recording == "posture.json" else "sample-out") / "mapping.json")
    assert agent.validate(POSTURE, transcript, mapping) == ["numbers not in any tool result of this run: ['9999']"]


def test_both_providers_record_the_same_shape() -> None:
    cli, api = (json.loads((RECORDED / name).read_text()) for name in ("posture.json", "posture.anthropic.json"))
    assert (cli["provider"], api["provider"]) == ("claude-cli", "anthropic") and set(cli) == set(api)
    assert (cli["billed"], api["billed"]) == (False, True)
