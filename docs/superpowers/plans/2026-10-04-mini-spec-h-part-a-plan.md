# Mini Spec H Part A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect SOC 2 Type 2 evidence over an audit window from N GitHub repos: settings, change population, sample evidence, a hash-chained ledger and a window report. Then release it as `grc-evidence` v2.0.0.

**Architecture:** New collectors read the GitHub API through a `Transport` interface. Tests use recorded responses; production uses HTTPS. Collectors emit findings in the existing contract (`tool: "github"`), so mapping, OSCAL and the report need no new path. Every collection and every `grc run` appends a hash-chained entry to `evidence/ledger.jsonl`. `grc window` derives control history from that ledger only.

**Tech Stack:** Python 3.14, stdlib `urllib` and `hmac`, PyYAML, pytest, ruff, mypy, uv_build. No new runtime dependency.

**Spec:** `docs/superpowers/specs/2026-10-04-mini-spec-h-type2-evidence-window.md`

## Global Constraints

- `requires-python = ">=3.14"`. Runtime dependencies stay `pyyaml` only.
- Read-only: no code path sends a write request (POST to REST, a GraphQL `mutation`) to GitHub. GraphQL reads use POST. That is the only POST.
- The token comes from `GITHUB_TOKEN`, then `GH_TOKEN`. It never appears in an output, a log line, an exception message or the ledger.
- Window bounds: `[start 00:00:00Z, end+1 00:00:00Z)`. `near_boundary` = within 8 hours of either bound.
- Ledger `schema_version` = `"1.0"`. Output contract `SCHEMA_VERSION` = `"1.2"`.
- Pseudonym = `"p-"` + first 10 hex characters of HMAC-SHA256(salt, login). Salt env default `GRC_PEOPLE_SALT`.
- Absence is never a pass: unreadable rules, missing checks and collectors that did not run never yield `no-violations-detected`.
- Clean-room: no client, employer or person names in code, fixtures, docs or commits. Fixtures committed to the public repo hold only pseudonymized logins.
- Docs, docstrings, comments and commit messages are in ASD-STE100 Simplified Technical English.
- `uv run pytest -q`, `uv run ruff check` and `uv run mypy` pass after every task.

## Review Focus

1. **A control evidenced only by `github:*` rules, with no `github` config.** It must be `not-assessed` (`rules-not-run`), not `no-violations-detected`. Test: Task 8, `test_github_rules_not_run_without_config`.
2. **GraphQL fails in the middle of pagination** (HTTP 502, or a secondary rate limit as HTTP 403 with `retry-after`). Nothing is written and no ledger entry is appended. The run exits with the repo name. Test: Task 8, `test_collect_failure_writes_nothing`.
3. **A pagination cursor that does not advance**, or `hasNextPage` stays true with the same cursor. Stop with an error; never loop. Test: Task 7, `test_pagination_same_cursor_raises`.
4. **The same collector runs twice on one day.** The window report uses the last entry of each day, with no double counting. Test: Task 10, `test_same_day_entries_last_wins`.
5. **A recorded fixture that still holds a real login.** A repo test scans every JSON file under `tests/fixtures/github/` and fails on any `login` value that does not start with `p-` (except `ghost`). Test: Task 12, `test_fixtures_pseudonymized`.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/okf_grc/window.py` (new) | UTC bounds, `in_window`, `near_boundary`, timestamp parsing |
| `src/okf_grc/config.py` (modify) | `window`, `ledger`, `people`, `people_salt_env`, `window_max_gap_days`, `github.*`; `RepoSpec` |
| `src/okf_grc/ledger.py` (new) | Canonical JSON, append with hash chain, read, verify |
| `src/okf_grc/github_api.py` (new) | `Transport` protocol, `HttpTransport`, `RecordedTransport`, `GitHubError` |
| `src/okf_grc/github_queries.py` (new) | GraphQL query strings (constants only) |
| `src/okf_grc/people.py` (new) | `Namer`: real or pseudonymous logins |
| `src/okf_grc/collect_scm.py` (new) | Posture reading, workflow parsing, `scm-*` findings |
| `src/okf_grc/collect_changes.py` (new) | Population fetch, approver rules, `change-*` findings, CSV/JSON writers |
| `src/okf_grc/collect.py` (new) | `grc collect` command; the `collect` step of `grc run`; ledger entries |
| `src/okf_grc/sample.py` (new) | `grc sample` |
| `src/okf_grc/window_report.py` (new) | `grc window` |
| `src/okf_grc/cli.py`, `map_findings.py`, `manifest.py`, `run_scan.py`, `data/__init__.py`, `data/schemas/findings.schema.json` (modify) | Wiring, contract 1.2 |
| `src/okf_grc/data/base/scanners/github.md` (new) | `rule_ids: ["github:scm-*", "github:change-*"]`, tag `cc8.1` |
| `tests/fixtures/github/` (new) | Recorded and synthetic API responses |

---

### Task 1: Window bounds and config

**Files:**
- Create: `src/okf_grc/window.py`, `tests/test_window.py`
- Modify: `src/okf_grc/config.py` (`_SHAPE`, `Config`, `_fields`), `tests/test_config.py`

**Interfaces:**
- Produces:
  - `utc_bounds(start: date, end: date) -> tuple[datetime, datetime]`
  - `parse_ts(value: str) -> datetime` (aware UTC; accepts `Z` and `+00:00`; raises `ValueError` on a naive value)
  - `in_window(ts: datetime, bounds: tuple[datetime, datetime]) -> bool`
  - `near_boundary(ts: datetime, bounds: tuple[datetime, datetime], hours: int = 8) -> bool`
  - `RepoSpec(name: str, tier: str, collect: tuple[str, ...])` (frozen dataclass in `config.py`)
  - New `Config` fields:
    - `window_start: date | None = None`
    - `window_end: date | None = None`
    - `window_max_gap_days: int = 7`
    - `ledger: str = "evidence/ledger.jsonl"`
    - `people: str = "real"`
    - `people_salt_env: str = "GRC_PEOPLE_SALT"`
    - `github_repos: tuple[RepoSpec, ...] = ()`
    - `github_branches: tuple[str, ...] = ()`
    - `github_scanner_jobs: tuple[str, ...] = ()`
  - `Config.bounds() -> tuple[datetime, datetime]` (raises `ConfigError("no window in grc.yaml")` when unset)
  - Constants: `TIERS = ("in-scope", "library", "deferred", "dormant")`, `COLLECTORS = ("scm", "changes")`

- [ ] **Step 1: Write the failing tests**

```python
def test_bounds_include_last_day():
    lo, hi = utc_bounds(date(2026, 6, 1), date(2026, 8, 31))
    assert lo == datetime(2026, 6, 1, tzinfo=UTC) and hi == datetime(2026, 9, 1, tzinfo=UTC)
    assert in_window(parse_ts("2026-08-31T23:59:59Z"), (lo, hi))
    assert not in_window(parse_ts("2026-09-01T00:00:00Z"), (lo, hi))

def test_near_boundary_eight_hours():
    b = utc_bounds(date(2026, 6, 1), date(2026, 8, 31))
    assert near_boundary(parse_ts("2026-08-31T16:00:00Z"), b)
    assert not near_boundary(parse_ts("2026-08-31T15:59:59Z"), b)

def test_parse_ts_rejects_naive():
    with pytest.raises(ValueError):
        parse_ts("2026-08-31T10:00:00")

def test_github_repos_from_yaml(tmp_path):  # in tests/test_config.py
    repo = _repo(tmp_path, "window: {start: 2026-06-01, end: 2026-08-31}\n"
                 "github:\n  repos:\n    - {name: acme/api, tier: in-scope, collect: [scm, changes]}\n")
    c = load_config(repo)
    assert c.github_repos == (RepoSpec("acme/api", "in-scope", ("scm", "changes")),)
    assert c.window_end == date(2026, 8, 31)
```

Add rejection tests, each asserting `ConfigError` with the key in the message:
- `end` before `start`
- an unknown tier
- an unknown collector
- a duplicate repo name
- a name that is not `owner/name`
- `people: anonymous`
- a `repos_file` outside the repo root

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_window.py tests/test_config.py -q`
Expected: FAIL (`ModuleNotFoundError: okf_grc.window`, unknown key `window`).

- [ ] **Step 3: Implement**

- `window.py` uses only `datetime`.
- In `config.py`, `window`, `github`, `people`, `ledger` and `window_max_gap_days` are parsed in a new `_extended(raw) -> dict` before `_fields`. Remove those keys from `raw` so that `_SHAPE` keeps leaf-only validation.
- `github.repos_file` is a YAML list with the same item shape as `github.repos`. It is read relative to the repo root, and its items join `github.repos`.
- YAML dates arrive as `date`. A string date is parsed with `date.fromisoformat`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/okf_grc/window.py src/okf_grc/config.py tests/test_window.py tests/test_config.py
git commit -m "Add the audit window and the GitHub repo list to grc.yaml"
```

### Task 2: Ledger with hash chain

**Files:**
- Create: `src/okf_grc/ledger.py`, `tests/test_ledger.py`
- Modify: `src/okf_grc/cli.py` (command `ledger`)

**Interfaces:**
- Produces:
  - `LEDGER_SCHEMA = "1.0"`
  - `canonical(obj: dict) -> bytes`: `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()`
  - `append(path: Path, entry: dict) -> dict`: adds `schema_version`, `prev_id` and `entry_id`. Creates parent directories. Returns the stored entry.
  - `read(path: Path) -> list[dict]`: `[]` when the file does not exist
  - `verify(path: Path) -> int | None`: the 1-based number of the first bad line, or `None`
  - `make_entry(collector: str, repo: str | None, window: dict | None, inputs: dict, outputs: dict[str, str], summary: dict, rate_limit: dict | None, now: str, engine_version: str, supersedes: str | None = None) -> dict`
  - CLI: `grc ledger verify [--ledger PATH]`. Exits 1 with "ledger line N: hash mismatch" or "ledger line N: broken chain".

- [ ] **Step 1: Write the failing tests**

```python
def test_chain(tmp_path):
    p = tmp_path / "l.jsonl"
    a = append(p, _entry("scm")); b = append(p, _entry("changes"))
    assert a["prev_id"] is None and b["prev_id"] == a["entry_id"]
    assert verify(p) is None

def test_edit_fails(tmp_path):
    p = tmp_path / "l.jsonl"; append(p, _entry("scm")); append(p, _entry("changes"))
    lines = p.read_text().splitlines(); lines[0] = lines[0].replace('"scm"', '"run"')
    p.write_text("\n".join(lines) + "\n")
    assert verify(p) == 1

def test_deleted_line_breaks_chain(tmp_path): ...  # remove line 1 of 3 -> verify == 1 (prev_id not None on first line)
def test_entry_id_excludes_itself(tmp_path): ...    # sha256(canonical(entry minus entry_id)) == entry_id
def test_cli_verify_exit_code(tmp_path, monkeypatch): ...  # SystemExit with "line 2"
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest tests/test_ledger.py -q`
Expected: FAIL (no module).

- [ ] **Step 3: Implement `ledger.py` and the `ledger` CLI subcommand**

`append` reads only the last line to get `prev_id`. It writes one line with `\n` and opens the file in append mode.

- [ ] **Step 4: Run tests**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git commit -am "Add the evidence ledger: append-only JSON Lines with a hash chain"
```

### Task 3: GitHub transport

**Files:**
- Create: `src/okf_grc/github_api.py`, `src/okf_grc/github_queries.py`, `tests/test_github_api.py`, `tests/fixtures/github/transport/`

**Interfaces:**
- Produces:
  - `class GitHubError(GrcError, RuntimeError)`
  - `class Transport(Protocol)`:
    - `graphql(self, query: str, variables: dict) -> dict` returns `data`. It raises `GitHubError` on HTTP errors and on a non-empty `errors` list.
    - `rest(self, path: str) -> dict | list | None` returns `None` on 403 or 404 (not readable). It raises `GitHubError` on other errors.
  - `HttpTransport(token: str, api: str = "https://api.github.com")`
  - `token_from_env() -> str` raises `GitHubError("set GITHUB_TOKEN or GH_TOKEN")`
  - `RecordedTransport(root: Path)`:
    - GraphQL key: `sha256(canonical({"q": query, "v": variables}))[:16] + ".json"`
    - REST key: `"rest" + path.replace("/", "__") + ".json"`
    - A file holding `{"status": 404}` means `None`.
    - A missing file raises `GitHubError` naming the key and the query's first line.
  - `RecordingTransport(inner: Transport, root: Path, namer: "Namer")` writes the response after the namer replaces every `login` value (used in Task 12)
  - `rate_limit(data: dict) -> dict | None` returns `{"cost": int, "remaining": int}` from a `rateLimit` field
  - Queries:
    - `MERGED_PRS`, with variables `owner`, `name`, `cursor`, and `rateLimit { cost remaining }`
    - `WORKFLOWS`, with variables `owner`, `name`, `expr` (`HEAD:.github/workflows`)
    - `DEFAULT_BRANCH`

- [ ] **Step 1: Write the failing tests**

```python
def test_recorded_graphql_roundtrip(tmp_path): ...  # write fixture under computed key; graphql() returns its data
def test_missing_fixture_names_key(tmp_path): ...   # GitHubError message contains the key
def test_rest_404_is_none(tmp_path): ...
def test_graphql_errors_raise(tmp_path): ...        # fixture {"errors":[{"message":"x"}]} -> GitHubError
def test_token_never_in_error(monkeypatch):
    t = HttpTransport("ghp_SECRET123")
    monkeypatch.setattr(urllib.request, "urlopen", _raise_http(401))
    with pytest.raises(GitHubError) as e:
        t.graphql("query{viewer{login}}", {})
    assert "ghp_SECRET123" not in str(e.value)
def test_only_reads(): ...  # assert "mutation" not in any constant of github_queries
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest tests/test_github_api.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

- `HttpTransport` sets `Authorization: Bearer <token>`, `User-Agent: grc-evidence` and a 30-second timeout.
- On an HTTP error it raises `GitHubError(f"GitHub API {status} on {path or 'graphql'}")`.
- A 403 with `retry-after` gets the message `"secondary rate limit; retry after N s"`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git commit -am "Add a read-only GitHub transport with recorded responses for tests"
```

### Task 4: Spike — which branch-rule endpoint a read-only token can read (owner runs it)

**Files:**
- Modify: `docs/limits.md` (new section "Repository settings")
- Create: `tests/fixtures/github/spike/README.md` (the commands and the result, no tokens)

This task decides how Task 6 reads rules. It has no code.

- [ ] **Step 1: Make a fine-grained token** with read-only access to the owner's public repos ("Contents: read", "Metadata: read", "Administration: read" if the owner's repos are included).
- [ ] **Step 2: Run the commands** against one owned repo and against `GoogleCloudPlatform/microservices-demo`:

```bash
gh api repos/OWNER/REPO/rules/branches/main
gh api repos/OWNER/REPO/branches/main/protection
gh api graphql -f query='query{repository(owner:"OWNER",name:"REPO"){branchProtectionRules(first:5){nodes{pattern requiredApprovingReviewCount}}}}'
```

Record the HTTP status and whether the response has the review count, the checks and the bypass list. Also run the same three with the Actions `GITHUB_TOKEN` in a throwaway workflow on the demo repo.

- [ ] **Step 3: Write the decision** in `docs/limits.md`: the endpoint order Task 6 uses. Expected outcome to confirm:
  - `rules/branches/{branch}` (rulesets) is readable with read access.
  - Classic protection needs admin rights.
  - On a non-owned repo, classic protection is therefore unreadable, which gives `scm-rules-unreadable`.
- [ ] **Step 4: Commit**

```bash
git commit -am "Record which branch-rule endpoints a read-only token can read"
```

### Task 5: People namer

**Files:**
- Create: `src/okf_grc/people.py`, `tests/test_people.py`

**Interfaces:**
- Produces:
  - `class Namer`: `__init__(self, mode: str, salt: bytes | None)`; `name(self, login: str | None) -> str`
  - A `None` login gives `"ghost"` in both modes.
  - `namer_from_config(config: Config, environ: Mapping[str, str] = os.environ) -> Namer` raises `ConfigError("people: pseudonymous needs GRC_PEOPLE_SALT")`, naming the variable from config.
  - `pseudonym(login: str, salt: bytes) -> str`

- [ ] **Step 1: Write the failing tests**

```python
def test_pseudonym_shape():
    p = pseudonym("octocat", b"s")
    assert re.fullmatch(r"p-[0-9a-f]{10}", p) and p == pseudonym("octocat", b"s")
    assert p != pseudonym("octocat", b"t")
def test_real_mode_identity(): assert Namer("real", None).name("octocat") == "octocat"
def test_ghost(): assert Namer("pseudonymous", b"s").name(None) == "ghost"
def test_missing_salt_raises(): ...
def test_salt_not_in_repr(): assert "s3cret" not in repr(Namer("pseudonymous", b"s3cret"))
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest tests/test_people.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement** with `hmac.new(salt, login.encode(), "sha256").hexdigest()[:10]`.
- [ ] **Step 4: Run tests**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git commit -am "Add real or pseudonymous names for people in outputs"
```

### Task 6: SCM posture collector

**Files:**
- Create: `src/okf_grc/collect_scm.py`, `tests/test_collect_scm.py`, `tests/fixtures/github/scm/` (synthetic repos `acme/api`, `acme/lib`, `acme/locked`)
- Create: `src/okf_grc/data/base/scanners/github.md` (type `Scanner`, `rule_ids: ["github:scm-*", "github:change-*"]`, tags `[cc8.1]`, a `generated` block, no `verified`; the owner verifies it before release)

**Interfaces:**
- Consumes: `Transport`, `RepoSpec`, `Config.github_scanner_jobs`
- Produces:
  - `@dataclass(frozen=True) class Posture`:
    - `repo: str`, `branch: str`, `readable: bool`
    - `required_reviews: int | None`, `dismiss_stale: bool | None`
    - `required_checks: tuple[str, ...]`, `admin_bypass: bool | None`
    - `scanner_jobs: dict[str, dict[str, bool]]` (`{"present": bool, "can_fail": bool}`)
    - `workflow_errors: tuple[str, ...]`
  - `read_posture(t: Transport, repo: RepoSpec, scanner_jobs: tuple[str, ...]) -> Posture`
  - `scanner_job_status(workflows: dict[str, str], patterns: tuple[str, ...]) -> tuple[dict[str, dict[str, bool]], tuple[str, ...]]`
    - A pattern matches when it is a case-insensitive substring of the job id or the job `name`.
    - A workflow file that does not parse goes into the errors tuple, and its jobs count as not present.
  - `posture_findings(p: Posture) -> list[Finding]` returns findings built with `run_scan._finding("github", rule_id, severity, f"github:{p.repo}", message)`, with the severities `scm-rules-unreadable` = `unknown`, `scm-no-required-review` = `high`, and the others `medium`.
  - `posture_summary(p: Posture) -> dict`

- [ ] **Step 1: Write the failing tests** (one per rule id of spec §4.2, plus):

```python
def test_unreadable_is_not_a_pass(transport):
    p = read_posture(transport, RepoSpec("acme/locked", "in-scope", ("scm",)), ("semgrep",))
    assert not p.readable and p.required_reviews is None
    assert [f["rule_id"] for f in posture_findings(p)] == ["scm-rules-unreadable"]
def test_job_level_and_step_level_continue_on_error(): ...
def test_malformed_workflow_counts_as_missing(): ...
def test_pattern_matches_job_name_case_insensitive(): ...
def test_base_bundle_maps_github_rules(): ...  # load_bundle(base).by_rule("github","scm-no-required-review") non-empty, keys include soc2:cc8.1
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest tests/test_collect_scm.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

- Read the rules in the order that Task 4 recorded.
- Map ruleset rule types: `pull_request.parameters.required_approving_review_count`, `required_status_checks.parameters.required_status_checks[].context`.
- Bypass: any `bypass_actors` entry with `bypass_mode: always`.
- Run `make sync-base` so `knowledge/` gets `scanners/github.md`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest -q`
Expected: PASS (including `test_base_bundle.py` and `test_bundle_conformance.py`).

- [ ] **Step 5: Commit**

```bash
git commit -am "Add the SCM posture collector and its rules in the base bundle"
```

### Task 7: Change population collector

**Files:**
- Create: `src/okf_grc/collect_changes.py`, `tests/test_collect_changes.py`, `tests/fixtures/github/changes/` (synthetic `acme/api`, 3 pages)

**Interfaces:**
- Consumes: `Transport`, `MERGED_PRS`, `window.*`, `Namer`, `ledger.read`
- Produces:
  - `@dataclass(frozen=True) class Change`:
    - `repo: str`, `number: int`, `title: str`
    - `author: str | None`, `merged_by: str | None`, `merged_at: datetime`, `merge_sha: str`, `base: str`
    - `approvers: tuple[str, ...]`, `flags: tuple[str, ...]`
    - `checks: tuple[tuple[str, str], ...]` (name, conclusion)
  - `fetch_merged(t: Transport, repo: str, bounds: tuple[datetime, datetime]) -> Iterator[dict]`:
    - pages by `updatedAt` descending and stops after a page whose last `updatedAt` < `bounds[0]`
    - raises `GitHubError("pagination did not advance")` when the cursor repeats
  - `approvers(reviews: list[dict], author: str | None, merged_at: datetime) -> tuple[str, ...]`
  - `rule_since(entries: list[dict], repo: str) -> datetime | None`: the `recorded_at` of the first `scm` entry for `repo` whose summary has `required_reviews >= 1`
  - `to_change(pr: dict, repo: str, bounds, since: datetime | None) -> Change` (flags: `no_approval`, `self_merge_without_review`, `merged_before_rule`, `near_boundary`)
  - `collect_changes(t, repo: RepoSpec, bounds, branches: tuple[str, ...], default_branch: str, entries: list[dict]) -> tuple[list[Change], dict]`: the second value is the summary (`in_population`, `merged_all_branches`, `flags`)
  - `change_findings(changes: list[Change]) -> list[Finding]`:
    - `change-no-approval` and `change-self-merge-without-review`, severity `high`
    - target `github:<repo>#<n>`
  - `write_population(out: Path, changes: list[Change], summary: dict, namer: Namer) -> dict[str, str]`:
    - writes `collect/population.csv` and `collect/changes.json`
    - returns path → sha256
    - the CSV header must equal spec §5.3 exactly

- [ ] **Step 1: Write the failing tests**

```python
B = utc_bounds(date(2026, 6, 1), date(2026, 8, 31))
def test_last_second_in_first_second_out(): ...
def test_self_merge_without_review(): ...   # author == merged_by, no approvers -> both flags + 2 findings
def test_dismissed_after_approval_not_approver(): ...  # APPROVED then DISMISSED by same reviewer -> ()
def test_review_after_merge_ignored(): ...
def test_author_review_ignored(): ...
def test_rule_became_active_mid_window(): ...  # entries: scm required_reviews 0 on 06-10, 1 on 07-01 -> PR merged 06-20 flagged
def test_empty_population_keeps_denominator(): ...  # no PR on base, 4 on other branches -> in_population 0, merged_all_branches 4
def test_pagination_stops_before_window(): ...  # 3 pages, page 3 never requested (RecordedTransport has no page-3 fixture)
def test_pagination_same_cursor_raises(): ...   # Review Focus 3
def test_ghost_author(): ...                    # author null -> "ghost" in CSV
def test_csv_header_and_utc_z(): ...
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest tests/test_collect_changes.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement.** Approvers: group reviews by author, drop the PR author and reviews with `submittedAt >= mergedAt`, take the latest state per reviewer, and keep `APPROVED`. Sort the result.
- [ ] **Step 4: Run tests**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git commit -am "Add the change population collector with approval rules and a denominator"
```

### Task 8: `grc collect`, the run step, mapping and the contract

**Files:**
- Create: `src/okf_grc/collect.py`, `tests/test_collect.py`
- Modify:
  - `src/okf_grc/cli.py`: add `collect` to `COMMANDS`; add `"collect"` to `RUN_STEPS` after `"scan"` (Task 2 adds `ledger`, Task 9 `sample`, Task 10 `window`)
  - `src/okf_grc/map_findings.py` (`main`): also read `out/collect/github-findings.json` when it exists
  - `src/okf_grc/run_scan.py` (`tools_not_run`): add `"github"` when no repo lists a collector
  - `src/okf_grc/manifest.py`: `OPTIONAL_OUTPUTS = ("collect/github-findings.json", "collect/scm-posture.json", "collect/population.csv", "collect/changes.json")`, hashed when present
  - `src/okf_grc/data/__init__.py`: `SCHEMA_VERSION = "1.2"`
  - `src/okf_grc/data/schemas/findings.schema.json`: add `"github"` to the `tool` enum; the target description allows `github:<owner>/<name>[#n]`

**Interfaces:**
- Consumes: Tasks 1–7
- Produces:
  - `collect_main(argv: list[str], transport: Transport | None = None) -> None` (`grc collect {scm,changes,all} [--config] [--out] [--record DIR]`)
  - `run_collect(config: Config, out: Path, transport: Transport, now: str) -> list[dict]`:
    - writes the outputs into `out/collect/`
    - returns ledger entries for the caller to append only after every repo succeeded
    - each entry's `inputs` = `{"query_sha256": sha256 of the GraphQL query text, "branch": default branch}`; `rate_limit` from `github_api.rate_limit`
  - `grc run` appends its `collect` entries plus one `run` entry. The `run` entry's summary is `{control_key: status}` from `mapping.json`. It is appended after `os.replace` of the outputs.

- [ ] **Step 1: Write the failing tests**

```python
def test_github_rules_not_run_without_config(tmp_path): ...  # Review Focus 1
def test_collect_failure_writes_nothing(tmp_path): ...      # Review Focus 2: repo 2 of 2 raises -> no out/collect files, ledger unchanged
def test_run_maps_github_findings_to_cc81(tmp_path): ...    # mapping.json soc2:cc8.1 not-satisfied with a github finding
def test_run_appends_run_entry_last(tmp_path): ...
def test_manifest_hashes_optional_outputs(tmp_path): ...
def test_schema_accepts_github_target(): ...
```

Use `RecordedTransport` through an injectable seam:

- `cli.run` reads `GRC_GITHUB_FIXTURES`. When it is set, it uses `RecordedTransport`.
- That variable exists only for tests and the offline examples. Document it in `docs/limits.md`.

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest tests/test_collect.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement.** The collect step writes into the run's staging directory, so a failed run leaves `out/` and the ledger as they were.
- [ ] **Step 4: Run tests**

Run: `uv run pytest -q`
Expected: PASS. Existing golden tests (`report.golden.md`, OSCAL) still pass with no `github` config.

- [ ] **Step 5: Commit**

```bash
git commit -am "Add grc collect and run the collectors inside grc run; contract 1.2"
```

### Task 9: `grc sample`

**Files:**
- Create: `src/okf_grc/sample.py`, `tests/test_sample.py`
- Modify: `src/okf_grc/cli.py`

**Interfaces:**
- Consumes: `out/collect/changes.json` (Task 7), `Config.github_scanner_jobs`
- Produces:
  - `sample_evidence(changes_doc: dict, rows: list[tuple[str, int]], scanner_jobs: tuple[str, ...]) -> list[dict]`. Each output row has the columns of spec §6:
    - `ci_conclusion` is `success` only when every check concluded `SUCCESS`, `NEUTRAL` or `SKIPPED`. Otherwise it is `failure`, or `none` when there are no checks.
    - `scanner_checks` is `name=conclusion` joined with `;`, for checks that match a scanner pattern.
    - `missing` lists `not-in-population`, `no-checks` and `no-scanner-check`.
  - `sample_main(argv: list[str]) -> None` (`grc sample --list FILE [--out]`) writes `out/collect/sample-evidence.csv`

- [ ] **Step 1: Write the failing tests**

```python
def test_not_in_population_is_missing(): ...
def test_no_checks_is_none_not_success(): ...
def test_skipped_counts_as_success(): ...
def test_bad_sample_header_raises(): ...  # GrcError naming the expected header "repo,number"
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest tests/test_sample.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**
- [ ] **Step 4: Run tests**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git commit -am "Add grc sample: per-change evidence for an auditor's sample"
```

### Task 10: `grc window`

**Files:**
- Create: `src/okf_grc/window_report.py`, `tests/test_window_report.py`
- Modify: `src/okf_grc/cli.py`

**Interfaces:**
- Consumes: `ledger.read`, `Config.bounds()`, `Config.window_max_gap_days`
- Produces:
  - `window_status(entries: list[dict], bounds, max_gap_days: int) -> dict[str, dict]`:
    - one value per control key: `{"first_satisfied": str | None, "last_evidence": str | None, "gaps": list[[str, str]]}`
    - dates are `YYYY-MM-DD` (UTC)
    - uses only `run` entries inside the bounds and the last entry of each day
  - `render_window(status: dict, bounds) -> str` (markdown table)
  - `window_main(argv: list[str]) -> None` writes `out/window.json` and `out/window.md`

- [ ] **Step 1: Write the failing tests**

```python
def test_seeded_gap(): ...                  # satisfied 06-01..06-10, not-satisfied 06-11, satisfied 06-12.. -> gaps [["2026-06-11","2026-06-11"]]
def test_silence_longer_than_max_is_gap(): ...  # entries 06-01 and 06-20, max 7 -> gap ["2026-06-02","2026-06-19"]
def test_no_entries_whole_window_gap(): ...
def test_same_day_entries_last_wins(): ...  # Review Focus 4
def test_entries_outside_window_ignored(): ...
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest tests/test_window_report.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement.** A gap is a maximal run of days in the window that is either:
  - a day whose last entry has a status other than `no-violations-detected`, or
  - a day further than `max_gap_days` from the last entry before it, with no entry of its own.

  Days after the last entry, up to the end of the window, are not a gap if that end is in the future (`today < end`).
- [ ] **Step 4: Run tests**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git commit -am "Add grc window: control history over the audit window from the ledger"
```

### Task 11: Package rename to grc-evidence

**Files:**
- Move: `src/okf_grc/` → `src/grc_evidence/` (`git mv`)
- Create: `src/okf_grc/__init__.py` (shim), `tests/test_shim.py`
- Modify:
  - `pyproject.toml`: `name = "grc-evidence"`, `version = "2.0.0"`, `grc = "grc_evidence.cli:main"`, ruff/mypy paths
  - `Makefile`: `include` path, `LOCKS`, `$(PY_LLM) grc_evidence.eval_triage`
  - `.github/workflows/ci.yml` and `release.yml`: `hashFiles` paths
  - every `from okf_grc` and `import okf_grc` in `src/` and `tests/`
  - `cli.py`: `version("grc-evidence")` and the install hint
  - `to_oscal.py`: `PROP_NS = "https://github.com/cdevarenne/grc-evidence/ns/oscal"` and the three `_metadata` titles (`"grc-evidence …"`)
  - `src/grc_evidence/data/skill/*`: the install command text

**Interfaces:**
- Produces:
  - Importing `okf_grc` emits a `DeprecationWarning`.
  - `import okf_grc.config` returns the same module object as `grc_evidence.config` (shim: a `sys.meta_path` finder that aliases `okf_grc.*` to `grc_evidence.*`).

- [ ] **Step 1: Write the failing tests**

```python
def test_old_import_warns_and_aliases():
    with pytest.warns(DeprecationWarning):
        import okf_grc.config as old
    import grc_evidence.config as new
    assert old is new
def test_version_reads_new_name(): assert version("grc-evidence") == "2.0.0"
def test_prop_ns(): assert "grc-evidence" in to_oscal.PROP_NS
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest tests/test_shim.py -q`
Expected: FAIL.

- [ ] **Step 3: Move and edit.** Check how `uv_build` ships two top-level modules: `[tool.uv.build-backend] module-name = ["grc_evidence", "okf_grc"]`. If the pinned `uv_build` does not accept a list, ship the shim as a second package under `src/` with the backend's documented namespace option. Record the choice in the commit message.
- [ ] **Step 4: Verify**

```bash
uv sync && uv run pytest -q && uv run ruff check && uv run mypy
uv build && unzip -l dist/grc_evidence-2.0.0-*.whl | grep -E "grc_evidence/__init__|okf_grc/__init__"
grep -rIn "okf_grc\|okf-grc" src tests pyproject.toml Makefile .github | grep -v "src/okf_grc/__init__.py\|test_shim.py"
```

Expected: tests pass, and both `__init__` files are in the wheel. The last grep prints nothing.

- [ ] **Step 5: Commit**

```bash
git commit -am "Rename the package to grc-evidence and the module to grc_evidence

okf_grc stays as a deprecated alias for one minor release.
The OSCAL property namespace changes to the grc-evidence URI."
```

### Task 12: Demo data, examples, docs and the v2.0.0 release

**Files:**
- Create:
  - `tests/fixtures/github/demo/` (recorded, pseudonymized)
  - `tests/test_fixtures_pseudonymized.py`
  - `examples/collect/population.csv`, `examples/collect/sample-evidence.csv`, `examples/window.md`
- Modify:
  - `Makefile` (target `examples-h`)
  - `docs/limits.md`, `docs/roadmap.md`, `docs/outputs.md`, `docs/using-the-skill.md`
  - `README.md` (new commands; the section "Type 2 evidence over a window")
  - the demo repo (`grc-evidence-boutique`): `grc.yaml`, `Makefile`, `.github/workflows/evidence.yml`

**Interfaces:**
- Consumes: everything above

- [ ] **Step 1: Write the failing test** (Review Focus 5)

```python
def test_fixtures_pseudonymized():
    for f in Path("tests/fixtures/github").rglob("*.json"):
        for login in _logins(json.loads(f.read_text())):
            assert login == "ghost" or re.fullmatch(r"p-[0-9a-f]{10}", login), f
```

- [ ] **Step 2: Run it.** It fails only if a synthetic fixture uses a plain login. In that case, convert the synthetic fixtures to `p-` names.
- [ ] **Step 3: Record the demo fixtures.** This uses the owner's token and salt, and must not run in CI.

```bash
GRC_PEOPLE_SALT=… uv run grc collect changes --config tests/fixtures/github/demo/grc.yaml \
  --out /tmp/demo-out --record tests/fixtures/github/demo
```

The demo config:

```yaml
window: {start: 2026-06-01, end: 2026-08-31}
people: pseudonymous
github:
  repos:
    - {name: GoogleCloudPlatform/microservices-demo, tier: in-scope, collect: [changes]}
```

- [ ] **Step 4: Regenerate the examples offline** with `make examples-h` (`GRC_GITHUB_FIXTURES=tests/fixtures/github/demo`). Run it twice. The second run must produce identical files (`git diff --exit-code examples/`).
- [ ] **Step 5: Update the demo repo** (separate commit, in `grc-evidence-boutique`):
  - `grc.yaml`: the upstream repo with `collect: [changes]`; the owner's repos with `collect: [scm]`; `people: pseudonymous`
  - `evidence.yml`: nightly. One job has `permissions: contents: write`, checks out the `ledger` branch into `evidence/`, runs `grc collect all`, `grc ledger verify` and `grc window`, and pushes only `evidence/ledger.jsonl`. `GRC_PEOPLE_SALT` is a repo secret.
  - Run `uv run zizmor .github` with no high findings.
  - Pin `OKF_GRC_VERSION` (rename it to `GRC_VERSION`) to `v2.0.0` and the package to `grc-evidence[...]`, then `make baseline` in the same commit.
- [ ] **Step 6: Docs.**
  - `docs/limits.md`: GitHub only; read-only; unreadable rules; no back-fill; the pseudonymization scope; the fixtures variable.
  - `docs/roadmap.md`: Spec H Part A built; Part B and Spec I next.
- [ ] **Step 7: Verify everything**

```bash
uv run pytest -q && uv run ruff check && uv run mypy && make audit
grep -rIniF -f ~/.config/grc/clean-room-denylist.txt . --exclude-dir=.git --exclude-dir=.venv   # owner-kept list of names that must not appear; must print nothing
```

- [ ] **Step 8: Release.** Bump the version in the release notes, tag `v2.0.0`, push, and watch `release.yml`. In the demo, check that `make scan check gate` passes on `v2.0.0`.
- [ ] **Step 9: Commit**

```bash
git commit -am "Add the Type 2 demo data, examples and docs; release v2.0.0"
```
