# Architecture — SansadSearch

**PRD version:** v1.0
**Generated:** 2026-05-28

---

## 1. System Overview

SansadSearch is a two-subsystem application:

- **Ingestion pipeline** — local CLI that scrapes, parses, segments, canonicalizes, and indexes parliamentary records from three government sources. Writes canonical records to PostgreSQL (primary record store) and pushes a derived search index to Meilisearch Cloud.
- **Web application** — FastAPI backend + React SPA serving search, filtering, sorting, and result display. Read-only. No authentication.

The two subsystems share no runtime coupling. Ingestion runs offline on the operator's machine. The web application is a stateless read interface over the populated stores.

---

## 2. Tech Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| Backend API | Python 3.12 + FastAPI 0.111+ | Async-native; same language as ingestion pipeline |
| Frontend | React 18 + Vite 5 (SPA) | Static build deployed to Vercel |
| Primary record store | PostgreSQL 16 (Railway managed) | Canonical source of truth; enables SQL inspection and re-indexing without re-scraping |
| Search engine | Meilisearch Cloud | Derived index; eliminates search infrastructure ops |
| HTTP client (ingestion) | httpx (async) | Rate-limited fetching from government sites |
| HTML parsing | BeautifulSoup4 | LS/RS HTML record parsing |
| PDF text extraction | PyMuPDF (fitz) | Embedded text extraction; Tesseract fallback for scanned pages |
| OCR | Tesseract 5 + pytesseract | Scanned CA PDF volumes; ingestion-time only |
| PostgreSQL client | asyncpg (API) / psycopg2 (ingestion) | asyncpg for async API reads; psycopg2 for bulk ingestion writes |
| Meilisearch Python client | meilisearch-python | Document push, index configuration |
| Frontend routing | React Router v6 | Homepage ↔ Results page; query params encode search state |
| Cookie management | js-cookie | F08 recent/saved searches |
| API hosting | Railway | Managed Python deploy; same platform as PostgreSQL |
| Frontend hosting | Vercel | CDN-edge static file serving |

**PostgreSQL as primary store:** The ingestion pipeline is expensive (rate-limited scraping, OCR). Without a primary store, any Meilisearch schema change or index rebuild requires re-scraping. PostgreSQL enables re-indexing from local data and provides SQL-based inspection for debugging ingestion anomalies.

**Meilisearch as derived search index:** Handles full-text ranking, synonym expansion, typo tolerance, and multi-field boosting without custom scoring code. Managed hosting eliminates search infrastructure ops entirely.

**React SPA over SSR:** Two-page application with no SEO requirements. Static Vite build is the simplest deployment path.

---

## 3. Folder Structure

`/app/` is the project root for all application code. Package manifests and configuration files live inside `/app/`.

```
/app/
  api/
    main.py                      # FastAPI entry; CORS config, lifespan hooks
    routes/
      search.py                  # POST /api/search
      status.py                  # GET /api/status
    services/
      query_expander.py          # Query parsing, stop-word stripping, synonym lookup,
                                 # phrase synonym detection, expansion notice generation
      search.py                  # Meilisearch filter construction, result formatting,
                                 # snippet post-processing
    lib/
      meilisearch_client.py      # Shared Meilisearch async client (singleton, search key)
      db.py                      # asyncpg connection pool init and teardown

  ingest/
    main.py                      # CLI entry (--source ca|ls|rs|all, --date-override)
    sources/
      _http.py                   # Shared HTTP utility: USER_AGENT, RobotsChecker,
                                 # fetch_with_retry with 4xx/5xx/429 error handling per F01 spec
      ca.py                      # CA volume URL enumeration + fetcher
      ls.py                      # LS session/sitting URL enumeration + fetcher
      rs.py                      # RS session/sitting URL enumeration + fetcher
    parsers/
      html_parser.py             # BeautifulSoup4: HTML → raw record dicts
      pdf_parser.py              # PyMuPDF text extraction; Tesseract OCR fallback
    segmenters/
      speech.py                  # Raw text/markup → Speech unit dicts
      qa.py                      # Raw text/markup → Q+A exchange unit dicts
    canonical/
      names.py                   # Speaker name canonicalization against names_dict.csv
      sessions.py                # Session name canonicalization to canonical format
    checkpoints/
      store.py                   # SQLite-backed processed-URL log and dedup key store
    indexer.py                   # PostgreSQL writer + Meilisearch document pusher
                                 # + index_status table update on run completion
    setup_meilisearch.py         # One-time/deploy-time: push synonyms.json to
                                 # Meilisearch synonyms API; configure index settings

  ui/
    src/
      components/
        ResultCard.jsx           # Dispatches to SpeechCard or QACard by record_type
        SpeechCard.jsx
        QACard.jsx
        FilterChip.jsx
        Pagination.jsx
        SkeletonCard.jsx
        Toast.jsx
        AdvancedSearchModal.jsx
        RecentSearchesDropdown.jsx
        SavedSearchesPanel.jsx
      pages/
        Home.jsx
        Results.jsx
      hooks/
        useSearch.js             # POST /api/search call; loading/error state management
        useCookieHistory.js      # Recent searches read/write (F08)
        useSavedSearches.js      # Saved searches read/write (F08)
      lib/
        cookie.js                # Cookie read/write/delete helpers
        filterState.js           # Filter shape definition, defaults, validation helpers
        expansionNotice.js       # Parse expansion_notice array from API response
        constants.js             # Proceeding type labels, source labels
      main.jsx                   # SPA entry point; mounts React root; defines BrowserRouter
                                 # routes: / → Home, /search → Results, * → redirect /
      index.css                  # CSS custom properties (design tokens: colours, fonts,
                                 # shadows); global base styles (box-sizing, body, button)
    public/
    index.html
    package.json
    vite.config.js

  db/
    schema.sql                   # CREATE TABLE + index statements for speeches,
                                 # qa_exchanges, and index_status; run once against
                                 # Railway PostgreSQL before first ingestion

  data/
    synonyms.json                # Synonym dictionary — sole source for Meilisearch synonyms
                                 # API and FastAPI expansion notice generation
    names_dict.csv               # Canonical member names (ingestion only; not deployed)

  requirements.txt               # Python dependencies (API + ingestion)
  pyproject.toml                 # Python project config
```

`data/ingestion_checkpoints.db` (SQLite, created at runtime) — local to the operator's machine; in `.gitignore`.

---

## 4. Key Data Flows

The Coding Agent updates this table after any change to API routes or core lib files.

| Flow | Path |
|------|------|
| **Search request** | Browser → `POST /api/search` → `query_expander.py` (parse, strip stop words, synonym lookup, phrase detection) → `services/search.py` (build Meilisearch filter expression, call Meilisearch Cloud, format results and snippets) → Browser |
| **Index status (F07)** | Browser → `GET /api/status` → asyncpg query on `index_status` table (most recent row) → Browser |
| **Search history (F08)** | Browser ↔ Browser cookies only — no server involvement |
| **Bulk ingestion** | Operator CLI → source enumerator → httpx fetcher (rate-limited, robots.txt compliant) → HTML/PDF parser → Tesseract OCR (if no embedded text) → segmenter → canonicalizer → PostgreSQL writer → Meilisearch document pusher → `index_status` table updated on completion |
| **Re-indexing** | `SELECT * FROM speeches UNION ALL SELECT * FROM qa_exchanges` → `indexer.py` → Meilisearch Cloud (no re-scraping) |
| **Synonym deploy** | `data/synonyms.json` → `ingest/setup_meilisearch.py` → Meilisearch synonyms API |

---

## 5. Key Design Patterns

**Search-as-derived-view.** PostgreSQL is the authoritative record store. Meilisearch holds a derived, denormalized view optimized for search. Any discrepancy between the two is resolved by re-indexing from PostgreSQL — the scraping step is never repeated.

**Server-side query expansion.** All synonym lookup, phrase detection, stop-word stripping, and query preprocessing runs in `api/services/query_expander.py`. The frontend sends a raw query string; the API response includes an `expansion_notice` array listing the expanded terms shown in the UI. No synonym logic exists in the frontend.

**Single synonym source of truth.** `data/synonyms.json` is loaded by both `query_expander.py` (to generate the expansion notice) and `ingest/setup_meilisearch.py` (to configure Meilisearch's synonyms API). These two uses must always reference the same file. A synonym not in `synonyms.json` must not appear in either system.

**Meilisearch ranking approximation.** The PRD requires three-tier expansion weight (original term > synonym match > spell-corrected match). This is approximated using Meilisearch's built-in ranking rules:
- `exactness` rule — exact-token matches rank above synonym-expanded matches
- `typos` rule — typo-corrected matches rank below exact and synonym matches
- `words` rule — records matching more original query terms outrank records matching only expansions

No custom scoring functions are implemented. This approximation is acceptable for v1.

**Speaker and session substring filtering.** F03 requires case-insensitive substring match for the speaker and session filters. These use Meilisearch's `CONTAINS` filter operator (available in Meilisearch 1.6+) on the `speaker_name` and `session_name` filterable attributes. The application layer constructs the filter string: `speaker_name CONTAINS "Singh"`.

**Local checkpoint store (ingestion only).** A SQLite database (`data/ingestion_checkpoints.db`) on the operator's machine tracks processed source document URLs (for resumability) and inserted deduplication keys (for fast duplicate detection without querying PostgreSQL). This file is never deployed to production and is in `.gitignore`.

**Pre-computed index status.** The ingestion pipeline writes a row to the `index_status` PostgreSQL table on successful completion. The `GET /api/status` endpoint reads the most recent row. The status panel never issues a Meilisearch document count query at request time.

---

## 6. Integration Points

| Integration | Direction | Used by | Notes |
|-------------|-----------|---------|-------|
| Meilisearch Cloud | Read (search) | API (`meilisearch_client.py`) | Search-only API key used at runtime |
| Meilisearch Cloud | Write (index, settings) | Ingestion pipeline | Master key used for document push and index config; never exposed to API at runtime |
| PostgreSQL (Railway) | Read | API (`db.py`) | `index_status` table for F07 status endpoint only; records not served directly from Postgres |
| PostgreSQL (Railway) | Write | Ingestion pipeline | All speech and Q+A records; `index_status` on completion |
| sansad.in | Read (HTTP) | Ingestion sources | Rate-limited; robots.txt compliant; CA + LS records |
| rajyasabha.gov.in | Read (HTTP) | Ingestion sources | Rate-limited; robots.txt compliant; RS records |
| Google Fonts CDN | Read (HTTP) | Frontend (browser) | Merriweather and Inter; loaded at page render |
| Tesseract (local binary) | Subprocess | `pdf_parser.py` | OCR for scanned CA PDF pages; runs on operator's machine only |

---

## 7. Non-Negotiables

Decisions that must not be changed without explicit user approval. Changes to any of these require significant rework.

1. **PostgreSQL is the primary record store.** Meilisearch is a derived index. Re-indexing always reads from PostgreSQL; it never re-scrapes source websites.

2. **Meilisearch Cloud is the search engine.** No migration to another search backend (Elasticsearch, Typesense, PostgreSQL FTS) without explicit decision.

3. **Query expansion runs server-side only.** `api/services/query_expander.py` is the sole location for synonym lookup and query preprocessing. No synonym expansion logic in the frontend.

4. **`data/synonyms.json` is the sole source of synonym definitions.** A synonym not in this file must not be applied — not in Meilisearch configuration, not in application code. Updates to synonyms require re-running `setup_meilisearch.py` to sync Meilisearch.

5. **`index_status` PostgreSQL table is the sole data source for the F07 status panel.** The API never queries Meilisearch document counts at request time for status display.

6. **Cookie-only storage for F08.** Recent searches and saved searches are stored exclusively in browser cookies. No server-side user data. No user identifiers created or stored.

7. **Ingestion pipeline is local CLI only.** It is never triggered via the production API. There is no `/api/ingest` endpoint or equivalent.

8. **React SPA — no SSR.** The frontend is a static Vite build served from Vercel. No server-side rendering.
