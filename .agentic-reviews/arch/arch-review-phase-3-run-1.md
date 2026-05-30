# Arch Review — Phase 3 Run 1
Date: 2026-05-28
PRD version: v1.0
Prior run: first review

## Status: GAPS FOUND

## Gaps

| File | Issue | Severity | Non-Negotiable violated? |
|------|-------|----------|--------------------------| 
| `app/api/routes/search.py` | Error responses (400 and 503) are wrapped under FastAPI's `{"detail": ...}` envelope due to `raise HTTPException(status_code=N, detail=<error_dict>)`. DATA-MODELS.md 3.1 specifies bare top-level error objects: `{"error": "validation_error", "code": "...", "message": "..."}` and `{"error": "search_unavailable", "message": "..."}`. The frontend (Phase 4) will parse `response.error` and `response.code` per the spec — the actual shape `response.detail.error` / `response.detail.code` will silently break all error-code handling in the frontend. Fix: replace `raise HTTPException(...)` with `return JSONResponse(status_code=N, content=<error_dict>)` from `fastapi.responses`. | Major | No |
| `app/api/services/search.py` | `format_result()` always includes `"snippet": null` when `full_text_en` is null. PHASES.md Phase 3 spec states: "null full_text_en produces no snippet field (frontend handles display)." The key is present-but-null rather than absent. JavaScript consumers handle both equivalently, but the Phase 4 build is against the documented contract which specifies field absence. Fix: conditionally exclude `"snippet"` and `"snippet_from_supplementary"` when `full_text_en` is null, or accept the deviation if Phase 4 handles null safely. | Minor | No |

Severity:
- Critical: non-negotiable violated; must fix before next phase
- Major: significant pattern deviation; should fix before next phase
- Minor: small inconsistency; does not block next phase. Deferred to Coding Agent's judgment — fix opportunistically during the next build session for this area of the codebase.

## Escalations

None. All patterns are within documented architectural decisions.

## Verified

- **Non-Negotiable 1** — PostgreSQL as primary record store: status route reads exclusively from `index_status` PostgreSQL table; search route never touches PostgreSQL. ✓
- **Non-Negotiable 2** — Meilisearch Cloud as search engine: `execute_search()` calls Meilisearch `parliamentary_records` index exclusively. ✓
- **Non-Negotiable 3** — Query expansion server-side only: `query_expander.py` is the sole location for stop-word stripping, phrase synonym detection, and term synonym lookup. The route calls `expand_query()` before forwarding the clean query to Meilisearch. No synonym logic in the frontend. ✓
- **Non-Negotiable 4** — `data/synonyms.json` sole synonym source: `query_expander.py` reads `_DATA_DIR / "synonyms.json"` (resolves to `app/data/synonyms.json`). No synonym definitions embedded in code. ✓
- **Non-Negotiable 5** — `index_status` table sole data source for F07: `status.py` uses `SELECT * FROM index_status ORDER BY run_completed_at DESC LIMIT 1` with no Meilisearch call. Confirmed by `test_reads_from_db_not_meilisearch`. ✓
- **Non-Negotiable 7** — No ingestion endpoint: `POST /api/search` and `GET /api/status` are the only routes registered; no `/api/ingest` or equivalent. ✓
- **Storage abstraction**: `status.py` acquires a connection via `get_pool()` from `api.lib.db`; `search.py` uses `get_client()` from `api.lib.meilisearch_client`. No direct `asyncpg` or `meilisearch` SDK imports outside `lib/`. ✓
- **Meilisearch search-only key**: `meilisearch_client.py` initializes with `MEILISEARCH_SEARCH_KEY`. Master key never used in the API layer. ✓
- **Folder structure**: `routes/search.py`, `routes/status.py`, `services/query_expander.py`, `services/search.py` all placed in correct locations per ARCHITECTURE.md section 3. ✓
- **Key Data Flows**: Search request flow (route → query_expander → search service → Meilisearch → route) and Index status flow (route → asyncpg → index_status table → route) match documented paths in ARCHITECTURE.md section 4. ✓
- **Separation of concerns**: Route layer handles HTTP validation and error mapping; service layer handles business logic; lib layer handles infrastructure clients. Routes call services; services do not import from routes. ✓
- **API request schema** (DATA-MODELS.md 3.1): `SearchRequest` and `FilterInput` Pydantic models match documented field names, types, and defaults exactly. ✓
- **API 200 response schema** (DATA-MODELS.md 3.1): `execute_search()` returns all documented top-level fields (`total`, `total_display`, `page`, `total_pages`, `per_page`, `expansion_notice`, `results`). Each result includes all documented fields for both speech and Q+A record types. ✓
- **Status endpoint response shapes** (DATA-MODELS.md 3.2): All three shapes (populated, never-run, unavailable) implemented correctly. Never-run returns `status: "ok"` with zeros and null dates. Unavailable returns HTTP 200 (not 503). ✓
- **Sort secondary key**: Both `chronological` and `reverse_chronological` include `sequence_within_sitting` as secondary sort key per DATA-MODELS.md 2.5. ✓
- **Filter expression patterns** (DATA-MODELS.md 2.4): All six filter types (`source IN`, `proceeding_type IN`, `date >=`, `date <=`, `speaker_name CONTAINS`, `session_name CONTAINS`) built correctly and joined with AND. Speaker and session values quote-escaped before injection into filter string. ✓
- **`total_display` formatting**: Returns `"10,000+"` when `total >= 10000`, comma-formatted string otherwise, per DATA-MODELS.md 3.1. ✓
- **Query stop-word stripping**: Quoted phrases preserved verbatim; unquoted stop words removed; `only_stopwords` flag returned correctly for validation. ✓
- **Synonym phrase detection priority**: Phase 1 (phrase synonyms) runs before Phase 2 (single-term synonyms); consumed token positions prevent double-expansion. ✓
