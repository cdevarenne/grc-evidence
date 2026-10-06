"""Replay the responses recorded once from the real API: the model's own output must pass the validators."""

import json
from pathlib import Path

from grc_evidence.digest import bundle_digest, scan_digest
from grc_evidence.llm import LLM
from grc_evidence.map_findings import map_findings
from grc_evidence.narrate import narrate
from grc_evidence.okf_lib import load_bundle
from grc_evidence.triage import triage

FIXTURES = Path(__file__).parent / "fixtures"
BUNDLE = load_bundle(FIXTURES / "bundle")
MAPPING = map_findings(BUNDLE, json.loads((FIXTURES / "findings.json").read_text()))


def _replay(tmp_path: Path) -> LLM:
    return LLM(mode="replay", fixtures=FIXTURES / "llm", cache=tmp_path / "cache", ledger=tmp_path / "usage.jsonl")


def test_recorded_narratives_pass_the_validator(tmp_path: Path) -> None:
    narratives, errors = narrate(_replay(tmp_path), bundle_digest(BUNDLE), MAPPING)
    assert errors == []
    assert set(narratives) == set(MAPPING["controls"])


def test_recorded_triage_proposals_are_valid(tmp_path: Path) -> None:
    proposals = triage(_replay(tmp_path), bundle_digest(BUNDLE), scan_digest(MAPPING)["gaps"])
    assert [p["rule"] for p in proposals] == ["checkov:CKV_TEST_99", "conftest:orphan_rule"]
    assert all(p["proposal"] != "invalid" for p in proposals), proposals


def test_replay_bills_nothing(tmp_path: Path) -> None:
    llm = _replay(tmp_path)
    narrate(llm, bundle_digest(BUNDLE), MAPPING)
    assert llm.spent_usd() == 0.0


def test_recorded_scoped_triage_proposals_are_valid(tmp_path: Path) -> None:
    gaps = scan_digest(MAPPING, targets=True)["gaps"]
    proposals = triage(_replay(tmp_path), bundle_digest(BUNDLE, scoped=True), gaps, variant="scoped")
    assert [p["rule"] for p in proposals] == ["checkov:CKV_TEST_99", "conftest:orphan_rule"]
    assert all(p["proposal"] != "invalid" for p in proposals), proposals
