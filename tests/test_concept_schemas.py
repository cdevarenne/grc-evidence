"""The written contract for the bundle's extension fields (Spec J §4.2): every concept validates against its schema,
and the schemas reject the same syntax errors the loader rejects."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

from grc_evidence import data
from grc_evidence.okf_lib import (
    FRAMEWORK_TYPES,
    SUPPRESSION_TYPE,
    BundleError,
    load_bundle,
)

ROOT = Path(__file__).parent.parent
SCHEMAS = Path(str(data.path("schemas"))) / "concepts"
BUNDLES = {"knowledge": ROOT / "knowledge", "base": Path(str(data.path("base")))}


def _validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((SCHEMAS / f"{name}.schema.json").read_text()))


def _as_json(frontmatter: Any) -> Any:
    """YAML dates as ISO strings, as they are written in the files."""
    return json.loads(json.dumps(frontmatter, default=str))


def _schemas_for(frontmatter: dict) -> list[str]:
    names = []
    if frontmatter.get("type") in FRAMEWORK_TYPES.values():
        names.append("control")
    if "rule_ids" in frontmatter:
        names.append("rule-declaring")
    if frontmatter.get("type") == SUPPRESSION_TYPE:
        names.append("suppression")
    return names


def test_schemas_are_valid_json_schema() -> None:
    for path in SCHEMAS.glob("*.schema.json"):
        Draft202012Validator.check_schema(json.loads(path.read_text()))


@pytest.mark.parametrize("bundle", list(BUNDLES))
def test_every_concept_validates_against_its_schemas(bundle: str) -> None:
    checked = 0
    for concept in load_bundle(BUNDLES[bundle]).concepts.values():
        for name in _schemas_for(dict(concept.frontmatter)):
            _validator(name).validate(_as_json(concept.frontmatter))
            checked += 1
    assert checked > 20  # controls, rule-declaring concepts and suppressions are all present


@pytest.mark.parametrize("bundle", list(BUNDLES))
def test_root_index_validates(bundle: str) -> None:
    text = (BUNDLES[bundle] / "index.md").read_text()
    _validator("root-index").validate(_as_json(yaml.safe_load(text.split("---\n")[1])))


SUPPRESSION = {"type": "Suppression", "kind": "false-positive", "owner": "human:r", "approved": "2026-10-01",
               "expires": "2026-10-30", "finding": {"tool": "trivy", "rule_id": "CVE-1", "target": "app/x"}}
POLICY = {"type": "Rego Policy", "rule_ids": ["conftest:deny_x"], "tags": ["cc8.1"]}
CONTROL = {"type": "ISO/IEC 42001 Control", "framework": "iso42001", "tags": ["iso42001:a.6"]}


@pytest.mark.parametrize(("schema", "frontmatter"), [
    ("rule-declaring", POLICY | {"rule_ids": ["no-tool-prefix"]}),
    ("rule-declaring", POLICY | {"rule_ids": ["conftest:deny*x"]}),
    ("suppression", SUPPRESSION | {"kind": "maybe"}),
    ("suppression", SUPPRESSION | {"owner": "reviewer"}),
    ("suppression", SUPPRESSION | {"approved": "Oct 1"}),
    ("suppression", SUPPRESSION | {"finding": {"tool": "trivy", "rule_id": "CVE-*", "target": "app/x"}}),
    ("suppression", SUPPRESSION | {"finding": {"tool": "trivy", "target": "app/x"}}),
    ("control", CONTROL | {"framework": "soc2"}),
    ("control", CONTROL | {"applies_when": ["high"]}),
])
def test_schemas_reject_the_syntax_cases(tmp_path: Path, schema: str, frontmatter: dict) -> None:
    """Each case fails the schema, and the loader rejects the same file: the two stay in step."""
    assert not _validator(schema).is_valid(frontmatter)
    root = tmp_path / "kb"
    (root / "c").mkdir(parents=True)
    (root / "index.md").write_text('---\nokf_version: "0.2"\n---\n# Bundle\n')
    (root / "c" / "x.md").write_text(f"---\n{yaml.safe_dump(frontmatter)}---\n# Reason\n\nReviewed.\n")
    with pytest.raises(BundleError):
        load_bundle(root)


@pytest.mark.parametrize(("schema", "frontmatter"), [("suppression", SUPPRESSION), ("rule-declaring", POLICY), ("control", CONTROL)])
def test_schemas_accept_the_valid_cases(schema: str, frontmatter: dict) -> None:
    assert _validator(schema).is_valid(frontmatter)
