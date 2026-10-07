# Mini Spec J Implementation Plan — okflib as the OKF reader

**Goal:** okflib checks every concept and gives OKF's signals, review intervals make a person look at a concept again, our extension fields get schemas, and `okflib view` draws the graph. No change to the mapping, OSCAL, the report or the gate. Release 2.1.0.

**Spec:** `docs/superpowers/specs/2026-10-06-mini-spec-j-okflib-reader.md`. **Issue:** #139. **Review:** revised on 2026-10-06 after the Gemini 3.8 Flash plan review (`reviews/grc-evidence/claude-assessment-of-adversarial-review-gemini-3.8-flash-high06Oct261905.md`).

## Global constraints

- Our YAML parse stays the source of `Concept.frontmatter`, the body and the links. okflib parses the same text as a check and for the signals.
- A file that does not parse, for us or for okflib, fails the load with a `BundleError` naming the file. okflib's permissive `Bundle.load` is not used.
- The public API of `grc_evidence.okf_lib` does not change, except additions (`Concept.stale_after`).
- Runtime dependencies: `pyyaml` and `okflib==0.5.0`, pinned exactly in `pyproject.toml` (`uv tool install` does not read `uv.lock`).
- `uv run pytest -q`, `uv run ruff check` and `uv run mypy` pass after every task.

## Review focus

1. **A silent skip or a raw error.** Every malformed case fails with `BundleError` and the path. Test: Task 3, `test_okflib_errors_name_the_file`.
2. **A changed output.** Scan outputs equal 2.0.1's. Test: Task 1's output snapshot, run again in Task 3.
3. **A base copy that breaks every adopter.** An overdue base copy warns unless `base: fail`. Test: Task 5, `test_overdue_base_copy_warns_unless_base_fail`.
4. **A schema that drifts from the runtime checks.** Test: Task 4, `test_schemas_reject_the_syntax_cases`.
5. **okflib's network code on our path.** Test: Task 2, `test_okflib_llm_and_mcp_are_not_imported`.

---

### Task 1: Snapshot the parsed bundles and the scan outputs with 2.0.1's reader

**Files:** Create `scripts/okf_snapshot.py`, `tests/test_okf_snapshot.py`, `tests/fixtures/okf_snapshot/`.

- [ ] **Step 1:** `scripts/okf_snapshot.py` writes, for `knowledge/`, the base bundle and the two fixture bundles, every parsed concept: `id`, `path`, `type`, `title`, `description`, `tags`, `rule_ids`, `frontmatter` (JSON, exact), `body`, `links`. It also maps `tests/fixtures/findings.json` with each bundle and writes `mapping.json`, the three OSCAL documents and `report.md` with a fixed `now` and run id.
- [ ] **Step 2:** `tests/test_okf_snapshot.py` rebuilds both and compares byte for byte. It also runs on `../grc-evidence-boutique/knowledge` when that folder exists, and skips otherwise.
- [ ] **Step 3:** Commit: "Snapshot the parsed bundles and scan outputs before the reader changes".

### Task 2: Add the dependency

**Files:** `pyproject.toml`, `uv.lock`, `README.md` (Pins), `tests/test_okflib_dependency.py`.

- [ ] **Step 1: Failing test:** `test_okflib_llm_and_mcp_are_not_imported`: in a subprocess, `import grc_evidence.cli, grc_evidence.okf_lib`, then `okflib.llm` and `okflib.mcp` are not in `sys.modules`.
- [ ] **Step 2:** `dependencies = ["pyyaml>=6.0.2", "okflib==0.5.0"]`; `uv lock`; `make audit` passes.
- [ ] **Step 3:** README "Pins": okflib, exact pin, Apache-2.0.
- [ ] **Step 4:** Commit: "Depend on okflib 0.5.0, pinned exactly".

### Task 3: okflib checks every concept and gives `stale_after`

**Files:** `src/grc_evidence/okf_lib.py`; create `tests/test_okf_reader.py`.

- [ ] **Step 1: Failing tests**

```python
@pytest.mark.parametrize("frontmatter", [
    "type: X\nstale_after: soon\n",                     # ValueError in okflib
    "type: X\ngenerated: {by: a, at: yesterday}\n",     # ValueError
    "type: X\ntags: 5\n",                               # TypeError
    "type: X\nverified: human:reviewer\n",              # a string, not a list of stamps
])
def test_okflib_errors_name_the_file(tmp_path, frontmatter): ...  # BundleError "<path>: ..."
def test_stale_after_is_read(tmp_path): ...       # Concept.stale_after == date(2027, 1, 1)
def test_links_unchanged_for_anchors_and_escapes(tmp_path): ...  # #x, ../../README.md, mailto: dropped as today
```

- [ ] **Step 2: Implement.** In `_parse`, after our checks: `okflib.Concept.from_text(text)` inside `try`, turning `FrontmatterError`, `OKFError`, `ValueError` and `TypeError` into `BundleError(f"{rel_path}: ...")`. A `verified` that is not a list of mappings is a `BundleError`. `Concept.stale_after` comes from okflib. Frontmatter, body and links stay ours.
- [ ] **Step 3:** Task 1's snapshot test passes unchanged; the full suite passes.
- [ ] **Step 4:** Commit: "okflib checks every concept and gives stale_after".

### Task 4: Schemas for the extension fields' syntax

**Files:** `src/grc_evidence/data/schemas/concepts/{control,rule-declaring,suppression,root-index}.schema.json`, `tests/test_concept_schemas.py`, `docs/okf-extensions.md`, `README.md` (link).

- [ ] **Step 1: Failing tests:** every concept in `knowledge/` and the base bundle validates against its schema; `test_schemas_reject_the_syntax_cases` runs the syntax cases of the loader's rejection tests (a `rule_ids` entry that is not a literal prefix, an unknown `kind`, an `owner` without `human:`, a date that is not `YYYY-MM-DD`) against the schemas.
- [ ] **Step 2: Write the schemas.** Syntax only. The 90-day limit, `# Reason`, and an accepted risk that must map to a control stay runtime checks; `docs/okf-extensions.md` says which is which.
- [ ] **Step 3:** Commit: "Schemas for the syntax of the bundle's extension fields".

### Task 5: Review intervals in `grc check`

**Files:** `src/grc_evidence/config.py` (`review:`), `src/grc_evidence/adopt.py` (`check(repo, config, today)`), `grc.yaml` (new, `review:` only), `tests/test_config.py`, `tests/test_adopt.py`, `docs/new-repo.md`.

- [ ] **Step 1: Failing tests**

```python
def test_review_config_parses_durations(tmp_path): ...       # 90d, 6m, 1y; calendar months
def test_unknown_type_in_by_type_is_an_error(tmp_path): ...
def test_due_from_latest_human_verification(tmp_path): ...  # due = latest human verified.at + interval
def test_explicit_stale_after_earlier_wins(tmp_path): ...
def test_warns_within_warn_before_and_fails_after(tmp_path): ...
def test_overdue_base_copy_warns_unless_base_fail(tmp_path): ...
def test_suppressions_are_not_reviewed(tmp_path): ...
def test_no_review_section_only_stale_after_counts(tmp_path): ...
```

- [ ] **Step 2: Implement.** `Config.review_default`, `review_by_type`, `review_warn_before` (30 days), `review_base` (`warn`). `adopt.check` gets `today: date | None = None` and returns warnings apart from problems; `grc check` prints warnings and fails only on problems.
- [ ] **Step 3:** This repo's `grc.yaml`: the intervals of spec §4.3 and `base: fail`. `grc check` passes today (the latest verifications are from 2026-09-25 to 2026-10-06).
- [ ] **Step 4:** Commit: "Review intervals: grc check warns before a verification expires and fails after".

### Task 6: `make render` with `okflib view`

**Files:** `Makefile`, `src/grc_evidence/data/tools.lock`, `tests/test_tools_lock.py` (if it lists `OKF_COMMIT`), `README.md`, `docs/limits.md`, `docs/screenshots/knowledge-graph.png`.

- [ ] **Step 1:** `render: mkdir -p out; uv run okflib view -C knowledge -o out/knowledge-viz.html --no-open`; remove `OKF` and `OKF_COMMIT`.
- [ ] **Step 2:** Run it after `make clean`; the page lists every concept.
- [ ] **Step 3: Owner:** a new screenshot of the graph for the README.
- [ ] **Step 4:** Commit: "make render uses okflib view; drop the reference visualizer pin".

### Task 7: Release 2.1.0

- [ ] **Step 1:** Version 2.1.0; `docs/limits.md`, `docs/roadmap.md`; the install pins.
- [ ] **Step 2:** `make examples` on a clean tree: the mapping, OSCAL and report equal 2.0.1's, timestamps and run ids aside; the narratives are reused.
- [ ] **Step 3:** The demo: pin 2.1.0; its `grc.yaml` gets the same `review:` section with `base: warn`; `make scan check gate` passes with no change to `expected/`.
- [ ] **Step 4:** The owner tags `v2.1.0`; release notes.
