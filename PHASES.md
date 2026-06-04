# SansadSearch — Phase Plan

PRD version: v2.1
Generated: 2026-05-29; updated 2026-05-30 (Phases 7–9 added — ingestion pipeline rebuild for redesigned source chain + schema fixes); updated 2026-06-02 (Phases 10–11 added — PRD v2.0: new ingestion fields, CA parsing rules, shared sequence, F05 badge changes, F09 record detail page; merge-conflict marker in header resolved); updated 2026-06-03 (Phase 12 added — two-stage pipeline + raw_documents table per ARCH 2026-06-03 update); updated 2026-06-04 (Phase 12 main.py: --date-from/--date-to scope both stages — Stage 1 applies post-parse date-window gate; routing updated to run_stage1(date_from, date_to); stop condition for Stage 1 date filter added)

---

## Phase 1 — Project Foundation + Ingestion Parsers and Segmenters

PRD sections: F01 (partial — parsers and segmenters only), F04 (synonyms.json data file only)
UI sections: none

Implement:
- `/app/` folder structure matching ARCHITECTURE.md section 3 exactly
- `app/db/schema.sql` — CREATE TABLE statements for speeches, qa_exchanges, and index_status with all indexes defined in DATA-MODELS.md sections 1.1 and 1.2
- `app/data/synonyms.json` — complete synonym dictionary covering all groups defined in F04: legislative bodies, constitutional terminology, parliamentary procedure, abbreviations, well-known legislation; bidirectional entries
- `app/data/names_dict.csv` — file with header row only (populated during ingestion)
- `requirements.txt` — all Python dependencies (FastAPI, uvicorn, asyncpg, psycopg2, meilisearch-python, httpx, beautifulsoup4, PyMuPDF, pytesseract, python-dotenv)
- `pyproject.toml` — Python project config
- FastAPI skeleton: `app/api/main.py` (app instance, CORS config, lifespan hooks), `app/api/lib/db.py` (asyncpg pool init and teardown), `app/api/lib/meilisearch_client.py` (singleton async client using search key)
- `app/ui/package.json`, `app/ui/vite.config.js`, `app/ui/index.html` — React + Vite SPA shell
- `app/ingest/setup_meilisearch.py` — creates the parliamentary_records index if absent; configures searchableAttributes, filterableAttributes, sortableAttributes, rankingRules, typoTolerance, and pagination.maxTotalHits per DATA-MODELS.md section 2.3; loads synonyms.json and pushes all synonym pairs to the Meilisearch synonyms API (full replace)
- `app/ingest/parsers/html_parser.py` — BeautifulSoup4: HTML → raw record dicts for all LS/RS proceeding types
- `app/ingest/parsers/pdf_parser.py` — PyMuPDF: embedded text extraction; Tesseract OCR fallback for pages with no embedded text; ocr_low_confidence flag on low-confidence pages
- `app/ingest/segmenters/speech.py` — raw text/markup → Speech unit dicts; handles all proceeding types listed in F01; language handling: English (verbatim), Hindi with translation (store translation), bilingual (concatenate English + translated portions), Hindi without translation (full_text_en: null, has_untranslated_content: true); excludes unattributed speech and presiding officer interventions per F01 rules
- `app/ingest/segmenters/qa.py` — raw text/markup → Q+A exchange unit dicts; starred (main question + minister answer + all supplementary questions with attribution + minister responses) and unstarred (question text + written answer only)

Stop when: all project directories exist; `app/db/schema.sql` executes against a local PostgreSQL instance without error and produces the correct tables and indexes; `setup_meilisearch.py` configures the Meilisearch index with all settings from DATA-MODELS.md 2.3; synonyms.json is valid JSON and contains all synonym groups from F04; parser and segmenter unit tests pass against fixture HTML and PDF samples covering all proceeding types, both record types, and all four language handling cases.
Do not implement anything from Phase 2 or later.
Tests: write and run tests for all items above before finishing.

---

## Phase 2 — Ingestion Pipeline Complete (F01)

PRD sections: F01 (complete)
UI sections: none

Implement:
- `app/ingest/sources/ca.py` — CA volume URL enumeration; fetches all 12 volumes from sansad.in archives; rate-limited with configurable inter-request delay; robots.txt compliant
- `app/ingest/sources/ls.py` — LS session and sitting URL enumeration; fetches all records from 2014-01-01 for all proceeding types in F01; rate-limited; robots.txt compliant; HTML preferred over PDF for same proceeding
- `app/ingest/sources/rs.py` — RS session and sitting URL enumeration; fetches all records from 2014-01-01; rate-limited; robots.txt compliant
- HTTP error handling: 4xx (excluding 429) → log and skip; 5xx → retry up to 3 times with exponential backoff, then log and skip; 429 → exponential backoff and retry, never skip
- `app/ingest/canonical/names.py` — strips honorific prefixes (Shri, Smt., Dr., Prof., Adv., Kumari); resolves abbreviation and ordering variants against names_dict.csv; sets speaker_name_unresolved: true for unresolved names
- `app/ingest/canonical/sessions.py` — canonicalizes session name strings to "[Session Type] Session [Year]" format with "(Part N)" for multi-part sessions; CA records produce session_name: null
- `app/ingest/checkpoints/store.py` — SQLite-backed store with two tables: processed_urls (url TEXT PRIMARY KEY, processed_at TIMESTAMP) and inserted_dedup_keys (dedup_key TEXT PRIMARY KEY); used for resumability and fast duplicate detection
- `app/ingest/indexer.py` — writes canonical records to PostgreSQL speeches and qa_exchanges tables; pushes denormalized documents to Meilisearch parliamentary_records index per DATA-MODELS.md 2.2 (omit fields not applicable to record type; exclude page_reference, ocr_low_confidence, has_untranslated_content, session_number, created_at, dedup_key from Meilisearch documents); updates index_status table on successful run completion; `--reindex-from-db` mode reads all records from PostgreSQL and pushes to Meilisearch without re-scraping
- `app/ingest/main.py` — CLI entry point: `--source ca|ls|rs|all`; optional `--date-override` for LS/RS end date; real-time progress logging (document processed, records indexed, errors, skipped); completion summary (total records indexed per source, total errors, total skipped); reads checkpoint store to skip already-processed documents; runs canonicalization before indexing

Stop when: all F01 test requirements pass — resumability (re-running against a fully indexed corpus produces zero new records and zero duplicates; interrupted + resumed run produces identical final count to a clean run); deduplication (compound dedup key correctly distinguishes two speeches by the same member in the same sitting); language handling integration (is_translated and has_untranslated_content set correctly for all four cases); canonicalization (same member appearing as "Shri Narendra Modi", "Narendra Modi", "N. Modi" produces identical speaker_name; unresolved names stored with speaker_name_unresolved: true); progress log contains real-time entries; completion summary count matches actual index count; records with missing date are skipped with one logged error each; unattributed speech never appears as a standalone indexed record.
Do not implement anything from Phase 3 or later.
Tests: write and run tests for all items above before finishing.

---

## Phase 3 — Search API (F02, F03, F04, F06, F07)

PRD sections: F02, F03, F04, F06, F07
UI sections: none

Implement:
- `app/api/routes/search.py` — POST /api/search per DATA-MODELS.md 3.1: request validation (query too short, stop-words-only query, empty sources array, empty proceeding_types array, date_from > date_to); query truncation to 500 characters; pagination (page ≥ 1, 20 results per page); response body including total, total_display, total_pages, expansion_notice, and per-result fields
- `app/api/services/query_expander.py` — strips stop words from query; detects and applies phrase synonyms when full phrase is present in query; applies unidirectional term synonyms for remaining terms; generates expansion_notice array of expanded term strings; delegates typo tolerance to Meilisearch (no custom spell-correction code); terms fewer than 4 characters exempt from typo tolerance via minWordSizeForTypos; reads synonyms from data/synonyms.json only
- `app/api/services/search.py` — constructs Meilisearch filter expression from active filters: source IN [...], proceeding_type IN [...], date >= ..., date <= ..., speaker_name CONTAINS "...", session_name CONTAINS "..."; joins multiple active filters with AND; maps sort selection to Meilisearch sort parameter per DATA-MODELS.md 2.5; calls Meilisearch parliamentary_records index; formats results: proceeding_type_label from constants, date_display as DD Month YYYY, snippet extracted from highest query-term-density passage in full_text_en with matched terms wrapped in mark tags (HTML-safe; all other HTML stripped); snippet_from_supplementary: true when best-match passage is from supplementary exchange; null full_text_en produces no snippet field (frontend handles display); total_display: "10,000+" when total ≥ 10000 else comma-formatted string
- `app/api/routes/status.py` — GET /api/status: reads most recent row from index_status table; returns populated response when row exists, never-run response when table is empty, unavailable response when table is unreadable or malformed per DATA-MODELS.md 3.2

Stop when: all F02, F03, F04, F06, and F07 test requirements pass at the API level using fixture data pre-loaded into a local Meilisearch instance — including expansion weight ordering (original term > synonym > spell correction), filter AND combination, session filter implicit CA exclusion, date gap handling (1948–2015 range returns CA and LS/RS records with no gap error), CA-only proceeding type constraint, sort secondary key (sequence_within_sitting), relevance sort isolation from date order, and status panel reading from pre-computed summary only.
Do not implement anything from Phase 4 or later.
Tests: write and run tests for all items above before finishing.

---

## Phase 4 — Frontend: Homepage, Results Page, Result Cards (F02, F05, F06, F07 UI)

PRD sections: F02 (frontend), F05, F06 (frontend), F07 (frontend)
UI sections: 02-ui-ux-spec.md sections 1 (Homepage), 2 (Results Page), Visual Identity, Interaction Patterns, Canonical Text

Implement:
- `app/ui/src/lib/constants.js` — proceeding type label map, source label map (per F05 Proceeding Type Labels)
- `app/ui/src/lib/filterState.js` — FilterState shape definition, default values, validation helpers (empty sources, empty proceeding_types, date_from > date_to)
- `app/ui/src/lib/expansionNotice.js` — parses expansion_notice array from API response for "Also searching for:" display
- `app/ui/src/hooks/useSearch.js` — POST /api/search call; loading, error, and success state management
- `app/ui/src/pages/Home.jsx` — wordmark, tagline, search bar (48px height, submit icon button), "Advanced Search" link placeholder, saved searches bookmark icon placeholder, indexing status strip pinned to page bottom reading from GET /api/status (F07); layout: centered 680px column; responsive breakpoints per UI spec section 1
- `app/ui/src/pages/Results.jsx` — sticky header (wordmark + centered search bar + "Advanced Search" placeholder + bookmark icon), query expansion notice (conditional), results header row (result count + sort dropdown), result card list, pagination, "Index status" footer link (F07); layout: 860px centered column; responsive breakpoints per UI spec section 2; loading state (5 skeleton cards), empty state, error state with Retry button
- `app/ui/src/components/ResultCard.jsx` — dispatches to SpeechCard or QACard by record_type
- `app/ui/src/components/SpeechCard.jsx` — metadata row (proceeding type badge, legislative body full label, date DD Month YYYY, session if available); speaker row (SemiBold, party and constituency/state if available; "Speaker unknown" if null); subject line (truncated one line); snippet with mark-highlighted terms (background rgba(201,106,30,0.15), text #C96A1E); null full_text_en shows "This speech was delivered in Hindi. No English text is available."; is_translated indicator; "View source ↗" link (omitted if source_url null); hover state; all F05 edge cases (missing party/constituency omitted with no placeholder; speaker_name_unresolved displayed as raw name without error indicator; HTML in snippet rendered as plain text; script tags do not execute)
- `app/ui/src/components/QACard.jsx` — metadata row; subject line (two lines); question number; questioner row ("+N others" for co-signatories: 1 questioner → no label, 4 total → "+3 others"); minister/ministry row; snippet with "From supplementary exchange — " prefix when snippet_from_supplementary: true; translation indicator; source link; all F05 edge cases
- `app/ui/src/components/Pagination.jsx` — previous/next buttons, current page (navy background), adjacent pages; result count display (exact for ≤9,999, "10,000+" for ≥10,000, "0 results" for empty); URL encodes both query and page number (shareable/bookmarkable); direct URL to page N loads that page
- `app/ui/src/components/SkeletonCard.jsx` — animated shimmer blocks matching card dimensions
- `app/ui/src/pages/IndexingStatusPage.jsx` — full F07 indexing status panel: "Search Index Status" header; total records count with thousands separator; per-source table (Constituent Assembly, Lok Sabha, Rajya Sabha) each showing record count and date coverage range; a source with zero records shows "0 records – not yet indexed" with no date range; "Last updated: DD Month YYYY" or "Never" when ingestion has never run; "Status unavailable" message (replacing counts and dates) when summary record is malformed or unreadable; reads from GET /api/status only (no direct index query); accessible via the "Index status" footer link in Results.jsx
- `app/ui/src/components/Toast.jsx` — bottom-center, 16px from bottom, 3s auto-dismiss, Inter 13px white text on #1C3461 background, border-radius 6px; one toast at a time
- Sort dropdown (F06): three options (Relevance default, Newest first, Oldest first); selecting re-sorts immediately; persists across query refinements; defaults to Relevance on every new search; result count does not change on sort change
- Search bar inline validation: query empty or < 2 non-whitespace characters → "Enter at least 2 characters to search." in #C96A1E below search bar; no search executes; message dismisses on typing

Stop when: all F05 and F06 acceptance criteria verified in browser; homepage status strip displays F07 data from GET /api/status; full F07 indexing status panel renders correctly for all states (loaded data, fresh deployment showing "Never" and zero-record rows as "0 records – not yet indexed", status unavailable message); all result card types render correctly for all edge cases; pagination URL persistence works (direct URL to page 3 loads page 3); sort dropdown behaves correctly including default-on-new-search; search bar inline validation triggers and dismisses correctly; loading skeleton, empty state, and error state all display correctly.
Do not implement anything from Phase 5 or later.
Tests: write and run tests for all items above before finishing.

---

## Phase 5 — Frontend: Advanced Search Modal and Filter Chips (F03 UI)

PRD sections: F03 (frontend)
UI sections: 02-ui-ux-spec.md sections 2 (Results Page — filter chips row), 3 (Advanced Search Modal), Interaction Patterns

Implement:
- `app/ui/src/components/AdvancedSearchModal.jsx` — modal overlay (rgba(0,0,0,0.4) background); modal panel (white, border-radius 12px, padding 24px, max-width 560px, max-height 90vh scrollable); all 5 filter dimensions: (1) Legislative Body multi-select checkboxes (CA, Lok Sabha, Rajya Sabha; all checked by default), (2) Date Range pickers (From and To, both optional, side-by-side), (3) Speaker text input with helper text, (4) Session text input with helper text, (5) Proceeding Type multi-select checkboxes (all checked by default; when only CA selected, all non-Debate options are visually disabled and non-interactive); inline validation: all bodies unchecked → "Select at least one source"; From > To → "From date must be before To date"; all types unchecked → "Select at least one proceeding type"; Apply button disabled (opacity 0.4, not clickable) while any validation is failing; Clear all resets all fields to defaults; pre-populates from active filter state when opened while filters are active; on Apply: modal closes, filters applied as chips, search re-executes; close icon (×) top-right
- `app/ui/src/components/FilterChip.jsx` — pill shape (background #EDF0F7, text #1C3461, 13px Medium, border-radius 20px); × dismiss icon; on × click: chip removed, filter cleared, search re-runs; "Clear all" text link at end of chip row resets all filters and re-runs search
- Wire filter chips row into Results.jsx — shown only when one or more filters are active; horizontal row 12px below sticky header; horizontally scrollable on overflow
- Wire "Advanced Search" link in homepage below-bar row and results header to open modal
- Wire filter state into useSearch.js: active filters included in POST /api/search body; filter state persists across query refinements (new query submitted while filters active keeps filter state); only explicit clear (chip × or Clear all or modal Clear all) resets filter state
- Responsive: modal full-width with 16px side margins on mobile; checkboxes stack vertically on mobile

Stop when: all F03 UI acceptance criteria verified in browser — filter chips appear after Apply and persist across query refinements; individual chip × and Clear all behave correctly; CA-only disabling of proceeding types works; all three inline validation messages display correctly and disable Apply; modal pre-populates from active filter state; session filter active excludes CA records from results; responsive layout correct on mobile.
Do not implement anything from Phase 6.
Tests: write and run tests for all items above before finishing.

---

## Phase 6 — Search History (F08)

PRD sections: F08
UI sections: 02-ui-ux-spec.md sections 4 (Recent Searches Dropdown), 5 (Saved Searches Panel)

Implement:
- `app/ui/src/lib/cookie.js` — cookie read, write, and delete helpers; enforces 4 KB combined size limit across ss_recent and ss_saved cookies; near-capacity handling: trim oldest ss_recent entries first; never auto-remove ss_saved entries; cookies-disabled detection (silent, no error)
- `app/ui/src/hooks/useCookieHistory.js` — recent searches: auto-record every submitted query (query text + timestamp); max 10 entries, FIFO rotation on 11th distinct entry; duplicate query updates timestamp and position (one entry per unique query string); 30-day cookie expiry from most recent submission; stores query text and timestamp only (no filter state)
- `app/ui/src/hooks/useSavedSearches.js` — saved searches: max 20 entries, no expiry; stores name (default = query text, editable up to 60 characters), query text, active filter state (FilterState shape), and save timestamp; same query may be saved twice as two separate entries; re-run restores query + filter state with default sort; stale/unrecognised filter values silently ignored on re-run (search executes with valid values only)
- `app/ui/src/components/RecentSearchesDropdown.jsx` — triggers when search bar focused and empty; anchored below search bar, full search bar width; section label "Recent searches"; up to 10 items (magnifying glass icon + query text); click populates and submits search bar (with default filters, not saved filter state); "Clear history" footer link clears all recent entries; empty state "No recent searches"; dismiss on outside click or Escape
- `app/ui/src/components/SavedSearchesPanel.jsx` — triggered by bookmark icon in header (results page) and homepage; width 320px, max-height 400px scrollable; header "Saved searches"; up to 20 items each showing name (one line, truncated) and filter summary (Inter 12px Text secondary: e.g. "Lok Sabha · 2019–2024 · Starred Question"; "No filters" if no filter state); pencil icon → inline rename input (60-char max, confirm with checkmark or cancel with ×); trash icon → delete item + "Search removed" toast; clicking item text runs search restoring query + filter state; "Save current search" full-width outline button at bottom (results page only, hidden on homepage); on save: name defaults to query text, "Search saved" toast; at 20-entry limit: button disabled (opacity 0.4), label "Saved searches full — delete one to save"; empty state "No saved searches yet."; dismiss on outside click or Escape
- Wire RecentSearchesDropdown into search bar focus event on both homepage and results page
- Wire SavedSearchesPanel into bookmark icon on both homepage and results header

Stop when: all F08 test requirements pass in browser — FIFO rotation (10 entries, 11th removes oldest); duplicate deduplication (same query 3 times → 1 entry with latest timestamp); re-running a recent search executes with default filters regardless of original filter state; saved search filter restoration (body=RS + proceeding=Starred Question + from=2020-01-01 restores exactly); save disabled at exactly 20 entries with no 21st entry creatable by any means; same query saved twice produces two separate entries; cookies-disabled shows no error; saved search name 60 characters accepted, 61 rejected without losing the save action; stale filter value does not cause error.
Do not implement anything beyond Phase 6.
Tests: write and run tests for all items above before finishing.

---

## Phase 7 — Ingestion Rebuild: Schema + Shared Infrastructure

PRD sections: F01 (schema change — ocr_low_confidence drop; shared pipeline primitives)
UI sections: none

Implement:
- `app/db/schema.sql` — remove `ocr_low_confidence` column from `speeches` table
- `requirements.txt` — remove `pytesseract`; confirm no remaining OCR dependencies
- `app/ingest/sources/_http.py` — shared HTTP utility: USER_AGENT constant, RobotsChecker, `fetch_with_retry` with 4xx (log + skip), 5xx (retry ×3 exponential then log + skip), 429 (exponential backoff + retry, never skip)
- `app/ingest/sources/_discovery.py` — shared discovery helpers: HTML listing crawl, DSpace browse-by-date pagination, IA `advancedsearch.php` enumeration
- `app/ingest/sources/_provider.py` — Provider contract: `discover() → [DocumentRef]`; `fetch(DocumentRef) → bytes|text`; DocumentRef dataclass carrying corpus, provider, format (html|pdf|ia_text), fetch_url, canonical_doc_id, citation_url, discovered metadata
- `app/ingest/parsers/ia_text_parser.py` — IA `_djvu.txt` OCR text + IA metadata JSON → raw record dicts; maps `eparlib_*` custom fields; no local OCR
- `app/ingest/parsers/pdf_parser.py` — updated: embedded-text extraction only; no OCR fallback; text-less PDFs logged and skipped
- `app/ingest/checkpoints/store.py` — redesigned: `processed_documents(canonical_doc_id TEXT PRIMARY KEY, corpus TEXT, provider TEXT, fetch_url TEXT, processed_at TIMESTAMP)` + `inserted_dedup_keys(dedup_key TEXT PRIMARY KEY)`; replaces old `processed_urls` table
- `app/ingest/indexer.py` — updated: remove `ocr_low_confidence` from Meilisearch document push; accept DocumentRef input shape; no other behavioral changes
- `app/ingest/setup_meilisearch.py` — verify all index configuration constants match DATA-MODELS.md §2.3 exactly (searchableAttributes, filterableAttributes, sortableAttributes, rankingRules, typoTolerance, pagination.maxTotalHits); correct any discrepancies found

Stop when: `schema.sql` produces speeches table without `ocr_low_confidence` column; checkpoint store creates `processed_documents` and `inserted_dedup_keys` tables correctly; `_http.py` tests cover all three retry cases with mocked httpx; `ia_text_parser.py` tests parse fixture `_djvu.txt` + metadata JSON into correct raw record dicts; `pdf_parser.py` tests confirm text-less PDFs are skipped (no OCR path triggered); `indexer.py` tests confirm `ocr_low_confidence` absent from pushed documents; `setup_meilisearch.py` constants verified against DATA-MODELS.md §2.3 with a unit test asserting no deviation.
Do not implement anything from Phase 8 or later.
Tests: write and run tests for all items above before finishing.

---

## Phase 8 — CA + LS Corpus Providers

PRD sections: F01 (CA corpus; LS corpus)
UI sections: none

Implement:
- `app/ingest/sources/providers/coi_html.py` — constitutionofindia.net CA provider: volume index → per-volume → per-day URL discovery (runtime listing crawl, not hardcoded); HTML main-content fetch; returns DocumentRef with format=html, corpus=CA; covers 167 sittings across 12 volumes (9 Dec 1946 – 24 Jan 1950)
- `app/ingest/sources/providers/internet_archive.py` — archive.org IA provider: `advancedsearch.php` enumerate `eparlib.nic.in.{N}` identifiers; metadata JSON fetch; `_djvu.txt` download; maps `eparlib_*` custom fields (`eparlib_document_url`, `eparlib_date`, `eparlib_lok_sabha_number`, `eparlib_session_number`); `citation_url` set to `eparlib_document_url`; `canonical_doc_id` = handle number N; format = ia_text
- `app/ingest/sources/providers/eparlib_dspace.py` — eparlib.sansad.in LS fallback: DSpace browse `?type=dateissued` pagination; item-page bitstream URL resolution (never constructs filenames); collection handle `/7`; returns DocumentRef with format=pdf; invoked only for items with `canonical_doc_id` absent from checkpoint store
- `app/ingest/sources/ca.py` — updated: CA corpus orchestrator using provider chain `[coi_html]`; document-level dedup on `canonical_doc_id`; passes DocumentRef to parsers → segmenters → indexer
- `app/ingest/sources/ls.py` — updated: LS corpus orchestrator using provider chain `[internet_archive, eparlib_dspace]`; date filter >= 2014-01-01; document-level dedup on `canonical_doc_id`; first provider yielding parseable content wins

Stop when: `coi_html.py` tests discover all 12 volumes from fixture HTML and produce correct DocumentRef list; `internet_archive.py` tests enumerate fixture IA search results, fetch fixture metadata JSON, and return DocumentRef with `citation_url` = `eparlib_document_url` (never archive.org); `eparlib_dspace.py` tests resolve bitstream URL from fixture item page (never from a constructed filename); `ca.py` integration test runs provider chain against mocked HTTP and produces correctly segmented CA speech records with no `ocr_low_confidence` field; `ls.py` integration test: IA path produces ia_text records, DSpace fallback invoked only for items absent from IA, re-run against fully-processed fixture corpus produces zero new records.
Do not implement anything from Phase 9 or later.
Tests: write and run tests for all items above before finishing.

---

## Phase 9 — RS Corpus Providers + PRD v1.3 Canonical Citation Rules

PRD sections: F01 (RS corpus; RS source_url canonical-citation rule; RS-via-IA no-handle edge case)
UI sections: none

Implement:
- `app/ingest/sources/providers/sansad_rs_html.py` — sansad.in/rs RS provider: HTML listing crawl `/rs/debates/officials`; per-sitting HTML fetch and parse; returns DocumentRef with format=html, corpus=RS; date filter >= 2014-01-01
- `app/ingest/sources/providers/rsdebate_dspace.py` — rsdebate.nic.in RS fallback: DSpace browse `?type=dateissued` pagination; item-page bitstream URL resolution (never constructs filenames); returns DocumentRef with format=pdf
- `app/ingest/sources/providers/internet_archive.py` — extended for RS: when corpus=RS, `citation_url` set to rsdebate.nic.in item URL derived from handle N extracted from IA identifier `eparlib.nic.in.{N}`; if handle not derivable, `citation_url` = null and warning logged (PRD v1.3 edge case: RS-via-IA with no DSpace handle)
- `app/ingest/sources/rs.py` — updated: RS corpus orchestrator using provider chain `[sansad_rs_html, internet_archive, rsdebate_dspace]`; date filter >= 2014-01-01; document-level dedup on `canonical_doc_id`; first provider yielding parseable content wins

Stop when: `sansad_rs_html.py` tests crawl fixture HTML listing and produce correct DocumentRef list for RS sittings; `rsdebate_dspace.py` tests resolve bitstream URL from fixture DSpace item page (no constructed filenames); `internet_archive.py` RS tests: (a) `citation_url` = rsdebate.nic.in URL when handle derivable from IA identifier; (b) `citation_url` = null + warning logged when identifier contains no derivable handle (PRD v1.3 edge case); `rs.py` integration test: sansad.in/rs HTML path preferred for recent sittings, IA fallback for older items, DSpace fallback for IA-missing items, no archive.org URL in any `citation_url`, checkpoint skip works on re-run.
Do not implement anything beyond Phase 9.
Tests: write and run tests for all items above before finishing.

---

## Phase 10 — v2.0 Ingestion: New Fields, CA Parsing, Shared Sequence

PRD sections: F01 (lang_original, time_of_day, word_count new fields; sequence_within_sitting on qa_exchanges; CA field-level parsing rules; shared sitting sequence assignment)
UI sections: none

Implement:
- `app/db/schema.sql` — add `lang_original` (VARCHAR(5) NOT NULL CHECK IN ('en','hi','mixed')), `time_of_day` (VARCHAR(5) NULL), `word_count` (INTEGER NULL) to `speeches` and `qa_exchanges`; add `sequence_within_sitting` (INTEGER NULL) to `qa_exchanges`; add composite sitting indexes `idx_speeches_sitting` and `idx_qa_sitting` per DATA-MODELS.md §1.1 and §1.2
- `app/ingest/segmenters/speech.py` — compute `lang_original` for all four F01 language-handling cases (case 1→`en`; cases 2 & 4→`hi`; case 3→`mixed` if genuinely alternating, `hi` if predominantly Hindi with only translation fragments); compute `word_count` (word count of `full_text_en`, null when `full_text_en` is null); accept `time_of_day` from parser and pass through to record dict
- `app/ingest/segmenters/qa.py` — same `lang_original` and `word_count` computation; accept and pass through `time_of_day`
- `app/ingest/parsers/html_parser.py` — CA date: derive from URL slug (`DD-MMM-YYYY`, e.g. `09-dec-1946`); discard any date found in HTML body even when present; CA subject: nearest preceding standalone bold section header in document order (not bold speaker names inside speech-grid rows); walk DOM, update current topic on each section header, assign to subsequent speeches until next header; if no header precedes first speech, fall back to first item's link text in page TOC `<ul>`; surface `time_of_day` from HTML timestamp elements where present (CA coi + RS sansad.in/rs); build-time verification: confirm CA TOC `<li><a href="#ID">` anchor IDs correspond to `id=` attributes on body elements — if mapping exists, use it for first-topic fallback; document finding
- `app/ingest/parsers/ia_text_parser.py` — `time_of_day` = None (IA pre-OCR text has no sitting start time)
- `app/ingest/parsers/pdf_parser.py` — `time_of_day` = None (PDF sources have no sitting start time)
- `app/ingest/sources/ca.py` — assign shared `sequence_within_sitting` across all speech and Q+A records within each sitting in document order (1-based; speech and Q+A share the sequence space, never the same number); assignment at orchestrator level after both segmenters have run for the sitting; build-time verification: confirm CA (coi HTML) format exposes a reliable interleaved order between speech and Q+A record types — document finding
- `app/ingest/sources/ls.py` — same shared `sequence_within_sitting` assignment; build-time verification: confirm IA text + DSpace PDF formats expose reliable interleaved order — document finding
- `app/ingest/sources/rs.py` — same shared `sequence_within_sitting` assignment; build-time verification: confirm sansad.in/rs HTML + IA + rsdebate PDF formats expose reliable interleaved order — document finding
- `app/ingest/indexer.py` — include `lang_original` and `time_of_day` in Meilisearch document push for both record types; include `sequence_within_sitting` in Q+A Meilisearch document (was previously excluded — DATA-MODELS §2.2 v2.0 adds it to Q+A docs); exclude `word_count` from Meilisearch (PostgreSQL-only per DATA-MODELS §2.2)
- `app/ingest/setup_meilisearch.py` — verify index configuration matches DATA-MODELS §2.3 exactly after v2.0 changes (`sequence_within_sitting` now in `sortableAttributes` for Q+A documents); correct any discrepancies; unit test asserts no deviation from DATA-MODELS §2.3

Stop when: `schema.sql` adds all five new columns and both composite sitting indexes without error on a clean PostgreSQL instance; segmenter tests compute `lang_original` correctly for all four language-handling cases and `word_count` correctly (null when `full_text_en` is null); `html_parser.py` tests confirm CA date derived from URL slug (body date discarded); CA subject tests confirm section-header walk assigns correct topics and TOC fallback activates when no header precedes first speech; `time_of_day` extracted from HTML fixture and None for IA/PDF; orchestrator tests confirm shared `sequence_within_sitting` assigned in document order across speech+Q+A in a fixture sitting (no number shared between the two types); `indexer.py` tests confirm `lang_original`, `time_of_day`, and Q+A `sequence_within_sitting` present in Meilisearch push and `word_count` absent; `setup_meilisearch.py` unit test passes against DATA-MODELS §2.3; build-time verification findings documented in test output or a comment in the relevant orchestrator/parser file.
Do not implement anything from Phase 11 or later.
Tests: write and run tests for all items above before finishing.

---

## Phase 11 — F05 Result Card Badges + F09 Record Detail Page

PRD sections: F05 (lang_original badge, time_of_day on result cards), F09 (record detail page)
UI sections: 02-ui-ux-spec.md (visual identity and card interaction patterns); ARCHITECTURE.md §3 (RecordDetail.jsx and useRecord.js spec); DATA-MODELS.md §3.3 (GET /api/record/{id} contract)

Implement:
- `app/api/routes/record.py` — GET /api/record/{id}; returns 404 with `{"error":"not_found","message":"Record not found."}` when no row in either table matches the id
- `app/api/services/record.py` — fetch one record by id: `SELECT ... FROM speeches WHERE id = $1 UNION ALL SELECT ... FROM qa_exchanges WHERE id = $1`; 404 if empty result; adjacent-neighbour query: union both tables for the same sitting (`source` + `date` + `sitting_number IS NOT DISTINCT FROM`), ordered by `sequence_within_sitting`, resolve `prev_id` (seq−1, null at lower boundary) and `next_id` (seq+1, null at upper boundary); compute `sitting_total` (count of all records in the same sitting across both tables); format response per DATA-MODELS §3.3: `proceeding_type_label`, `date_display` (DD Month YYYY), speech/Q+A fields null for the inapplicable record type
- `app/api/main.py` — register the record route (`/api/record/{id}`)
- `app/ui/src/components/SpeechCard.jsx` — replace `is_translated` indicator with `lang_original` badge (`hi`→"Hindi original", `mixed`→"Mixed language", `en`→no badge rendered); add `time_of_day` row near the date (rendered verbatim as "HH:MM"; omitted silently when null)
- `app/ui/src/components/QACard.jsx` — same `lang_original` badge and `time_of_day` row
- `app/ui/src/components/ResultCard.jsx` — wrap each card in a link to `/record/:id` (the record's `id` field from the search result)
- `app/ui/src/hooks/useRecord.js` — GET /api/record/{id}; loading, error, and 404 state (404 is a distinct state, not collapsed into error)
- `app/ui/src/pages/RecordDetail.jsx` — full text display + all metadata fields from DATA-MODELS §3.3 response; prev/next adjacent controls (disabled when `adjacent.prev_id` or `adjacent.next_id` is null — not hidden); position indicator "[sequence_within_sitting] of [sitting_total]"; back-nav: "← Back to results" when router location state carries a referrer, "← Search" when loaded via direct URL; 404 state renders "Record not found" message (no blank page, no JS error); loading state; error state with Retry
- `app/ui/src/main.jsx` — add `/record/:id` route pointing to RecordDetail.jsx

Stop when: GET /api/record/{id} returns correct full response for a fixture speech record and a fixture Q+A record (including adjacent nav, sitting_total, proceeding_type_label, date_display); 404 returned and rendered correctly when id does not exist in either table; SpeechCard and QACard render `lang_original` badge correctly for all three values (`hi`, `mixed`, `en`/absent) and render `time_of_day` when present, silent when null; ResultCard links correctly to /record/:id; RecordDetail.jsx renders full text, all metadata, prev/next controls (disabled at boundaries), position indicator, and correct back-nav for both in-app and direct-URL entry; all tests pass.
Do not implement anything from Phase 12 or later.
Tests: write and run tests for all items above before finishing.

---

## Phase 12 — Two-Stage Pipeline & Raw Document Store

PRD sections: F01 (two-stage pipeline; raw document store)
UI sections: none
ARCH sections: ARCHITECTURE.md §1/§4/§5, DATA-MODELS.md §1.4, DEPLOYMENT.md §3.5/§6.1/§6.4

Implement:
- `app/db/schema.sql` — add `raw_documents` table per DATA-MODELS §1.4: PK `canonical_doc_id TEXT`, `corpus VARCHAR(2) NOT NULL CHECK IN ('CA','LS','RS')`, `date DATE`, `provider VARCHAR(50) NOT NULL`, `format VARCHAR(10) NOT NULL CHECK IN ('html','ia_text','pdf')`, `extracted_text TEXT`, `metadata_json JSONB NOT NULL DEFAULT '{}'`, `fetch_url TEXT`, `citation_url TEXT`, `fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`; create `idx_raw_documents_corpus_date ON raw_documents(corpus, date)`
- `app/ingest/indexer.py` — add Stage 1 write path: `write_raw_document(canonical_doc_id, corpus, date, provider, format, extracted_text, metadata_json, fetch_url, citation_url)` inserts into `raw_documents` (no-op on PK conflict); `check_raw_document_exists(canonical_doc_id) → bool` (Stage 1 PK dedup guard — corpus orchestrators call this before fetching); `read_raw_documents_for_scope(corpus, date_from=None, date_to=None)` → iterator of `raw_documents` rows for Stage 2 to consume; existing `reindex_from_db()` and `update_index_status()` unchanged; `index_status` update remains Stage 2 completion only
- `app/ingest/main.py` — add `--stage fetch|process|all` argument (default `all`); add `--date-from YYYY-MM-DD` and `--date-to YYYY-MM-DD` to scope both stages: Stage 1 applies a post-parse date-window gate, writing only documents within the window to `raw_documents`; Stage 2 reads only `raw_documents` rows within the window; routing: `--stage fetch` → call each orchestrator's `run_stage1(date_from, date_to)` only; `--stage process` → call each orchestrator's `run_stage2()` only, passing `date_from`/`date_to`; `--stage all` → `run_stage1(date_from, date_to)` then `run_stage2(date_from, date_to)` for each source sequentially; remove `--date-override` (replaced by `--date-from`); update progress logging and completion summary to distinguish Stage 1 (documents written to `raw_documents`) from Stage 2 (records written to `speeches`/`qa_exchanges`)
- `app/ingest/checkpoints/store.py` — `processed_documents` semantics are Stage 2 complete signal only per ARCHITECTURE §5; remove any Stage 1 checkpoint writes (Stage 1 dedup is `raw_documents` PK lookup in PostgreSQL); `inserted_dedup_keys` unchanged
- `app/ingest/sources/ca.py` — split orchestrator into `run_stage1()` (discover → `coi_html` provider chain → `html_parser` → `indexer.write_raw_document()` per document; skip if `indexer.check_raw_document_exists(canonical_doc_id)` returns True) and `run_stage2(date_from=None, date_to=None)` (reads `raw_documents` rows via `indexer.read_raw_documents_for_scope('CA', date_from, date_to)` → segmenters → canonicalizers → `indexer.index_record()` → checkpoint); `run()` calls `run_stage1()` then `run_stage2()` for `--stage all`
- `app/ingest/sources/ls.py` — same Stage 1/2 split as CA; Stage 1 checks `raw_documents` PK before any fetch; Stage 2 reads from `raw_documents` for scope
- `app/ingest/sources/rs.py` — same Stage 1/2 split as CA; Stage 1 checks `raw_documents` PK before any fetch; Stage 2 reads from `raw_documents` for scope

Stop when: `schema.sql` creates the `raw_documents` table and `idx_raw_documents_corpus_date` index without error on a clean PostgreSQL instance; `indexer.write_raw_document()` inserts a row and is a no-op on PK conflict; `indexer.check_raw_document_exists()` returns True for an existing `canonical_doc_id` and False for an absent one; `--stage fetch` against mocked providers writes exactly one `raw_documents` row per document; `--stage process` against mocked `raw_documents` rows produces correct `speeches`/`qa_exchanges` records; Stage 1 re-run against an already-fetched corpus writes zero new rows (PK dedup skips all); Stage 2 re-run after interruption resumes from SQLite `processed_documents` checkpoint, skipping already-processed docs; `--stage process --date-from 2024-01-01 --date-to 2024-12-31` reads only the matching date range from `raw_documents` and writes no records outside that range; `--stage fetch --date-from 2024-01-01 --date-to 2024-12-31` writes only documents with dates within that range to `raw_documents` and skips all out-of-range documents; `--stage fetch` without a date filter writes all discovered documents regardless of date; `--stage all` produces identical final `speeches`/`qa_exchanges` state to running `--stage fetch` then `--stage process` separately; all existing Phase 1–11 tests pass without modification.
Do not implement anything beyond Phase 12.
Tests: write and run tests for all items above before finishing.
