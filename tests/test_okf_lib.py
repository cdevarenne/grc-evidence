from pathlib import Path

import pytest

from okf_grc.map_findings import map_findings
from okf_grc.okf_lib import BundleError, load_bundle

FIXTURE = Path(__file__).parent / "fixtures" / "bundle"


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_loads_concepts_and_skips_reserved_files() -> None:
    bundle = load_bundle(FIXTURE)
    assert "controls/cc6.1" in bundle.concepts
    assert not any(cid.endswith(("index", "log")) for cid in bundle.concepts)


def test_concept_fields() -> None:
    trivy = load_bundle(FIXTURE).concepts["scanners/trivy"]
    assert trivy.type == "Scanner"
    assert trivy.path == "scanners/trivy.md"
    assert trivy.rule_ids == ("trivy:CVE-*",)
    assert trivy.control_tags == ("cc7.1",)
    assert trivy.links == ("controls/cc7.1",)


def test_links_resolve_absolute_and_relative_and_keep_broken() -> None:
    app = load_bundle(FIXTURE).concepts["stack/app"]
    assert app.links == ("controls/cc6.1", "controls/cc7.1", "controls/missing")


def test_controls_and_lookup_by_code() -> None:
    bundle = load_bundle(FIXTURE)
    assert [c.code for c in bundle.controls()] == ["cc6.1", "cc7.1", "cc7.2", "cc8.1"]
    assert bundle.control("cc7.1").title.startswith("CC7.1")
    assert bundle.control("cc9.9") is None


def test_by_rule_exact_and_glob() -> None:
    bundle = load_bundle(FIXTURE)
    assert [c.id for c in bundle.by_rule("checkov", "CKV_TEST_1")] == ["policies/require-non-root"]
    assert [c.id for c in bundle.by_rule("trivy", "CVE-2024-0001")] == ["scanners/trivy"]
    assert bundle.by_rule("trivy", "DS026") == []
    assert bundle.by_rule("checkov", "CVE-2024-0001") == []


def test_section() -> None:
    bundle = load_bundle(FIXTURE)
    trivy = bundle.concepts["scanners/trivy"]
    assert bundle.section(trivy, "Remediation") == "Upgrade the affected dependency to a fixed version."
    assert bundle.section(trivy, "Nope") is None


def test_missing_type_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "a.md", "---\ntitle: no type\n---\nbody\n")
    with pytest.raises(BundleError, match="a.md"):
        load_bundle(tmp_path)


def test_missing_frontmatter_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "sub/b.md", "just markdown\n")
    with pytest.raises(BundleError, match="sub/b.md"):
        load_bundle(tmp_path)


def test_unknown_type_and_keys_are_tolerated(tmp_path: Path) -> None:
    _write(tmp_path, "c.md", "---\ntype: Mystery\nwhatever: 1\n---\n")
    concept = load_bundle(tmp_path).concepts["c"]
    assert concept.type == "Mystery"
    assert concept.frontmatter["whatever"] == 1
    assert concept.title == "c"


def _concept(tags: str, rule_ids: str) -> str:
    return f"---\ntype: Rego Policy\ntags: {tags}\nrule_ids: {rule_ids}\n---\n"


@pytest.mark.parametrize(
    ("tags", "rule_ids"),
    [
        ("cc6.1", '["conftest:x"]'),
        ("[cc6.1]", "trivy:DS-0002"),
        ("[cc6.1]", '["trivy:*"]'),
        ("[cc6.1]", '["trivy:**"]'),
        ("[cc6.1]", '["checkov:?*"]'),
        ("[cc6.1]", '["x:[!_]*"]'),
        ("[cc6.1]", '["x:*-*"]'),
        ("[cc6.1]", '[":CVE-1"]'),
        ("[cc6.1]", '["no-colon"]'),
        ("[cc6.1, cc7.1]", '["conftest:x"]'),
        ("[opa]", '["conftest:x"]'),
    ],
)
def test_malformed_grounding_is_rejected(tmp_path: Path, tags: str, rule_ids: str) -> None:
    _write(tmp_path, "p/bad.md", _concept(tags, rule_ids))
    with pytest.raises(BundleError, match="p/bad.md"):
        load_bundle(tmp_path)


@pytest.mark.parametrize("rule", ["trivy:CVE-*", "trivy:GHSA-*", "checkov:CKV_K8S_14"])
def test_literal_prefix_rules_are_accepted(tmp_path: Path, rule: str) -> None:
    _write(tmp_path, "p/ok.md", _concept("[opa, cc6.1]", f'["{rule}"]'))
    assert load_bundle(tmp_path).concepts["p/ok"].rule_ids == (rule,)


def test_declaring_returns_rule_declarers_carrying_the_code() -> None:
    bundle = load_bundle(FIXTURE)
    assert [c.id for c in bundle.declaring("cc6.1")] == ["policies/require-non-root"]
    assert [c.id for c in bundle.declaring("cc7.1")] == ["scanners/trivy"]
    assert bundle.declaring("cc7.2") == []


def test_soc2_availability_tags_and_scanner_check_guardrails(tmp_path) -> None:
    """#85: A1 (availability) tags are SOC 2 controls; a Scanner Check groups third-party rules as a guardrail."""
    (tmp_path / "controls").mkdir()
    (tmp_path / "controls" / "a1.1.md").write_text("---\ntype: SOC 2 Control\ntitle: A1.1\ntags: [a1.1]\n---\n# Intent\n\nx\n")
    (tmp_path / "policies").mkdir()
    (tmp_path / "policies" / "limits.md").write_text(
        "---\ntype: Scanner Check\ntitle: Limits\ntags: [a1.1]\nrule_ids:\n  - trivy:KSV-0011\n---\n# Rule\n\nx\n"
    )
    bundle = load_bundle(tmp_path)
    assert bundle.control("a1.1").key == "soc2:a1.1"
    assert [c.id for c in bundle.declaring("soc2:a1.1")] == ["policies/limits"]
    finding = {"tool": "trivy", "rule_id": "KSV-0011", "severity": "low", "target": "k8s/a.yaml", "message": "m", "tags": []}
    entry = map_findings(bundle, [finding])["controls"]["soc2:a1.1"]
    assert entry["status"] == "not-satisfied" and entry["satisfied_by"] == ["policies/limits"]
