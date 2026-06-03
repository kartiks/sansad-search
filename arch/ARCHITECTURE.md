# Architecture — SansadSearch

**PRD version:** v2.0
**Generated:** 2026-05-28 (v1.0); updated 2026-05-29 (v1.1); updated 2026-05-30 (ingestion source integration redesign — multi-provider per corpus; reconciled to PRD v1.2: OCR removed pipeline-wide, direct DSpace PDF fallback is embedded-text-only); updated 2026-05-31 (reconciled to PRD v1.3: RS-via-IA canonical citation = rsdebate.nic.in derived from DSpace handle N, never eparlib_document_url; null on no-derivable-handle; dual-corpus InternetArchiveProvider ratified); updated 2026-06-01 (PRD v2.0: F09 record-detail page served from PostgreSQL — `GET /api/record/{id}` + adjacent navigation; F01 new fields `lang_original`/`time_of_day`/`word_count` + Q+A `sequence_within_sitting`; F05 `lang_original` badge + `time_of_day` in search results; CA field-level parsing rules); updated 2026-06-03 (§5 CA Date: document all three URL slug formats — DD-MMM-YYYY, DD-MMMM-YYYY, YYYY-MM-DD)

---

## 1. System Overview

SansadSearch is a two-subsystem application:

- **Ingestion pipeline** — local CLI that discovers, fetches, parses, segments, canonicalizes, and indexes parliamentary records across three corpora (CA, LS, RS). Each corpus is served by an ordered chain of providers (government sites plus the Internet Archive mirror); URLs are discovered at runtime from listing/browse pages, never hardcoded. Writes canonical records to PostgreSQL (primary record store) and pushes a derived search index to Meilisearch Cloud.
- **Web application** — FastAPI backend + React SPA serving search, filtering, sorting, result display, and a single-record detail view (F09). Read-only. No authentication.

The two subsystems share no runtime coupling. Ingestion runs offline on the operator's machine. The web application is a stateless read interface over the populated stores.

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
| Pre-OCR'd bulk text | Internet Archive (`{id}_djvu.txt`) | Preferred LS/RS path: OCR text already extracted by IA; the pipeline runs no OCR of its own |
| PostgreSQL client | asyncpg (API) / psycopg2 (ingestion) | asyncpg for async API reads; psycopg2 for bulk ingestion writes |
| Meilisearch Python client | meilisearch-python | Document push, index configuration |
| Frontend routing | React Router v6 | Homepage ↔ Results page; query params encode search state |
| Cookie management | js-cookie | F08 recent/saved searches |
| API hosting | Railway | Managed Python deploy; same platform as PostgreSQL |
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
      search.py                  # POST /api/search
      status.py                  # GET /api/status
      record.py                  # GET /api/record/{id} (F09 detail; 404 if not found)
    services/
      query_expander.py          # Query parsing, stop-word stripping, synonym lookup,
                                 # phrase synonym detection, expansion notice generation
      search.py                  # Meilisearch filter construction, result formatting,
                                 # snippet post-processing
      record.py                  # F09: fetch one record by id (speeches UNION qa_exchanges),
                                 # adjacent-neighbour query (same sitting, by sequence),
                                 # sitting_total count, response formatting
    lib/
      meilisearch_client.py      # Shared Meilisearch async client (singleton, search key)
      db.py                      # asyncpg connection pool init and teardown

  ingest/
    main.py                      # CLI entry (--source ca|ls|rs|all, --date-override)
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
                                 # eparlib.nic.in.{N}; metadata JSON; _djvu.txt download; maps
                                 # eparlib_* custom fields. Dual-corpus: single provider serves
                                 # both LS and RS via a `corpus` constructor param; citation_url
                                 # dispatches on corpus = eparlib_document_url (LS) |
                                 # rsdebate.nic.in URL (RS, derived from handle N) |
                                 # null (RS no-derivable-handle edge case, PRD v1.3)
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
      ia_text_parser.py          # Internet Archive _djvu.txt OCR text + IA metadata JSON
                                 # → raw record dicts; no local OCR
    segmenters/
      speech.py                  # Raw text/markup → Speech unit dicts
      qa.py                      # Raw text/markup → Q+A exchange unit dicts
    canonical/
      names.py                   # Speaker name canonicalization against names_dict.csv
      sessions.py                # Session name canonicalization to canonical format
    checkpoints/
      store.py                   # SQLite-backed processed-document log (keyed on canonical
                                 # doc id N / coi day-URL) and record-level dedup key store
    indexer.py                   # PostgreSQL writer + Meilisearch document pusher
                                 # + index_status table update on run completion
    setup_meilisearch.py         # One-time/deploy-time: push synonyms.json to
                                 # Meilisearch synonyms API; configure index settings

  ui/
    src/
      components/
        ResultCard.jsx           # Dispatches to SpeechCard or QACard by record_type;
                                 # each card links to /record/:id
        SpeechCard.jsx           # F05: renders lang_original badge + time_of_day row
        QACard.jsx               # F05: renders lang_original badge + time_of_day row
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
        IndexingStatusPage.jsx   # Full F07 indexing status panel (detailed: total +
                                 # per-source counts + per-source date coverage +
                                 # last-updated); reached via Results.jsx footer link
        RecordDetail.jsx         # F09 detail page (route /record/:id): full text +
                                 # all metadata; prev/next adjacent controls (disabled at
                                 # boundaries); back-nav = "Back to results" (in-app referrer
                                 # via router location state) | "Search" (direct URL)
      hooks/
        useSearch.js             # POST /api/search call; loading/error state management
        useRecord.js             # GET /api/record/{id} call (F09); loading/error/404 state
        useCookieHistory.js      # Recent searches read/write (F08)
        useSavedSearches.js      # Saved searches read/write (F08)
      lib/
        cookie.js                # Cookie read/write/delete helpers
        filterState.js           # Filter shape definition, defaults, validation helpers
        expansionNotice.js       # Parse expansion_notice array from API response
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
| **Index status (F07)** | Browser → `GET /api/status` → asyncpg query on `index_status` table (most recent row) → Browser. Both F07 surfaces share this one flow: the homepage strip (`Home.jsx`, condensed — counts + last-updated) and the full panel (`IndexingStatusPage.jsx`, detailed — total + per-source counts + per-source date coverage + last-updated) render different subsets of the same response. No separate endpoint. |
| **Record detail (F09)** | Browser → `GET /api/record/{id}` → `services/record.py`: (1) asyncpg fetch by id — `speeches WHERE id` UNION ALL `qa_exchanges WHERE id`; 404 if neither matches. (2) adjacent-neighbour query over the same sitting (`source` + `date` + `sitting_number IS NOT DISTINCT FROM`), both tables unioned, ordered by `sequence_within_sitting`; resolves `prev_id`/`next_id` (null at boundaries) and `sitting_total` → Browser. **Detail is served from PostgreSQL, not Meilisearch** (the canonical store holds every display field, incl. `session_number`, `has_untranslated_content`, `page_reference`, `word_count`). Search remains Meilisearch-only. |
| **Search history (F08)** | Browser ↔ Browser cookies only — no server involvement |
| **Bulk ingestion** | Operator CLI → corpus orchestrator → provider chain `discover()` (HTML listing crawl / DSpace browse / IA `advancedsearch`; document-level dedup on canonical doc id `N`) → httpx fetcher (rate-limited, robots.txt compliant) → parser by format: HTML (`html_parser`) / IA pre-OCR text (`ia_text_parser`) / PDF (`pdf_parser`, embedded-text only) → segmenter → canonicalizer → PostgreSQL writer → Meilisearch document pusher → `index_status` table updated on completion |
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

**Cross-source document identity.** The DSpace handle number `N` is the canonical document identity for LS/RS. The Internet Archive identifier `eparlib.nic.in.{N}` maps to DSpace handle `123456789/{N}` — `N` is the cross-provider join key. The checkpoint store dedupes at the **document level** on this canonical id so a document available from more than one provider is fetched and parsed once; the record-level `dedup_key` (DATA-MODELS §1.4) remains the final guard against duplicate records.

**Internet Archive pre-OCR text path.** LS/RS bulk ingestion prefers the IA mirror, which serves `{identifier}_djvu.txt` (OCR already extracted by IA) plus a metadata JSON carrying `eparlib_*` fields (`eparlib_title`, `eparlib_date`, `eparlib_lok_sabha_number`, `eparlib_session_number`, `eparlib_document_url`). `ia_text_parser.py` consumes the text and maps the metadata. The pipeline runs no OCR of its own. A **single `InternetArchiveProvider` serves both corpora** (dual-corpus, selected by a `corpus` constructor parameter); citation derivation dispatches on the corpus:
- **LS:** `source_url` is set to the canonical `eparlib_document_url`.
- **RS:** `source_url` is set to the `rsdebate.nic.in` item URL derived from the DSpace handle `N` (the IA identifier `eparlib.nic.in.{N}` ↔ handle `123456789/{N}`); when no handle is derivable from the IA record, `source_url` is null, a warning is logged, and the item is still ingested (PRD v1.3 no-handle edge case).

In neither case is the archive.org mirror URL ever used as `source_url` (Non-Negotiable #9). Direct DSpace PDF (embedded-text extraction via PyMuPDF, no OCR) is the fallback for items absent from the mirror; a fallback PDF with no text layer is logged and skipped.

**DSpace bitstream resolution.** DSpace PDF URLs (eparlib.sansad.in, rsdebate.nic.in) are always resolved by reading the real bitstream URL from the item page/metadata. Bitstream filenames are **never constructed** — the convention is inconsistent across years (e.g. `lsd_08_09_04-12-1987.pdf`, `lsd_10_V_01_12_1992.pdf`, `lsd_08_1_30-01-1985.pdf`).

**HTML-preferred parsing.** Where a corpus offers HTML (CA via coi; recent RS via sansad.in/rs), HTML is parsed in preference to PDF, consistent with the PRD HTML-over-PDF deduplication rule.

**Local checkpoint store (ingestion only).** A SQLite database (`data/ingestion_checkpoints.db`) on the operator's machine tracks processed source documents (by canonical doc id, for resumability and cross-provider dedup) and inserted record-level deduplication keys (for fast duplicate detection without querying PostgreSQL). This file is never deployed to production and is in `.gitignore`.

**Pre-computed index status.** The ingestion pipeline writes a row to the `index_status` PostgreSQL table on successful completion. The `GET /api/status` endpoint reads the most recent row. The status panel never issues a Meilisearch document count query at request time.

**Record detail served from PostgreSQL (F09).** The detail page reads from PostgreSQL, not Meilisearch. PostgreSQL is the canonical store and already holds every field the detail page shows — including fields deliberately excluded from the Meilisearch document (`session_number`, `has_untranslated_content`, `page_reference`, `word_count`). `GET /api/record/{id}` fetches one record (`speeches` UNION ALL `qa_exchanges` by `id`) and runs one adjacent-neighbour query over the same sitting. This is the **only** record-serving Postgres read path; search continues to run exclusively against Meilisearch. The split is deliberate: search needs ranking/typo/synonym behaviour (Meilisearch); detail needs the complete record with no document-size pressure (Postgres). PERF-2 (≤500ms p95) is met by the `id` primary-key lookup plus a composite sitting index (DATA-MODELS §1.1/§1.2).

**Unified sitting-level sequence assignment.** `sequence_within_sitting` is a single 1-based ordering **shared** across speech and Q+A records within one sitting (a Q+A exchange and a speech never share a number). It is assigned at the corpus-orchestrator level by walking the sitting's parsed proceedings in document order across both record types — not independently inside `segmenters/speech.py` and `segmenters/qa.py`. This shared space is what makes F09 adjacent navigation (prev = seq−1, next = seq+1) traverse speeches and questions in true document order. `sequence_within_sitting` is **not** part of the Q+A `dedup_key` (DATA-MODELS §1.4).

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
| PostgreSQL (Railway) | Read | API (`db.py`) | Two read paths: `index_status` table for the F07 status endpoint, and `speeches`/`qa_exchanges` for the F09 record-detail endpoint (`GET /api/record/{id}` — single record + adjacent navigation). Search records are **not** served from Postgres (search runs on Meilisearch) |
| PostgreSQL (Railway) | Write | Ingestion pipeline | All speech and Q+A records; `index_status` on completion |
| constitutionofindia.net (CLPR) | Read (HTTP) | Ingestion `providers/coi_html.py` | CA primary & only; clean semantic HTML, one page per sitting; rate-limited; robots.txt compliant |
| archive.org (Internet Archive) | Read (HTTP) | Ingestion `providers/internet_archive.py` | **Preferred LS/RS bulk path**; pre-OCR `_djvu.txt` + metadata JSON via `advancedsearch.php` / `metadata`; identifier `eparlib.nic.in.{N}` ↔ DSpace handle `123456789/{N}` |
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

7. **Ingestion pipeline is local CLI only.** It is never triggered via the production API. There is no `/api/ingest` endpoint or equivalent.

8. **React SPA — no SSR.** The frontend is a static Vite build served from Vercel. No server-side rendering.

9. **IA-sourced records cite the canonical record, not the mirror.** For LS records ingested via the Internet Archive, `source_url` is set to `eparlib_document_url` (the official parliamentary-library URL). For RS records ingested via the Internet Archive, `source_url` is set to the `rsdebate.nic.in` item URL derived from the DSpace handle `N`; when no handle is derivable, `source_url` is null (PRD v1.3 no-handle edge case). The archive.org mirror URL is never cited in either case — the mirror is a fetch path, not a citation.

---

## 8. Build-Time Verifications (PRD v2.0)

Items the Coding Agent must confirm against live source structure during the build that introduces F01 v2.0 fields and F09; architecture is silent on the outcome because it depends on source-document reality.

1. **Shared speech↔Q+A sequence feasibility (all three providers).** Confirm that, for CA (coi HTML), LS (IA text + DSpace PDF), and RS (sansad.in/rs HTML + IA + rsdebate PDF), the sitting's speeches and Q+A exchanges can be ordered into a single document-order sequence. If a provider's format does not expose a reliable interleaved order between the two record types, flag it — F09 adjacent navigation depends on the shared space.

2. **CA TOC anchor mapping.** For the CA subject fallback, verify whether TOC `<li><a href="#ID">` anchor IDs correspond to `id=` attributes on body elements. If the mapping exists, use it to resolve the first-topic fallback; otherwise fall back to the first TOC item's link text. Record the finding.

3. **`time_of_day` extraction surface.** Confirm which HTML sources expose a sitting start time (CA coi, recent RS sansad.in/rs). `time_of_day` is HTML-only — null for all IA pre-OCR text and PDF-sourced records by design.
