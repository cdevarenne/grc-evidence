"""`applies_when` + the AI inventory decide which controls are in scope; `not-applicable` is never a pass."""

from pathlib import Path

import pytest

from okf_lib import applies, load_bundle

FIXTURES = Path(__file__).parent / "fixtures"
AI = load_bundle(FIXTURES / "ai_bundle")


@pytest.mark.parametrize(
    ("context", "expected"),
    [({"risk_tier": "limited"}, False), ({"risk_tier": "high"}, True), ({}, True)],
)
def test_applies_reads_the_risk_tier(context: dict, expected: bool) -> None:
    assert applies(AI.control("eu-ai-act:art-12"), context) is expected


def test_control_without_applies_when_always_applies() -> None:
    assert applies(AI.control("eu-ai-act:art-50"), {"risk_tier": "minimal"})
