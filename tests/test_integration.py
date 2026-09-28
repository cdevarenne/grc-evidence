"""End-to-end: `make scan` finds every seeded issue and maps it exactly as SEEDED.yaml expects."""

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from oscal_schema import validate

ROOT = Path(__file__).parent.parent
OUT = ROOT / "out"
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def mapping() -> dict:
    subprocess.run(["make", "scan"], cwd=ROOT, check=True)
    return json.loads((OUT / "mapping.json").read_text())


def _located(mapping: dict, tool: str, rule_id: str, file: str) -> set[str]:
    """Where a finding landed: control codes, or 'gap:<reason>'."""
    hits = {
        code
        for code, entry in mapping["controls"].items()
        for f in entry["findings"]
        if (f["tool"], f["rule_id"], f["target"]) == (tool, rule_id, file)
    }
    hits |= {
        f"gap:{u['reason']}"
        for u in mapping["unmapped"]
        if (u["finding"]["tool"], u["finding"]["rule_id"], u["finding"]["target"]) == (tool, rule_id, file)
    }
    return hits


SEEDED = yaml.safe_load((ROOT / "app" / "SEEDED.yaml").read_text())


@pytest.mark.parametrize("seed", SEEDED, ids=lambda s: s["id"])
def test_seeded_issue_lands_where_expected(mapping: dict, seed: dict) -> None:
    expected = set(seed["expect"].get("controls", [])) or {f"gap:{seed['expect']['gap']}"}
    for detector in seed["detected_by"]:
        tool, rule_id = detector.split(":", 1)
        assert _located(mapping, tool, rule_id, seed["file"]) == expected, f"{seed['id']} {detector}"


def test_outputs_exist_and_oscal_validates(mapping: dict) -> None:
    assert (OUT / "report.md").read_text().startswith("# Compliance Scan Report")
    validate(json.loads((OUT / "oscal" / "component-definition.json").read_text()), "oscal_component_schema.json")
    validate(json.loads((OUT / "oscal" / "assessment-results.json").read_text()), "oscal_assessment-results_schema.json")


def test_monitoring_control_is_not_assessed(mapping: dict) -> None:
    assert mapping["controls"]["soc2:cc7.2"]["status"] == "not-assessed"
