# Mini Spec E — Compliance Data Layer (not started; revised 2026-10-04)

- **Date:** 2026-09-29
- **Status:** not started. Revised 2026-10-04 after Spec H: the store now holds two kinds of record (§2). Needs review before a plan.
- **Related:** [Spec H](2026-10-04-mini-spec-h-type2-evidence-window.md) writes the evidence ledger as JSON Lines first. This spec moves that ledger into the store (§3.2).
- **Depends on:** v1.0 (Specs A–D).
- **LLM cost:** none. Embeddings use a pinned local model.

## 1. Why

The bundle is read in memory on every run, and each scan's results live only in
`out/`. A queryable store would give two things v1.0 lacks: search and graph
queries over the knowledge bundle, and a history of control status across scan
runs (a view of control health over time).

## 2. Principles

- **Two kinds of record, two sources of truth.**
  - **Knowledge** (controls, crosswalks, policies, scanners, suppressions,
    risk acceptances): a person writes it, the volume is small, and a pull
    request is its review step. Markdown in git is its source of truth. The
    tables in §3.1 are a rebuildable projection of it.
  - **Evidence** (ledger entries, change populations, posture snapshots,
    scan results): code writes it, it grows with every run and every target
    repo, and it is append-only. The store is its source of truth (§3.2).
    Before the store exists, the JSON Lines ledger of Spec H is the source
    of truth, and an import moves it into the store with no loss.
- **Knowledge projection rules.** The database copy of the bundle is a
  rebuildable projection. Every row traces to a concept file or a scan output. Lose the
  database, re-ingest, lose nothing. Migrations version the schema, never data.
- **Read and write are separate for knowledge.** People and agents change the bundle through
  markdown commits; the store changes only by re-ingestion.
- **Deterministic, idempotent ingest.** A per-concept `content_hash`
  (sha256 of canonical frontmatter + body) gates upserts; a full rebuild from a
  given commit yields the same rows.
- **Retrieval is navigation, never mapping.** A finding maps to a control only
  through `rule_ids`, as in v1.0. No search result, similarity score, or tag
  overlap may attach a finding to a control.
- **Pin the embedding model and dimension**; record them per chunk; re-embed on
  change.

## 3. Scope

### 3.1 Knowledge projection

Postgres + pgvector (local Docker), one engine for full-text, vector, graph,
and metadata queries.

| Table | Rows |
|---|---|
| `concept` | one per concept file: id, path, type, title, tags, frontmatter (jsonb), body, `content_hash`, `bundle_version`, generated `tsvector` |
| `concept_edge` | one per markdown link: `src_id`, `dst_id` (NULL when dangling), raw `dst_path`, `rel_type` (start with `links`) |
| `concept_chunk` | body chunks with `embedding vector(n)` and `model` |
| `scan_run` | one per `make scan`: time, tool versions from `tools.lock`, `bundle_version` |
| `control_status` | one per control per run: status, finding counts, suppressed and accepted counts |
| `finding` | one per finding per run, with its control keys or gap reason and any suppression |

- `ingest.py`: walk the bundle through `okf_lib`, hash-gated upsert, derive
  edges, chunk and embed; load `mapping.json` for a scan run.
- `retrieve.py`: keyword (FTS), semantic (vector), hybrid (reciprocal rank
  fusion), graph traversal (recursive CTE), dangling links, and the rule-based
  grounding lookup (`rule_ids`, not tags).
- A `control_health` view: latest status per control and its change across runs.
- `make reingest` rebuilds the store from the bundle at the current commit.

Full-text search works without embeddings, so unit tests do not depend on the
model; vector search is layered on top.

### 3.2 Evidence records (added 2026-10-04)

These tables are the source of truth for evidence. Rows are inserted, never
updated or deleted. A correction is a new row that names the row it
supersedes.

| Table | Rows |
|---|---|
| `ledger_entry` | one per Spec H ledger line: `entry_id` (sha256), `prev_id`, `schema_version`, `recorded_at`, `engine_version`, `collector`, `repo`, `window_start`, `window_end`, `inputs` (jsonb), `outputs` (jsonb: path → sha256), `summary` (jsonb), `rate_limit` (jsonb, nullable), `supersedes` |
| `change` | one per merged change per collection: `entry_id`, `repo`, `number`, `author`, `merged_by`, `merged_at`, `merge_sha`, `base_ref`, `approvers` (array), `flags` (array) |
| `posture_snapshot` | one per repo per collection: `entry_id`, `repo`, `branch`, `required_reviews`, `required_checks` (array), `admin_bypass`, `scanner_jobs` (jsonb), `readable` |

- **Import:** `grc ledger import evidence/ledger.jsonl` loads the JSON Lines
  ledger. It checks the hash chain first and stops on the first broken link.
  Import is idempotent: an `entry_id` that is already stored is skipped.
- **Equivalence test:** the window report computed from the store equals the
  report computed from the JSON Lines file for the same entries.
- **Backends:** SQLite (default, no server) and Postgres. The schema uses
  only types that both support, and uses JSON text where Postgres would use
  `jsonb`. Postgres adds GIN indexes. The choice between them, and the
  benchmark against plain files and object storage, is a separate backlog
  item.
- **Many target repos:** every evidence row carries `repo`. One store serves
  one grc instance that collects from N repos.

## 4. Out of scope

Hosted databases (AlloyDB is Postgres-compatible and would be the managed
target at scale), dedicated vector or graph databases, agents writing to the
store, and a UI.

## 5. Open questions for review

1. Local embedding model and dimension.
2. Whether the in-memory `okf_lib` path stays the default with the store as an
   optional sink (recommended), or the scan reads from the store. For
   knowledge, the in-memory path stays the default. For evidence, the store
   becomes the default once it exists.
3. Prune concepts whose file was deleted on incremental ingest, or only on full
   rebuild.
