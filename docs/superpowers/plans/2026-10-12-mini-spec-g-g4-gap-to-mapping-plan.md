# Spec G, G4 Implementation Plan — coverage gaps become reviewable mapping drafts

**Goal:** each coverage gap that `grc triage` maps to a control with high confidence arrives as a patch that adds a draft `Scanner Check` concept declaring the rule; gaps no control covers arrive as an issue body. A person applies the patch, writes the concept, and signs it. Release 2.3.0 (with #141).

**Spec:** `docs/superpowers/specs/2026-10-01-mini-spec-g-agentic-workflows.md`, story G4. **Order:** Spec G §7 (G1 → G2 → G4 → G6 → G3 → G5 → G7).

## What exists

- `grc triage` writes `out/proposals.json`: per gap rule, `proposal` (an in-bundle control key, `none`, or `invalid`), `rationale`, `confidence`, and `cutoff_from` when the confidence cutoff turned a proposal into `none`. The schema restricts proposals to in-bundle keys. The default (Haiku 4.5, scoped input, `low` and `medium` treated as `none`) is measured in `docs/llm.md`: confirm accuracy 0.80, then 0.88, 0.76, 0.84 over three fresh runs.
- The proposals are not tied to the mapping they were made from, and do not name the model or settings.
- A concept that declares `rule_ids` needs exactly one control tag per framework; a `Scanner Check` concept (`knowledge/policies/set-resource-limits.md`) has `# Rule`, `# Satisfies`, `# Enforced at`, `# Remediation`.
- `grc check` fails on any concept without a `human:` verification (Spec I decision 7a).

## Decisions for the owner

1. **No new model call.** G4 turns triage's already validated proposals into drafts deterministically. Spec G placed G4 among the agent workflows; it needs no agent loop, so it is a `grc` command, not a `grc agent` workflow. Recommendation: yes.
2. **Where the rule goes.** (a) A new `Scanner Check` concept per gap rule, `knowledge/policies/<tool>-<rule_id>.md`, tagged with the proposed control; the patch never edits a reviewed concept, and the reviewer can merge it into an existing check. (b) Append the rule to an existing concept tagged with that control, which means choosing among several (a judgment the proposals do not carry) and re-verifying that concept. Recommendation: (a).
3. **Outputs.** `out/agent/mapping-<run_id>.patch` (for `git apply`) and `out/agent/gaps-<run_id>.md` (an issue body for the gaps no control covers, for `gh issue create -F`). No `--publish`: the command writes nothing outside `out/` and nothing to GitHub. Recommendation: yes.
4. **`proposals.json` names its inputs.** It becomes `{"mapping_sha256", "model", "variant", "abstain_on", "proposals": [...]}` instead of a bare list, so G4 refuses proposals made from another mapping (as `narratives.json` does) and the draft's `generated.by` names the model. `proposals.json` is not in the output contract; the skill text and `docs/llm.md` change with it. Recommendation: yes.
5. **The draft marker for every concept.** The new concept carries `<!-- grc: draft` lines in `# Rule` and `# Remediation`. Spec I made a signed suppression with a marker a load error; extend that to every concept type. Recommendation: yes.
6. **The evaluation figures** are referenced, not copied: the patch notes name the triage configuration and link `docs/llm.md`, so they never go stale. Recommendation: yes.
7. **MCP `draft_mapping`** (Spec G G1 said it would come with G4): left out until an agent needs it. Recommendation: defer.

## Rules

- **Proposals, never changes.** The command writes only under `out/agent/`. Applying the patch is a person's act; `grc check` then fails until the concept is signed, and a signed concept with a marker fails to load.
- **Only what triage validated.** A draft only for a proposal with `confidence: high`, a control key in the current bundle, a rule that is still a gap in the current `mapping.json`, and a rule id the loader accepts as a literal (no `*?[]`). Everything else is listed in the issue body or skipped with a reason.
- **Scanner and model text is quoted, one line, never a heading or a link.**

## Review focus

1. **A draft that maps without a signature.** Test: Task 3 `test_applied_patch_fails_check_until_signed`.
2. **Stale proposals.** Test: Task 1 `test_draft_refuses_proposals_for_another_mapping`.
3. **A patch that does not apply or does not load.** Test: Task 3 `test_patch_applies_and_the_gap_moves_to_the_control` (`git apply --check`, then `load_bundle` and `map_findings`).
4. **Text injection** from scanner messages or the model's rationale into frontmatter or headings. Test: Task 3 `test_untrusted_text_stays_quoted`.

---

### Task 1: `proposals.json` names its mapping and configuration

**Files:** `src/grc_evidence/triage.py`, `tests/test_triage.py`, `src/grc_evidence/data/skill/SKILL.md`, `docs/llm.md`.

- [ ] **Step 1: Failing tests:** `test_proposals_file_names_its_inputs` (keys `mapping_sha256` = `narrate.mapping_sha256(out/mapping.json)`, `model`, `variant`, `abstain_on`, `proposals`).
- [ ] **Step 2: Implement;** docs.
- [ ] **Step 3:** Commit: "grc triage: proposals.json names its mapping, model and settings".

### Task 2: A signed concept must not keep a draft marker

**Files:** `src/grc_evidence/okf_lib.py`, `tests/test_okf_reader.py`, `docs/okf-extensions.md`.

- [ ] **Step 1: Failing tests:** `test_signed_concept_with_marker_fails` (a `Scanner Check`), `test_unsigned_concept_with_marker_loads`. The suppression tests keep passing.
- [ ] **Step 2: Implement:** move the check from `_check_suppression` to `_parse`.
- [ ] **Step 3:** Commit: "Any signed concept with a draft marker fails to load".

### Task 3: `grc propose`

**Files:** create `src/grc_evidence/propose.py`, `tests/test_propose.py`; `src/grc_evidence/cli.py`, `docs/llm.md`, `README.md` (the command list).

- [ ] **Step 1: Failing tests** (fixture: the test bundle, a mapping with three gap rules, proposals: one `high` to `soc2:cc7.1`, one `none` with `cutoff_from`, one `invalid`)

```python
def test_patch_applies_and_the_gap_moves_to_the_control(tmp_path): ...  # git apply --check; load_bundle; map_findings: rule on cc7.1
def test_applied_patch_fails_check_until_signed(tmp_path): ...         # grc check: not verified; signed with markers: BundleError
def test_issue_body_lists_none_and_invalid(tmp_path): ...              # with the model's leaning (cutoff_from) and the reason
def test_draft_refuses_proposals_for_another_mapping(tmp_path): ...
def test_skips_rule_no_longer_a_gap_and_unknown_control(tmp_path): ...
def test_skips_rule_id_with_wildcard_characters(tmp_path): ...
def test_refuses_existing_concept_path(tmp_path): ...
def test_untrusted_text_stays_quoted(tmp_path): ...                   # message/rationale with "\n# H", "---", "](x)"
def test_no_gaps_writes_nothing(tmp_path): ...
```

- [ ] **Step 2: Implement.** `drafts(bundle, mapping, proposals_doc, run_id) -> (patch_text, issue_text, skipped)` is pure; `main` reads `out/`, writes `out/agent/`, prints what it wrote and what it skipped. The concept: `type: Scanner Check`, `title: <tool> <rule_id>`, `tags: [<control tag>]`, `rule_ids: [<tool>:<rule_id>]`, `generated: {by: <model> via grc triage, at}`, no `verified`; `# Rule` (marker, the scanner message and targets, the triage rationale, quoted), `# Satisfies` (link to the control), `# Enforced at`, `# Remediation` (marker).
- [ ] **Step 3:** Commit: "grc propose: coverage gaps as a mapping patch and an issue body".

### Task 4: Release 2.3.0

- [ ] **Step 1:** Version 2.3.0 (G4 and #141); `docs/roadmap.md`, `docs/limits.md`, install pins; `docs/outputs.md` says #141 ships in 2.3.0.
- [ ] **Step 2:** `make examples` unchanged apart from versions; owner runs `LLM_MODE=claude-cli make examples-llm`.
- [ ] **Step 3: Owner:** tags `v2.3.0`; release notes.
- [ ] **Step 4: Demo (optional):** `make triage` and `grc propose` on the demo's gaps; the owner decides whether any draft is worth applying.
