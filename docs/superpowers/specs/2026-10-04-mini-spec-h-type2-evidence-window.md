# Mini Spec H — Type 2 evidence over a window, for N repos

- **Date:** 2026-10-04
- **Status:** approved by the owner for planning. Part A has a plan: [plan](../plans/2026-10-04-mini-spec-h-part-a-plan.md). Part B gets its own plan after Part A ships. Revised 2026-10-05 after the Gemini 3.8 Flash plan review (§3.2, §5.2, §5.4, §6, §10, §11).
- **Depends on:** v1.8.1.
- **Release:** Part A ships as `v2.0.0`, together with the package rename (§7).
- **LLM cost:** none. A population memo drafted by an LLM, with numbers bound to the population summary, belongs to the Spec G `package` workflow, not to this spec.

## 1. Why

A SOC 2 Type 2 audit asks whether controls operated over an observation window, often three to twelve months. A scan of one commit shows the state on one day. The auditor asks for other evidence:

- **The change population:** every change merged into a production branch in the window, with who wrote it, who approved it and who merged it. The auditor picks a sample from it.
- **Sample evidence:** for each sampled change, its approvals and the CI result on the merged commit.
- **Repository settings over time:** required reviews, required checks, and scanner jobs that can fail the build. The evidence must be dated. Today's setting does not prove last month's setting.
- **Proof that a zero is real:** "no unapproved changes" needs the count of all changes beside it.

Teams collect this by hand from the SCM API, again for each audit request. This spec makes the collection a `grc` command. The rules stay the same: code decides each status, count and date; an LLM only drafts prose; a person approves.

## 2. One grc instance, N target repos

An adopter runs **one grc instance** (one config repo, one ledger) for **all the repos in scope**. That can be one repo or several hundred.

- The target list is in `grc.yaml` (`github.repos`) or in a separate file (`github.repos_file`), with a tier per repo.
- The collectors (§4, §5) read only the GitHub API. They need no clone, so they scale to hundreds of repos. The cost is API rate limit, and the ledger records it per run. A rate limit stops the run at once, with the retry time in the error. There is no retry loop; the next scheduled run tries again.
- Every evidence record carries its `repo`.
- **Part B** (§9) adds scanning N repos with the code scanners (clone, scan, aggregate, shard in CI). Part A does not clone target repos.

## 3. Window and ledger

### 3.1 Window

```yaml
window:
  start: 2026-04-01   # inclusive
  end: 2026-06-30     # inclusive
```

Code converts the window to UTC bounds `[start 00:00:00Z, end+1 00:00:00Z)`. Every query and filter uses these two bounds, so the last day is never dropped. A change merged within 8 hours of either bound gets the flag `near_boundary`, because a reviewer in another time zone may date it differently.

### 3.2 Ledger

`evidence/ledger.jsonl` (path set by `ledger:` in `grc.yaml`). One JSON object per line. Lines are only appended. The ledger is written only when `grc.yaml` has a `window`: that is how a repo opts into Type 2 evidence, so `grc run` in other repos creates no ledger.

| Field | Meaning |
|---|---|
| `schema_version` | `"1.0"` |
| `entry_id` | sha256 of the canonical JSON of the entry without `entry_id` |
| `prev_id` | `entry_id` of the line before, or `null` for the first line (a hash chain) |
| `recorded_at` | UTC timestamp, seconds |
| `engine_version` | the grc version |
| `collector` | `run`, `scm` or `changes` |
| `repo` | `owner/name`, or `null` for a `run` entry |
| `window` | `{start, end}` or `null` |
| `inputs` | what the collector read (for example the GraphQL query sha256, the branch) |
| `outputs` | output path → sha256 |
| `summary` | the collector's result summary (§4.3, §5.3; for `run`: the status of each control) |
| `rate_limit` | `{cost, remaining}` from the API, or `null` |
| `supersedes` | an `entry_id` this entry corrects, or `null` |

Canonical JSON: keys sorted, separators `,` and `:`, UTF-8, no trailing newline.

`grc ledger verify` checks every `entry_id` and the `prev_id` chain. It reports the first bad line number and exits non-zero. A ledger that has been edited fails.

A later step (Spec E §3.2) imports this file into SQLite or Postgres with no loss of fields. `window` becomes the two columns `window_start` and `window_end`.

### 3.3 Snapshot is not history

A posture collection records the settings on the day it runs. The window report uses only ledger entries. It never back-fills earlier days from a current reading.

## 4. SCM posture collector (`grc collect scm`)

### 4.1 What it reads

For each repo with `scm` in its `collect` list:

- The default branch name.
- The active rules for that branch:
  - the number of required approving reviews
  - whether stale reviews are dismissed
  - the required status checks
  - whether anyone can bypass the rules (admins, ruleset bypass actors, classic review bypass allowances)
- The workflow files in `.github/workflows/` at the default branch head. For each job whose id or name matches an entry of `github.scanner_jobs`, read whether the job or any of its steps has `continue-on-error: true`.

The rules endpoint that a read-only token can call is decided by the Part A spike (plan Task 4). If the token cannot read the rules of a repo, the collector says so (`scm-rules-unreadable`). It never treats an unreadable setting as a pass.

### 4.2 Findings

The collector emits findings in the existing findings contract, with `tool: "github"` and `target: "github:<owner>/<name>"`. They map to controls only through `rule_ids` in the bundle, as scanner findings do.

| `rule_id` | When |
|---|---|
| `scm-no-required-review` | fewer than 1 required approving review on the default branch |
| `scm-no-required-checks` | no required status checks |
| `scm-bypass` | someone can bypass the rules: admins when they are not enforced, a ruleset bypass actor in any mode, or a classic review bypass allowance |
| `scm-scanner-job-missing` | a `github.scanner_jobs` entry matches no job |
| `scm-scanner-job-can-fail` | a matching job or step has `continue-on-error: true` |
| `scm-rules-unreadable` | the token cannot read the branch rules |

A new base-bundle concept, `scanners/github.md`, declares `rule_ids: ["github:scm-*", "github:change-*"]` and the tag `cc8.1`.

### 4.3 Outputs

`out/collect/scm-posture.json`: one object per repo with the fields of §4.1 and a `readable` flag. The ledger summary per repo holds `required_reviews`, `required_checks`, `bypass` and `readable`.

## 5. Change population (`grc collect changes`)

### 5.1 What it reads

For each repo with `changes` in its `collect` list, it uses one paged GraphQL query per repo. The query reads merged pull requests, newest update first, and stops when `updatedAt` is before the window start. It keeps the PRs whose `mergedAt` is inside the window bounds and whose base branch is the default branch or is listed in `github.branches`.

For each PR:

- repo, number, title, author, merged by, merged at, merge commit SHA, base branch
- the reviews: author (and whether it is a bot), state, submitted at, the commit reviewed, and whether the reviewer can push to the repo
- the final commit of the pull request (`headRefOid`)
- the checks on the merge commit: name and conclusion

### 5.2 Rules (code decides)

- **Approvers:** the latest review state per reviewer, among reviews submitted before `mergedAt`, where the reviewer is not the author. Only the states `APPROVED`, `CHANGES_REQUESTED` and `DISMISSED` count. A `COMMENTED` review does not withdraw an approval on GitHub, so it is ignored. A reviewer counts as an approver when that state is `APPROVED`, the reviewer can push to the repo (GitHub ignores approvals from people who cannot), and the approval was given on the final commit.
- **Bots:** a review by a bot is ignored, unless `github.accepted_bots` lists the bot with a reason (`{login, reason}`). A listed bot's approval counts without push access, and the change gets the flag `bot_approval`. The reason is in the resolved config in `run.json`. Accepting it is the team's decision; an auditor can reject it.
- `approval_not_on_final_commit` (a flag, not a finding): an approval was given on an earlier commit and does not count.
- `change-no-approval`: no approver.
- `change-self-merge-without-review`: the author merged it and there is no approver. Both logins must be present: a deleted author and an unknown merger are not a self-merge.
- `merged_before_rule` (a flag, not a finding): the last `scm` ledger entry for the repo on or before `mergedAt` shows fewer than 1 required review.
- `rule_not_evidenced` (a flag, not a finding): no readable `scm` ledger entry for the repo exists on or before `mergedAt`. The rule may have been on or off; the ledger has no evidence. It is never read as "rule on".
- `near_boundary` (a flag, not a finding): `mergedAt` is within 8 hours of either window bound.
- `reviews_incomplete` and `checks_incomplete` (flags, not findings): GitHub returned only the first 100 reviews or checks of the change. With `reviews_incomplete` the change counts as having no approver, because a later dismissal may be cut off: it fails closed.

Each `change-*` result is also a finding with `target: "github:<owner>/<name>#<number>"`, so suppressions and risk acceptances can name one change.

### 5.3 Outputs

- `out/collect/population.csv` — one row per change: `repo,number,title,author,merged_by,merged_at,merge_sha,base,approvers,flags`. Lists are joined with `;`. Times are UTC ISO 8601 with `Z`. A text cell that starts with `=`, `+`, `-` or `@` gets a leading `'`, so a spreadsheet does not run a pull request title as a formula.
- `out/collect/changes.json` — the same rows plus the checks, for `grc sample`.
- **Summary** (in the ledger and in `changes.json`): `in_population`, `merged_all_branches` (the denominator, always present), and a count per flag.

### 5.4 People

`people: real | pseudonymous` (default `real`). With `pseudonymous`, every login in every output becomes `p-` plus the first 10 hex characters of HMAC-SHA256(salt, login). The salt comes from the environment variable that `people_salt_env` names (default `GRC_PEOPLE_SALT`). It is never written to an output. The collector applies the names when it reads the data, so no real login reaches a finding message, `mapping.json`, the report, OSCAL or the ledger. Titles are left empty, because a title can hold a login ("Merge … from alice/branch", "@alice"). If the salt is not set, the run stops with an error. An adopter's audit needs real names. A public demo that republishes other people's activity does not.

## 6. Sample and window report

- **`grc sample --list sample.csv`.** `sample.csv` has the columns `repo,number`. The command reads `out/collect/changes.json` and writes `out/collect/sample-evidence.csv` with these columns: `repo,number,merged_at,approvers,ci_conclusion,scanner_checks,missing`. A sampled change that is not in the population, or that has no checks, is listed in `missing`. It is never reported as passing.
- **`grc collect`** writes the collector outputs and appends its `scm` and `changes` entries to the ledger. It writes no `run` entry. Control status comes only from `grc run`, which runs the collectors as one of its steps. A scheduled evidence job therefore runs `grc run`, not `grc collect`.
- **`grc window`.** It reads the `run` entries of the ledger inside the window and writes `out/window.json` and `out/window.md`. For each control it gives:
  - `first_satisfied`: the first entry date with `no-violations-detected`
  - `last_evidence`: the last entry date
  - `gaps`: periods inside the window where the status was anything else (a control missing from a run counts), and periods longer than `window_max_gap_days` (default 7) with no entry. Such a period is a gap for its whole length. While the window is open, it is read up to today. A ledger that fails `grc ledger verify` gives no report.

## 7. Package rename (v2.0.0)

- Distribution `okf-grc` → `grc-evidence`; module `okf_grc` → `grc_evidence`; the CLI stays `grc`.
- `okf_grc` stays importable for one minor release. It gives a `DeprecationWarning` and forwards to `grc_evidence`.
- The OSCAL property namespace changes to `https://github.com/cdevarenne/grc-evidence/ns/oscal`. The release notes state the change.
- The output schema minor version goes to `1.2` (new optional outputs). The ledger has its own `schema_version` `1.0`.

## 8. Out of scope (Part A)

- GitLab and other SCMs (not planned)
- live cloud configuration
- ticket systems
- OSCAL observations for the population (later)
- risk acceptances and POA&M (Spec I)
- any write to GitHub
- scanning N repos (Part B)

## 9. Part B — scanning N repos (outline, own plan)

- **`grc fleet run`:** shallow-clone each in-scope repo at the head of its default branch into a cache. Run the scanners per repo into `out/repos/<owner>__<name>/`. Then write one aggregate mapping and report.
- **Incremental:** skip a repo when its head SHA, the engine version and the bundle hash equal the last `run` ledger entry for it.
- **Sharding:** `--shard i/n` selects a stable subset of repos, for a CI matrix. `grc fleet merge` joins the shard outputs.
- **Limits:** the clone size cap and the per-repo timeout come from config. A repo that fails is reported as not assessed, never as passing.

## 10. Demo

- The demo repo collects:
  - the change population of the public upstream `GoogleCloudPlatform/microservices-demo`, for a fixed past window of three full months, with `people: pseudonymous`
  - the posture of the owner's own repos (`collect: [scm]`)
- The upstream repo has no `scm` entries in the demo ledger, so each of its changes has the flag `rule_not_evidenced`.
- The owner's repos are maintained by one person and have no required reviews. The tool reports this as `scm-no-required-review`. Spec I turns it into a signed risk acceptance.
- The recorded API responses for the demo window are test fixtures. The committed outputs can be reproduced offline.
- **Two windows** (owner decision, 2026-10-06). `grc window` reads only `run` entries recorded during the window, so a past window can never show control history. The engine's examples keep the past window for the population and the sample (recorded fixtures). The demo repo's own `grc.yaml` uses the current quarter (2026-10-01 to 2026-12-31), so its nightly runs build a real history.

## 11. Done when (Part A)

1. `grc collect scm`, `grc collect changes`, `grc sample`, `grc window` and `grc ledger verify` work in the demo CI with a fine-grained read-only token (owner decision, 2026-10-06: the Actions `GITHUB_TOKEN` cannot read classic branch protection; see `docs/limits.md`).
2. Unit tests run offline from recorded responses. They cover:
   - a merge at `end 23:59:59Z` (in), and one at `end+1 00:00:00Z` (out)
   - a self-merge with no review
   - a review that was approved, then dismissed
   - a review that was approved, then commented on (still an approval)
   - a review submitted after the merge
   - a rule that became active inside the window
   - no `scm` entry before a merge (`rule_not_evidenced`)
   - a rate limit (the run stops, writes nothing and names the retry time)
   - an empty population (the denominator is still reported)
   - an unreadable rules endpoint
   - pagination across the window start
3. An edited ledger fails `grc ledger verify`.
4. `examples/` has a population CSV and a sample table, pseudonymized. The window report example comes from the demo's real ledger after its first weeks of nightly runs, in a v2.0.x docs commit (owner decision, 2026-10-06).
5. `v2.0.0` is released with the package rename, and the demo pins it.
6. `docs/limits.md` states what is not covered.
