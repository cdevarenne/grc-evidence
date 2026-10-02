"""The base bundle ships with the engine; this repo's knowledge/ and policies/ hold byte-identical copies."""

import re
from pathlib import Path

import pytest
import yaml

from okf_grc import data
from okf_grc.okf_lib import load_bundle

ROOT = Path(__file__).parent.parent
BASE = Path(str(data.path("base")))
POLICIES = Path(str(data.path("policies")))
BUNDLE = load_bundle(BASE)
# A link to `stack/index.md` is fine: every adopter bundle has a stack section; its components are its own.
SAMPLE_ONLY = re.compile(r"app/|sample app|\.\./stack/(?!index\.md)|suppressions/|drf-authenticated-writes", re.IGNORECASE)


def _files(root: Path, pattern: str) -> list[Path]:
    """Files under `root`, skipping caches and hidden files such as `.DS_Store`."""
    return sorted(
        p.relative_to(root) for p in root.rglob(pattern)
        if "__pycache__" not in p.parts and not any(part.startswith(".") for part in p.relative_to(root).parts)
    )


def test_base_is_a_standalone_bundle() -> None:
    root = yaml.safe_load((BASE / "index.md").read_text().split("---\n")[1])
    assert root == {"okf_version": "0.2"}
    assert {c.type for c in BUNDLE.concepts.values()} >= {"SOC 2 Control", "ISO/IEC 42001 Control", "EU AI Act Article", "Scanner"}
    for concept in BUNDLE.concepts.values():
        for link in concept.links:
            assert link in BUNDLE.concepts, f"{concept.path}: link to {link} leaves the base"


CONCEPTS = sorted(BUNDLE.concepts.values(), key=lambda c: c.id)


@pytest.mark.parametrize("concept", CONCEPTS, ids=[c.id for c in CONCEPTS])
def test_base_concepts_are_verified_and_name_no_sample_app(concept) -> None:
    assert any(str(e.get("by", "")).startswith("human:") for e in concept.frontmatter.get("verified") or [])
    assert not SAMPLE_ONLY.search((BASE / concept.path).read_text()), concept.path


@pytest.mark.parametrize("rel", [p for p in _files(BASE, "*.md") if p.name != "index.md"], ids=str)
def test_knowledge_copies_each_base_concept(rel: Path) -> None:
    assert (ROOT / "knowledge" / rel).read_bytes() == (BASE / rel).read_bytes()


@pytest.mark.parametrize("rel", _files(POLICIES, "*.*"), ids=str)
def test_policies_copies_each_base_policy_file(rel: Path) -> None:
    assert (ROOT / "policies" / rel).read_bytes() == (POLICIES / rel).read_bytes()


def test_sample_only_policy_stays_out_of_the_base() -> None:
    assert not (BASE / "policies" / "drf-authenticated-writes.md").exists()
    assert not list(POLICIES.rglob("drf-*"))
    assert (ROOT / "policies" / "semgrep" / "drf-allowany.yaml").is_file()
