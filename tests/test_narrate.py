"""narrate: the LLM writes prose only; one changed status, invented number, or missing control rejects it all."""

import json
from pathlib import Path

import pytest

from digest import bundle_digest, scan_digest
from llm import LLMError
from llm_stub import StubLLM
from map_findings import map_findings
from narrate import narrate, validate
from okf_lib import load_bundle

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
    errors = validate(output, MAPPING, "")
    assert "missing controls: ['soc2:cc7.2']" in errors
    assert "controls not in the bundle: ['soc2:cc9.9']" in errors


def test_llm_failure_falls_back_to_no_narratives() -> None:
    assert narrate(StubLLM(LLMError("no recorded response")), DIGEST, MAPPING) == ({}, ["no recorded response"])
