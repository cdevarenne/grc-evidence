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


UNBOUND_IN_1_7 = {"posture.json": [41, 2], "posture.anthropic.json": [7, 5, 10, 7]}


@pytest.mark.parametrize("recording", UNBOUND_IN_1_7)
def test_drafts_that_passed_in_1_7_are_rejected_by_binding(recording: str) -> None:
    """#124: real runs recorded under 1.7.0 passed its validation. Binding rejects the numbers that sat next to
    nothing they count: a group named in words ("namespace isolation violations (41)"), how many findings a
    suppression covers (no tool reported it then), and per-tool counts the model added up itself ("checkov (7),
    trivy (5)")."""
    transcript = json.loads((RECORDED / recording).read_text())
    mapping = read_mapping(RECORDED / ("demo-out" if recording == "posture.json" else "sample-out") / "mapping.json")
    problems = agent.validate(POSTURE, transcript, mapping)
    (numbers,) = [p for p in problems if p.startswith("numbers that are not the count")]
    assert [int(item.split()[0]) for item in eval(numbers.split(": ", 1)[1])] == UNBOUND_IN_1_7[recording]


@pytest.mark.parametrize("recording", UNBOUND_IN_1_7)
def test_a_recorded_draft_with_a_changed_number_is_rejected(recording: str) -> None:
    transcript = json.loads((RECORDED / recording).read_text())
    transcript["output"]["summary"] += " In all, 9999 findings."
    mapping = read_mapping(RECORDED / ("demo-out" if recording == "posture.json" else "sample-out") / "mapping.json")
    assert any("9999" in p for p in agent.validate(POSTURE, transcript, mapping))


def test_both_providers_record_the_same_shape() -> None:
    cli, api = (json.loads((RECORDED / name).read_text()) for name in ("posture.json", "posture.anthropic.json"))
    assert (cli["provider"], api["provider"]) == ("claude-cli", "anthropic") and set(cli) == set(api)
    assert (cli["billed"], api["billed"]) == (False, True)


def test_the_1_8_0_demo_drafts_under_1_8_1() -> None:
    """Recorded on the demo repo's outputs with okf-grc 1.8.0. Its first draft put 11 next to soc2:cc7.1 ("11 rules
    at 4 findings each", a count no tool reports) and was rejected; 1.8.0 passed the corrected draft. Under 1.8.1 (#125)
    the corrected draft is rejected too: "2 CKV_K8S_21 findings" for the suppression is a count no tool reported then
    (`findings_by_suppression` reports it now), and in 1.8.0 it passed only because 2 was also a reported total."""
    recorded = json.loads((RECORDED / "posture.corrected.json").read_text())
    mapping = read_mapping(RECORDED / "demo-out" / "mapping.json")

    def unbound(transcript: agent.Transcript) -> list[int]:
        (numbers,) = [p for p in agent.validate(POSTURE, transcript, mapping) if p.startswith("numbers that are not the count")]
        return [int(item.split()[0]) for item in eval(numbers.split(": ", 1)[1])]

    assert unbound(recorded["rejected"]) == [2, 11]
    assert unbound(recorded["corrected"]) == [2]


def test_a_demo_run_with_binding_is_rejected_then_corrected(tmp_path: Path) -> None:
    """#125, recorded on the demo repo's outputs: the first draft gave three rules a range ("each have 12-13
    findings") and was rejected; the correction round put each count next to its rule, and that draft passed."""
    recorded = json.loads((RECORDED / "posture.bound.json").read_text())
    out = tmp_path / "out"
    shutil.copytree(RECORDED / "demo-out", out)
    runs = iter([recorded["rejected"], recorded["corrected"]])
    record = agent.run_workflow(POSTURE, lambda w, o, lim: next(runs), out, agent.Limits())
    (attempt,) = record["rejected_attempts"]
    assert "13 in 'Fix soc2:cc8.1 (61 findings)" in attempt["problems"][0]
    assert record["validation"] == {"passed": True, "problems": []} and record["draft"]
