"""The real knowledge/ bundle: OKF v0.2 conformance plus this repo's grounding conventions."""

import re
from pathlib import Path

import pytest
import yaml

from okf_lib import FRAMEWORK_TYPES, load_bundle

KNOWLEDGE = Path(__file__).parent.parent / "knowledge"
TOOLS = {"semgrep", "trivy", "checkov", "conftest"}
TYPES = {
    *FRAMEWORK_TYPES.values(), "Crosswalk", "Stack Component", "Rego Policy", "Semgrep Rule", "Scanner", "Reference",
    "Suppression",
}
RISK_TIERS = {"minimal", "limited", "high"}
BUNDLE = load_bundle(KNOWLEDGE)  # raises BundleError on a missing or empty `type` (OKF §11)


def test_bundle_has_the_expected_controls() -> None:
    keys = {c.key for c in BUNDLE.controls()}
    assert {k for k in keys if k.startswith("soc2:")} == {f"soc2:{c}" for c in ("cc6.1", "cc6.6", "cc7.1", "cc7.2", "cc8.1")}
    assert {k for k in keys if k.startswith("iso42001:")} == {f"iso42001:a.{n}" for n in range(4, 10)}
    assert {k for k in keys if k.startswith("eu-ai-act:")} == {f"eu-ai-act:art-{n}" for n in (9, 10, 12, 13, 14, 15, 50)}


def test_applies_when_uses_known_fields_and_tiers() -> None:
    for control in BUNDLE.controls():
        applies_when = control.frontmatter.get("applies_when") or {}
        assert set(applies_when) <= {"risk_tier"}, control.path
        assert set(applies_when.get("risk_tier", [])) <= RISK_TIERS, control.path


def test_high_risk_articles_declare_their_tier() -> None:
    for n in (9, 10, 12, 13, 14, 15):
        assert BUNDLE.control(f"eu-ai-act:art-{n}").frontmatter["applies_when"] == {"risk_tier": ["high"]}
    assert "applies_when" not in BUNDLE.control("eu-ai-act:art-50").frontmatter


def test_inventory_tier_is_known() -> None:
    inventory = yaml.safe_load((KNOWLEDGE.parent / "app" / "ai-inventory.yaml").read_text())
    assert inventory["risk_tier"] in RISK_TIERS


def test_every_crosswalk_links_controls_across_frameworks() -> None:
    pairs = BUNDLE.crosswalk_pairs()
    assert {cw for cw, _, _ in pairs} == {c.id for c in BUNDLE.of_type("Crosswalk")}
    for cw, left, right in pairs:
        a, b = BUNDLE.concepts[left], BUNDLE.concepts[right]
        assert a.framework != b.framework, f"{cw}: {left} and {right} are in the same framework"


def test_types_are_the_documented_set() -> None:
    assert {c.type for c in BUNDLE.concepts.values()} <= TYPES


@pytest.mark.parametrize("concept", BUNDLE.concepts.values(), ids=lambda c: c.id)
def test_required_metadata(concept) -> None:
    fm = concept.frontmatter
    assert fm.get("title") and fm.get("description") and fm.get("tags"), concept.path
    assert fm.get("generated", {}).get("by") and fm["generated"].get("at"), concept.path


@pytest.mark.parametrize("concept", [c for c in BUNDLE.concepts.values() if c.rule_ids], ids=lambda c: c.id)
def test_rule_declarations_are_grounded(concept) -> None:
    for entry in concept.rule_ids:
        tool, _, rule = entry.partition(":")
        assert tool in TOOLS, f"{concept.path}: unknown tool in {entry!r}"
        assert re.fullmatch(r"[^*?\[\]]+\*?", rule), f"{concept.path}: {entry!r} is not a literal prefix"
    frameworks = [key.partition(":")[0] for key in concept.control_keys]
    assert frameworks and len(frameworks) == len(set(frameworks)), f"{concept.path}: one control tag per framework"


def test_every_control_tag_names_a_control() -> None:
    for concept in BUNDLE.concepts.values():
        for tag in concept.control_tags:
            assert BUNDLE.control(tag), f"{concept.path}: tag {tag} has no control concept"


def test_every_control_names_its_framework() -> None:
    for control in BUNDLE.controls():
        assert control.frontmatter.get("framework") in FRAMEWORK_TYPES, control.path


def test_controls_carry_their_own_key_as_tag() -> None:
    for control in BUNDLE.controls():
        assert control.key in control.control_keys, control.path


def test_no_broken_links() -> None:
    for concept in BUNDLE.concepts.values():
        for link in concept.links:
            assert link in BUNDLE.concepts, f"{concept.path}: broken link to {link}"


def test_index_files_have_no_frontmatter_except_root_version() -> None:
    for index in KNOWLEDGE.rglob("index.md"):
        text = index.read_text(encoding="utf-8")
        if index.parent == KNOWLEDGE:
            fm = yaml.safe_load(text.split("---\n")[1])
            assert fm == {"okf_version": "0.2"}
        else:
            assert not text.startswith("---"), index


def test_log_dates_are_iso() -> None:
    for log in KNOWLEDGE.rglob("log.md"):
        for heading in re.findall(r"^## (.+)$", log.read_text(encoding="utf-8"), re.M):
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", heading), f"{log}: {heading}"


def test_every_rule_id_tool_has_a_matching_scanner_concept() -> None:
    """A Scanner concept's file stem is the tool name used in rule_ids (scanners/trivy.md <-> trivy:)."""
    scanner_codes = {c.code for c in BUNDLE.of_type("Scanner")}
    tools = {entry.partition(":")[0] for c in BUNDLE.concepts.values() for entry in c.rule_ids}
    assert tools <= scanner_codes


def test_links_are_relative() -> None:
    """The pinned OKF visualizer ignores bundle-absolute links, so the bundle uses relative ones."""
    for concept in BUNDLE.concepts.values():
        assert "](/" not in concept.body, f"{concept.path}: use a relative link"

@pytest.mark.parametrize("concept", BUNDLE.concepts.values(), ids=lambda c: c.id)
def test_every_concept_is_human_verified(concept) -> None:
    verified = concept.frontmatter.get("verified")
    entries = verified if isinstance(verified, list) else [verified] if verified else []
    assert any(str(e.get("by", "")).startswith("human:") for e in entries), f"{concept.path}: not human-verified"


def test_suppressions_name_a_known_tool_and_one_owner() -> None:
    """Load-time checks enforce kind, exact match, owner, reason, and the 90-day window; this adds the tool set."""
    for s in BUNDLE.suppressions():
        assert s.tool in TOOLS, f"{s.id}: unknown tool {s.tool!r}"
        assert s.owner.startswith("human:"), s.id
