"""`grc suppress draft` (Spec I Part A): a pending suppression from the last scan; a person writes the reason and signs."""

import json
import shutil
from datetime import date
from pathlib import Path

import pytest
import yaml

from grc_evidence.adopt import check_report
from grc_evidence.config import load_config
from grc_evidence.data import SCHEMA_VERSION
from grc_evidence.errors import GrcError
from grc_evidence.map_findings import map_findings
from grc_evidence.okf_lib import BundleError, load_bundle
from grc_evidence.suppress import main

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = "2026-10-12"
GO_MODS = [f"upstream/src/{s}/go.mod" for s in ("checkoutservice", "frontend", "productcatalogservice", "shippingservice")]
CVE = {"tool": "trivy", "rule_id": "CVE-2026-78669", "severity": "high", "message": "golang.org/x/net:\nHTTP/2 DoS", "tags": ["vulnerability"]}
GAP = {"tool": "checkov", "rule_id": "CKV_TEST_99", "severity": "low", "target": "app/Dockerfile", "message": "m", "tags": []}
FINDINGS = [CVE | {"target": t} for t in GO_MODS] + [GAP]


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repo with the fixture bundle as `knowledge/` and the last scan's `out/mapping.json`."""
    shutil.copytree(FIXTURES / "bundle", tmp_path / "knowledge")
    (tmp_path / "out").mkdir()
    mapping = map_findings(load_bundle(tmp_path / "knowledge"), FINDINGS, today=date.fromisoformat(TODAY))
    (tmp_path / "out" / "mapping.json").write_text(json.dumps({"schema_version": SCHEMA_VERSION, **mapping}))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _draft(*args: str, targets: list[str] = GO_MODS, kind: str = "accepted-risk", owner: str = "human:reviewer") -> None:
    main(["draft", "--tool", "trivy", "--rule-id", "CVE-2026-78669", *(a for t in targets for a in ("--target", t)),
          "--kind", kind, "--owner", owner, "--today", TODAY, *args])


def _frontmatter(path: Path) -> dict:
    return yaml.safe_load(path.read_text().split("---\n")[1])


def test_draft_writes_one_file_for_several_targets(repo: Path) -> None:
    _draft()
    fm = _frontmatter(repo / "knowledge/suppressions/trivy-cve-2026-78669.md")
    assert fm["finding"] == {"tool": "trivy", "rule_id": "CVE-2026-78669", "targets": GO_MODS}
    assert (fm["title"], fm["kind"], fm["owner"], fm["approved"], fm["expires"]) == (
        "CVE-2026-78669 in 4 files", "accepted-risk", "human:reviewer", "2026-10-12", "2026-11-11"
    )
    assert fm["tags"] == ["suppression"] and fm["generated"]["by"].startswith("grc-evidence/")


def test_draft_single_target_uses_target(repo: Path) -> None:
    _draft(targets=[GO_MODS[1]])
    fm = _frontmatter(repo / "knowledge/suppressions/trivy-cve-2026-78669-upstream-src-frontend-go-mod.md")
    assert fm["finding"]["target"] == GO_MODS[1] and fm["title"] == f"CVE-2026-78669 in {GO_MODS[1]}"


def test_draft_slug_is_cut_to_100(repo: Path) -> None:
    long = "upstream/" + "a" * 120 + "/go.mod"
    (repo / "out/mapping.json").write_text(json.dumps({"schema_version": SCHEMA_VERSION, **map_findings(
        load_bundle(repo / "knowledge"), [CVE | {"target": long}], today=date.fromisoformat(TODAY))}))
    _draft(targets=[long])
    (path,) = (repo / "knowledge/suppressions").glob("*.md")
    assert len(path.stem) == 100 and path.stem.startswith("trivy-cve-2026-78669-upstream-aaa")


def test_draft_has_no_verified_and_has_marker(repo: Path) -> None:
    _draft()
    text = (repo / "knowledge/suppressions/trivy-cve-2026-78669.md").read_text()
    assert "verified" not in _frontmatter(repo / "knowledge/suppressions/trivy-cve-2026-78669.md")
    reason = text.split("# Reason\n", 1)[1]
    assert reason.count("<!-- grc: draft") == 2  # Reason and Compensating control
    assert '- `upstream/src/frontend/go.mod`: high, "golang.org/x/net: HTTP/2 DoS" (controls: soc2:cc7.1)' in text


def test_draft_accepted_risk_has_compensating_control_section(repo: Path) -> None:
    _draft()
    assert "\n# Compensating control\n\n<!-- grc: draft" in (repo / "knowledge/suppressions/trivy-cve-2026-78669.md").read_text()
    main(["draft", "--tool", "checkov", "--rule-id", "CKV_TEST_99", "--target", "app/Dockerfile",
          "--kind", "false-positive", "--owner", "human:reviewer", "--today", TODAY])
    text = (repo / "knowledge/suppressions/checkov-ckv-test-99-app-dockerfile.md").read_text()
    assert "# Compensating control" not in text and "(coverage gap)" in text


def test_draft_is_pending_until_verified(repo: Path) -> None:
    _draft()
    mapping = map_findings(load_bundle(repo / "knowledge"), FINDINGS, today=date.fromisoformat(TODAY))
    assert mapping["pending_suppressions"] == [
        {"id": "suppressions/trivy-cve-2026-78669", "approved": TODAY, "reason": "not verified by a person"}
    ]
    assert mapping["suppressed"] == []


def _sign(path: Path, *, keep_markers: bool = False) -> None:
    text = path.read_text()
    if not keep_markers:
        text = "\n".join(line for line in text.splitlines() if not line.startswith("<!-- grc: draft")) + "\n"
    head, body = text.split("---\n", 2)[1:]
    path.write_text(f"---\n{head}verified:\n  - by: \"human:reviewer\"\n    at: \"2026-10-12T10:00:00+00:00\"\n---\n{body}")


def test_check_rejects_draft_until_signed(repo: Path) -> None:
    """Spec decision 7a: an unsigned draft fails `grc check`, as any unverified concept; signed, it passes."""
    _draft()
    path = repo / "knowledge/suppressions/trivy-cve-2026-78669.md"
    config = load_config(repo)

    def problems() -> list[str]:
        return [p for p in check_report(repo, config)[0] if "suppressions/" in p]

    assert problems() == ["knowledge/suppressions/trivy-cve-2026-78669.md: not verified by a person"]
    _sign(path, keep_markers=True)
    with pytest.raises(BundleError, match="draft marker"):
        load_bundle(repo / "knowledge")
    path.unlink()
    _draft()
    _sign(path)
    assert problems() == []
    mapping = map_findings(load_bundle(repo / "knowledge"), FINDINGS, today=date.fromisoformat(TODAY))
    assert len(mapping["suppressed"]) == 4


@pytest.mark.parametrize(("args", "error"), [
    ({"targets": ["upstream/src/adservice/go.mod"]}, "no trivy:CVE-2026-78669 finding in upstream/src/adservice/go.mod"),
    ({"days": "0"}, "--days must be from 1 to 90"),
    ({"days": "91"}, "--days must be from 1 to 90"),
    ({"owner": "reviewer"}, "--owner must be a person"),
    ({"owner": "human:<you>"}, "replace <you> with your name"),
    ({"id": "../x"}, "--id"),
    ({"id": "a/b"}, "--id"),
    ({"id": "Index"}, "--id"),
    ({"id": "index"}, "--id"),
    ({"id": "log"}, "--id"),
    ({"id": "a" * 101}, "--id"),
])
def test_draft_refuses(repo: Path, args: dict, error: str) -> None:
    extra = [*(["--days", args["days"]] if "days" in args else []), *(["--id", args["id"]] if "id" in args else [])]
    kwargs = {k: v for k, v in args.items() if k in ("targets", "owner")}
    with pytest.raises(GrcError, match=error):
        _draft(*extra, **kwargs)
    assert not (repo / "knowledge/suppressions").exists() or not list((repo / "knowledge/suppressions").glob("*.md"))


def test_draft_refuses_accepted_risk_on_gap(repo: Path) -> None:
    with pytest.raises(GrcError, match="coverage gap; only false-positive"):
        main(["draft", "--tool", "checkov", "--rule-id", "CKV_TEST_99", "--target", "app/Dockerfile",
              "--kind", "accepted-risk", "--owner", "human:reviewer", "--today", TODAY])


def test_draft_refuses_finding_already_named(repo: Path) -> None:
    """Pending, active and expired alike: renewing or widening one is a person's edit."""
    _draft(targets=GO_MODS[:2])
    with pytest.raises(GrcError, match=r"suppressions/trivy-cve-2026-78669\.md already names .*; edit or remove it first"):
        _draft("--id", "other", targets=GO_MODS[1:])


def test_draft_refuses_existing_file(repo: Path) -> None:
    (repo / "knowledge/suppressions").mkdir()
    (repo / "knowledge/suppressions/trivy-cve-2026-78669.md").write_text("---\ntype: Reference\ntitle: kept\n---\n# Kept\n")
    with pytest.raises(GrcError, match="exists; pass --id"):
        _draft()
    assert "kept" in (repo / "knowledge/suppressions/trivy-cve-2026-78669.md").read_text()
