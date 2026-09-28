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
    assert len(seed["expect"]) == 1 and set(seed["expect"]) <= {"controls", "gap"}
    for key in seed["expect"].get("controls", []):
        assert ":" in key, f"{seed['id']}: control {key!r} is not a framework:code key"
