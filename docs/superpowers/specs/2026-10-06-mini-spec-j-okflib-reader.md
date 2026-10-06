# Mini Spec J — okflib as the OKF reader, with schemas for our extension fields

- **Date:** 2026-10-06
- **Status:** draft, for the owner's review and an adversarial plan review. Plan: [plan](../plans/2026-10-06-mini-spec-j-okflib-reader-plan.md).
- **Issue:** #139. **Release:** 2.1.0. **LLM cost:** none.
- **Depends on:** v2.0.1.

## 1. Why

- **One reader across the repos.** Three OKF readers have drifted apart: grounded-context's `bundle.py`, this repo's `okf_lib.py`, and a copy in the drone repo. [okflib](https://pypi.org/project/okflib/) (Apache-2.0, PyPI 0.5.0) reads OKF v0.1 and v0.2 and keeps every unknown frontmatter key. This repo adopts it first.
- **The format as a contract.** The real contract of this bundle is in fields OKF does not define (`rule_ids`, `framework`, `applies_when`, `sdks`, the suppression fields, `base_version`). None has a written schema.
- **Staleness.** Frameworks and regulations change, but no concept here has `stale_after`. okflib supports it.

## 2. What the spike showed (#139, 2026-10-06)

- On five bundles (this repo's `knowledge/`, the base bundle, the demo's `knowledge/`, two test fixtures; 175 concepts), `okflib.Concept.from_text` gives the same type, title, description, tags, body and frontmatter keys as `okf_lib._parse`.
- okflib returns raw link targets (`../controls/cc8.1.md`). Resolved with okflib's own rule they equal ours, except that ours drops duplicates and links to `index.md`.
- `frontmatter_dict()` equals the raw YAML for every key except `generated.at` (`Z` for `+00:00`).
- `okflib.Bundle.load` skips a file that does not parse unless `strict=True`, and with `strict=True` its error does not name the file.

## 3. Rules

1. **No output changes.** Mapping, OSCAL, the report, `run.json` and the gate give the same bytes for the same inputs (timestamps and run ids aside). A test compares every parsed concept before and after (§5.1).
2. **Fail closed.** A file that does not parse stops the load with a `BundleError` that names the file, as today. okflib's permissive default is never used.
3. **What stays ours.** The directory walk, the grounding rules (`rule_ids`, one control tag per framework), the control and suppression checks, `section`, `by_rule`, `declaring`, `suppressions`, crosswalks, and the public API of `okf_lib` (`load_bundle`, `Bundle`, `Concept`, `BundleError`, the framework tables). Callers do not change.
4. **The dependency is pinned exactly** (`okflib==0.5.0`); `uv.lock` holds its hash, and `make audit` covers it.

## 4. Scope

### 4.1 The reader (Part 1)

`okf_lib._parse` uses `okflib.Concept.from_text` for the frontmatter and the body, and keeps its own checks. `Concept.links` comes from okflib's links, resolved, without duplicates, and without `index.md` targets. `Concept.frontmatter` is okflib's `frontmatter_dict()`. On the 175 spike concepts it equals the raw YAML for every key, `verified` and the extension fields included, except `generated.at`, written with `Z` instead of `+00:00`: the same instant, and no engine code reads it.

### 4.2 Schemas for the extension fields (Part 2)

One JSON Schema per concept type that uses extension fields, in `src/grc_evidence/data/schemas/concepts/`: controls (`framework`, `applies_when`), rule-declaring concepts (`rule_ids`, `sdks`, control tags), suppressions (`finding`, `kind`, `owner`, `approved`, `expires`), and the root `index.md` (`okf_version`, `base_version`). The conformance tests validate every concept of this repo's `knowledge/` and the base bundle against its schema (`jsonschema` is already a dev dependency). The runtime checks in `okf_lib` stay the enforcement; the schemas are the written contract, and a test keeps the two in step.

### 4.3 `stale_after` (Part 3)

`grc check` reports a concept whose `stale_after` has passed as a problem ("stale since <date>: review it and set a new date"), next to the "not verified" problems. The dates are the owner's decision; the plan proposes them for the base controls and crosswalks.

## 5. Done when

1. A test loads the five spike bundles and compares each parsed concept with a snapshot taken before the change: same fields, same links.
2. The full test suite, the integration tests and `make audit` pass; `make examples` on a clean tree gives the same mapping, OSCAL and report as 2.0.1 (timestamps and run ids aside).
3. A file with broken frontmatter fails the load with its path in the message.
4. Every concept in `knowledge/` and the base bundle validates against its schema.
5. `grc check` reports a concept past its `stale_after`.
6. 2.1.0 is released; the demo pins it, and its gate passes with no change to `expected/`.

## 6. Out of scope

- grounded-context and the drone repo adopting okflib (their own issues).
- `make render` with `okflib view` instead of the OKF reference visualizer: an owner decision (§7).
- Writing bundles with okflib (`grc init` and `grc sync-base` copy files; they do not serialize concepts).

## 7. Owner decisions

1. The `stale_after` dates for the base controls and crosswalks, and whether a stale concept fails `grc check` (proposed) or only warns.
2. Whether `make render` moves to `okflib view` (one less pinned git dependency), in this spec or later.
