# PRD Summary — v2.0
**Date:** 2026-06-01

---

## Feature Index

| # | Feature | One-line description | Dependencies | NFR flags |
|---|---------|---------------------|--------------|-----------|
| F01 | Data Ingestion | Fetches, parses, segments, and indexes CA/LS/RS records; resumable via per-document checkpoints | None | Rate limiting, storage, processing time, resumability |
| F02 | Full-text Search | Keyword search with query expansion across all indexed fields; ranked results | F01, F04 | Response time (PERF-1), scalability (SCALE-1) |
| F03 | Search Filters | Five filter dimensions (body, date, speaker, session, proceeding type) combinable and persistent | F01, F02 | None beyond PERF-1 |
| F04 | Query Expansion | Synonym and spell-correction expansion via static dictionary; reduced-weight OR alternatives | F02 | None beyond PERF-1 |
| F05 | Result Display | Paginated result cards with snippet, metadata, lang_original badge, time_of_day, and source link | F01, F02 | None beyond PERF-1 |
| F06 | Sorting | Relevance / chronological / reverse-chronological sort; persists across refinements | F01, F02 | None beyond PERF-1 |
| F07 | Indexing Status Panel | Read-only panel showing per-source record counts and last ingestion date | F01 | None |
| F08 | Search History | Cookie-based recent searches (10, 30-day) and saved searches (20, persistent) with filter capture | F02, F03 | Privacy (PRIV-1) |
| F09 | Detail Page | Full-text + all metadata for a single record; adjacent navigation within sitting; stable URL | F01, F02 | Detail page response time (PERF-2) |

---

## Cross-Feature Interaction Map

| Features | Interaction |
|----------|-------------|
| F01 → F02 | F02 searches the index F01 populates; all searchable fields must be indexed by F01 |
| F01 → F05 | F05 renders fields indexed by F01; `lang_original`, `time_of_day`, `word_count`, `id`, `sequence_within_sitting` (Q+A) are new F01 fields consumed by F05 and F09 |
| F01 → F06 | F06 secondary sort key `sequence_within_sitting` is set at ingest by F01 |
| F01 → F07 | F07 reads the per-source summary record written by F01 at end of each ingestion run |
| F01 → F09 | F09 fetches single records by `id` set at ingest; adjacent navigation uses `sequence_within_sitting` assigned by F01 |
| F02 → F03 | F03 applies filter constraints to F02 search execution; AND logic across all active filters |
| F02 → F04 | F04 augments queries before F02 executes; F02 consumes synonym and correction expansions with weighted scoring |
| F02 → F05 | F02 provides ranked results and match position data for F05 snippet extraction and term highlighting |
| F02 → F06 | F06 relevance sort uses the relevance score computed by F02 |
| F02 → F08 | F08 re-executes stored queries by passing them to F02; recent search re-runs use F02 with default filters |
| F03 → F08 | F08 saved searches capture and restore F03 filter state; recent searches do not capture filter state |
| F05 → F09 | F09 detail page uses same proceeding type label map defined in F05; lang_original badge values consistent |

---

## Active NFR Summary

| ID | Requirement |
|----|------------|
| PERF-1 | Search results: ≤2 seconds p95 from query submission to result list rendered, full corpus, with query expansion active |
| PERF-2 | Detail page full load including neighbour fetch: ≤500ms p95 |
| INF-R1 | Ingestion resumable from per-document checkpoint; identical final record count on re-run; no duplicates |
| INF-S1 | Storage architecture must be sized for full CA + 12-year LS/RS corpus before build |
| INF-RL1 | Comply with robots.txt on all source sites; HTTP 429 triggers exponential backoff and retry, not skip |
| INF-P1 | Bulk ingestion is long-running; real-time progress logging required; no human supervision needed |
| SCALE-1 | Search within PERF-1 target under concurrent user load; exact concurrency targets are architecture deliverable |
| PRIV-1 | No search queries, filter selections, or history persisted server-side; all stored in client-side cookies only |
