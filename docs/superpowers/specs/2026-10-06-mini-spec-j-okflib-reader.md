# Mini Spec J — okflib as the OKF reader, with schemas for our extension fields

- **Date:** 2026-10-06
- **Status:** approved by the owner on 2026-10-06, after the Gemini 3.8 Flash plan review (assessment: `reviews/grc-evidence/claude-assessment-of-adversarial-review-gemini-3.8-flash-high06Oct261905.md`). Plan: [plan](../plans/2026-10-06-mini-spec-j-okflib-reader-plan.md).
- **Issue:** #139. **Release:** 2.1.0. **LLM cost:** none.
- **Depends on:** v2.0.1.

## 1. Why

- **One reader across the repos.** Three OKF readers have drifted apart: grounded-context's `bundle.py`, this repo's `okf_lib.py`, and a copy in the drone repo. [okflib](https://pypi.org/project/okflib/) (Apache-2.0, PyPI 0.5.0) reads OKF v0.1 and v0.2 and keeps every unknown frontmatter key. This repo adopts it first.
- **The format as a contract.** The real contract of this bundle is in fields OKF does not define (`rule_ids`, `framework`, `applies_when`, `sdks`, the suppression fields, `base_version`). None has a written schema.
- **Staleness.** Frameworks, regulations and the policies built on them change, but nothing makes a person look at a concept again after verifying it once.

## 2. What the spike showed (#139, 2026-10-06)

- On five bundles (this repo's `knowledge/`, the base bundle, the demo's `knowledge/`, two test fixtures; 175 concepts), `okflib.Concept.from_text` gives the same type, title, description, tags, body and frontmatter keys as `okf_lib._parse`.
- okflib returns raw link targets (`../controls/cc8.1.md`). Resolved with okflib's own rule they equal ours, except that ours drops duplicates and links to `index.md`.
- `frontmatter_dict()` equals the raw YAML for every key except `generated.at` (`Z` for `+00:00`).
- The plan review (2026-10-06) found more, each checked against okflib 0.5.0: a bad `stale_after` or `generated.at` raises a raw `ValueError`, `tags: 5` a raw `TypeError`, and a string `verified` becomes one stamp per character; okflib's link resolution turns `#anchor`, `../../README.md` and `mailto:` links into made-up concept ids or crashes; `frontmatter_dict()` drops empty lists such as `tags: []`.
- `okflib.Bundle.load` skips a file that does not parse unless `strict=True`, and with `strict=True` its error does not name the file.

## 3. Rules

1. **No output changes.** Mapping, OSCAL, the report and the gate give the same bytes for the same inputs (timestamps and run ids aside). `run.json` changes only additively: the resolved config gains the `review` settings (§4.3). Tests compare every parsed concept, and the scan outputs, with 2.0.1.
2. **Fail closed.** A file that does not parse, for us or for okflib, stops the load with a `BundleError` that names the file. okflib's permissive `Bundle.load` is never used, and every okflib error (`FrontmatterError`, `OKFError`, `ValueError`, `TypeError`) becomes a `BundleError`.
3. **What stays ours.** The directory walk, the grounding rules (`rule_ids`, one control tag per framework), the control and suppression checks, `section`, `by_rule`, `declaring`, `suppressions`, crosswalks, and the public API of `okf_lib` (`load_bundle`, `Bundle`, `Concept`, `BundleError`, the framework tables). Callers do not change.
4. **The dependency is pinned exactly in `pyproject.toml`** (`okflib==0.5.0`), because `uv tool install` and `uvx` do not read `uv.lock` (checked: a lock pinning `six` 1.15.0 installed 1.17.0). `make audit` covers it. Only `okf_lib.py` imports okflib, and a test checks that importing `grc_evidence` does not import `okflib.llm` or `okflib.mcp`.

## 4. Scope

### 4.1 The reader (Part 1)

Our own YAML parse stays the source of `Concept.frontmatter`, the body and the links (`_LINK`, `_resolve_link`), so outputs cannot change by construction (owner decision, 2026-10-06, after the plan review). `okf_lib._parse` also runs `okflib.Concept.from_text` on the same text: as a conformance check of OKF's core fields and v0.2 signals, and as the source of `stale_after` and the `verified` stamps. `Concept` gains `stale_after: date | None` (additive).

What okflib gives this repo: one reading of OKF's core fields and signals, shared with the other repos; its conformance checks; and `okflib view`. It does not remove our parser.

### 4.2 Schemas for the extension fields (Part 2)

One JSON Schema per concept type that uses extension fields, in `src/grc_evidence/data/schemas/concepts/`: controls (`framework`, `applies_when`), rule-declaring concepts (`rule_ids`, `sdks`, control tags), suppressions (`finding`, `kind`, `owner`, `approved`, `expires`), and the root `index.md` (`okf_version`, `base_version`). The conformance tests validate every concept of this repo's `knowledge/` and the base bundle against its schema (`jsonschema` is already a dev dependency). The schemas cover field syntax only: types, patterns (`rule_ids`, `owner` starting `human:`), enums (`kind`), and the date format. Rules that span fields, the body or the bundle stay runtime checks in `okf_lib`: the 90-day limit on a suppression, its `# Reason` section, and an accepted risk that must map to a control. A test runs the syntax cases of the loader's rejection tests against the schemas.

### 4.3 Review intervals and `stale_after` (Part 3)

A person's verification stays valid for an interval set in `grc.yaml` (owner decisions, 2026-10-06):

```yaml
review:
  default: 1y
  by_type:
    SOC 2 Control: 1y
    Crosswalk: 6m
  warn_before: 30d    # default
  base: warn          # base-bundle copies: warn (default) or fail
```

- An interval is a number with `d`, `m` or `y`; months and years are calendar months.
- A concept is due at its latest `human:` verification plus the interval for its type (`default` for a type not listed). A concept's own `stale_after` also counts; the earlier date wins.
- Without a `review:` section, only an explicit `stale_after` counts, so nothing changes for an adopter that does not opt in.
- `grc check` warns from `warn_before` before the due date and fails after it ("<path>: review due <date>: verify it again").
- Base-bundle copies: an adopter cannot re-verify a copy without drift, so with `base: warn` (the default) an overdue copy is a warning ("overdue in the engine; upgrade when a release re-verifies it"). The engine's own `grc.yaml` sets `base: fail`, so the engine's owner must re-verify before a release.
- Suppressions are excluded; they keep their own `expires`, at most 90 days.
- A type in `by_type` that the bundle does not have is a config error naming it.

This repo's `grc.yaml` and the demo's: `1y` for `SOC 2 Control`, `ISO/IEC 42001 Control` and `EU AI Act Article`; `6m` for `Crosswalk`, `Rego Policy`, `Semgrep Rule`, `Scanner Check` and `Scanner`; `90d` for `Stack Component`; `default: 1y`.

### 4.4 `make render` with okflib (Part 4)

`make render` runs `okflib view` (owner decision, 2026-10-06) instead of the OKF reference visualizer, which drops the pinned `OKF_COMMIT` git dependency from `tools.lock`. The README's graph screenshot is replaced. `okflib view` loads the bundle permissively; that is acceptable for a picture, because `grc check` and every scan load it strictly.

## 5. Done when

1. A test loads the five spike bundles and compares each parsed concept with a snapshot taken before the change: same fields, same links.
2. The full test suite, the integration tests and `make audit` pass; `make examples` on a clean tree gives the same mapping, OSCAL and report as 2.0.1 (timestamps and run ids aside).
3. A file with broken frontmatter fails the load with its path in the message.
4. Every concept in `knowledge/` and the base bundle validates against its schema.
5. `grc check` warns on a concept due within `warn_before` and fails on an overdue one, from the `review:` intervals and `stale_after`; an overdue base copy only warns unless `base: fail`.
6. `make render` writes `out/knowledge-viz.html` with `okflib view`, and `tools.lock` has no `OKF_COMMIT`.
7. 2.1.0 is released; the demo pins it, and its gate passes with no change to `expected/`.

## 6. Out of scope

- grounded-context and the drone repo adopting okflib (their own issues).
- Writing bundles with okflib (`grc init` and `grc sync-base` copy files; they do not serialize concepts).

## 7. Owner decisions (2026-10-06)

1. A stale concept fails `grc check`, after a warning window.
2. `make render` moves to `okflib view` in this spec.
3. After the plan review: our YAML parse stays the source of frontmatter, body and links; okflib checks the same text and gives the signals.
4. Review intervals in `grc.yaml` as in §4.3: any `Nd`/`Nm`/`Ny`; clock from the latest human verification; explicit `stale_after` also counts (earlier wins); opt in; base copies warn in adopters and fail in the engine; `warn_before` configurable (30 days); suppressions excluded; unknown types are an error.
