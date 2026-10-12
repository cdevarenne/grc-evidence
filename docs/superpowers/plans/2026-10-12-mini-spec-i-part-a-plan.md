# Mini Spec I Part A Implementation Plan — suppression drafts, one acceptance across several files

**Goal:** a suppression can name one advisory in several listed files; `grc suppress draft` writes a pending suppression from the last scan; the gate prints the draft command for each new finding it fails on. Release 2.2.0.

**Spec:** `docs/superpowers/specs/2026-10-12-mini-spec-i-part-a-suppression-drafts.md`. **Issue:** #143. **Review:** revised on 2026-10-12 after the Gemini 3.8 Flash plan review (`reviews/grc-evidence/claude-assessment-of-adversarial-review-gemini-3.8-flash-high12Oct261132.md`).

## Global constraints

- Nothing applies unsigned; no wildcards; the 90-day maximum and the accepted-risk-needs-a-control rule are unchanged.
- `grc suppress draft` creates one new file and never writes `verified`, a reason, or an existing file.
- For a bundle without `targets`, scan outputs equal 2.1.0's apart from `schema_version` (1.3 to 1.4).
- `uv run pytest -q`, `uv run ruff check` and `uv run mypy` pass after every task.

## Review focus

1. **A suppression that applies without a signature, or wider than written.** Tests: Task 1 `test_targets_match_only_listed_files`, Task 2 `test_signed_draft_marker_fails_the_load`, Task 3 `test_draft_is_pending_until_verified`.
2. **Shell injection through the printed command.** Rule ids and targets come from scanned files. Test: Task 4 `test_draft_command_quotes_scanner_text`.
3. **A draft that hides a finding it should not cover.** Draft refuses targets with no finding, a kind the finding cannot take, and a finding another suppression already names. Tests: Task 3, one per refusal.
4. **A changed output for adopters who change nothing.** Test: Task 1 `test_single_target_outputs_unchanged`.
5. **A file written outside `suppressions/`.** Test: Task 3 `test_draft_refuses_bad_id`.

---

### Task 1: `targets` — one acceptance across several named files

**Files:** `src/grc_evidence/okf_lib.py`, `src/grc_evidence/map_findings.py`, `src/grc_evidence/render_report.py`, `src/grc_evidence/data/__init__.py` (`SCHEMA_VERSION = "1.4"`), `src/grc_evidence/data/schemas/concepts/suppression.schema.json`, `src/grc_evidence/data/schemas/mapping.schema.json`, `tests/test_suppressions.py`, `tests/test_concept_schemas.py`, `tests/test_contract.py` and `tests/test_render_report.py` (`s.target` becomes `s.targets[0]`), `docs/suppressions.md`, `docs/outputs.md`, `docs/okf-extensions.md`.

- [ ] **Step 1: Failing tests**

```python
def test_targets_match_only_listed_files(tmp_path): ...       # 2 of 3 files listed: 2 suppressed, 1 counts
def test_unused_target_is_reported(tmp_path): ...            # unused_targets == [{"id": ..., "target": ...}]
def test_fully_unused_multi_target_is_unused_suppression(tmp_path): ...
def test_target_and_targets_together_rejected(tmp_path): ...
def test_one_item_or_duplicate_targets_rejected(tmp_path): ...
def test_wildcard_in_targets_rejected(tmp_path): ...
def test_single_target_outputs_unchanged(): ...              # the Spec J snapshot fixtures, schema_version aside
```

Plus schema cases in `test_schemas_reject_the_syntax_cases` (both keys, one item, duplicates, a wildcard).

- [ ] **Step 2: Implement.** `_check_suppression` accepts `target` or `targets` (list, ≥ 2, distinct, each non-empty, no `*?[`). `Suppression.targets: tuple[str, ...]`; `matches` tests membership. `map_findings` records the matched `(id, target)` pairs and emits `unused_targets` for partly used suppressions, only when non-empty. `render_report` lists them under **Unused suppressions**. Schema: `oneOf` `target` / `targets`.
- [ ] **Step 3:** Docs: `targets` in `docs/suppressions.md` and `docs/okf-extensions.md`; `unused_targets` and contract 1.4 in `docs/outputs.md`.
- [ ] **Step 4:** Commit: "Suppressions: one acceptance may name several files (targets)".

### Task 2: A signed draft that was not edited fails the load

**Files:** `src/grc_evidence/okf_lib.py`, `tests/test_suppressions.py`.

- [ ] **Step 1: Failing tests:** `test_signed_draft_marker_fails_the_load` (verified + `<!-- grc: draft` in either section → `BundleError` naming the file); `test_unsigned_draft_marker_is_pending`.
- [ ] **Step 2: Implement** `DRAFT_MARKER = "<!-- grc: draft"` in `okf_lib`; checked in `_suppression` construction, or a bundle-level check beside `_check_accepted_risks`.
- [ ] **Step 3:** Commit: "A signed suppression must not keep the draft marker".

### Task 3: `grc suppress draft`

**Files:** create `src/grc_evidence/suppress.py`, `tests/test_suppress_draft.py`; `src/grc_evidence/cli.py` (`suppress` command), `docs/suppressions.md`.

- [ ] **Step 1: Failing tests** (fixture: a bundle with a CC7.1 control declaring `trivy:CVE-`, a `mapping.json` with four `go.mod` findings and one gap finding)

```python
def test_draft_writes_one_file_for_several_targets(tmp_path): ...  # suppressions/trivy-cve-2026-78669.md, 4 targets, "<rule> in 4 files"
def test_draft_single_target_uses_target(tmp_path): ...           # suppressions/trivy-cve-2026-78669-upstream-src-frontend-go-mod.md
def test_draft_slug_is_cut_to_100(tmp_path): ...
def test_draft_is_pending_until_verified(tmp_path): ...            # loads; map lists it in pending_suppressions
def test_draft_has_no_verified_and_has_marker(tmp_path): ...
def test_draft_refuses_target_without_finding(tmp_path): ...
def test_draft_refuses_accepted_risk_on_gap(tmp_path): ...
def test_draft_refuses_finding_already_named(tmp_path): ...       # pending, active and expired alike
def test_draft_refuses_existing_file(tmp_path): ...
def test_draft_refuses_days_and_owner(tmp_path): ...              # 0, 91; owner without human:
def test_draft_refuses_placeholder_owner(tmp_path): ...            # human:<you>
def test_draft_refuses_bad_id(tmp_path): ...                       # ../x, a/b, Index, index, log, 101 chars
def test_draft_accepted_risk_has_compensating_control_section(tmp_path): ...
def test_check_rejects_draft_until_signed(tmp_path): ...           # grc check: not verified; signed + markers gone: passes
def test_draft_approved_is_utc_today(tmp_path): ...               # injectable --today
```

- [ ] **Step 2: Implement.** `draft(bundle, mapping, request, today, now) -> (rel_path, text)` is pure; `main` takes `--config`, `--knowledge`, `--out`, `--today`, reads `grc.yaml` and `out/mapping.json`, writes the file, prints next steps. Frontmatter by `yaml.safe_dump`; scanner text in the facts list is collapsed to one line and quoted.
- [ ] **Step 3:** `grc check` on the fixture fails on the draft ("not verified by a person") and passes once it is signed and the markers are gone. No change to `adopt.py` (spec decision 7a).
- [ ] **Step 4:** Commit: "grc suppress draft: a pending suppression from the last scan".

### Task 4: The gate prints a draft command for each failing finding

**Files:** `src/grc_evidence/gate.py`, `tests/test_gate.py`, `docs/ci.md`.

- [ ] **Step 1: Failing tests**

```python
def test_gate_prints_one_command_per_rule(tmp_path): ...       # 4 go.mod targets -> one command, 4 --target
def test_command_kind_follows_mapping(): ...                    # control -> accepted-risk; gap (in unmapped) -> false-positive
def test_no_command_for_change_or_below_fail_on(): ...
def test_draft_command_quotes_scanner_text(): ...                # target "a b; rm -rf x" stays one quoted word; owner printed 'human:<you>'
def test_commands_are_sorted_and_on_stderr(): ...                # in the SystemExit message, after the failure list
def test_summary_has_the_commands(tmp_path): ...                # ### Draft suppressions, a ```sh block
def test_printed_command_drafts_one_suppression(tmp_path): ...   # end to end: run it (owner filled), sign it: grc check and the gate pass
```

- [ ] **Step 2: Implement.** `drafts(mapping, baseline, fail_on) -> list[str]` from the same new findings `problems` fails on, grouped by tool and rule id; the kind from whether the rule's findings are in `mapping["unmapped"]`. `main` adds them to the `SystemExit` message; `--summary` appends them. `findings()` is unchanged.
- [ ] **Step 3:** Commit: "grc gate: print a suppression draft command for each new finding".

### Task 5: Release 2.2.0

- [ ] **Step 1:** Version 2.2.0; `docs/roadmap.md` (Spec I Part A done), `docs/limits.md`, install pins.
- [ ] **Step 2:** `make examples` on a clean tree: outputs equal 2.1.0's apart from `schema_version`, timestamps and run ids; narratives reused.
- [ ] **Step 3: Owner:** tags `v2.2.0`; release notes.
- [ ] **Step 4: Demo:** pin 2.2.0; `make scan check gate` passes with no change to `expected/`. If decision 6 is yes: `grc suppress draft` for CVE-2026-78669 across the four files replaces the four suppressions; the owner writes the reason (or keeps the reviewed one) and signs.
