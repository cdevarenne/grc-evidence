"""The labeled triage eval set: real gaps only, labels drawn from the bundle, enough abstention cases."""

from collections import Counter
from pathlib import Path

import pytest
import yaml

from okf_lib import load_bundle

ROOT = Path(__file__).parent.parent
CASES = yaml.safe_load((ROOT / "tests" / "fixtures" / "triage_eval.yaml").read_text())
BUNDLE = load_bundle(ROOT / "knowledge")


def test_size_and_mix() -> None:
    labels = Counter("none" if c["expected"] == "none" else "control" for c in CASES)
    assert len(CASES) == 25 and labels["none"] >= 8 and labels["control"] >= 12


def test_rules_are_unique() -> None:
    assert len({c["rule"] for c in CASES}) == len(CASES)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["rule"])
def test_case_is_a_real_gap_with_an_in_bundle_label(case: dict) -> None:
    tool, _, rule_id = case["rule"].partition(":")
    assert tool and rule_id and case["message"]
    assert BUNDLE.by_rule(tool, rule_id) == [], f"{case['rule']} is declared in the bundle, so it is not a gap"
    assert case["expected"] == "none" or BUNDLE.control(case["expected"]), case["expected"]
