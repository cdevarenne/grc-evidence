"""triage: proposals are `none` or an in-bundle control; anything else is marked invalid, and nothing is applied."""

import json
from pathlib import Path

from okf_grc.digest import bundle_digest, scan_digest
from llm_stub import StubLLM
from okf_grc.map_findings import map_findings
from okf_grc.okf_lib import FRAMEWORK_SCOPES, load_bundle
from okf_grc.triage import SCOPE_RULE, SYSTEM, request, triage

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


def test_each_gap_is_sent_with_the_exact_rule_the_proposal_must_echo() -> None:
    llm = StubLLM({})
    triage(llm, DIGEST, _gaps())
    (req,) = llm.requests
    sent = json.loads(req.user.split("\n", 1)[1])
    assert [g["rule"] for g in sent] == ["checkov:CKV_TEST_99", "conftest:orphan_rule"]
    rule_schema = req.schema["properties"]["proposals"]["items"]["properties"]["rule"]
    assert rule_schema == {"type": "string", "enum": ["checkov:CKV_TEST_99", "conftest:orphan_rule"]}


def _scoped_gaps() -> list[dict]:
    return scan_digest(MAPPING, targets=True)["gaps"]


def test_scan_digest_can_carry_each_gaps_targets() -> None:
    assert [g["targets"] for g in _scoped_gaps()] == [["app/Dockerfile"], ["app/infra/main.tf"]]
    assert "targets" not in scan_digest(MAPPING)["gaps"][0]


def test_scoped_bundle_digest_marks_ai_controls_as_ai_only() -> None:
    ai = bundle_digest(load_bundle(FIXTURES / "ai_bundle"), scoped=True)
    assert ai["soc2:cc6.1"]["scope"] == FRAMEWORK_SCOPES["soc2"]
    assert ai["iso42001:a.6"]["scope"] == ai["eu-ai-act:art-50"]["scope"]
    assert "AI system components only" in ai["iso42001:a.6"]["scope"]
    assert "scope" not in bundle_digest(load_bundle(FIXTURES / "ai_bundle"))["iso42001:a.6"]


def test_baseline_request_has_no_scope_rule_and_no_targets() -> None:
    req = request(DIGEST, _scoped_gaps())
    assert req.system.startswith(SYSTEM) and SCOPE_RULE not in req.system
    assert all("targets" not in g for g in json.loads(req.user.split("\n", 1)[1]))


def test_scoped_request_sends_the_scope_rule_and_targets() -> None:
    req = request(bundle_digest(BUNDLE, scoped=True), _scoped_gaps(), "scoped")
    assert SCOPE_RULE in req.system and '"scope"' in req.system
    assert [g["targets"] for g in json.loads(req.user.split("\n", 1)[1])] == [["app/Dockerfile"], ["app/infra/main.tf"]]


def test_unknown_variant_is_refused() -> None:
    import pytest

    with pytest.raises(ValueError, match="variant"):
        request(DIGEST, _gaps(), "tuned")


def test_main_batch_flag_sends_one_message_batch(tmp_path, monkeypatch) -> None:
    import sys

    from okf_grc import triage as triage_module
    (tmp_path / "mapping.json").write_text(json.dumps(MAPPING))
    ok = {"proposal": "none", "rationale": "r", "confidence": "high"}
    calls: list[str] = []

    class Recorder(StubLLM):
        model = "stub"

        def complete(self, request):  # type: ignore[no-untyped-def]
            calls.append("complete")
            gaps = json.loads(request.user.split("\n", 1)[1])
            return {"proposals": [ok | {"rule": g["rule"]} for g in gaps]}

        def complete_batch(self, requests):  # type: ignore[no-untyped-def]
            calls.append("batch")
            return {cid: self.complete(r) for cid, r in requests.items()}

    monkeypatch.setattr(triage_module.LLM, "from_env", staticmethod(lambda out, default_model: Recorder({})))
    for flag, expected in (([], "complete"), (["--batch"], "batch")):
        calls.clear()
        monkeypatch.setattr(sys, "argv", ["triage", "--knowledge", str(FIXTURES / "bundle"), "--out", str(tmp_path), *flag])
        triage_module.main()
        assert calls[0] == expected
    assert len(json.loads((tmp_path / "proposals.json").read_text())) == 2
