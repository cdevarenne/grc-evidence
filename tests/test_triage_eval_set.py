"""The labeled triage eval set: real gaps only, labels drawn from the bundle, enough abstention cases."""

from collections import Counter
from pathlib import Path

import pytest
import yaml

from okf_grc.okf_lib import load_bundle

ROOT = Path(__file__).parent.parent
CASES = yaml.safe_load((ROOT / "tests" / "fixtures" / "triage_eval.yaml").read_text())
BUNDLE = load_bundle(ROOT / "knowledge")


def _split(name: str) -> list[dict]:
    return [c for c in CASES if c["split"] == name]


def test_every_case_has_a_split_and_a_target() -> None:
    assert {c["split"] for c in CASES} == {"tune", "holdout", "confirm"}
    assert all(c["target"].startswith("app/") for c in CASES)


def test_tune_split_is_the_first_baseline_set() -> None:
    labels = Counter("none" if c["expected"] == "none" else "control" for c in _split("tune"))
    assert labels == {"control": 15, "none": 10}


def test_holdout_split_can_catch_both_failure_modes() -> None:
    """Enough `none` cases to measure abstention, and enough AI cases to catch over-suppression."""
    holdout = _split("holdout")
    ai = [c for c in holdout if c["expected"].startswith(("iso42001:", "eu-ai-act:"))]
    assert len(holdout) >= 15
    assert sum(c["expected"] == "none" for c in holdout) >= 5
    assert len(ai) >= 5 and all("assistant" in c["target"] or "ai-inventory" in c["target"] for c in ai)


def test_rules_are_unique() -> None:
    assert len({c["rule"] for c in CASES}) == len(CASES)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["rule"])
def test_case_is_a_real_gap_with_an_in_bundle_label(case: dict) -> None:
    tool, _, rule_id = case["rule"].partition(":")
    assert tool and rule_id and case["message"]
    assert BUNDLE.by_rule(tool, rule_id) == [], f"{case['rule']} is declared in the bundle, so it is not a gap"
    assert case["expected"] == "none" or BUNDLE.control(case["expected"]), case["expected"]


def test_confirm_split_is_fresh_and_has_traps() -> None:
    """A second holdout for the default decision, with AI-file cases whose answer is not an AI control."""
    confirm = _split("confirm")
    ai_file = [c for c in confirm if "assistant" in c["target"] or "ai-inventory" in c["target"]]
    assert len(confirm) >= 25
    assert sum(c["expected"] == "none" for c in confirm) >= 6
    assert sum(c["expected"].startswith(("iso42001:", "eu-ai-act:")) for c in confirm) >= 6
    assert any(not c["expected"].startswith(("iso42001:", "eu-ai-act:")) for c in ai_file)
    earlier = {c["rule"] for c in CASES if c["split"] != "confirm"}
    assert not earlier & {c["rule"] for c in confirm}
