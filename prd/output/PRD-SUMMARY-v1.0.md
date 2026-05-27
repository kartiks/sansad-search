# SansadSearch — PRD Summary

**PRD version:** v1.0  
**Date:** 2026-05-28  

---

## Feature Index

| # | Feature | One-line description | Dependencies | NFR flags |
|---|---------|----------------------|--------------|-----------|
| F01 | Data Ingestion | Scrape, parse, segment, and index CA/LS/RS records as speech and Q+A units; one-time bulk load; resumable | None | Rate limiting, storage, processing time, OCR, resumability |
| F02 | Full-text Search | Keyword search across indexed corpus with weighted query expansion and field-boosted relevance ranking | F01, F04 | Response time (≤2s p95), scalability |
| F03 | Search Filters | Narrow results by legislative body, date range, speaker (text match), session (text match), and proceeding type | F01, F02 | None beyond F02 |
| F04 | Query Expansion | Synonym dictionary and spell correction; expanded terms are OR alternatives with reduced relevance weights | F02 | None beyond F02 |
| F05 | Result Display | Per-result card with metadata, highlighted snippet, translation indicator, and source link; 20-per-page pagination | F01, F02 | None beyond F02 |
| F06 | Sorting | Sort results by relevance (default), chronological, or reverse chronological; sort persists across refinements | F01, F02 | None beyond F02 |
| F07 | Indexing Status Panel | Read-only display of indexed record counts per source, date coverage, and last ingestion timestamp | F01 | None |
| F08 | Search History | Cookie-only recent searches (10, no filter state) and saved searches (20, with filter state); no authentication | F02, F03 | Privacy (client-side only) |

---

## Cross-Feature Interaction Map

| Feature A | Feature B | Interaction |
|-----------|-----------|-------------|
| F01 | F02 | F02 queries the corpus produced and indexed by F01; canonical fields (speaker_name, session_name) from F01 are search targets in F02 |
| F01 | F03 | F03 speaker and session filters depend on F01's canonicalized speaker_name and session_name fields being consistent across records |
| F01 | F05 | F05 result cards read all metadata fields written by F01; sequence_within_sitting and source_url are required |
| F01 | F06 | F06 date-based sort uses F01's date and sequence_within_sitting fields as primary and secondary sort keys |
| F01 | F07 | F07 reads the summary record written by F01's ingestion pipeline at run completion |
| F02 | F03 | F03 filter constraints are applied inside F02's search execution; filter state persists across F02 query refinements |
| F02 | F04 | F04 provides the synonym and spell-correction expansion that F02 applies to every query; F02 degrades to exact-match without F04 |
| F02 | F05 | F02 provides ranked results and match position data that F05 uses for snippet extraction and term highlighting |
| F02 | F06 | F06 relevance sort uses the relevance score computed by F02; changing sort does not re-execute the search |
| F02 | F08 | F08 re-runs saved and recent searches by submitting stored query text back through F02's search execution |
| F03 | F08 | F08 saved searches store and restore F03 filter state; recent searches do not store filter state |
| F04 | F02 | See F02↔F04 above |

---

## Active NFR Summary

| ID | Category | Requirement |
|----|----------|-------------|
| PERF-1 | Performance | Search response ≤2 seconds at p95 across full corpus, with query expansion active |
| INF-R1 | Reliability | Ingestion pipeline resumable from per-document checkpoint; re-runs produce identical count, no duplicates |
| INF-S1 | Storage | Corpus storage (CA full + 12 years LS/RS) must be sized at architecture stage |
| INF-RL1 | Compliance | robots.txt compliance on sansad.in and rajyasabha.gov.in; HTTP 429 triggers backoff, not skip |
| INF-P1 | Processing | Bulk ingestion requires real-time progress logging; no human supervision needed during run |
| INF-P2 | Processing | OCR required for scanned CA PDFs; low-confidence records flagged, not dropped |
| SCALE-1 | Scalability | PERF-1 target must hold under concurrent user load; concurrency targets set at architecture stage |
| PRIV-1 | Privacy | No server-side persistence of search queries, filters, or history; all stored client-side in cookies only |
