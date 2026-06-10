# SansadSearch — PRD Summary

**PRD version:** 3.1  
**Date:** 2026-06-09

---

## Feature Index

| # | Feature | One-line description | Dependencies | NFR flags |
|---|---------|---------------------|--------------|-----------|
| F01 | Data Ingestion | Two-stage pipeline fetching, parsing, and indexing CA/LS/RS parliamentary records with resumable checkpointing | — | Rate limiting, storage, processing time, resumability |
| F02 | Full-text Search | Keyword search with BM25 ranking and query expansion across all indexed records | F01, F04 | Response time (PERF-1), scalability |
| F03 | Search Filters | Six combinable filter dimensions: body, date range, speaker, session, subject, proceeding type | F01, F02 | None beyond PERF-1 |
| F04 | Query Expansion | Curly quote normalization, parliamentary synonym dictionary, and edit-distance spell correction | F02 | None beyond PERF-1 |
| F05 | Result Display | Result cards with ≥200-word snippets, metadata, language badges, and source links; 20-per-page pagination | F01, F02 | None beyond PERF-1 |
| F06 | Sorting | Three sort modes: relevance (default), chronological, reverse chronological | F01, F02 | None beyond PERF-1 |
| F07 | Indexing Status Panel | Read-only panel showing per-source record counts, date coverage, and last ingestion timestamp | F01 | None |
| F08 | Search History | Cookie-only recent searches (10, 30-day) and saved searches (20, persistent) with filter state capture | F02, F03 | Privacy (PRIV-1) |
| F09 | Detail Page | Full-record view at /record/:id with inline adjacent sitting navigation (load 5 prev/next) | F01, F02 | Performance (PERF-2) |
| F10 | Debug Mode | ?debug=1 activates per-result 4-section panel and global 5-section search trace with lazy DB fetches | F01, F02 | Security (SEC-1), PERF-3 exempt |

---

## Cross-Feature Interaction Map

| Features | Interaction |
|----------|-------------|
| F01 → F02 | F02 queries the Meilisearch index populated by F01; indexed field set and types must match search config |
| F01 → F03 | F03 filters on `speaker_name`, `session_name`, `subject`, `source`, `proceeding_type`, `date` — all written by F01 |
| F01 → F07 | F07 reads the per-source summary record written by F01 at ingestion completion |
| F01 → F09 | F09 reads `speeches`/`qa_exchanges` via Postgres; `sequence_within_sitting`, `lok_sabha_number`, `canonical_doc_id` are F01 outputs |
| F01 → F10 | F10 lazy-fetches full rows from `speeches`/`qa_exchanges` and `raw_documents` — all F01 outputs; `canonical_doc_id` links the two tables |
| F02 → F03 | F03 applies filter constraints as parameters to the F02 search execution; filter state and query are ANDed |
| F02 → F04 | F04 preprocesses and expands the query before F02 executes it; expansion results feed F02's OR/weight model |
| F02 → F05 | F05 renders ranked results and snippets derived from F02 search response including match position data |
| F02 → F06 | F06 controls the sort parameter passed to F02; relevance sort uses F02 scoring; date sorts use F01 fields |
| F02 → F08 | F08 stores query strings from F02 submissions; re-run reconstructs a F02 query call with stored parameters |
| F02 → F10 | F10 debug envelope is added to F02 API response when ?debug=1; F02 must pass the debug flag to Meilisearch |
| F03 → F08 | F08 saved searches capture F03 filter state; re-run restores that state before executing F02 |
| F05 → F09 | F09 detail page reuses F05 proceeding type label map; card click in F05 navigates to F09 route |

---

## Active NFR Summary

| ID | Requirement |
|----|-------------|
| PERF-1 | Search results rendered within 2 seconds at p95 across full corpus with query expansion active |
| PERF-2 | Detail page full load (record + adjacent fetch) within 500ms at p95 |
| PERF-3 | PERF-1 and PERF-2 exempt when ?debug=1 is active |
| INF-R1 | Ingestion must be resumable from per-document checkpoint; re-run produces identical record count with no duplicates |
| SEC-1 | Debug mode exposes unauthenticated DB/index access; review required before production use with sensitive data |
| INF-S1 | Storage architecture must be sized for full corpus before build; exact sizing is architecture-stage deliverable |
| INF-RL1 | Ingestion must comply with robots.txt on constitutionofindia.net, elibrary.sansad.in, and Internet Archive; 429 → exponential backoff |
| INF-P1 | Bulk ingestion has no max time constraint but requires real-time progress logging and must run unattended |
| SCALE-1 | Search must meet PERF-1 under concurrent load; concurrency targets are architecture-stage deliverable |
| PRIV-1 | No search queries, filter selections, or history stored server-side; all history is cookie-only client-side |
