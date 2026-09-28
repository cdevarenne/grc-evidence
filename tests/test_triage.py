"""triage: proposals are `none` or an in-bundle control; anything else is marked invalid, and nothing is applied."""

import json
from pathlib import Path

from digest import bundle_digest, scan_digest
from llm_stub import StubLLM
from map_findings import map_findings
from okf_lib import load_bundle
from triage import triage

FIXTURES = Path(__file__).parent / "fixtures"
BUNDLE = load_bundle(FIXTURES / "bundle")
MAPPING = map_findings(BUNDLE, json.loads((FIXTURES / "findings.json").read_text()))
DIGEST = bundle_digest(BUNDLE)


def _gaps() -> list[dict]:
    return scan_digest(MAPPING)["gaps"]


def test_triage_keeps_valid_proposals_including_none() -> None:
    outputs = {
        "checkov:CKV_TEST_99": {"rule": "checkov:CKV_TEST_99", "proposal": "none", "rationale": "r", "confidence": "high"},
        "conftest:orphan_rule": {"rule": "conftest:orphan_rule", "proposal": "soc2:cc6.1", "rationale": "r", "confidence": "low"},
    }
    proposals = triage(StubLLM(outputs), DIGEST, _gaps())
    assert [p["proposal"] for p in proposals] == ["none", "soc2:cc6.1"]


def test_triage_marks_off_bundle_or_missing_proposals_invalid() -> None:
    outputs = {
        "checkov:CKV_TEST_99": {"rule": "checkov:CKV_TEST_99", "proposal": "soc2:a1.2", "rationale": "r", "confidence": "sure"},
    }
    first, second = triage(StubLLM(outputs), DIGEST, _gaps())
    assert first["proposal"] == "invalid" and len(first["errors"]) == 2
    assert "not `none` or an in-bundle control" in first["errors"][0]
    assert second == {"rule": "conftest:orphan_rule", "proposal": "invalid", "errors": ["no proposal returned for this rule"]}


def test_triage_sends_gaps_in_chunks() -> None:
    gaps = [{"tool": "t", "rule_id": f"r{i}", "message": "m", "reason": "no-rule-match", "count": 1} for i in range(19)]
    outputs = {f"t:r{i}": {"rule": f"t:r{i}", "proposal": "none", "rationale": "r", "confidence": "low"} for i in range(19)}
    llm = StubLLM(outputs)
    proposals = triage(llm, DIGEST, gaps)
    assert [len(json.loads(r.user.split("\n", 1)[1])) for r in llm.requests] == [8, 8, 3]
    assert [p["rule"] for p in proposals] == [f"t:r{i}" for i in range(19)]


def test_batch_and_sequential_triage_agree() -> None:
    outputs = {
        "checkov:CKV_TEST_99": {"rule": "checkov:CKV_TEST_99", "proposal": "none", "rationale": "r", "confidence": "high"},
        "conftest:orphan_rule": {"rule": "conftest:orphan_rule", "proposal": "none", "rationale": "r", "confidence": "low"},
    }
    assert triage(StubLLM(outputs), DIGEST, _gaps()) == triage(StubLLM(outputs), DIGEST, _gaps(), batch=True)


def test_triage_schema_enumerates_only_bundle_controls() -> None:
    llm = StubLLM({})
    triage(llm, DIGEST, _gaps())
    enum = llm.requests[0].schema["properties"]["proposals"]["items"]["properties"]["proposal"]["enum"]
    assert enum == ["none", "soc2:cc6.1", "soc2:cc7.1", "soc2:cc7.2", "soc2:cc8.1"]
