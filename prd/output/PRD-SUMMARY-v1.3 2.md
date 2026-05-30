# SansadSearch — PRD Summary

**Version:** 1.3
**Date:** 2026-05-30

---

## Feature Index

| # | Feature | One-line description | Dependencies | NFR flags |
|---|---------|----------------------|--------------|-----------|
| F01 | Data Ingestion | One-time bulk pipeline fetching CA (constitutionofindia.net HTML), LS (eparlib.sansad.in + IA _djvu.txt fallback), and RS (sansad.in/rs + IA + rsdebate.nic.in) records into the search index | none | rate limiting, storage, processing time, resumability |
| F02 | Full-text Search | Keyword search with query expansion (synonyms + spell correction) and multi-field relevance ranking | F01, F04 | response time (≤2s p95), scalability |
| F03 | Search Filters | Five combinable filter dimensions: legislative body, date range, speaker, session, proceeding type | F01, F02 | none (inherits F02) |
| F04 | Query Expansion | Static parliamentary synonym dictionary and edit-distance spell correction applied before search execution | F02 | none (inherits F02) |
| F05 | Result Display | Paginated result cards with metadata, highlighted snippet, and source link; two card types (speech, Q+A) | F01, F02 | none (inherits F02) |
| F06 | Sorting | Three sort options on results page: relevance (default), chronological, reverse chronological | F01, F02 | none (inherits F02) |
| F07 | Indexing Status Panel | Read-only panel showing per-source record counts, date coverage, and last ingestion date; two surfaces (homepage strip + full panel via footer link) | F01 | none |
| F08 | Search History | Cookie-based recent searches (auto, 10 max, 30-day TTL) and saved searches (explicit, 20 max, persistent) with no server-side storage | F02, F03 | privacy |

---

## Cross-Feature Interaction Map

| Features | Interaction |
|----------|-------------|
| F01 → F02 | F02 search executes against the indexed corpus produced by F01; corpus must exist before search can return results |
| F01 → F07 | F01 writes a summary record at ingestion end; F07 reads that summary record (never queries the index directly) |
| F02 ↔ F03 | F03 filter constraints are ANDed with the F02 query at search execution; filter state persists across F02 query refinements |
| F02 ↔ F04 | F04 synonym and spell-correction expansions are consumed by F02 as OR alternatives with reduced relevance weights |
| F02 → F05 | F02 provides ranked results and match position data that F05 uses for snippet extraction and term highlighting |
| F02 → F06 | F06 relevance sort uses the F02 relevance score; date-based sorts are independent of F02 scoring |
| F02 → F08 | F08 re-executes stored queries through the F02 search interface; recent searches use default filters, saved searches restore stored filter state |
| F03 → F08 | F08 saved searches store and restore F03 filter state; re-running a saved search reapplies the exact filter selections captured at save time |

---

## Active NFR Summary

| ID | Category | Requirement |
|----|----------|-------------|
| PERF-1 | Performance | Search response ≤2s at p95 across full indexed corpus with query expansion active |
| INF-R1 | Reliability | Ingestion resumable from per-document checkpoint; re-run produces identical record count with no duplicates |
| INF-S1 | Storage | Full-text corpus storage must be sized at architecture stage |
| INF-RL1 | Rate limiting | robots.txt compliance on constitutionofindia.net, eparlib.sansad.in, sansad.in, rsdebate.nic.in, and Internet Archive; 429 → exponential backoff + retry |
| INF-P1 | Processing | Bulk ingestion requires real-time progress logging; no human supervision required |
| SCALE-1 | Scalability | Search remains within PERF-1 target under concurrent load; concurrency targets set at architecture stage |
| PRIV-1 | Privacy | Search queries and history stored client-side in cookies only; nothing persisted server-side |
