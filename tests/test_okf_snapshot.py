"""Spec J guard: the OKF reader change leaves every parsed concept and every scan output byte-identical to 2.0.1.

`python tests/test_okf_snapshot.py --write` records the snapshots with the current reader (Spec J Task 1, before
the change). The tests then compare. The demo's bundle is compared only while its commit is the recorded one.
These snapshots guard the reader change only; Spec J Task 7 removes them.
"""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from grc_evidence import data
from grc_evidence.map_findings import map_findings
from grc_evidence.okf_lib import load_bundle
from grc_evidence.render_report import render_report
from grc_evidence.run_scan import load_pins
from grc_evidence.to_oscal import (
    assessment_plan,
    assessment_results,
    component_definition,
)

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
SNAPSHOTS = FIXTURES / "okf_snapshot"
DEMO = ROOT.parent / "grc-evidence-boutique"
NOW, RUN_ID, TODAY = "2026-10-06T12:00:00+00:00", "00000000-0000-5000-8000-000000000000", date(2026, 10, 6)
BUNDLES = {  # name: (bundle, findings mapped against it)
    "knowledge": (ROOT / "knowledge", FIXTURES / "findings.json"),
    "base": (Path(str(data.path("base"))), FIXTURES / "findings.json"),
    "fixture-bundle": (FIXTURES / "bundle", FIXTURES / "findings.json"),
    "fixture-ai-bundle": (FIXTURES / "ai_bundle", FIXTURES / "ai_findings.json"),
    "demo": (DEMO / "knowledge", FIXTURES / "findings.json"),
}


def snapshot(root: Path, findings_file: Path) -> dict[str, Any]:
    """Every parsed concept, and the mapping, OSCAL and report built from it, as JSON-ready values."""
    bundle = load_bundle(root)
    concepts = {
        cid: {
            "path": c.path, "type": c.type, "title": c.title, "description": c.description, "tags": list(c.tags),
            "rule_ids": list(c.rule_ids), "frontmatter": json.loads(json.dumps(c.frontmatter, default=str)),
            "body": c.body, "links": list(c.links),
        }
        for cid, c in sorted(bundle.concepts.items())
    }
    mapping = map_findings(bundle, json.loads(findings_file.read_text()), {}, TODAY)
    pins = load_pins(data.path("tools.lock"))
    return {
        "concepts": concepts,
        "mapping": mapping,
        "component-definition": component_definition(bundle, NOW),
        "assessment-plan": assessment_plan(bundle, mapping, NOW, pins),
        "assessment-results": assessment_results(bundle, mapping, NOW, RUN_ID),
        "report": render_report(bundle, mapping, NOW),
    }


def _demo_commit() -> str | None:
    if not DEMO.is_dir():
        return None
    return subprocess.run(["git", "-C", str(DEMO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or None


@pytest.mark.parametrize("name", list(BUNDLES))
def test_reader_change_leaves_concepts_and_outputs_unchanged(name: str) -> None:
    recorded = json.loads((SNAPSHOTS / f"{name}.json").read_text(encoding="utf-8"))
    if name == "demo" and _demo_commit() != recorded.get("demo_commit"):
        pytest.skip("the demo repo is absent or not at the recorded commit")
    expected = {k: v for k, v in recorded.items() if k != "demo_commit"}
    assert json.loads(json.dumps(snapshot(*BUNDLES[name]), default=str)) == expected


if __name__ == "__main__" and sys.argv[1:] == ["--write"]:
    SNAPSHOTS.mkdir(exist_ok=True)
    for name, (root, findings) in BUNDLES.items():
        if name == "demo" and _demo_commit() is None:
            continue
        doc = json.loads(json.dumps(snapshot(root, findings), default=str))
        if name == "demo":
            doc["demo_commit"] = _demo_commit()
        (SNAPSHOTS / f"{name}.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {name}: {len(doc['concepts'])} concepts")
