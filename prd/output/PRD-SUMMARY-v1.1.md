# PRD Summary — v1.1
Date: 2026-05-29

---

## Feature Index

| # | Feature | One-line description | Depends on | NFR flags |
|---|---------|----------------------|------------|-----------|
| F01 | Data Ingestion | Bulk pipeline fetches, parses, and indexes CA/LS/RS records into the search index | — | Yes: rate limiting, storage, processing time, resumability, OCR |
| F02 | Full-text Search | Keyword search with query expansion across all indexed records; returns ranked results | F01, F04 | Yes: response time (≤2s p95), scalability |
| F03 | Search Filters | Five filter dimensions (body, date, speaker, session, proceeding type) combinable with search | F01, F02 | No |
| F04 | Query Expansion | Synonym and spell-correction dictionary augments queries before search execution | F02 | No |
| F05 | Result Display | Paginated result cards with metadata, highlighted snippet, and source link | F01, F02 | No |
| F06 | Sorting | Three sort options (relevance, chronological, reverse-chronological); default relevance | F01, F02 | No |
| F07 | Indexing Status Panel | Two-surface display of index state: condensed homepage strip and detailed full panel via footer link | F01 | No |
| F08 | Search History | Cookie-based recent searches (auto-recorded, max 10) and saved searches (explicit, max 20) | F02, F03 | Yes: privacy (client-side only) |

---

## Cross-Feature Interaction Map

| Features | Interaction |
|----------|-------------|
| F01 → F02 | F02 search executes against the corpus F01 indexed; F01 field structure determines which fields F02 searches |
| F01 → F07 | F01 writes the pre-computed summary record that F07 reads for counts, date coverage, and last-updated timestamp |
| F02 → F03 | F03 filter constraints are ANDed with the F02 query at search execution time |
| F02 → F05 | F02 provides ranked results and match position data that F05 uses for snippet extraction and highlighting |
| F02 → F06 | F06 relevance sort uses the relevance score F02 produces; F02 scoring model governs expansion-based rank ordering |
| F02 → F08 | F08 recent searches re-execute via F02; F08 saved searches restore query text that F02 accepts |
| F03 → F08 | F08 saved searches store and restore the filter state model that F03 defines |
| F04 → F02 | F04 synonym and spell-correction expansions are consumed by F02's search execution model as OR alternatives at reduced weight |

---

## Active NFR Summary

| ID | Requirement |
|----|-------------|
| PERF-1 | Search results returned ≤2s at p95, query submission to full result list rendered, with query expansion active |
| INF-R1 | Ingestion pipeline resumable from per-document checkpoint; interrupted run produces identical final record count, no duplicates |
| INF-S1 | Storage architecture sized for full-text corpus (CA full record + 12 years LS/RS) before build begins |
| INF-RL1 | Ingestion complies with robots.txt on sansad.in and rajyasabha.gov.in; HTTP 429 triggers exponential backoff and retry |
| INF-P1 | Bulk ingestion requires no human supervision; real-time progress logging required |
| INF-P2 | OCR component required for scanned CA PDFs; low-confidence records flagged, not dropped |
| SCALE-1 | Search remains within PERF-1 target under concurrent user load; exact concurrency targets are architecture-stage deliverable |
| PRIV-1 | No server-side persistence of search queries, filter selections, or search history; all stored client-side in cookies only |
