# Feature 10: Debug Mode

## Description

Debug mode is a developer and diagnostic facility that exposes internal search scoring, index data, and database records for each search result. It is activated via a URL parameter and requires no authentication. When active, each result card shows an expandable debug panel, and a global search debug panel appears at the top of the results list.

## Activation

Debug mode is activated by appending `?debug=1` to any search results URL. It applies for the duration of that page view. Removing the parameter deactivates debug mode.

## User Flows

**Activating debug mode:**
1. User appends `?debug=1` to a search results URL (or constructs a URL with the parameter)
2. Page loads in debug mode: a global debug panel appears above the results; each result card shows a "Debug" toggle

**Inspecting a result:**
1. User clicks the "Debug" toggle on a result card
2. The debug panel expands, showing 4 collapsible sections (all collapsed by default):
   - Scoring details
   - Document in index
   - Processed record
   - Raw document
3. User expands a section by clicking its header
4. Scoring details and Document in index render immediately (data loaded with search response)
5. Processed record and Raw document each trigger a network request on first expand; data renders when the request returns
6. Sections can be independently collapsed and re-expanded; subsequent expands of Processed record or Raw document use the previously fetched data (no re-fetch)

**Inspecting overall search behavior:**
1. User clicks to expand a section in the global search debug panel
2. Content renders from data captured at search time (no additional requests)

## Per-Result Debug Panel

When debug mode is active, each result card displays a "Debug" toggle. Expanding it reveals four collapsible sections:

### 1. Scoring details

Meilisearch ranking score data for this result, included in the search response when debug mode is active:
- `_rankingScore`: the overall relevance score (0.0–1.0)
- `_rankingScoreDetails`: per-rule breakdown (words, typo, proximity, attribute, exactness, and any custom ranking rules configured)
- All score fields returned by Meilisearch for this document are shown; the set of fields depends on the configured ranking rules

### 2. Document in index

The full Meilisearch document for this result as stored in the search index, included in the search response when debug mode is active. Displays every field present in the index document.

### 3. Processed record

The full row from `speeches` or `qa_exchanges` in PostgreSQL corresponding to this result. Fetched lazily from `GET /api/debug/processed/{id}` on first expand of this section. Displays every column in the row, including `segments` (JSONB).

### 4. Raw document

The full row from `raw_documents` in PostgreSQL from which this record was processed. Fetched lazily from `GET /api/debug/raw/{id}` on first expand of this section. Displays every column in the row, including the full extracted text content.

## Global Search Debug Panel

Shown above the result list when debug mode is active. Contains five collapsible sections (all collapsed by default):

### 1. Processed query

The query as transformed by the search service before submission to Meilisearch: after synonym expansion, stopword filtering, and any other query transformations applied. Sourced from the debug envelope in the API response.

### 2. API request

The exact HTTP request sent from the frontend to the backend search API: method, URL, query parameters, and request body (if any).

### 3. API response

The full HTTP response from the backend search API: status code, response headers, and response body. The body includes the debug envelope alongside the normal result payload.

### 4. Meilisearch request

The exact HTTP request sent from the backend to Meilisearch: method, URL, and request body as captured by the backend. Sourced from the debug envelope in the API response.

### 5. Meilisearch response

The full HTTP response body received from Meilisearch by the backend. Sourced from the debug envelope in the API response.

## Backend Requirements

When `debug=true` (or `debug=1`) is present as a query parameter on the search endpoint:
- Include `_rankingScore` and `_rankingScoreDetails` in each Meilisearch search hit
- Include the full document fields in each Meilisearch search hit (no field masking)
- Include a debug envelope in the API response containing: the processed/expanded query string, the Meilisearch request (method + URL + body), and the full Meilisearch response body

New lazy-fetch endpoints (no authentication required):
- `GET /api/debug/processed/{id}` — returns the full PostgreSQL row from `speeches` or `qa_exchanges` for the given `id`; returns 404 if not found
- `GET /api/debug/raw/{id}` — returns the full PostgreSQL row from `raw_documents` corresponding to the record with the given `id`; returns 404 if no raw document is linked to this record

## Acceptance Criteria

- Appending `?debug=1` to a search results URL activates debug mode; removing the parameter returns to normal mode
- In debug mode, every result card shows a "Debug" toggle; no debug toggle appears when debug mode is inactive
- The global search debug panel is visible above the result list in debug mode; it is not rendered when debug mode is inactive
- Scoring details and Document in index sections render without additional network requests (data is in the initial search response)
- Processed record section triggers exactly one `GET /api/debug/processed/{id}` request on first expand; subsequent expands of the same section produce no additional requests
- Raw document section triggers exactly one `GET /api/debug/raw/{id}` request on first expand; subsequent expands produce no additional requests
- Processed record and Raw document sections are independent: expanding one does not fetch the other
- All 4 per-result sections and all 5 global sections are individually collapsible and expandable
- `GET /api/debug/processed/{id}` returns 404 for an unknown id; the UI shows an error message in that section rather than leaving it blank or crashing
- `GET /api/debug/raw/{id}` returns 404 if no raw document is linked; the UI shows an error message in that section
- No calls to `/api/debug/*` endpoints occur when debug mode is inactive

## Edge Cases

- Result with no `_rankingScoreDetails` returned by Meilisearch (e.g., Meilisearch version does not support it): Scoring details section shows whatever score fields are present; section is not hidden
- Result whose raw document has been deleted from `raw_documents` after processing: `GET /api/debug/raw/{id}` returns 404; the Raw document section displays an appropriate message ("Raw document not available")
- Very large raw document (full HTML of a parliamentary session): the Raw document section renders the full content; no truncation; the user scrolls within the section

## Dependencies

- Feature 01: `speeches`, `qa_exchanges`, and `raw_documents` tables; the link between a processed record and its raw document
- Feature 02: search endpoint must support the `debug` parameter and produce the debug envelope

## NFR Implications

- **Security:** Debug mode exposes internal data (full database records, raw source documents, internal query details) via unauthenticated endpoints; see `04-non-functional-requirements.md` SEC-1
- **Performance:** PERF-1 and PERF-2 response time targets do not apply in debug mode; see PERF-3
