"""okflib checks every concept the engine loads (Spec J): its errors fail the load and name the file."""

from datetime import date
from pathlib import Path

import pytest

from grc_evidence.okf_lib import BundleError, load_bundle


def _bundle(tmp_path: Path, frontmatter: str, body: str = "# Intent\nx\n") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "index.md").write_text('---\nokf_version: "0.2"\n---\n# Bundle\n')
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "a.md").write_text(f"---\n{frontmatter}---\n{body}")
    return tmp_path


@pytest.mark.parametrize("frontmatter", [
    "type: Reference\nstale_after: soon\n",                  # okflib: ValueError
    "type: Reference\ngenerated: {by: a, at: yesterday}\n",  # okflib: ValueError
    "type: Reference\nverified: human:reviewer\n",           # a string, not a list of stamps
    "type: Reference\nverified: [human:reviewer]\n",         # a list of strings, not of stamps
])
def test_okflib_errors_name_the_file(tmp_path: Path, frontmatter: str) -> None:
    with pytest.raises(BundleError, match=r"^notes/a\.md: "):
        load_bundle(_bundle(tmp_path, frontmatter))


def test_stale_after_is_read(tmp_path: Path) -> None:
    concept = load_bundle(_bundle(tmp_path, "type: Reference\nstale_after: 2027-01-01\n")).concepts["notes/a"]
    assert concept.stale_after == date(2027, 1, 1)
    assert load_bundle(_bundle(tmp_path / "b", "type: Reference\n")).concepts["notes/a"].stale_after is None


def test_links_unchanged_for_anchors_and_escapes(tmp_path: Path) -> None:
    """okflib would turn these into made-up concept ids; the engine's own link rules drop them."""
    body = "[top](#intro) [up](../../README.md) [mail](mailto:a@b.c) [img](x.png) [ok](b.md) [ok again](b.md#s)\n"
    bundle = _bundle(tmp_path / "x", "type: Reference\n", body)
    (bundle / "notes" / "b.md").write_text("---\ntype: Reference\n---\n")
    assert load_bundle(bundle).concepts["notes/a"].links == ("notes/b",)


def test_verified_stamps_still_read_as_written(tmp_path: Path) -> None:
    fm = 'type: Reference\nverified:\n  - by: "human:reviewer"\n    at: "2026-10-06T10:00:00-07:00"\n'
    concept = load_bundle(_bundle(tmp_path, fm)).concepts["notes/a"]
    assert concept.frontmatter["verified"] == [{"by": "human:reviewer", "at": "2026-10-06T10:00:00-07:00"}]
