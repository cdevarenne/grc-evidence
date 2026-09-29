# Mini Spec E — Compliance Data Layer (not started)

- **Date:** 2026-09-29
- **Status:** not started; recorded for a future `v1.1`. Needs review before a plan.
- **Depends on:** v1.0 (Specs A–D).
- **LLM cost:** none. Embeddings use a pinned local model.

## 1. Why

The bundle is read in memory on every run, and each scan's results live only in
`out/`. A queryable store would give two things v1.0 lacks: search and graph
queries over the knowledge bundle, and a history of control status across scan
runs (a view of control health over time).

## 2. Principles

- **Markdown in git is the source of truth; the database is a rebuildable
  projection.** Every row traces to a concept file or a scan output. Lose the
  database, re-ingest, lose nothing. Migrations version the schema, never data.
- **Read and write are separate.** People and agents change the bundle through
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

## 4. Out of scope

Hosted databases (AlloyDB is Postgres-compatible and would be the managed
target at scale), dedicated vector or graph databases, agents writing to the
store, and a UI.

## 5. Open questions for review

1. Local embedding model and dimension.
2. Whether the in-memory `okf_lib` path stays the default with the store as an
   optional sink (recommended), or the scan reads from the store.
3. Prune concepts whose file was deleted on incremental ingest, or only on full
   rebuild.
