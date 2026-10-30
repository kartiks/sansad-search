# Architecture — SansadSearch

**PRD version:** v3.3
**Generated:** 2026-05-28 (v1.0); updated 2026-05-29 (v1.1); updated 2026-05-30 (ingestion source integration redesign — multi-provider per corpus; reconciled to PRD v1.2: OCR removed pipeline-wide, direct DSpace PDF fallback is embedded-text-only); updated 2026-05-31 (reconciled to PRD v1.3: RS-via-IA canonical citation = rsdebate.nic.in derived from DSpace handle N, never eparlib_document_url; null on no-derivable-handle; dual-corpus InternetArchiveProvider ratified); updated 2026-06-01 (PRD v2.0: F09 record-detail page served from PostgreSQL — `GET /api/record/{id}` + adjacent navigation; F01 new fields `lang_original`/`time_of_day`/`word_count` + Q+A `sequence_within_sitting`; F05 `lang_original` badge + `time_of_day` in search results; CA field-level parsing rules); updated 2026-06-03 (§5 CA Date: document all three URL slug formats — DD-MMM-YYYY, DD-MMMM-YYYY, YYYY-MM-DD); updated 2026-06-03 (raw document store: new `raw_documents` PostgreSQL table; two-stage pipeline split via `--stage fetch|process|all`; dual-signal checkpoint — `raw_documents` PK = Stage 1 complete, SQLite `processed_documents` = Stage 2 complete); updated 2026-06-04 (§1/§3/§5/§6 stale `{identifier}_djvu.txt` URL construction references replaced with dynamic DjVuTXT URL discovery from IA metadata `files` array); updated 2026-06-04 (PRD v2.1: §3 main.py comment, §4 Stage 1 data flow, §5 Deferred Processing + Checkpoint store + Cross-source identity — `--date-from`/`--date-to` scope both stages; `raw_documents` PK corrected to composite `(canonical_doc_id, corpus)`; per-corpus dedup scope clarified); updated 2026-06-06 (PRD v3.0: **Non-Negotiable #9 reversed** — IA/archive.org URL is now the citation for LS and RS-via-IA/rsdebate; F01 adjacent speech merging + `lok_sabha_number`/`segments`/`canonical_doc_id` columns; F05 ≥400-word snippets; F09 inline adjacent loading replaces single Prev/Next nav — new `GET /api/record/{id}/adjacent`; F10 debug mode — new `api/routes/debug.py` + `api/services/debug.py`, search debug envelope, two lazy-fetch debug endpoints); updated 2026-06-09 (PRD v3.1: F05 `cropLength` reduced from 400 to 200 words); updated 2026-06-12 (ingestion checkpoint store moved from local SQLite to PostgreSQL — two new tables `processed_documents` + `ingestion_dedup_keys` on the same Railway instance as `raw_documents`/`speeches`/`qa_exchanges`; local `data/ingestion_checkpoints.db` eliminated; pipeline now deployable as a Railway Cron Job; Non-Negotiable #7 reworded — "CLI-only, never via the production API" (cloud Cron Job is still a CLI process, not an API route); **PRD F01 still names "the SQLite checkpoint store" (lines 115/120) — routed to `/spec` to make storage-agnostic; not a functional conflict**); updated 2026-06-22 (PRD v3.3: F02/F05 — configurable snippet size. `services/search.py` resolves an effective snippet size from a new optional `snippet_size` request field (clamp 20–1000; non-integer/non-numeric/missing → operator default `SNIPPET_DEFAULT_WORDS`, default 100), which drives a now-dynamic Meilisearch `cropLength` (was hardcoded 200; default lowered to 100); NFR PERF-4 bounds the parameter so PERF-1 holds at 1000. No new files, services, or non-negotiables; existing POST /api/search contract gains one optional field); updated 2026-06-22 (top-line PRD version header reconciled v3.1→v3.3 — body already carried the v3.3 changelog; closes Phase 18 arch review escalation 2)

---

## 1. System Overview

SansadSearch is a two-subsystem application:

- **Ingestion pipeline** — local CLI that runs a two-stage pipeline across three corpora (CA, LS, RS). **Stage 1 (fetch + parse):** discovers source documents via an ordered provider chain (government sites plus the Internet Archive mirror); URLs discovered at runtime from listing/browse pages, never hardcoded; writes extracted text and document-level metadata to `raw_documents` (PostgreSQL). **Stage 2 (segment + index):** reads from `raw_documents`, segments and canonicalizes records, writes to `speeches`/`qa_exchanges` (PostgreSQL), and pushes a derived search index to Meilisearch Cloud. Both stages are independently invokable.
- **Web application** — FastAPI backend + React SPA serving search, filtering, sorting, result display, a single-record detail view with inline adjacent loading (F09), and an unauthenticated debug mode (F10, `?debug=1`) exposing scoring, index, processed-record and raw-document diagnostics. Read-only. No authentication.

The two subsystems share no runtime coupling. Ingestion runs as a standalone CLI process — invoked either locally or as a scheduled Railway Cron Job in the same project — and shares no runtime state with the web application beyond the PostgreSQL stores it writes (all ingestion checkpoint state lives in PostgreSQL; there is no local checkpoint file). The web application is a stateless read interface over the populated stores.

---

## 2. Tech Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| Backend API | Python 3.12 + FastAPI 0.111+ | Async-native; same language as ingestion pipeline |
| Frontend | React 18 + Vite 5 (SPA) | Static build deployed to Vercel |
| Primary record store | PostgreSQL 16 (Railway managed) | Canonical source of truth; enables SQL inspection and re-indexing without re-scraping |
| Search engine | Meilisearch Cloud | Derived index; eliminates search infrastructure ops |
| HTTP client (ingestion) | httpx (async) | Rate-limited fetching from government sites, the Internet Archive, and DSpace repositories; also used for IA `advancedsearch.php` / `metadata` JSON (no IA SDK) |
| HTML parsing | BeautifulSoup4 | CA (constitutionofindia.net) and recent RS (sansad.in/rs) record parsing; also DSpace item-page parsing to resolve the real PDF bitstream URL |
| PDF text extraction | PyMuPDF (fitz) | **Embedded-text only** — direct DSpace PDFs (LS/RS) not present on the Internet Archive mirror. No OCR: a PDF with no text layer is logged and skipped per the F01 "unparseable document → skip" edge case (2014+ DSpace PDFs are digital-born) |
| Pre-OCR'd bulk text | Internet Archive (DjVuTXT file — URL discovered dynamically from IA metadata `files` array) | Preferred LS/RS path: OCR text already extracted by IA; the pipeline runs no OCR of its own; items with no DjVuTXT entry in the `files` array are logged and skipped |
| PostgreSQL client | asyncpg (API) / psycopg2 (ingestion) | asyncpg for async API reads; psycopg2 for bulk ingestion writes |
| Meilisearch Python client | meilisearch-python | Document push, index configuration |
| Frontend routing | React Router v6 | Homepage ↔ Results page; query params encode search state |
| Cookie management | js-cookie | F08 recent/saved searches |
| API hosting | Railway | Managed Python deploy; same platform as PostgreSQL |
| Ingestion hosting | Railway (Cron Job) | Standalone scheduled job in the same Railway project as the API and PostgreSQL; runs the pipeline to completion and exits. **Cron Job, not an always-on Worker** — a Worker restarts on process exit and would re-run the pipeline endlessly. All checkpoint state is in PostgreSQL, so the job is stateless between runs and resumable. May also be run locally as a plain CLI |
| Frontend hosting | Vercel | CDN-edge static file serving |

**PostgreSQL as primary store:** The ingestion pipeline is expensive (rate-limited scraping and parsing across multiple providers per corpus). Without a primary store, any Meilisearch schema change or index rebuild requires re-scraping. PostgreSQL enables re-indexing from local data and provides SQL-based inspection for debugging ingestion anomalies.

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
      search.py                  # POST /api/search (F10: ?debug=1 adds debug envelope)
      status.py                  # GET /api/status
      record.py                  # GET /api/record/{id} (F09 detail; 404 if not found) +
                                 # GET /api/record/{id}/adjacent (F09 inline range fetch)
      debug.py                   # F10: GET /api/debug/processed/{id} (full speeches/qa row;
                                 # 404 if not found) + GET /api/debug/raw/{id} (full
                                 # raw_documents row via record.canonical_doc_id+source;
                                 # 404 if no linked raw doc). No auth (NFR SEC-1)
    services/
      query_expander.py          # Query parsing, stop-word stripping, synonym lookup,
                                 # phrase synonym detection, expansion notice generation
      search.py                  # Meilisearch filter construction, result formatting,
                                 # snippet post-processing (F02/F05: resolves effective
                                 # snippet size from snippet_size param, clamp 20–1000,
                                 # default SNIPPET_DEFAULT_WORDS=100 → dynamic cropLength);
                                 # F10: when debug active, sets showRankingScore/
                                 # showRankingScoreDetails/attributesToRetrieve=["*"] and
                                 # assembles the debug envelope (processed_query +
                                 # Meilisearch request/response)
      record.py                  # F09: fetch one record by id (speeches UNION qa_exchanges),
                                 # sitting_total count, has_prev/has_next boundary flags,
                                 # and the adjacent range query (same sitting, by sequence,
                                 # direction + from_seq + limit); response formatting
      debug.py                   # F10: full-row fetch from speeches/qa_exchanges
                                 # (processed) and from raw_documents (raw, resolved via
                                 # the processed record's canonical_doc_id + source)
    lib/
      meilisearch_client.py      # Shared Meilisearch async client (singleton, search key)
      db.py                      # asyncpg connection pool init and teardown

  ingest/
    main.py                      # CLI entry: --source ca|ls|rs|all; --stage fetch|process|all
                             # (default all); both stages accept --date-from/--date-to:
                             # Stage 1 applies a post-parse date gate (write only in-window
                             # docs to raw_documents); Stage 2 reads only raw_documents rows
                             # within the window
    sources/
      _http.py                   # Shared HTTP utility: USER_AGENT, RobotsChecker,
                                 # fetch_with_retry with 4xx/5xx/429 error handling per F01 spec
      _discovery.py              # Shared discovery helpers: HTML listing crawl,
                                 # DSpace browse pagination, IA advancedsearch enumeration
      _provider.py               # Provider contract: discover() -> [DocumentRef];
                                 # fetch(DocumentRef) -> bytes|text. DocumentRef carries
                                 # corpus, provider, format (html|pdf|ia_text), fetch_url,
                                 # canonical_doc_id, citation_url, discovered metadata
      ca.py                      # CA corpus orchestrator — provider chain: [coi_html]
      ls.py                      # LS corpus orchestrator — provider chain:
                                 # [internet_archive, eparlib_dspace]; date filter >= 2014-01-01
      rs.py                      # RS corpus orchestrator — provider chain:
                                 # [sansad_rs_html, internet_archive, rsdebate_dspace];
                                 # date filter >= 2014-01-01
      providers/
        coi_html.py              # constitutionofindia.net (CA, primary & only): volume index
                                 # → per-volume → per-day discovery; HTML main-content fetch
        internet_archive.py      # archive.org (LS/RS, preferred bulk): advancedsearch enumerate
                                 # eparlib.nic.in.{N}; metadata JSON; DjVuTXT URL discovered
                                 # eparlib_* custom fields. Dual-corpus: single provider serves
                                 # both LS and RS via a `corpus` constructor param; also
                                 # extracts lok_sabha_number from eparlib_lok_sabha_number.
                                 # citation_url = the IA item URL
                                 # (archive.org/details/eparlib.nic.in.{N}) for BOTH LS and RS
                                 # (PRD v3.0 source_url reversal — Non-Negotiable #9);
                                 # null only when no IA identifier is derivable
        eparlib_dspace.py        # eparlib.sansad.in (LS, handle /7; IA-missing fallback):
                                 # DSpace browse + item-page bitstream URL resolution
                                 # (never constructs filenames)
        rsdebate_dspace.py       # rsdebate.nic.in (RS, fallback): DSpace browse
                                 # (?type=dateissued) + item-page bitstream URL resolution
                                 # (never constructs filenames)
        sansad_rs_html.py        # sansad.in/rs/debates/officials (RS, recent in-scope primary):
                                 # HTML listing crawl + parse
    parsers/
      html_parser.py             # BeautifulSoup4: HTML → raw record dicts (CA coi + RS sansad.in/rs)
      pdf_parser.py              # PyMuPDF embedded-text extraction for direct DSpace PDFs
                                 # (LS/RS) not on the IA mirror; no OCR — text-less PDFs
                                 # logged and skipped
      ia_text_parser.py          # Internet Archive DjVuTXT text (URL discovered from IA
                                 # metadata files array) + IA metadata JSON → raw record
                                 # dicts; no local OCR
    segmenters/
      speech.py                  # Raw text/markup → Speech unit dicts; applies F01 Adjacent
                                 # Speech Merging (consecutive same-speaker speeches in a
                                 # sitting with no break signal → one record with a `segments`
                                 # JSONB array, full_text_en = segments joined "\n\n",
                                 # word_count = combined, sequence = first segment's position)
      qa.py                      # Raw text/markup → Q+A exchange unit dicts (never merged);
                                 # minister_name from the response section, never question
                                 # preamble; fallback "Minister of [Ministry]" (PRD v3.0)
    canonical/
      names.py                   # Speaker name canonicalization against names_dict.csv
      sessions.py                # Session name canonicalization to canonical format
    checkpoints/
      store.py                   # PostgreSQL-backed Stage 2 checkpoint store (psycopg2, same
                                 # Railway instance as raw_documents/speeches/qa_exchanges; no
                                 # local file): processed-document log (processed_documents,
                                 # keyed on canonical_doc_id+corpus — DATA-MODELS §1.6) and the
                                 # record-level dedup-key mirror (ingestion_dedup_keys —
                                 # DATA-MODELS §1.7). The dedup mirror is a pre-filter only; the
                                 # authoritative duplicate guard is the speeches/qa_exchanges
                                 # UNIQUE(dedup_key) constraint via ON CONFLICT DO NOTHING
    indexer.py                   # PostgreSQL writer for both stages: Stage 1 writes
                                 # extracted text + metadata to raw_documents; Stage 2 writes
                                 # segmented records to speeches/qa_exchanges (incl. new v3.0
                                 # columns lok_sabha_number, segments, and canonical_doc_id =
                                 # the source raw_documents row's id, for F10 debug-raw) +
                                 # pushes to Meilisearch (lok_sabha_number/segments/
                                 # canonical_doc_id excluded from the document) + updates
                                 # index_status on run completion
    setup_meilisearch.py         # One-time/deploy-time: push synonyms.json to
                                 # Meilisearch synonyms API; configure index settings

  ui/
    src/
      components/
        ResultCard.jsx           # Dispatches to SpeechCard or QACard by record_type;
                                 # each card links to /record/:id; in debug mode renders a
                                 # ResultDebugPanel toggle below the card (F10)
        SpeechCard.jsx           # F05: renders lang_original badge + time_of_day row
        QACard.jsx               # F05: renders lang_original badge + time_of_day row
        FilterChip.jsx
        Pagination.jsx
        SkeletonCard.jsx
        Toast.jsx
        AdvancedSearchModal.jsx
        RecentSearchesDropdown.jsx
        SavedSearchesPanel.jsx
        ResultDebugPanel.jsx     # F10 per-result panel: 4 collapsible sections — Scoring
                                 # details + Document in index (from search response);
                                 # Processed record (lazy GET /api/debug/processed/{id});
                                 # Raw document (lazy GET /api/debug/raw/{id}); per-section
                                 # error message on 404/failure
        SearchDebugPanel.jsx     # F10 global panel above results: 5 collapsible sections —
                                 # Processed query, API request, API response, Meilisearch
                                 # request, Meilisearch response (from the response debug
                                 # envelope + the frontend's own captured request/response)
      pages/
        Home.jsx
        Results.jsx              # F10: reads ?debug=1; renders SearchDebugPanel + per-card
                                 # ResultDebugPanel; passes debug flag to useSearch
        IndexingStatusPage.jsx   # Full F07 indexing status panel (detailed: total +
                                 # per-source counts + per-source date coverage +
                                 # last-updated); reached via Results.jsx footer link
        RecordDetail.jsx         # F09 detail page (route /record/:id): full text + all
                                 # metadata (incl. lok_sabha_number "[N]th Lok Sabha" for LS);
                                 # inline adjacent loading — "Load 5 previous"/"Load 5 next"
                                 # controls prepend/append batches via useAdjacent, enabled
                                 # state from has_prev/has_next then has_more; URL unchanged;
                                 # back-nav = "Back to results" (in-app referrer via router
                                 # location state) | "Search" (direct URL)
      hooks/
        useSearch.js             # POST /api/search call; loading/error state management;
                                 # forwards debug flag (F10) and returns the debug envelope
        useRecord.js             # GET /api/record/{id} call (F09); loading/error/404 state
        useAdjacent.js           # F09: GET /api/record/{id}/adjacent calls (direction +
                                 # from_seq + limit); accumulates prepended/appended batches,
                                 # tracks per-direction has_more and in-flight/error state
        useDebugDetail.js        # F10: lazy GET /api/debug/processed/{id} and
                                 # GET /api/debug/raw/{id}; one fetch per section, cached
                                 # after first expand; 404/error state per section
        useCookieHistory.js      # Recent searches read/write (F08)
        useSavedSearches.js      # Saved searches read/write (F08)
      lib/
        cookie.js                # Cookie read/write/delete helpers
        filterState.js           # Filter shape definition, defaults, validation helpers
        expansionNotice.js       # Parse expansion_notice array from API response
        ordinal.js               # F09: integer → English ordinal ("17"→"17th","21"→"21st")
                                 # for lok_sabha_number display
        constants.js             # Proceeding type labels, source labels
      main.jsx                   # SPA entry point; mounts React root; defines BrowserRouter
                                 # routes: / → Home, /search → Results,
                                 # /index-status → IndexingStatusPage,
                                 # /record/:id → RecordDetail, * → redirect /
      index.css                  # CSS custom properties (design tokens: colours, fonts,
                                 # shadows); global base styles (box-sizing, body, button)
    public/
    index.html
    package.json
    vite.config.js

  db/
    schema.sql                   # CREATE TABLE + index statements for speeches,
                                 # qa_exchanges, raw_documents, index_status, and the two
                                 # ingestion checkpoint tables processed_documents +
                                 # ingestion_dedup_keys (DATA-MODELS §1.6/§1.7);
                                 # run once against Railway PostgreSQL before first ingestion

  data/
    synonyms.json                # Synonym dictionary — sole source for Meilisearch synonyms
                                 # API and FastAPI expansion notice generation
    names_dict.csv               # Canonical member names (ingestion only; not deployed)

  requirements.txt               # Python dependencies (API + ingestion)
  pyproject.toml                 # Python project config
```

The ingestion pipeline holds **no local checkpoint file**. All Stage 2 checkpoint state lives in PostgreSQL (`processed_documents`, `ingestion_dedup_keys` — DATA-MODELS §1.6/§1.7), co-located with the canonical record stores on the same Railway instance.

---

## 4. Key Data Flows

The Coding Agent updates this table after any change to API routes or core lib files.

| Flow | Path |
|------|------|
| **Search request** | Browser → `POST /api/search` → `query_expander.py` (parse, strip stop words, synonym lookup, phrase detection) → `services/search.py` (build Meilisearch filter expression, resolve the effective snippet size from the request `snippet_size` param — clamp 20–1000, else `SNIPPET_DEFAULT_WORDS` default 100 — set `attributesToCrop=["full_text_en"]`/`cropLength=<effective snippet size>` for F02/F05 snippets, call Meilisearch Cloud, format results and snippets) → Browser. **F10 debug:** when `?debug=1`, `search.py` also sets `showRankingScore`/`showRankingScoreDetails`/`attributesToRetrieve=["*"]`, captures the Meilisearch request + response, and returns a `debug` envelope (`processed_query` + Meilisearch request/response) alongside results |
| **Index status (F07)** | Browser → `GET /api/status` → asyncpg query on `index_status` table (most recent row) → Browser. Both F07 surfaces share this one flow: the homepage strip (`Home.jsx`, condensed — counts + last-updated) and the full panel (`IndexingStatusPage.jsx`, detailed — total + per-source counts + per-source date coverage + last-updated) render different subsets of the same response. No separate endpoint. |
| **Record detail (F09)** | Browser → `GET /api/record/{id}` → `services/record.py`: (1) asyncpg fetch by id — `speeches WHERE id` UNION ALL `qa_exchanges WHERE id`; 404 if neither matches. (2) same-sitting aggregate query (`source` + `date` + `sitting_number IS NOT DISTINCT FROM`, both tables unioned) → `sitting_total`, and `has_prev`/`has_next` (whether any record exists below/above the focal `sequence_within_sitting`) → Browser. **Detail is served from PostgreSQL, not Meilisearch** (the canonical store holds every display field, incl. `lok_sabha_number`, `session_number`, `has_untranslated_content`, `page_reference`, `word_count`). Search remains Meilisearch-only. |
| **Adjacent loading (F09)** | Browser (click "Load 5 previous/next") → `GET /api/record/{id}/adjacent?direction=&from_seq=&limit=5` → `services/record.py`: resolve the focal record's sitting from `id`, query both tables for up to `limit` records strictly below (`prev`) / above (`next`) `from_seq` ordered by `sequence_within_sitting` (served by `idx_*_sitting`), return them ascending + `has_more` → Browser prepends/appends inline (URL unchanged). PostgreSQL-only; exempt from PERF-2 (NFR PERF-2 clarification). |
| **Debug — processed record (F10)** | Browser (expand "Processed record") → `GET /api/debug/processed/{id}` → `services/debug.py`: asyncpg fetch full row `speeches WHERE id` then `qa_exchanges WHERE id`; 404 if neither → Browser. Returns every column incl. `segments`/`canonical_doc_id`. No auth (SEC-1); exempt from PERF (PERF-3). |
| **Debug — raw document (F10)** | Browser (expand "Raw document") → `GET /api/debug/raw/{id}` → `services/debug.py`: (1) fetch processed record by `id` → `canonical_doc_id` + `source`; (2) fetch `raw_documents WHERE canonical_doc_id=$1 AND corpus=$2` (composite PK); 404 if no processed record or no linked raw row → Browser. Full row incl. `extracted_text`. No auth (SEC-1); exempt from PERF (PERF-3). |
| **Search history (F08)** | Browser ↔ Browser cookies only — no server involvement |
| **Stage 1 ingestion (fetch + parse)** | Operator CLI (`--stage fetch`) → corpus orchestrator → provider chain `discover()` (HTML listing crawl / DSpace browse / IA `advancedsearch`; document-level dedup: `raw_documents` PK lookup on `(canonical_doc_id, corpus)` — if row exists, skip fetch) → httpx fetcher (rate-limited, robots.txt compliant) → parser by format: HTML (`html_parser`) / IA pre-OCR text (`ia_text_parser`) / PDF (`pdf_parser`, embedded-text only) → date-window gate: when `--date-from`/`--date-to` provided, write to `raw_documents` only if parsed date is within window; skip out-of-window docs → `indexer.py` writes extracted text + metadata to `raw_documents` (PostgreSQL) |
| **Stage 2 ingestion (segment + index)** | Operator CLI (`--stage process`) → reads `raw_documents` for scope (filtered by `--source`, optionally `--date-from`/`--date-to`) → segmenter → canonicalizer → `indexer.py` writes to `speeches`/`qa_exchanges` (PostgreSQL); a `processed_documents` row (PostgreSQL) is written + each new `dedup_key` mirrored into `ingestion_dedup_keys` (PostgreSQL) → Meilisearch document pusher → `index_status` table updated on completion |
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

**Listing-page-driven discovery.** Source document URLs are discovered at runtime by crawling listing/index pages — constitutionofindia.net volume index, DSpace browse-by-date (`?type=dateissued`), Internet Archive `advancedsearch.php` — never from a static, hardcoded URL list. Government and archive URL structures drift; static lists break (this redesign exists because hardcoded CA volume PDF URLs on sansad.in began returning 500). Every source provider obtains its document set from a listing/browse endpoint.

**Multi-provider corpus fallback.** Each corpus is served by an ordered provider chain; providers are tried in priority order per logical document, and the first yielding parseable content wins.
- **CA:** `[constitutionofindia.net (coi_html)]` — clean semantic HTML, one page per sitting, 167 sittings across 12 volumes (9 Dec 1946 → 24 Jan 1950); no OCR. (The eparlib.sansad.in handle `/4` "Constituent Assembly (Legislative)" collection is the *interim legislature* — a different body — and is **out of scope**; it is never ingested as CA.)
- **LS:** `[internet_archive, eparlib_dspace]` — IA pre-OCR text preferred; direct DSpace PDF only for items absent from the mirror.
- **RS:** `[sansad_rs_html, internet_archive, rsdebate_dspace]` — recent in-scope sessions via sansad.in/rs HTML; IA pre-OCR text next; rsdebate.nic.in DSpace PDF last.

**Cross-source document identity.** The DSpace handle number `N` is the canonical document identity for LS/RS. The Internet Archive identifier `eparlib.nic.in.{N}` maps to DSpace handle `123456789/{N}` — `N` is the cross-provider join key. The checkpoint store dedupes at the **document level** on this canonical id so a document available from more than one provider (within the same corpus) is fetched and parsed once; the record-level `dedup_key` (DATA-MODELS §1.5) remains the final guard against duplicate records. **Dedup is scoped per corpus** — the same `canonical_doc_id` may appear as both an LS row and an RS row in `raw_documents` (the composite PK `(canonical_doc_id, corpus)` allows this). A document fetched for LS does not suppress fetching the same handle N for RS.

**Internet Archive pre-OCR text path.** LS/RS bulk ingestion prefers the IA mirror. For each item, `internet_archive.py` fetches the IA metadata JSON and locates the entry with `"format" == "DjVuTXT"` in the top-level `files` array; the DjVuTXT URL is assembled from `server + dir + name` fields of that entry. Items where no DjVuTXT entry exists in the `files` array are logged and skipped — the URL is never constructed by guessing a filename pattern. The metadata JSON also carries `eparlib_*` fields (`eparlib_title`, `eparlib_date`, `eparlib_lok_sabha_number`, `eparlib_session_number`, `eparlib_document_url`). `ia_text_parser.py` consumes the text, maps the metadata, and extracts `lok_sabha_number` from `eparlib_lok_sabha_number` (LS only). The pipeline runs no OCR of its own. A **single `InternetArchiveProvider` serves both corpora** (dual-corpus, selected by a `corpus` constructor parameter); under PRD v3.0 the citation is the same for both:
- **LS and RS via IA:** `source_url` is set to the **Internet Archive item URL** (`https://archive.org/details/eparlib.nic.in.{N}`). This is the v3.0 reversal — `eparlib_document_url` (LS) and the derived `rsdebate.nic.in` URL (RS) are **no longer** used as the citation; the archive.org URL *is* the citation (Non-Negotiable #9). `source_url` is null only when no IA identifier is derivable.

Direct DSpace PDF (embedded-text extraction via PyMuPDF, no OCR) is the fallback for items absent from the mirror; a fallback PDF with no text layer is logged and skipped. For a fallback-path item genuinely absent from IA, no archive.org URL exists, so `source_url` is null per the v3.0 "null if no accessible URL can be derived" rule (see §8 build-time verification). Recent RS sourced from sansad.in HTML cites its sansad.in page URL.

**DSpace bitstream resolution.** DSpace PDF URLs (eparlib.sansad.in, rsdebate.nic.in) are always resolved by reading the real bitstream URL from the item page/metadata. Bitstream filenames are **never constructed** — the convention is inconsistent across years (e.g. `lsd_08_09_04-12-1987.pdf`, `lsd_10_V_01_12_1992.pdf`, `lsd_08_1_30-01-1985.pdf`).

**HTML-preferred parsing.** Where a corpus offers HTML (CA via coi; recent RS via sansad.in/rs), HTML is parsed in preference to PDF, consistent with the PRD HTML-over-PDF deduplication rule.

**Two-stage ingestion pipeline (deferred processing).** The ingestion pipeline is split into two independently invokable stages via `--stage fetch|process|all` (default `all`):
- **Stage 1 (fetch + parse):** Corpus orchestrators discover and fetch source documents, run format-specific parsers, and apply the date-window gate: when `--date-from`/`--date-to` are provided, only documents whose parsed date falls within the window are written to `raw_documents` (PostgreSQL); out-of-window documents are skipped after parsing. Once a row exists in `raw_documents` for a `(canonical_doc_id, corpus)` pair, Stage 1 will not re-fetch that document (composite PK dedup guard).
- **Stage 2 (segment + index):** Reads from `raw_documents` (optionally scoped by `--date-from`/`--date-to`), runs segmenters and canonicalizers, writes to `speeches`/`qa_exchanges`, and pushes to Meilisearch. The Stage 1 scraping cost is not paid again on a Stage 2 re-run.

Both stages accept `--date-from`/`--date-to` — Stage 1 applies the gate at write time; Stage 2 applies it at read time. When neither flag is provided, both stages operate on the full corpus without date restriction.

This decoupling serves two purposes: (1) segmentation logic and index schema can be iterated without re-scraping source websites; (2) Stage 2 can be selectively re-run over a date range without a full reindex. See DEPLOYMENT.md §6.4 for the selective re-processing runbook.

**Checkpoint store — dual signal (PostgreSQL).** The two-stage pipeline uses two independent checkpoint signals. **All checkpoint state lives in PostgreSQL** — on the same Railway instance as `raw_documents`/`speeches`/`qa_exchanges`. There is no local SQLite file; this is what makes the pipeline deployable as a stateless Railway Cron Job (§2 Tech Stack, DEPLOYMENT §3.7).
- **Stage 1 complete:** A row in the `raw_documents` PostgreSQL table keyed on `(canonical_doc_id, corpus)` (composite PK). Corpus orchestrators query this composite key before fetching — if a matching row exists for the same id and corpus, the document is skipped. No separate checkpoint entry is written for Stage 1 completion.
- **Stage 2 complete:** A row in the `processed_documents` PostgreSQL table (DATA-MODELS §1.6), keyed on `(canonical_doc_id, corpus)` — the same composite key as `raw_documents`. Written after all records from a raw document have been segmented, canonicalized, and written to `speeches`/`qa_exchanges`. Queried before processing each `raw_documents` row to guard against re-segmentation on Stage 2 resume.
- **Record-level guard:** The `ingestion_dedup_keys` PostgreSQL table (DATA-MODELS §1.7) mirrors the `UNIQUE(dedup_key)` constraint on `speeches`/`qa_exchanges`, giving Stage 2 a single cheap existence-check surface instead of UNION-ing the two large record tables. It is a **pre-filter only**: the authoritative duplicate guarantee is the `UNIQUE(dedup_key)` constraint enforced via `INSERT … ON CONFLICT (dedup_key) DO NOTHING`. The mirror may safely under-report (a missing entry just means the insert is attempted and `ON CONFLICT` resolves any collision); it must **never** over-report in a way that suppresses a legitimate insert — see the build invariant in §8 (item 7).

Both checkpoint tables are created by `schema.sql`, truncated by the full clean reindex (DEPLOYMENT §6.1), and backfillable from the canonical record tables (DEPLOYMENT §6.7 migration runbook) — they hold derived state, not source-of-truth data.

**Pre-computed index status.** The ingestion pipeline writes a row to the `index_status` PostgreSQL table on successful completion. The `GET /api/status` endpoint reads the most recent row. The status panel never issues a Meilisearch document count query at request time.

**Record detail + inline adjacent loading served from PostgreSQL (F09).** The detail page reads from PostgreSQL, not Meilisearch. PostgreSQL is the canonical store and already holds every field the detail page shows — including fields deliberately excluded from the Meilisearch document (`lok_sabha_number`, `segments`, `session_number`, `has_untranslated_content`, `page_reference`, `word_count`). `GET /api/record/{id}` fetches one record (`speeches` UNION ALL `qa_exchanges` by `id`) and reports `sitting_total` plus `has_prev`/`has_next` boundary flags. **Inline adjacent loading** (PRD v3.0, replacing single Prev/Next navigation) is served by a separate `GET /api/record/{id}/adjacent` range endpoint: given a `direction` and an exclusive `from_seq`, it returns up to 5 same-sitting records beyond that position (ordered by the shared `sequence_within_sitting`) plus `has_more`. The client prepends/appends batches without changing the URL. These are the **only** record-serving Postgres read paths; search continues to run exclusively against Meilisearch. The split is deliberate: search needs ranking/typo/synonym behaviour (Meilisearch); detail needs the complete record with no document-size pressure (Postgres). PERF-2 (≤500ms p95) covers the initial `GET /api/record/{id}` only — the `id` primary-key lookup plus a composite sitting index (DATA-MODELS §1.1/§1.2); adjacent batch loads are explicitly exempt from PERF-2 (NFR v3.0 clarification) and are served by the same `idx_*_sitting` indexes.

**Unified sitting-level sequence assignment.** `sequence_within_sitting` is a single 1-based ordering **shared** across speech and Q+A records within one sitting (a Q+A exchange and a speech never share a number). It is assigned at the corpus-orchestrator level by walking the sitting's parsed proceedings in document order across both record types — not independently inside `segmenters/speech.py` and `segmenters/qa.py`. This shared space is what makes F09 inline adjacent loading (range fetch below/above a `from_seq`) traverse speeches and questions in true document order. For a **merged speech** (Adjacent Speech Merging, below) the record's `sequence_within_sitting` is the position of the first segment in the merge group; the merged record occupies a single sequence slot. `sequence_within_sitting` is **not** part of the Q+A `dedup_key` (DATA-MODELS §1.5).

**Adjacent Speech Merging (F01, PRD v3.0).** During Stage 2, `segmenters/speech.py` merges consecutive speeches by the **same speaker** within the **same sitting** and **same `proceeding_type`**, consecutive in document order with **no break signal**, into a single `speeches` record. Break signals (any one prevents merging): a speech/interjection by a different speaker; a section heading (H1/H2/H3 or equivalent); a procedural entry (new question-number heading, block header such as "QUESTIONS"/"STARRED QUESTION NO. X", or a formal marker such as "The House adjourned for lunch"). The merged record stores a `segments` JSONB array (one element `{text, segment_index}` per original speech, 0-based); `full_text_en` = segment texts joined with `\n\n`; `word_count` = combined total; `sequence_within_sitting` = first segment's position. Unmerged speeches get a single-element `segments` array. Q+A exchanges are **never** merged. Because the Q+A dedup key excludes `sequence_within_sitting` and the speech dedup key uses the first-segment position, merging does not create duplicate rows on re-ingestion.

**Debug mode (F10, PRD v3.0).** An unauthenticated diagnostic surface gated by the `?debug=1` query parameter; it adds **no new infrastructure** and reuses the existing Railway Postgres pool and Meilisearch client. Three backend surfaces: (1) `POST /api/search?debug=1` augments the Meilisearch query (`showRankingScore`, `showRankingScoreDetails`, `attributesToRetrieve=["*"]`) and returns a `debug` envelope (processed query + captured Meilisearch request/response) alongside results; (2) `GET /api/debug/processed/{id}` returns the full `speeches`/`qa_exchanges` row; (3) `GET /api/debug/raw/{id}` returns the full `raw_documents` row, resolved via the processed record's `canonical_doc_id` + `source`. The frontend lazy-fetches (2) and (3) on first section expand and caches per section. All three are exempt from PERF-1/PERF-2 (NFR PERF-3) and expose full records without auth — a deliberate v1 choice flagged by NFR SEC-1 (review before production use with sensitive data). The `canonical_doc_id` column on `speeches`/`qa_exchanges` exists solely to make (3) a clean composite-PK lookup against `raw_documents`.

**CA field-level parsing (F01).** Two CA-only rules in the CA parse path (`providers/coi_html.py` → `parsers/html_parser.py`):
- **Date** — the constitutionofindia.net URL slug is the *authoritative* date source. The parser derives `date` from the slug and **discards** any date found in the HTML body, even when present. (Supersedes the prior URL-as-fallback-only behaviour.) A CA record's date is missing only if the slug itself fails to parse. Three slug formats are handled (all observed on the live site):
  1. `DD-MMM-YYYY` (e.g. `09-dec-1946`) — PRD canonical format, 3-letter month abbreviation
  2. `DD-MMMM-YYYY` (e.g. `29-july-1947`) — full month name
  3. `YYYY-MM-DD` (e.g. `1946-12-09`) — ISO format
- **Subject** — each CA speech's `subject` is the nearest *preceding standalone bold section header* in the sitting body (topic labels between speech entries; **not** bold speaker names inside speech-grid rows). Walk the DOM in document order, set the current topic on each section header, assign it to subsequent speeches until the next header. If no header precedes the first speech, fall back to the first item in the page TOC `<ul>`.

---

## 6. Integration Points

| Integration | Direction | Used by | Notes |
|-------------|-----------|---------|-------|
| Meilisearch Cloud | Read (search) | API (`meilisearch_client.py`) | Search-only API key used at runtime |
| Meilisearch Cloud | Write (index, settings) | Ingestion pipeline | Master key used for document push and index config; never exposed to API at runtime |
| PostgreSQL (Railway) | Read | API (`db.py`) | Read paths: `index_status` (F07 status); `speeches`/`qa_exchanges` for the F09 record-detail endpoint (`GET /api/record/{id}`) and the F09 inline adjacent-loading endpoint (`GET /api/record/{id}/adjacent`); and the F10 debug endpoints — `speeches`/`qa_exchanges` (`GET /api/debug/processed/{id}`) and `raw_documents` (`GET /api/debug/raw/{id}`, resolved via `canonical_doc_id`+`source`). Search records are **not** served from Postgres (search runs on Meilisearch). All read paths reuse the same asyncpg pool — no new infrastructure for v3.0 |
| PostgreSQL (Railway) | Write | Ingestion pipeline | Stage 1: extracted text + metadata to `raw_documents`. Stage 2: segmented records to `speeches`/`qa_exchanges`; `index_status` on completion |
| constitutionofindia.net (CLPR) | Read (HTTP) | Ingestion `providers/coi_html.py` | CA primary & only; clean semantic HTML, one page per sitting; rate-limited; robots.txt compliant |
| archive.org (Internet Archive) | Read (HTTP) | Ingestion `providers/internet_archive.py` | **Preferred LS/RS bulk path**; pre-OCR DjVuTXT (URL discovered dynamically from metadata `files` array — entry with `format == "DjVuTXT"`; items with no such entry are skipped) + metadata JSON via `advancedsearch.php` / `metadata`; identifier `eparlib.nic.in.{N}` ↔ DSpace handle `123456789/{N}` |
| eparlib.sansad.in (DSpace) | Read (HTTP) | Ingestion `providers/eparlib_dspace.py` | LS fallback (IA-missing items), collection handle `/7`; bitstream URL read from item page, **never constructed**; CA-Legislative collection `/4` excluded; migrated from `eparlib.nic.in` (item IDs preserved) |
| rsdebate.nic.in (DSpace) | Read (HTTP) | Ingestion `providers/rsdebate_dspace.py` | RS fallback; browse `?type=dateissued`; bitstream URL read from item page, **never constructed** |
| sansad.in (/rs) | Read (HTTP) | Ingestion `providers/sansad_rs_html.py` | RS recent in-scope sessions; HTML front end `/rs/debates/officials`; rate-limited; robots.txt compliant |
| Google Fonts CDN | Read (HTTP) | Frontend (browser) | Merriweather and Inter; loaded at page render |

---

## 7. Non-Negotiables

Decisions that must not be changed without explicit user approval. Changes to any of these require significant rework.

1. **PostgreSQL is the primary record store.** Meilisearch is a derived index. Re-indexing always reads from PostgreSQL; it never re-scrapes source websites.

2. **Meilisearch Cloud is the search engine.** No migration to another search backend (Elasticsearch, Typesense, PostgreSQL FTS) without explicit decision.

3. **Query expansion runs server-side only.** `api/services/query_expander.py` is the sole location for synonym lookup and query preprocessing. No synonym expansion logic in the frontend.

4. **`data/synonyms.json` is the sole source of synonym definitions.** A synonym not in this file must not be applied — not in Meilisearch configuration, not in application code. Updates to synonyms require re-running `setup_meilisearch.py` to sync Meilisearch.

5. **`index_status` PostgreSQL table is the sole data source for the F07 status panel.** The API never queries Meilisearch document counts at request time for status display.

6. **Cookie-only storage for F08.** Recent searches and saved searches are stored exclusively in browser cookies. No server-side user data. No user identifiers created or stored.

7. **Ingestion runs only as a standalone CLI process — never via the production API.** The pipeline is invoked as a CLI (`python -m ingest.main …`), whether run locally on an operator's machine or as a scheduled Railway Cron Job in the same project. It is **never** triggered through the web API: there is no `/api/ingest` endpoint or equivalent, and the API service neither imports nor invokes ingestion code. (Wording updated 2026-06-12: the pre-existing "local CLI only" phrasing predated cloud deployment; the invariant being protected is *no API-triggered ingestion*, which a Cron Job — a CLI process, not an API route — does not violate.)

8. **React SPA — no SSR.** The frontend is a static Vite build served from Vercel. No server-side rendering.

9. **`source_url` citation rules (PRD v3.0 — reverses the pre-v3.0 rule).** The Internet Archive (archive.org) URL **is** the citation for IA-sourced records:
   - **CA** → constitutionofindia.net day-page URL.
   - **LS** (any path) → the Internet Archive item URL (`https://archive.org/details/eparlib.nic.in.{N}`). `eparlib.sansad.in` is **not** reliably accessible and must **not** be used as the citation.
   - **RS via Internet Archive or rsdebate.nic.in** → the Internet Archive item URL.
   - **RS via sansad.in HTML** → the sansad.in page URL.
   - **NULL** when no accessible URL can be derived (e.g. an LS/RS item fetched via DSpace fallback that is genuinely absent from the IA mirror, so no archive.org URL exists).

   This **reverses** the prior non-negotiable (which forbade the archive.org URL and cited `eparlib_document_url` for LS / `rsdebate.nic.in` for RS). The change is user-approved for PRD v3.0. Build-time verification of IA-URL derivability for fallback-path items is in §8.

10. **Stage 2 re-processing requires prior clearing of the target scope.** Before re-running Stage 2 (`--stage process`) for any scope, the operator must delete all existing `speeches`/`qa_exchanges` records for that scope, delete the corresponding Meilisearch documents, and clear the matching `processed_documents` entries from the PostgreSQL checkpoint table. Stage 2 inserts with `ON CONFLICT DO NOTHING` — running it without clearing produces no changes to already-indexed records and silently leaves stale data in place. See DEPLOYMENT.md §6.4 for the full procedure.

---

## 8. Build-Time Verifications (PRD v2.0 + v3.0)

Items the Coding Agent must confirm against live source structure during the build; architecture is silent on the outcome because it depends on source-document reality.

### PRD v2.0 items (F01 v2.0 fields + F09)

1. **Shared speech↔Q+A sequence feasibility (all three providers).** Confirm that, for CA (coi HTML), LS (IA text + DSpace PDF), and RS (sansad.in/rs HTML + IA + rsdebate PDF), the sitting's speeches and Q+A exchanges can be ordered into a single document-order sequence. If a provider's format does not expose a reliable interleaved order between the two record types, flag it — F09 inline adjacent loading depends on the shared space.

2. **CA TOC anchor mapping.** For the CA subject fallback, verify whether TOC `<li><a href="#ID">` anchor IDs correspond to `id=` attributes on body elements. If the mapping exists, use it to resolve the first-topic fallback; otherwise fall back to the first TOC item's link text. Record the finding.

3. **`time_of_day` extraction surface.** Confirm which HTML sources expose a sitting start time (CA coi, recent RS sansad.in/rs). `time_of_day` is HTML-only — null for all IA pre-OCR text and PDF-sourced records by design.

### PRD v3.0 items (F01 source_url reversal + merging + lok_sabha_number)

4. **IA-URL derivability on fallback paths (`source_url`).** Non-Negotiable #9 requires the Internet Archive item URL as `source_url` for all LS records and for RS-via-IA/rsdebate. For items fetched on a **DSpace fallback path** (LS `eparlib_dspace`, RS `rsdebate_dspace`) because they are absent from the IA mirror, confirm whether a valid archive.org item URL can nonetheless be derived (e.g. the IA identifier `eparlib.nic.in.{N}` resolves to a real IA item) or whether no IA item exists. Per §7 the rule is: cite the IA URL when an IA item is derivable; otherwise `source_url` is **null**. Record which fallback items, if any, end up null so QA can assert the behaviour. (RS fetched from sansad.in HTML always cites its sansad.in page URL — not affected.)

5. **`lok_sabha_number` extraction surface.** `lok_sabha_number` is LS-only. Confirm the field is available on each LS path: IA (`eparlib_lok_sabha_number` in the metadata JSON — primary), and the DSpace PDF fallback (derive from metadata or document text if present). If a particular LS path cannot yield the term number, `lok_sabha_number` is null for those records; record the finding. RS and CA are always null by design.

6. **Adjacent-merge break-signal detection per format.** Adjacent Speech Merging depends on reliably detecting break signals (different speaker, section heading, procedural entry) in each source format: CA coi HTML, recent RS sansad.in HTML, IA pre-OCR plain text (LS/RS), and DSpace PDF embedded text (LS/RS). HTML exposes structural headings directly; pre-OCR/PDF text may not. Confirm that the segmenter can identify break signals in the flat-text formats (IA text, PDF) well enough to avoid over-merging distinct speeches; flag any format where heading/procedural boundaries are not recoverable, since over-merging silently corrupts `segments` and `full_text_en`.

### Checkpoint-store migration item (2026-06-12: SQLite → PostgreSQL)

7. **Dedup-mirror must not suppress legitimate inserts (`store.py` SQLite→PostgreSQL rewrite).** When `ingest/checkpoints/store.py` is rewritten from SQLite to PostgreSQL (`processed_documents`, `ingestion_dedup_keys`), the dedup-key mirror must remain a **pre-filter only**. The authoritative duplicate guarantee is the `speeches`/`qa_exchanges` `UNIQUE(dedup_key)` constraint via `INSERT … ON CONFLICT (dedup_key) DO NOTHING`. **Regression risk:** in the prior SQLite design, selective re-processing (DEPLOYMENT §6.4) cleared `processed_documents` but left the dedup mirror intact — this was safe only because the mirror never short-circuited an insert that `ON CONFLICT` would otherwise have performed. Preserve that exact semantics: after the canonical `speeches`/`qa_exchanges` rows for a scope are deleted, a Stage 2 re-run **must** re-insert them. Verify with a test that re-processes a previously-checkpointed scope after clearing only `speeches`/`qa_exchanges` + `processed_documents` (not `ingestion_dedup_keys`) and asserts the rows are re-created. Confirm `INF-R1` still holds: an interrupted-then-resumed run yields an identical record count with no duplicates, now using PostgreSQL checkpoints instead of a local file.
