"""The output contract: findings.json, mapping.json, and run.json validate against the shipped schemas."""

import copy
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from okf_grc import data
from okf_grc.config import load_config
from okf_grc.manifest import OUTPUTS, build_manifest, run_id
from okf_grc.map_findings import map_findings, read_findings
from okf_grc.okf_lib import load_bundle
from okf_grc.run_scan import dedupe
from okf_grc.to_oscal import PROP_NS, assessment_results
from oscal_schema import validate as validate_oscal

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
NOW = "2026-10-01T12:00:00+00:00"
FINDINGS = json.loads((FIXTURES / "findings.json").read_text())
BUNDLE = load_bundle(ROOT / "knowledge")
# One finding per suppression in the bundle, so the mapping's optional suppression keys are exercised too.
SUPPRESSED = [
    {"tool": s.tool, "rule_id": s.rule_id, "severity": "high", "target": s.target, "message": s.message_contains or "m", "tags": []}
    for s in BUNDLE.suppressions()
]


def _validate(doc: dict, name: str) -> None:
    schema = json.loads(data.path(f"schemas/{name}.schema.json").read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(doc)


def _outputs(out: Path) -> Path:
    for rel in OUTPUTS:
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_text(f"{rel}\n", encoding="utf-8")
    return out


def _documents(tmp_path: Path) -> dict[str, dict]:
    mapping = map_findings(BUNDLE, FINDINGS + SUPPRESSED, today=date(2026, 10, 1))
    assert mapping["suppressed"]
    return {
        "findings": {"schema_version": data.SCHEMA_VERSION, "findings": dedupe(FINDINGS)},
        "mapping": {"schema_version": data.SCHEMA_VERSION, **mapping},
        "run": build_manifest(ROOT, _outputs(tmp_path / "out"), load_config(ROOT), "4b1c0a9e-0000-5000-8000-000000000000", NOW),
    }


@pytest.mark.parametrize("name", ["findings", "mapping", "run"])
def test_documents_validate(tmp_path: Path, name: str) -> None:
    _validate(_documents(tmp_path)[name], name)


@pytest.mark.parametrize(
    ("name", "path"),
    [
        ("findings", ["schema_version"]),
        ("findings", ["findings", 0, "severity"]),
        ("mapping", ["controls", "soc2:cc6.1", "status"]),
        ("mapping", ["unmapped", 0, "reason"]),
        ("mapping", ["suppressed", 0, "owner"]),
        ("run", ["repository", "commit"]),
        ("run", ["outputs"]),
    ],
)
def test_removing_a_required_field_fails(tmp_path: Path, name: str, path: list) -> None:
    doc = copy.deepcopy(_documents(tmp_path)[name])
    parent = doc
    for key in path[:-1]:
        parent = parent[key]
    del parent[path[-1]]
    with pytest.raises(ValidationError):
        _validate(doc, name)


def test_manifest_hashes_the_outputs_and_names_the_commit(tmp_path: Path) -> None:
    out = _outputs(tmp_path / "out")
    manifest = build_manifest(ROOT, out, load_config(ROOT), "id", NOW)
    assert manifest["outputs"] == {rel: hashlib.sha256((out / rel).read_bytes()).hexdigest() for rel in OUTPUTS}
    assert len(manifest["repository"]["commit"]) == 40
    assert manifest["base_version"] == "1.1.0"
    assert manifest["scanners"]["trivy"] == "0.74.0"


def test_manifest_outside_git_has_no_commit(tmp_path: Path) -> None:
    manifest = build_manifest(tmp_path, _outputs(tmp_path / "out"), load_config(tmp_path), "id", NOW)
    assert manifest["repository"] == {"commit": None, "dirty": None}
    assert manifest["base_version"] is None


def test_manifest_requires_every_output(tmp_path: Path) -> None:
    out = _outputs(tmp_path / "out")
    (out / "report.md").unlink()
    with pytest.raises(FileNotFoundError):
        build_manifest(ROOT, out, load_config(ROOT), "id", NOW)


def test_run_id_is_stable_for_the_same_inputs() -> None:
    config = load_config(ROOT)
    assert run_id(ROOT, config, NOW) == run_id(ROOT, config, NOW) != run_id(ROOT, config, "2026-10-02T12:00:00+00:00")


def test_oscal_results_carry_the_run_id() -> None:
    doc = assessment_results(BUNDLE, map_findings(BUNDLE, FINDINGS, today=date(2026, 10, 1)), NOW, "run-123")
    validate_oscal(doc, "oscal_assessment-results_schema.json")
    (result,) = doc["assessment-results"]["results"]
    assert result["props"] == [{"name": "run-id", "ns": PROP_NS, "value": "run-123"}]


def test_read_findings_requires_the_versioned_document(tmp_path: Path) -> None:
    path = tmp_path / "findings.json"
    path.write_text(json.dumps({"schema_version": "1.3", "findings": FINDINGS}))
    assert read_findings(path) == FINDINGS
    for stale in (FINDINGS, {"schema_version": "2.0", "findings": []}):
        path.write_text(json.dumps(stale))
        with pytest.raises(ValueError, match="rerun `grc scan`"):
            read_findings(path)
