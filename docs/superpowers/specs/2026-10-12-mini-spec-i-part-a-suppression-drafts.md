# Mini Spec I, Part A — suppression drafts, and one acceptance across several files

- **Date:** 2026-10-12
- **Status:** draft, for the owner's plan review. Plan: [plan](../plans/2026-10-12-mini-spec-i-part-a-plan.md).
- **Issue:** #143. **Release:** 2.2.0. **LLM cost:** none (§6, decision 3).
- **Depends on:** v2.1.0.

## 1. Why

The demo's nightly gate failed twice in one week on new upstream advisories, with no change to the repo: CVE-2026-104873 (2026-10-06, one file) and CVE-2026-78669 (2026-10-10, four `go.mod` files). Each time the fix was the same: read the gate's output, write a suppression concept by hand, have a person review it and add `verified`. The second advisory took four near-identical files (demo commit `6f48989`).

Owner decisions:

- **2026-10-06 (#143):** keep up with new findings and new advisories without accepting anything unsigned. The gate names each new finding with a ready command; `grc suppress draft` writes everything except the reason and the `verified` block; a person writes the reason and signs.
- **2026-10-12 (#143 comment):** one reviewed acceptance may cover one advisory across several explicitly named files.

Spec I as a whole (roadmap) also covers signed risk acceptances, an OSCAL POA&M and an attestation for an empty population. Those are Part B and later, with their own plans.

## 2. Rules (unchanged from Spec C and 2.0.1)

1. **No wildcards.** A suppression names one tool and one rule id, and each target exactly.
2. **Nothing applies unsigned.** A suppression without a `human:` `verified` entry is pending: listed, never applied.
3. **Expiry at most 90 days after approval.** An expired suppression fails the gate.
4. **An accepted risk needs a control.** On a coverage gap it is rejected at load time.
5. **The tool drafts; a person decides.** `grc suppress draft` never writes `verified`, never writes a reason, and never edits an existing file.

## 3. One acceptance, several named files

```yaml
finding:
  tool: trivy
  rule_id: CVE-2026-78669
  targets:
    - upstream/src/checkoutservice/go.mod
    - upstream/src/frontend/go.mod
    - upstream/src/productcatalogservice/go.mod
    - upstream/src/shippingservice/go.mod
```

- `finding` has either `target` (a string, as today) or `targets` (a list of distinct strings, at least two). Not both. Each target follows today's no-wildcard rule.
- One `kind`, `owner`, `approved`, `expires`, `# Reason` and `verified` cover every listed target. `message_contains`, when set, applies to each target.
- Matching is unchanged per finding: `Suppression.matches` compares the finding's target against the set. `suppressed` keeps one entry per finding, so OSCAL (one `deviation-approved` risk per accepted finding), the report and the MCP `findings_by_suppression` count need no change.
- **Unused targets.** A suppression that matches no finding stays in `unused_suppressions`, as today. A multi-target suppression that matches some targets but not others lists each unmatched target in a new key, `unused_targets: [{id, target}]`. The report lists them under **Unused suppressions** ("`<id>`: `<target>` matches no finding; remove the target"). Neither fails the gate, as today.
- `mapping.json` gains `unused_targets` (additive): the output contract goes to **1.4**. The suppression concept schema gains `targets`.
- `Suppression.target: str` becomes `targets: tuple[str, ...]`. It is an internal dataclass; its callers are `okf_lib`, `map_findings` and the tests.

## 4. `grc suppress draft`

```
grc suppress draft --tool trivy --rule-id CVE-2026-78669 \
  --target upstream/src/frontend/go.mod --target upstream/src/shippingservice/go.mod \
  --kind accepted-risk --days 30 --owner human:cdevarenne
```

- **Reads** `out/mapping.json` (from the last `grc run`) and the bundle named by `grc.yaml`.
- **Checks, and refuses with a message:**
  - each target matches a finding in `mapping.json` with that tool and rule id (on a control or in the gap list);
  - `accepted-risk` only when the findings map to a control (the load-time rule, checked early);
  - no existing suppression, in any state, names the same tool, rule id and target ("edit or remove `<path>` first"; renewing stays a person's edit);
  - `--days` from 1 to 90; `--owner` starts with `human:`;
  - the file does not exist yet.
- **Writes** `<knowledge>/suppressions/<id>.md`. The id is `--id` when given, otherwise a slug of the tool, the rule id and, for one target, the target (`trivy-cve-2026-78669-upstream-src-frontend-go-mod`). The frontmatter: `type`, `title` (`<rule_id> in <target>` or `<rule_id> in <n> files`), `kind`, `finding`, `owner`, `approved` (today, UTC: the date `grc run` uses, so the draft is never "approved after this scan's date"), `expires`, `tags: [suppression]`, and `generated: {by: grc-evidence/<version>, at: <now>}`. No `verified`.
- **The body:** a `# Reason` section that holds the draft marker and the facts a reviewer needs, then, for `accepted-risk`, a `# Compensating control` section with the marker:

  ```markdown
  # Reason

  <!-- grc: draft. Write why this is accepted, then delete this line. -->

  From the scan of 2026-10-12 (scanner text, quoted as reported):

  - `upstream/src/frontend/go.mod`: high, "golang.org/x/net: HTTP/2 ..." (controls: soc2:cc7.1)
  ```

- **Prints** the path, and the next steps: write the reason, delete the marker lines, add `verified`, run `grc check` and `make scan gate`.

### 4.1 A signed draft that was not edited fails the load

A suppression with a `human:` `verified` entry whose body still contains `<!-- grc: draft` is a `BundleError` ("delete the draft marker after writing the reason"). An unverified draft loads and is pending, as any unverified suppression. This keeps a person from signing the facts list as the reason.

## 5. The gate names each new finding

When `grc gate` fails on new findings, it prints, after the failure list, one `grc suppress draft` command per tool and rule id, with a `--target` for each failing target:

```
grc gate: failed
  new high vulnerability: trivy:CVE-2026-78669 upstream/src/frontend/go.mod (0 -> 1)
  ...
To draft a suppression for review (a person writes the reason and signs it):
  grc suppress draft --tool trivy --rule-id CVE-2026-78669 --target upstream/src/checkoutservice/go.mod ... --kind accepted-risk --days 30 --owner human:<you>
```

- Only for the findings that failed the gate: not for `change-*` findings, not for vulnerabilities below `--fail-on`, not for a control regression without a new finding, not for an expired suppression.
- `--kind accepted-risk` when the findings map to a control, `--kind false-positive` when they are a coverage gap (the only kind allowed there). The person can change it before running the command; the draft records whatever kind it was given.
- Every value is shell-quoted (`shlex.quote`): targets and rule ids come from scanned files.
- `--summary` writes the same commands to the CI job summary, in a code block.

## 6. Decisions for the owner

1. **Separate flags, not `--finding tool:rule@target`.** #143 sketched `--finding trivy:CVE-…@<target>`. None of the demo's 445 scan findings has `:` or `@` in a rule id or target today, but neither field is constrained: a scoped npm path such as `node_modules/@scope/pkg` would hold `@`, and one string could then not be split reliably. Recommendation: `--tool`, `--rule-id`, `--target` (repeatable).
2. **Owner.** (a) `--owner` is required; the gate prints `--owner human:<you>`, so the command needs one edit. (b) An optional `suppress.owner` in `grc.yaml` fills it, so the printed command runs as is. Recommendation: (a): less code, and the person reads the command before running it.
3. **No LLM-drafted reason in Part A.** #143 allows one, bound to the finding. The facts list (§4) is deterministic and covers what a reviewer reads first. Recommendation: leave LLM drafting to Spec G G5 (suppression drafts), which can call `grc suppress draft` and only fill the reason.
4. **The draft marker is a load error once signed** (§4.1). Recommendation: yes.
5. **Default `--days`:** 30, as both demo acceptances. The gate prints `--days 30`.
6. **The demo's four `x/net` files.** After 2.2.0, merge them into one `targets` suppression? It needs a new `verified` entry. Recommendation: yes, as the first real use; the owner reviews and signs it.

## 7. Out of scope

- Renewing a suppression (`grc suppress renew`): an expired one is edited by a person, as today.
- An MCP `draft_suppression` tool (Spec G G5).
- Opening a pull request or issue for the draft.
- Signed acceptances, POA&M, attestation (Spec I Part B and later).

## 8. Done when

- A suppression with `targets` loads, applies per target, and reports unmatched targets in `unused_targets`; the schema and the loader reject `target` with `targets`, a one-item `targets`, duplicates and wildcards.
- `grc suppress draft` writes a file that `grc check` loads and the scan lists as pending; each refusal in §4 has a test.
- A verified suppression with the draft marker fails the load.
- On the CVE-2026-78669 case (a fixture with four `go.mod` findings), `grc gate` prints one command that, run as printed (owner filled in), writes one suppression covering the four files.
- `uv run pytest -q`, `ruff`, `mypy` and `make test-integration` pass; scan outputs for bundles without `targets` are unchanged apart from the contract version.
