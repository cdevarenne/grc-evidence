from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent
SEEDED = yaml.safe_load((ROOT / "app" / "SEEDED.yaml").read_text())
TOOLS = {"semgrep", "trivy", "checkov", "conftest"}


def test_ids_are_unique() -> None:
    assert len({s["id"] for s in SEEDED}) == len(SEEDED)


def test_has_a_coverage_gap_seed() -> None:
    assert any("gap" in s["expect"] for s in SEEDED)


@pytest.mark.parametrize("seed", SEEDED, ids=lambda s: s["id"])
def test_entry_is_well_formed(seed: dict) -> None:
    assert (ROOT / seed["file"]).is_file()
    assert seed["detected_by"]
    for detector in seed["detected_by"]:
        tool, _, rule = detector.partition(":")
        assert tool in TOOLS and rule
    outcome = set(seed["expect"]) & {"controls", "gap", "suppressed"}
    assert len(outcome) == 1, f"{seed['id']}: exactly one of controls, gap, suppressed"
    assert set(seed["expect"]) <= {"controls", "gap", "suppressed", "accepted", "unsuppressed", "suppression"}
    if "suppressed" in seed["expect"]:
        assert {"unsuppressed", "suppression"} <= set(seed["expect"]), f"{seed['id']}: say where it lands once expired"
    if "accepted" in seed["expect"]:
        assert "controls" in seed["expect"], f"{seed['id']}: an accepted risk stays on its controls"
    for key in seed["expect"].get("controls", []):
        assert ":" in key, f"{seed['id']}: control {key!r} is not a framework:code key"
