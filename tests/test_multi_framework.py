"""Controls from several frameworks, keyed `framework:code`, under the same grounding rule."""

from pathlib import Path

import pytest

from okf_lib import BundleError, control_key, load_bundle

FIXTURES = Path(__file__).parent / "fixtures"
AI = load_bundle(FIXTURES / "ai_bundle")


def _write(root: Path, rel: str, frontmatter: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}\n---\n", encoding="utf-8")


def test_control_keys_are_framework_qualified() -> None:
    assert [c.key for c in AI.controls()] == [
        "soc2:cc6.1", "eu-ai-act:art-12", "eu-ai-act:art-50", "iso42001:a.6", "iso42001:a.7",
    ]


def test_framework_defaults_to_soc2() -> None:
    bundle = load_bundle(FIXTURES / "bundle")
    assert {c.framework for c in bundle.controls()} == {"soc2"}


def test_control_key_normalizes_bare_soc2_tags() -> None:
    assert control_key("cc6.1") == "soc2:cc6.1"
    assert control_key("iso42001:a.6") == "iso42001:a.6"


def test_lookup_by_key_and_bare_soc2_code() -> None:
    assert AI.control("iso42001:a.6").title.startswith("A.6")
    assert AI.control("cc6.1") is AI.control("soc2:cc6.1")
    assert AI.control("a.6") is None


def test_one_guardrail_can_declare_one_control_per_framework() -> None:
    key = AI.concepts["policies/llm-hardcoded-key"]
    assert key.control_keys == ("soc2:cc6.1", "iso42001:a.6")
    assert [c.id for c in AI.declaring("iso42001:a.6")] == ["policies/llm-hardcoded-key"]


@pytest.mark.parametrize(
    "tags", ["[iso42001:a.6, iso42001:a.7]", "[cc6.1, cc7.1, iso42001:a.6]", "[iso42001]"]
)
def test_two_controls_in_one_framework_are_rejected(tmp_path: Path, tags: str) -> None:
    _write(tmp_path, "p/bad.md", f'type: Semgrep Rule\ntags: {tags}\nrule_ids: ["semgrep:x"]')
    with pytest.raises(BundleError, match="p/bad.md"):
        load_bundle(tmp_path)


@pytest.mark.parametrize(
    "frontmatter",
    [
        "type: ISO/IEC 42001 Control\nframework: eu-ai-act",
        "type: SOC 2 Control\nframework: iso42001",
        "type: EU AI Act Article\nframework: nist-ai-rmf",
        "type: EU AI Act Article\nframework: eu-ai-act\napplies_when: {risk_tier: high}",
        "type: EU AI Act Article\nframework: eu-ai-act\napplies_when: [high]",
    ],
)
def test_malformed_control_frontmatter_is_rejected(tmp_path: Path, frontmatter: str) -> None:
    _write(tmp_path, "controls/x.md", frontmatter)
    with pytest.raises(BundleError, match="controls/x.md"):
        load_bundle(tmp_path)


def test_crosswalk_pairs_are_lines_linking_two_controls() -> None:
    assert AI.crosswalk_pairs() == [
        ("crosswalk/iso42001-ai-act", "controls/iso42001/a.7", "controls/eu-ai-act/art-12"),
    ]
