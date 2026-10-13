"""`grc propose` (Spec G G4): triage's high-confidence proposals become a patch of draft concepts; the rest an issue body."""

import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest
import yaml

from grc_evidence import adopt, cli
from grc_evidence.config import load_config
from grc_evidence.data import SCHEMA_VERSION
from grc_evidence.errors import GrcError
from grc_evidence.map_findings import map_findings
from grc_evidence.narrate import mapping_sha256
from grc_evidence.okf_lib import BundleError, load_bundle
from grc_evidence.propose import main

TODAY = date(2026, 10, 12)
SLUG = "semgrep-gap-one"


def _finding(rule_id: str, target: str = "app/main.py", message: str = "weak hash") -> dict:
    return {"tool": "semgrep", "rule_id": rule_id, "severity": "medium", "target": target, "message": message, "tags": []}


FINDINGS = [_finding("gap.one"), _finding("gap.one", "app/util.py"), _finding("gap.two"), _finding("gap.three")]


def _proposal(rule: str, proposal: str, confidence: str = "high", **extra: object) -> dict:
    return {"rule": f"semgrep:{rule}", "proposal": proposal, "rationale": "r", "confidence": confidence, **extra}


PROPOSALS = [
    _proposal("gap.one", "soc2:cc7.1", rationale="It detects a weakness."),
    _proposal("gap.two", "none", "medium", cutoff_from="soc2:cc6.1"),
    {"rule": "semgrep:gap.three", "proposal": "invalid", "errors": ["no proposal returned for this rule"]},
]


def _repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, findings: list[dict] = FINDINGS,
          proposals: list[dict] = PROPOSALS, knowledge: str = "knowledge") -> Path:
    """A `grc init` repo with the last scan's `out/mapping.json` and triage's `out/proposals.json`."""
    adopt.init(tmp_path)
    if knowledge != "knowledge":
        shutil.move(tmp_path / "knowledge", tmp_path / knowledge)
    mapping = map_findings(load_bundle(tmp_path / knowledge), findings, today=TODAY)
    (tmp_path / "out").mkdir()
    (tmp_path / "out/mapping.json").write_text(json.dumps({"schema_version": SCHEMA_VERSION, **mapping}))
    _write_proposals(tmp_path, proposals)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _write_proposals(repo: Path, proposals: list[dict], **doc: object) -> None:
    doc = {"mapping_sha256": mapping_sha256(repo / "out/mapping.json"), "model": "claude-haiku-4-5",
           "variant": "scoped", "abstain_on": "low+medium", "proposals": proposals} | doc
    (repo / "out/proposals.json").write_text(json.dumps(doc))


def _apply(repo: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    for args in (["--check"], []):
        subprocess.run(["git", "apply", *args, "out/agent/mapping.patch"], cwd=repo, check=True)


def _frontmatter(path: Path) -> dict:
    return yaml.safe_load(path.read_text().split("---\n")[1])


def test_patch_applies_and_the_gap_moves_to_the_control(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path, monkeypatch)
    main([])
    _apply(repo)
    path = repo / f"knowledge/policies/{SLUG}.md"
    fm = _frontmatter(path)
    assert (fm["type"], fm["title"], fm["tags"], fm["rule_ids"]) == ("Scanner Check", "semgrep gap.one", ["cc7.1"],
                                                                     ["semgrep:gap.one"])
    assert fm["generated"]["by"] == "claude-haiku-4-5 via grc triage" and "verified" not in fm
    mapping = map_findings(load_bundle(repo / "knowledge"), FINDINGS, today=TODAY)
    assert [f["target"] for f in mapping["controls"]["soc2:cc7.1"]["findings"]] == ["app/main.py", "app/util.py"]
    assert {u["finding"]["rule_id"] for u in mapping["unmapped"]} == {"gap.two", "gap.three"}
    text = path.read_text()
    assert '"weak hash" in `app/main.py`, `app/util.py` (2 findings)' in text
    assert '"It detects a weakness."' in text and "[CC7.1 — " in text and "](../controls/cc7.1.md)" in text


def test_applied_patch_fails_check_until_signed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path, monkeypatch)
    main([])
    _apply(repo)
    assert adopt.check(repo, load_config(repo)) == [f"knowledge/policies/{SLUG}.md: not verified by a person"]
    path = repo / f"knowledge/policies/{SLUG}.md"
    signed = path.read_text().replace("---\n# Rule", 'verified:\n  - by: "human:reviewer"\n    at: "2026-10-12T10:00:00-07:00"\n---\n# Rule')
    path.write_text(signed)
    with pytest.raises(BundleError, match="delete every draft marker line"):
        load_bundle(repo / "knowledge")
    path.write_text("".join(line for line in signed.splitlines(keepends=True) if not line.startswith("<!-- grc: draft")))
    assert adopt.check(repo, load_config(repo)) == []


def test_issue_body_lists_none_and_invalid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path, monkeypatch)
    main([])
    body = (repo / "out/agent/gaps.md").read_text()
    assert body.startswith("# Coverage gaps no control covers\n")
    assert "(claude-haiku-4-5, scoped, abstain on low+medium)" in body
    assert f"mapping {mapping_sha256(repo / 'out/mapping.json')[:12]}" in body and "docs/llm.md" in body
    assert "| `semgrep:gap.two` | 1 | none (leaned soc2:cc6.1, medium) |" in body
    assert "| `semgrep:gap.three` | 1 | invalid: no proposal returned for this rule |" in body
    assert "gap.one" not in body


def test_draft_refuses_proposals_for_another_mapping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path, monkeypatch)
    _write_proposals(repo, PROPOSALS, mapping_sha256="0" * 64)
    with pytest.raises(GrcError, match="another mapping.json; rerun grc triage"):
        main([])
    assert not (repo / "out/agent").exists()


def test_refuses_list_shaped_proposals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path, monkeypatch)
    (repo / "out/proposals.json").write_text(json.dumps(PROPOSALS))
    with pytest.raises(GrcError, match="rerun grc triage"):
        main([])


def _gap_rows(repo: Path) -> list[str]:
    return [line for line in (repo / "out/agent/gaps.md").read_text().splitlines() if line.startswith("| `")]


def test_undraftable_gaps_go_to_the_issue_body(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                               capsys: pytest.CaptureFixture[str]) -> None:
    """Review F-03: a high-confidence proposal that cannot be drafted is still a gap to file, not only a printed line."""
    repo = _repo(tmp_path, monkeypatch, proposals=[
        _proposal("gap.one", "soc2:cc9.9"),
        _proposal("not.a.gap", "soc2:cc7.1"),
        _proposal("gap.two", "soc2:cc7.1"),
    ])
    main([])
    assert _gap_rows(repo) == ["| `semgrep:gap.one` | 2 | soc2:cc9.9 (high): control not in the bundle |"]
    assert "skipped semgrep:not.a.gap: not a coverage gap in out/mapping.json" in capsys.readouterr().out
    assert (repo / "out/agent/mapping.patch").read_text().count("\ndiff --git ") == 1  # gap.two only


def test_rule_id_with_wildcard_characters_is_not_drafted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path, monkeypatch, findings=[_finding("gap[1]")], proposals=[_proposal("gap[1]", "soc2:cc7.1")])
    main([])
    assert _gap_rows(repo) == [
        "| `semgrep:gap[1]` | 1 | soc2:cc7.1 (high): not a literal rule id (no whitespace in the tool, no * ? [ ]) |"]
    assert not (repo / "out/agent/mapping.patch").exists()


def test_existing_concept_path_is_not_drafted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path, monkeypatch, proposals=[_proposal("gap.one", "soc2:cc7.1"), _proposal("gap.two", "soc2:cc7.1")])
    (repo / f"knowledge/policies/{SLUG}.md").write_text("---\ntype: Reference\n---\n")
    main([])
    assert _gap_rows(repo) == [f"| `semgrep:gap.one` | 2 | soc2:cc7.1 (high): knowledge/policies/{SLUG}.md exists |"]
    patch = (repo / "out/agent/mapping.patch").read_text()
    assert "+++ b/knowledge/policies/semgrep-gap-two.md" in patch and SLUG + ".md" not in patch


def test_slug_collision_lists_the_second_rule(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Review F-05: two rules with one slug: the first is drafted, the second is filed, neither is lost."""
    repo = _repo(tmp_path, monkeypatch, findings=[_finding("gap.one"), _finding("gap-one")],
                 proposals=[_proposal("gap.one", "soc2:cc7.1"), _proposal("gap-one", "soc2:cc7.1")])
    main([])
    assert _gap_rows(repo) == [
        f"| `semgrep:gap-one` | 1 | soc2:cc7.1 (high): knowledge/policies/{SLUG}.md is drafted for semgrep:gap.one |"]


def test_control_without_its_own_tag_is_still_tagged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Review F-02: the loader accepts a control that does not carry its own key as a tag; the tag comes from the key."""
    repo = _repo(tmp_path, monkeypatch, proposals=[_proposal("gap.one", "soc2:cc7.1")])
    control = repo / "knowledge/controls/cc7.1.md"
    control.write_text(control.read_text().replace(", cc7.1]", "]").replace(" cc7.1,", ""))
    edited = load_bundle(repo / "knowledge").control("soc2:cc7.1")
    assert edited is not None and edited.control_tags == ()
    main([])
    _apply(repo)
    assert _frontmatter(repo / f"knowledge/policies/{SLUG}.md")["tags"] == ["cc7.1"]


@pytest.mark.parametrize(("key", "tag"), [("soc2:cc7.1", "cc7.1"), ("iso42001:a.6", "iso42001:a.6")])
def test_tag_is_the_controls_tag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: str, tag: str) -> None:
    repo = _repo(tmp_path, monkeypatch, proposals=[_proposal("gap.one", key)])
    main([])
    _apply(repo)
    assert _frontmatter(repo / f"knowledge/policies/{SLUG}.md")["tags"] == [tag]


def test_concept_path_is_a_slug_under_the_configured_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path, monkeypatch, findings=[_finding("a/B:c d")], proposals=[_proposal("a/B:c d", "soc2:cc7.1")],
                 knowledge="kb")
    main(["--knowledge", "kb"])
    _apply(repo)
    assert _frontmatter(repo / "kb/policies/semgrep-a-b-c-d.md")["rule_ids"] == ["semgrep:a/B:c d"]
    assert "semgrep-a-b-c-d" in load_bundle(repo / "kb").concepts["policies/semgrep-a-b-c-d"].path


def test_nothing_to_draft_removes_a_stale_patch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path, monkeypatch)
    main([])
    _write_proposals(repo, PROPOSALS[1:] + [_proposal("gap.one", "none")])
    main([])
    assert not (repo / "out/agent/mapping.patch").exists()
    assert "semgrep:gap.one" in (repo / "out/agent/gaps.md").read_text()


def test_untrusted_text_stays_quoted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hostile = "x\n# H\n---\n[y](../controls/cc6.1.md) | `z`"
    repo = _repo(tmp_path, monkeypatch, findings=[_finding("gap.one", message="m](../controls/cc6.1.md)\n# H"), _finding("gap.two")],
                 proposals=[_proposal("gap.one", "soc2:cc7.1", rationale=hostile),
                            {"rule": "semgrep:gap.two", "proposal": "invalid", "errors": [hostile]}])
    main([])
    _apply(repo)
    concept = load_bundle(repo / "knowledge").concepts[f"policies/{SLUG}"]
    assert concept.links == ("controls/cc7.1",)
    assert [line for line in concept.body.splitlines() if line.startswith(("#", "---"))] == [
        "# Rule", "# Satisfies", "# Enforced at", "# Remediation"]
    rows = [line for line in (repo / "out/agent/gaps.md").read_text().splitlines() if line.startswith("| `")]
    assert len(rows) == 1 and rows[0].count(" | ") == 2  # one row, three cells: the rule, the count, the reason


def test_no_gaps_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path, monkeypatch, findings=[], proposals=[])
    (repo / "out/agent").mkdir()
    (repo / "out/agent/gaps.md").write_text("stale\n")
    main([])
    assert list((repo / "out/agent").iterdir()) == []


def test_cli_refusal_is_one_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path, monkeypatch)
    (repo / "out/proposals.json").write_text(json.dumps(PROPOSALS))
    with pytest.raises(SystemExit, match=r"^grc propose: .*rerun grc triage$"):
        cli.main(["propose"])
