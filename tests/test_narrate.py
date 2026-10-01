"""narrate: the LLM writes prose only; one changed status, invented number, or missing control rejects it all."""

import json
from pathlib import Path

import pytest

from okf_grc.digest import bundle_digest, scan_digest
from okf_grc.llm import LLMError
from llm_stub import StubLLM
from okf_grc.map_findings import map_findings
from okf_grc.narrate import mapping_sha256, narrate, read_narratives, validate
from okf_grc.render_report import main as render_main
from okf_grc.okf_lib import load_bundle

FIXTURES = Path(__file__).parent / "fixtures"
BUNDLE = load_bundle(FIXTURES / "bundle")
MAPPING = map_findings(BUNDLE, json.loads((FIXTURES / "findings.json").read_text()))
DIGEST = bundle_digest(BUNDLE)


def _good() -> dict[str, dict[str, str]]:
    notes = {
        "soc2:cc6.1": "CC6.1 is not-satisfied with 2 open findings, 1 high and 1 medium.",
        "soc2:cc7.1": "CC7.1 is not-satisfied: 1 critical dependency finding.",
        "soc2:cc7.2": "CC7.2 is not-assessed; nothing in the bundle evidences it.",
        "soc2:cc8.1": "CC8.1 shows no-violations-detected, which is evidence, not an attestation.",
    }
    return {k: {"summary": v, "auditor_note": "Sample the evidence for this control."} for k, v in notes.items()}


def test_scan_digest_is_counts_and_gaps_not_raw_findings() -> None:
    doc = scan_digest(MAPPING)
    assert doc["controls"]["soc2:cc6.1"] == {"status": "not-satisfied", "findings": 2, "by_severity": {"high": 1, "medium": 1}}
    assert [(g["rule_id"], g["count"]) for g in doc["gaps"]] == [("CKV_TEST_99", 1), ("orphan_rule", 1)]


def test_bundle_digest_is_the_cached_system_block() -> None:
    llm = StubLLM({"narrate": _good()})
    narrate(llm, DIGEST, MAPPING)
    (req,) = llm.requests
    assert '"soc2:cc6.1"' in req.system and "Scan digest" in req.user and "Scan digest" not in req.system


def test_valid_narratives_are_accepted() -> None:
    narratives, errors = narrate(StubLLM({"narrate": _good()}), DIGEST, MAPPING)
    assert errors == [] and set(narratives) == set(MAPPING["controls"])


@pytest.mark.parametrize(
    ("key", "text", "error"),
    [
        ("soc2:cc8.1", "CC8.1 is satisfied.", "forbidden status word 'satisfied'"),
        ("soc2:cc8.1", "CC8.1 is fully compliant.", "forbidden status word 'compliant'"),
        ("soc2:cc7.2", "All checks passed.", "forbidden status word 'passed'"),
        ("soc2:cc7.2", "CC7.2 is not-satisfied.", "claims ['not-satisfied']"),
        ("soc2:cc6.1", "CC6.1 has 3 open findings.", "numbers not in the input ['3']"),
        # #68: "1" is in the prompt (other controls' counts) but not in cc7.2's own entries, which have 0 findings
        ("soc2:cc7.2", "CC7.2 has 1 open finding.", "numbers not in the input ['1']"),
    ],
)
def test_one_bad_claim_rejects_the_whole_output(key: str, text: str, error: str) -> None:
    output = _good()
    output[key]["summary"] = text
    narratives, errors = narrate(StubLLM({"narrate": output}), DIGEST, MAPPING)
    assert narratives == {} and any(error in e for e in errors), errors


def test_missing_or_extra_controls_are_rejected() -> None:
    output = _good()
    del output["soc2:cc7.2"]
    output["soc2:cc9.9"] = {"summary": "x", "auditor_note": "y"}
    errors = validate(output, MAPPING, {})
    assert "missing controls: ['soc2:cc7.2']" in errors
    assert "controls not in the bundle: ['soc2:cc9.9']" in errors


def test_llm_failure_falls_back_to_no_narratives() -> None:
    assert narrate(StubLLM(LLMError("no recorded response")), DIGEST, MAPPING) == ({}, ["no recorded response"])


def _out_with_mapping(tmp_path: Path, mapping: dict) -> Path:
    out = tmp_path / "out"
    out.mkdir()
    (out / "mapping.json").write_text(json.dumps(mapping), encoding="utf-8")
    return out


def test_narratives_are_used_only_for_the_mapping_they_were_written_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """#56: after a rescan changes mapping.json, the earlier narratives must not reach the report."""
    root = Path(__file__).parent.parent
    mapping = map_findings(load_bundle(root / "knowledge"), [])
    out = _out_with_mapping(tmp_path, mapping)
    note = {"soc2:cc6.1": {"summary": "Written for the first scan.", "auditor_note": "Check access."}}
    doc = {"mapping_sha256": mapping_sha256(out / "mapping.json"), "controls": note}
    (out / "narratives.json").write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.chdir(root)
    render_main(["--out", str(out), "--now", "2026-10-01T12:00:00+00:00"])
    assert "Written for the first scan." in (out / "report.md").read_text()
    gap = {"tool": "checkov", "rule_id": "CKV_NEW", "severity": "low", "target": "app/x.tf", "message": "m", "tags": []}
    rescan = map_findings(load_bundle(root / "knowledge"), [gap])  # a rescan found something new
    (out / "mapping.json").write_text(json.dumps(rescan), encoding="utf-8")
    render_main(["--out", str(out), "--now", "2026-10-01T12:00:00+00:00"])
    assert "Written for the first scan." not in (out / "report.md").read_text()
    assert "written for another mapping.json; ignored" in capsys.readouterr().out


def test_narratives_without_a_mapping_hash_are_stale(tmp_path: Path) -> None:
    out = _out_with_mapping(tmp_path, {"controls": {}, "unmapped": []})
    (out / "narratives.json").write_text(json.dumps({"soc2:cc6.1": {"summary": "s", "auditor_note": "n"}}))
    assert read_narratives(out) == ({}, True)


def test_no_narratives_file_is_not_stale(tmp_path: Path) -> None:
    assert read_narratives(_out_with_mapping(tmp_path, {"controls": {}, "unmapped": []})) == ({}, False)
