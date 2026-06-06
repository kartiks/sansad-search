# SansadSearch — PRD Summary

**PRD version:** 3.0  
**Date:** 2026-06-06

---

## Feature Index

| # | Feature | One-line description | Dependencies | NFR flags |
|---|---------|----------------------|--------------|-----------|
| F01 | Data Ingestion | Two-stage pipeline (fetch + process) ingesting CA/LS/RS records into PostgreSQL + Meilisearch; includes adjacent speech merging and lok_sabha_number extraction | None | Rate limiting, storage, processing time, resumability |
| F02 | Full-text Search | Keyword search across full_text_en, subject, speaker_name, minister_name, ministry with expansion-weighted ranking | F01, F04 | Response time (PERF-1), scalability |
| F03 | Search Filters | Five filter dimensions (body, date, speaker, session, proceeding type); combinable; state persists across query refinements | F01, F02 | None beyond PERF-1 |
| F04 | Query Expansion | Synonym dictionary + edit-distance spell correction; expanded terms at reduced weight; static dictionary file | F02 | None beyond PERF-1 |
| F05 | Result Display | Speech and Q+A result cards with metadata, 400-word snippet, language badge, and source link | F01, F02 | None beyond PERF-1 |
| F06 | Sorting | Relevance (default), chronological, reverse-chronological sort; persists across query refinements | F01, F02 | None beyond PERF-1 |
| F07 | Indexing Status Panel | Pre-computed summary of index state (counts, date coverage, last run) on homepage strip and full panel | F01 | None |
| F08 | Search History | Cookie-based recent searches (auto, 10 entries) and saved searches (explicit, 20 entries) with filter state | F02, F03 | Privacy (PRIV-1) |
| F09 | Detail Page | Full-record page at /record/:id with all metadata, full text, and inline adjacent speech loading (5 at a time) | F01, F02 | Performance (PERF-2) |
| F10 | Debug Mode | ?debug=1 activates per-result debug panels (scoring, index doc, PostgreSQL record, raw doc) and global search trace | F01, F02 | Security (SEC-1), PERF-3 exemption |

---

## Cross-Feature Interaction Map

| Feature A | Feature B | Interaction |
|-----------|-----------|-------------|
| F01 | F02 | F02 searches the Meilisearch index populated by F01; all metadata fields indexed by F01 are searchable via F02 |
| F01 | F05 | F05 result cards display fields (lok_sabha_number, segments, source_url) written by F01 at ingest |
| F01 | F07 | F07 reads the per-source count and date-coverage summary written by F01 at the end of each ingestion run |
| F01 | F09 | F09 detail page fetches the full record (including lok_sabha_number, segments) produced by F01 |
| F01 | F10 | F10 debug endpoints expose F01's PostgreSQL rows (speeches/qa_exchanges) and raw_documents rows |
| F02 | F03 | F03 filters are applied as constraints on the F02 search query; all active filters AND together with the query |
| F02 | F04 | F04 synonym and spell-correction expansions are consumed by F02 as reduced-weight OR alternatives |
| F02 | F06 | F06 relevance sort uses the ranking score computed by F02; date sorts use fields from F01 |
| F02 | F08 | F08 re-runs a saved search by passing the stored query and filter state to F02 |
| F02 | F10 | F10 adds a debug parameter to the F02 search request; F02 must return scoring details and a debug envelope when debug mode is active |
| F05 | F09 | F05 result cards link to F09 detail pages via /record/:id |
| F09 | F10 | F10 per-result debug panel is shown on the results page (F05 context), not on the F09 detail page; F10 lazy endpoints fetch PostgreSQL data that F09 also reads for the detail view |

---

## Active NFR Summary

| ID | Category | Requirement |
|----|----------|-------------|
| PERF-1 | Performance | Search results ≤2s at p95 from query submission to result list rendered; applies with query expansion active |
| PERF-2 | Performance | Detail page full load (initial record fetch only) ≤500ms at p95 |
| PERF-3 | Performance | PERF-1 and PERF-2 SLAs do not apply in debug mode (?debug=1) |
| INF-R1 | Reliability | Ingestion resumable from per-document checkpoint; re-run produces identical record count, no duplicates |
| SEC-1 | Security | Debug mode exposes full DB records and internal query details via unauthenticated endpoints — deliberate v1 choice; must be reviewed before production use with sensitive data |
| INF-S1 | Storage | Full-text corpus is large; storage architecture must be sized before build |
| INF-RL1 | Compliance | Ingestion must comply with robots.txt on all source sites; HTTP 429 → exponential backoff + retry |
| INF-P1 | Processing | Bulk ingestion is long-running; no time constraint but real-time progress logging required |
| SCALE-1 | Scalability | Search within PERF-1 under concurrent load; concurrency targets set at architecture stage |
| PRIV-1 | Privacy | No server-side storage of queries, filter selections, or search history; all client-side cookies only |
