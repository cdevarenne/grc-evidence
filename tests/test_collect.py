"""`grc collect` and the collect step of `grc run`: outputs, ledger entries, mapping and the 1.2 contract (Spec H)."""

import hashlib
import json
import shutil
from datetime import date
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_collect_changes import _pr

from grc_evidence import cli, collect, data, ledger, run_scan
from grc_evidence.collect import collectors_not_run, run_collect
from grc_evidence.config import AcceptedBot, Config, RepoSpec
from grc_evidence.github_api import GitHubError, NotFound
from grc_evidence.github_queries import DEFAULT_BRANCH, MERGED_PRS, WORKFLOWS
from grc_evidence.manifest import OPTIONAL_OUTPUTS
from grc_evidence.map_findings import NOT_RUN, map_findings
from grc_evidence.map_findings import main as map_main
from grc_evidence.okf_lib import load_bundle

NOW = "2026-10-06T06:00:00+00:00"
FIXTURES = Path(__file__).parent / "fixtures"
SCANNER = "jobs:\n  semgrep:\n    runs-on: ubuntu-latest\n    steps: [{run: semgrep scan}]\n"


class FakeGitHub:
    """Both collectors' reads for repos named in `prs`; `broken` repos fail like a GitHub outage."""

    def __init__(self, prs: dict[str, list[dict]], broken: tuple[str, ...] = ()) -> None:
        self.prs, self.broken = prs, broken

    def graphql(self, query: str, variables: dict) -> dict:
        repo = f"{variables['owner']}/{variables['name']}"
        if repo in self.broken:
            raise GitHubError(f"GitHub API 502 on graphql ({repo})")
        rate = {"rateLimit": {"cost": 1, "remaining": 4990}}
        if query == DEFAULT_BRANCH:
            return {**rate, "repository": {"defaultBranchRef": {"name": "main"}}}
        if query == WORKFLOWS:
            entries = [{"name": "ci.yml", "type": "blob", "object": {"text": SCANNER, "isTruncated": False}}]
            return {**rate, "repository": {"object": {"entries": entries}}}
        assert query == MERGED_PRS
        page = {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": self.prs[repo]}
        return {**rate, "repository": {"pullRequests": page}}

    def rest(self, path: str) -> dict | list | None:
        if path.endswith("/protection"):
            raise NotFound("GitHub API 404", "Branch not protected")
        return []


def _config(*repos: str, collect_on: tuple[str, ...] = ("scm", "changes")) -> Config:
    return Config(
        window_start=date(2026, 6, 1), window_end=date(2026, 8, 31), github_scanner_jobs=("semgrep",),
        github_repos=tuple(RepoSpec(r, "in-scope", collect_on) for r in repos),
        github_accepted_bots=(AcceptedBot("coderabbitai", "team policy"),),
    )


def test_collectors_not_run() -> None:
    """Only collectors that actually ran count, whatever grc.yaml lists."""
    assert collectors_not_run(()) == ["github"]
    assert collectors_not_run(("scm",)) == ["github:change-"]
    assert collectors_not_run(("scm", "changes")) == []


def _github_only_bundle(tmp_path: Path, rule_ids: str) -> Path:
    bundle = tmp_path / "bundle"
    shutil.copytree(FIXTURES / "bundle", bundle)
    (bundle / "scanners" / "github.md").write_text(
        f"---\ntype: Scanner\ntitle: GitHub\ndescription: Fixture.\ntags: [cc7.2]\nrule_ids: {rule_ids}\n---\n# Evidences\n"
    )
    return bundle


@pytest.mark.parametrize(("ran", "status"), [
    ((), "not-assessed"),
    (("scm",), "no-violations-detected"),
    (("scm", "changes"), "no-violations-detected"),
])
def test_github_rules_not_run_without_config(tmp_path: Path, ran: tuple[str, ...], status: str) -> None:
    """Review focus 1: a control evidenced only by github rules is never a pass when the collectors did not run."""
    bundle = load_bundle(_github_only_bundle(tmp_path, '["github:scm-*", "github:change-*"]'))
    entry = map_findings(bundle, [], {"tools_not_run": collectors_not_run(ran)})["controls"]["soc2:cc7.2"]
    assert entry["status"] == status
    if status == "not-assessed":
        assert entry["reason"] == NOT_RUN


def test_change_rules_not_run_when_only_scm_is_collected(tmp_path: Path) -> None:
    bundle = load_bundle(_github_only_bundle(tmp_path, '["github:change-*"]'))
    context = {"tools_not_run": collectors_not_run(("scm",))}
    assert map_findings(bundle, [], context)["controls"]["soc2:cc7.2"]["status"] == "not-assessed"


def test_run_collect_writes_outputs_and_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    prs = {"acme/api": [_pr(1, "2026-07-02T00:00:00Z", reviews=[])]}
    entries = run_collect(_config("acme/api"), tmp_path / "out", FakeGitHub(prs), NOW)
    assert [(e["collector"], e["repo"]) for e in entries] == [("scm", "acme/api"), ("changes", "acme/api")]
    for e in entries:
        assert e["window"] == {"start": "2026-06-01", "end": "2026-08-31"} and e["recorded_at"] == NOW
        assert e["rate_limit"]["remaining"] == 4990 and e["rate_limit"]["cost"] >= 1
        assert e["inputs"]["branch"] == "main" and e["inputs"]["query_sha256"]
        for rel, sha in e["outputs"].items():
            assert hashlib.sha256((tmp_path / "out" / rel).read_bytes()).hexdigest() == sha
    scm, changes = entries
    assert scm["summary"] == {"required_reviews": 0, "required_checks": [], "bypass": False, "readable": True}
    assert changes["summary"]["in_population"] == 1 and changes["summary"]["flags"]["no_approval"] == 1
    doc = json.loads((tmp_path / "out" / "collect" / "github-findings.json").read_text())
    assert doc["collectors"] == ["changes", "scm"]
    findings = doc["findings"]
    assert {f["rule_id"] for f in findings} == {"scm-no-required-review", "scm-no-required-checks", "change-no-approval"}
    assert not (tmp_path / "evidence").exists()  # run_collect returns entries; the caller appends them


def test_collect_failure_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Review focus 2: repo 2 of 2 fails, so no output is written and no ledger entry is appended."""
    monkeypatch.chdir(tmp_path)
    t = FakeGitHub({"acme/api": [], "acme/web": []}, broken=("acme/web",))
    with pytest.raises(GitHubError, match="acme/web"):
        run_collect(_config("acme/api", "acme/web"), tmp_path / "out", t, NOW)
    assert not (tmp_path / "out" / "collect").exists()


def _repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prs: dict[str, list[dict]], github: str) -> Path:
    """A repo with the base bundle, a grc.yaml naming `acme/api`, scanners stubbed and GitHub faked."""
    monkeypatch.chdir(tmp_path)
    shutil.copytree(Path(str(data.path("base"))), tmp_path / "knowledge")
    (tmp_path / "app").mkdir()
    (tmp_path / "grc.yaml").write_text(github)

    def scan(argv: list[str]) -> None:
        out = Path(argv[argv.index("--out") + 1])
        (out / "findings.json").write_text(json.dumps({"schema_version": data.SCHEMA_VERSION, "findings": []}))

    monkeypatch.setattr(run_scan, "main", scan)
    monkeypatch.setattr(collect, "transport_from_env", lambda: FakeGitHub(prs))
    return tmp_path


GITHUB = "conftest: {inputs: []}\nwindow: {start: 2026-06-01, end: 2026-08-31}\ngithub:\n  repos:\n    - {name: acme/api, tier: in-scope, collect: [scm, changes]}\n"


def test_run_maps_github_findings_to_cc81(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path, monkeypatch, {"acme/api": [_pr(1, "2026-07-02T00:00:00Z", reviews=[])]}, GITHUB)
    cli.main(["run"])
    cc81 = json.loads((repo / "out" / "mapping.json").read_text())["controls"]["soc2:cc8.1"]
    assert cc81["status"] == "not-satisfied"
    assert {f["rule_id"] for f in cc81["findings"] if f["tool"] == "github"} >= {"scm-no-required-review", "change-no-approval"}
    run = json.loads((repo / "out" / "run.json").read_text())
    assert set(OPTIONAL_OUTPUTS) <= set(run["outputs"]) and run["schema_version"] == data.SCHEMA_VERSION


def test_run_appends_run_entry_last(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path, monkeypatch, {"acme/api": []}, GITHUB)
    cli.main(["run"])
    entries = ledger.read(repo / "evidence" / "ledger.jsonl")
    assert [e["collector"] for e in entries] == ["scm", "changes", "run"]
    run = entries[-1]
    mapping = json.loads((repo / "out" / "mapping.json").read_text())
    assert run["summary"] == {key: c["status"] for key, c in mapping["controls"].items()}
    assert run["repo"] is None and run["outputs"]["run.json"] == hashlib.sha256((repo / "out" / "run.json").read_bytes()).hexdigest()
    assert ledger.verify(repo / "evidence" / "ledger.jsonl") is None


def test_no_window_means_no_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A repo opts into Type 2 evidence with `window`; without it, `grc run` writes no ledger."""
    repo = _repo(tmp_path, monkeypatch, {}, "conftest: {inputs: []}\n")
    cli.main(["run"])
    assert (repo / "out" / "run.json").is_file() and not (repo / "evidence").exists()
    assert not (repo / "out" / "collect").exists()


def test_a_failed_collection_leaves_out_and_the_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path, monkeypatch, {"acme/api": []}, GITHUB)
    cli.main(["run"])
    before = (repo / "evidence" / "ledger.jsonl").read_bytes(), (repo / "out" / "run.json").read_bytes()
    monkeypatch.setattr(collect, "transport_from_env", lambda: FakeGitHub({}, broken=("acme/api",)))
    with pytest.raises(SystemExit, match="grc run: .*502"):
        cli.main(["run"])
    assert ((repo / "evidence" / "ledger.jsonl").read_bytes(), (repo / "out" / "run.json").read_bytes()) == before


def test_grc_collect_alone_appends_no_run_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path, monkeypatch, {"acme/api": []}, GITHUB)
    cli.main(["collect", "scm"])
    assert [e["collector"] for e in ledger.read(repo / "evidence" / "ledger.jsonl")] == ["scm"]
    assert (repo / "out" / "collect" / "scm-posture.json").is_file()
    assert not (repo / "out" / "collect" / "population.csv").exists()


def test_accepted_bots_reach_the_collector(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    review = {"author": {"login": "coderabbitai", "__typename": "Bot"}, "state": "APPROVED", "submittedAt": "2026-07-01T09:00:00Z",
              "authorCanPushToRepository": False, "commit": {"oid": "a" * 40}}
    run_collect(_config("acme/api"), tmp_path / "out", FakeGitHub({"acme/api": [_pr(1, "2026-07-02T00:00:00Z", reviews=[review])]}), NOW)
    doc = json.loads((tmp_path / "out" / "collect" / "changes.json").read_text())
    assert doc["changes"][0]["approvers"] == "coderabbitai" and "bot_approval" in doc["changes"][0]["flags"]


def test_schema_accepts_github_target() -> None:
    schema = json.loads(Path(str(data.path("schemas/findings.schema.json"))).read_text())
    finding = {"tool": "github", "rule_id": "change-no-approval", "severity": "high", "target": "github:acme/api#1",
               "message": "m", "tags": []}
    Draft202012Validator(schema).validate({"schema_version": "1.2", "findings": [finding]})



def _map_status(repo: Path) -> str:
    """Map an empty scan in `repo` (grc.yaml lists acme/api); cc7.2 has only github rules."""
    (repo / "out").mkdir(exist_ok=True)
    (repo / "out" / "findings.json").write_text(json.dumps({"schema_version": data.SCHEMA_VERSION, "findings": []}))
    map_main(["--out", "out"])
    return json.loads((repo / "out" / "mapping.json").read_text())["controls"]["soc2:cc7.2"]["status"]


def test_map_trusts_only_a_collection_that_ran(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """grc.yaml lists collectors, but a run without the collect step maps github rules as not run."""
    repo = _repo(tmp_path, monkeypatch, {"acme/api": []}, GITHUB)
    shutil.rmtree(repo / "knowledge")
    shutil.copytree(_github_only_bundle(repo / "b", '["github:scm-*", "github:change-*"]'), repo / "knowledge")
    assert _map_status(repo) == "not-assessed"
    (repo / "out" / "collect").mkdir()
    (repo / "out" / "collect" / "github-findings.json").write_text(
        json.dumps({"schema_version": data.SCHEMA_VERSION, "collectors": ["scm", "changes"], "findings": []}))
    assert _map_status(repo) == "no-violations-detected"


def test_run_without_collect_reaches_neither_github_nor_the_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The MCP scan tool runs the pipeline this way: an agent cannot reach GitHub or write evidence."""
    repo = _repo(tmp_path, monkeypatch, {}, GITHUB)

    def no_github() -> FakeGitHub:
        raise AssertionError("an agent's scan must not read GitHub")

    monkeypatch.setattr(collect, "transport_from_env", no_github)
    cli.run(["--out", "out"], collect=False)
    assert (repo / "out" / "run.json").is_file()
    assert not (repo / "out" / "collect").exists() and not (repo / "evidence").exists()
    run = json.loads((repo / "out" / "run.json").read_text())
    assert not set(OPTIONAL_OUTPUTS) & set(run["outputs"])


def test_grc_run_no_collect_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """2.0.1: pull request runs skip the collectors, so they need no token and write no ledger."""
    repo = _repo(tmp_path, monkeypatch, {}, GITHUB)

    def no_github() -> FakeGitHub:
        raise AssertionError("a --no-collect run must not read GitHub")

    monkeypatch.setattr(collect, "transport_from_env", no_github)
    cli.main(["run", "--no-collect"])
    assert (repo / "out" / "run.json").is_file() and not (repo / "evidence").exists()
