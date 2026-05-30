# Arch Review — Phase 3 Run 2
Date: 2026-05-28
PRD version: v1.0
Prior run: run-1 GAPS FOUND — 1 Major (400/503 error responses wrapped in FastAPI {"detail":...} instead of bare top-level objects per DATA-MODELS.md 3.1), 1 Minor (snippet key present-but-null instead of absent for null full_text_en)

## Status: CLEAR

## Gaps

No gaps found.

Severity:
- Critical: non-negotiable violated; must fix before next phase
- Major: significant pattern deviation; should fix before next phase
- Minor: small inconsistency; does not block next phase. Deferred to Coding Agent's judgment — fix opportunistically during the next build session for this area of the codebase.

## Escalations

None.

## Verified

**Run-1 gaps confirmed resolved:**

- **[was Major] Error response envelope** (`app/api/routes/search.py`): `HTTPException` replaced with `return JSONResponse(status_code=N, content=<error_dict>)` for both 400 validation errors and 503 backend errors. Error objects now appear at top level per DATA-MODELS.md 3.1. All validation error tests updated to assert `body["error"]` and `body["code"]` directly (not via `body["detail"]`). 503 test updated to assert `body["error"] == "search_unavailable"`. ✓
- **[was Minor] Snippet key omission** (`app/api/services/search.py`): `format_result()` now uses a conditional `if full_text:` block to add `snippet` and `snippet_from_supplementary` only when `full_text_en` is present. Keys are absent (not null) when `full_text_en` is null. New tests `test_null_full_text_omits_snippet_key` and `test_present_full_text_includes_snippet_key` confirm both branches. ✓

**All previously verified constraints remain intact:**

- **Non-Negotiable 1** — PostgreSQL as primary record store: search route touches no PostgreSQL; status route reads `index_status` table exclusively. ✓
- **Non-Negotiable 2** — Meilisearch Cloud as search engine: `execute_search()` calls Meilisearch `parliamentary_records` index exclusively. ✓
- **Non-Negotiable 3** — Query expansion server-side only: `query_expander.py` remains the sole location for stop-word stripping, phrase synonym detection, and term synonym lookup. ✓
- **Non-Negotiable 4** — `data/synonyms.json` sole synonym source: `query_expander.py` reads `app/data/synonyms.json` only. No synonym definitions in code. ✓
- **Non-Negotiable 5** — `index_status` table sole data source for F07: status route unchanged; reads only from PostgreSQL `index_status`. ✓
- **Non-Negotiable 7** — No ingestion endpoint: only `POST /api/search` and `GET /api/status` registered; no `/api/ingest`. ✓
- **Storage abstraction**: no direct `asyncpg` or `meilisearch` SDK imports outside `lib/`. ✓
- **Meilisearch search-only key**: `meilisearch_client.py` uses `MEILISEARCH_SEARCH_KEY`; master key not present in API layer. ✓
- **Folder structure**: all Phase 3 files in correct locations per ARCHITECTURE.md section 3. ✓
- **Key Data Flows**: search and status flows match ARCHITECTURE.md section 4. ✓
- **Separation of concerns**: route → service → lib layering maintained; no cross-layer import violations. ✓
- **API request schema**: `SearchRequest` / `FilterInput` match DATA-MODELS.md 3.1 exactly. ✓
- **API 200 response schema**: all documented top-level and per-result fields present and correctly typed. ✓
- **Status endpoint response shapes**: all three shapes (populated, never-run, unavailable) correct; unavailable returns HTTP 200. ✓
- **Sort secondary key**: `sequence_within_sitting` present in both chronological and reverse_chronological sort params. ✓
- **Filter expression patterns**: all six filter types built correctly and joined with AND per DATA-MODELS.md 2.4. ✓
- **`total_display` formatting**: `"10,000+"` at ≥ 10000; comma-formatted otherwise. ✓
- **Query stop-word stripping and synonym expansion**: quoted phrases preserved; consumed-token mechanism prevents double-expansion. ✓
