# Mini Spec J Implementation Plan — okflib as the OKF reader

**Goal:** Parse the OKF bundle with okflib, write schemas for our extension fields, fail `grc check` on stale concepts, and render the graph with `okflib view`, with no change to any scan output. Release 2.1.0.

**Spec:** `docs/superpowers/specs/2026-10-06-mini-spec-j-okflib-reader.md`. **Issue:** #139.

## Global constraints

- No output changes: mapping, OSCAL, the report, `run.json` and the gate are the same for the same inputs (timestamps and run ids aside).
- A file that does not parse fails the load with a `BundleError` naming the file. okflib's permissive `Bundle.load` is not used.
- The public API of `grc_evidence.okf_lib` does not change; no caller changes.
- Runtime dependencies: `pyyaml` and `okflib==0.5.0`, pinned exactly.
- `uv run pytest -q`, `uv run ruff check` and `uv run mypy` pass after every task.

## Review focus

1. **A silent skip.** A concept file whose frontmatter does not parse must stop the load, never be skipped. Test: Task 3, `test_broken_frontmatter_names_the_file`.
2. **Links.** Duplicates and `index.md` targets are dropped as today; a link that leaves the bundle stays out. Test: Task 1's snapshot, and Task 3, `test_links_match_the_old_reader`.
3. **A frontmatter value that changes type.** okflib re-serializes `generated` and `verified`; the snapshot compares every frontmatter value, `generated.at` normalized. Test: Task 1.
4. **A schema that drifts from the runtime checks.** Test: Task 4, `test_schemas_reject_what_the_loader_rejects`.

---

### Task 1: Snapshot the parsed bundles with the current reader

**Files:** Create `tests/test_okf_snapshot.py`, `tests/fixtures/okf_snapshot.json`, `scripts/okf_snapshot.py`.

- [ ] **Step 1:** `scripts/okf_snapshot.py` loads `knowledge/`, the base bundle and the two fixture bundles with the current `load_bundle` and writes, per concept: `id`, `path`, `type`, `title`, `description`, `tags`, `rule_ids`, `frontmatter` (JSON, `generated.at` normalized to UTC `Z`), `body`, `links`.
- [ ] **Step 2:** `test_okf_snapshot.py` reloads the four bundles and compares with the snapshot. It passes now, on the old reader.
- [ ] **Step 3:** Commit: "Snapshot the parsed OKF bundles before the reader changes".

The demo's `knowledge/` is outside this repo: compare it by hand in Task 6.

### Task 2: Add the dependency

**Files:** Modify `pyproject.toml`, `uv.lock`, `README.md` (Pins).

- [ ] **Step 1:** `dependencies = ["pyyaml>=6.0.2", "okflib==0.5.0"]`; `uv lock`.
- [ ] **Step 2:** `make audit` passes (Trivy reads `uv.lock`).
- [ ] **Step 3:** README "Pins": okflib is pinned exactly, Apache-2.0.
- [ ] **Step 4:** Commit: "Depend on okflib 0.5.0".

### Task 3: Parse with okflib

**Files:** Modify `src/grc_evidence/okf_lib.py`; create `tests/test_okf_reader.py`.

- [ ] **Step 1: Write the failing tests**

```python
def test_broken_frontmatter_names_the_file(tmp_path): ...  # BundleError "<path>: unparseable frontmatter"
def test_missing_type_names_the_file(tmp_path): ...
def test_links_match_the_old_reader(): ...  # duplicates and index.md dropped; resolved ids
def test_okflib_does_the_parsing(monkeypatch): ...  # okflib.Concept.from_text is called once per file
```

- [ ] **Step 2: Implement.** In `_parse`, call `okflib.Concept.from_text(text)`; turn `FrontmatterError` into `BundleError(f"{rel_path}: ...")`. `frontmatter = parsed.frontmatter_dict()`, `body = parsed.body`, `links` = the resolved concept links, unique and sorted as today, without `index.md` targets. Keep the directory walk and every existing check. Remove the regexes this makes unused.
- [ ] **Step 3: Run** the snapshot test and the full suite.
- [ ] **Step 4:** Commit: "Parse OKF concepts with okflib; keep our checks and API".

### Task 4: Schemas for the extension fields

**Files:** Create `src/grc_evidence/data/schemas/concepts/{control,rule-declaring,suppression,root-index}.schema.json`, `tests/test_concept_schemas.py`.

- [ ] **Step 1: Write the failing tests:** every concept in `knowledge/` and the base bundle validates against the schema for its type; `test_schemas_reject_what_the_loader_rejects` runs the malformed cases of `test_suppressions.py` and `test_bundle_conformance.py` against the schemas.
- [ ] **Step 2: Write the schemas** from the runtime checks in `okf_lib` (`_check_grounding`, `_check_control`, `_check_suppression`): `rule_ids` as `<tool>:<literal prefix>[*]`, `kind` in the two kinds, `owner` starting `human:`, dates as `YYYY-MM-DD`, at most 90 days.
- [ ] **Step 3:** `docs/okf-extensions.md`: one table per schema, linked from the README.
- [ ] **Step 4:** Commit: "Schemas for the bundle's extension fields".

### Task 5: Flag stale concepts in `grc check`

**Files:** Modify `src/grc_evidence/adopt.py`; tests in `tests/test_adopt.py`.

- [ ] **Step 1: Write the failing test:** a concept with `stale_after` before today makes `grc check` fail with `"<path>: stale since <date>: review it and set a new date"`; one after today gives nothing.
- [ ] **Step 2: Implement** with okflib's `Concept.is_stale(on=today)`.
- [ ] **Step 3: Owner:** set `stale_after` on the base controls and crosswalks (spec §7.1), then `grc sync-base`.
- [ ] **Step 4:** Commit: "grc check flags a concept past its stale_after".

### Task 6: `make render` with `okflib view`

**Files:** Modify `Makefile`, `src/grc_evidence/data/tools.lock`, `tests/test_tools_lock.py` (if it lists `OKF_COMMIT`), `README.md`, `docs/limits.md`; replace `docs/screenshots/knowledge-graph.png`.

- [ ] **Step 1:** `render: uv run okflib view --bundle knowledge -o out/knowledge-viz.html --no-open`; remove `OKF` and `OKF_COMMIT`.
- [ ] **Step 2:** Run it; the page lists every concept.
- [ ] **Step 3: Owner:** a new screenshot of the graph for the README.
- [ ] **Step 4:** Commit: "make render uses okflib view; drop the reference visualizer pin".

### Task 7: Release 2.1.0

- [ ] **Step 1:** Version 2.1.0; `docs/limits.md` (the reader), `docs/roadmap.md`; the install pins.
- [ ] **Step 2:** `make examples` on a clean tree: the mapping, OSCAL and report equal 2.0.1's, timestamps and run ids aside. The narratives are reused, since `mapping.json` does not change.
- [ ] **Step 3:** The demo: load its `knowledge/` with the old and the new reader and compare (as the spike did); pin 2.1.0; `make scan check gate` passes with no change to `expected/`.
- [ ] **Step 4:** The owner tags `v2.1.0`; release notes.
