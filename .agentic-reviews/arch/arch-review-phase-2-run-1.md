# Arch Review — Phase 2 Run 1
Date: 2026-05-28
PRD version: v1.0
Prior run: first review

## Status: GAPS FOUND

## Gaps

| File | Issue | Severity | Non-Negotiable violated? |
|------|-------|----------|--------------------------|
| `app/ingest/sources/_http.py` | File exists but is absent from `ARCHITECTURE.md §3` (Folder Structure). The Coding Agent introduced `_http.py` as a shared HTTP utility module reused by `ca.py`, `ls.py`, and `rs.py`. This is a sound refactoring (shared retry logic, `RobotsChecker`, and `fetch_with_retry` extracted into one place) but the file is not documented in the architecture. `ARCHITECTURE.md §3` lists only `ca.py`, `ls.py`, `rs.py` inside `sources/`. Fix: add `_http.py` to the `ingest/sources/` block in `ARCHITECTURE.md §3` with description "Shared HTTP utility: `USER_AGENT`, `RobotsChecker`, `fetch_with_retry` with 4xx/5xx/429 error handling per F01 spec". No code change required. | Minor | No |

## Escalations

None. The `_http.py` module is a straightforward, well-scoped shared utility. No architectural conflict; the folder structure doc gap is the only action required.

## Verified

**Non-Negotiables (all 8):**
- NNG-1 (PostgreSQL as primary store): `indexer.py` writes all canonical records to `speeches` and `qa_exchanges` via psycopg2. `reindex_from_db()` reads from PostgreSQL and pushes to Meilisearch — never re-scrapes. `update_index_status()` writes to `index_status` after each run. ✓
- NNG-2 (Meilisearch as search engine): `_connect_meilisearch()` in `main.py` uses `meilisearch.Client` (synchronous — correct for ingestion). No alternative search backend referenced. ✓
- NNG-3 (Query expansion server-side only): No synonym or expansion logic anywhere in Phase 2. ✓
- NNG-4 (`data/synonyms.json` sole synonym source): No synonym loading or hardcoded synonyms in any Phase 2 file. ✓
- NNG-5 (`index_status` sole source for F07): `indexer.update_index_status()` correctly writes one row to `index_status` at run completion. No Meilisearch document count queries. ✓
- NNG-6 (Cookie-only for F08): Not touched in Phase 2. ✓
- NNG-7 (Ingestion pipeline is local CLI only): `main.py` is a CLI script invoked via `python -m ingest.main`. No API trigger endpoint created or referenced. ✓
- NNG-8 (React SPA, no SSR): Not touched in Phase 2. ✓

**Storage abstraction:**
- `psycopg2` imported only in `ingest/main.py` (`_connect_postgres()`). `indexer.py` takes `pg_conn: Any` as a constructor argument and uses standard DBAPI2 interface — does not import psycopg2 directly. ✓
- `meilisearch.Client` (sync) instantiated only in `ingest/main.py` (`_connect_meilisearch()`). `indexer.py` takes `meili_client: Any` — no direct meilisearch import. ✓
- `sqlite3` imported only in `ingest/checkpoints/store.py` — the designated checkpoint abstraction layer. ✓
- `canonical/names.py`, `canonical/sessions.py`, `sources/ca.py`, `sources/ls.py`, `sources/rs.py`, `sources/_http.py` — none import any storage SDK. ✓
- Ingestion uses `meilisearch.Client` (synchronous), API uses `meilisearch.AsyncClient` — correct split per ARCHITECTURE.md §2. ✓

**Key Data Flows:**
- **Bulk ingestion flow** correctly implemented end-to-end: `main.py` (CLI) → `CASource/LSSource/RSSource` (enumerators) → `httpx.AsyncClient` (HTTP fetcher) → `parse_html/parse_pdf` (parsers) → `segment_speeches/segment_qa` (segmenters) → `_canonicalize_record()` (canonicalizer) → `indexer.index_record()` → psycopg2 INSERT (PostgreSQL writer) → `indexer.flush()` → `index.add_documents()` (Meilisearch push) → `indexer.update_index_status()` (completion). ✓
- **Re-indexing flow** correctly implemented: `--reindex-from-db` flag → `indexer.reindex_from_db()` → `SELECT * FROM speeches UNION ALL SELECT * FROM qa_exchanges` → batch push to Meilisearch. No re-scraping. ✓
- ARCHITECTURE.md §4 data flows table already covers both flows — no update needed. ✓

**Folder structure:**
- `ingest/sources/ca.py`, `ls.py`, `rs.py` ✓
- `ingest/canonical/names.py`, `sessions.py` ✓
- `ingest/checkpoints/store.py` ✓
- `ingest/indexer.py` ✓
- `ingest/main.py` ✓
- `ingest/sources/_http.py` — present on disk but absent from ARCHITECTURE.md §3 (flagged above as Minor).

**DATA-MODELS.md alignment:**
- `_SPEECH_COLUMNS` in `indexer.py` matches `DATA-MODELS.md §1.1` exactly (excludes `id` (PK/auto) and `created_at` (default)). ✓
- `_QA_COLUMNS` matches `DATA-MODELS.md §1.2` exactly. ✓
- `_MEILI_EXCLUDED` = `{page_reference, ocr_low_confidence, has_untranslated_content, session_number, created_at, dedup_key}` matches `DATA-MODELS.md §2.2` exclusion list exactly. ✓
- `build_dedup_key()` implements `DATA-MODELS.md §1.4` format exactly: speech key `{source}_{date}_{sitting}_{pt}_{speaker_norm}_{seq}`, Q+A key `{source}_{date}_{sitting}_{pt}_{qnum}`. ✓
- `normalize_for_dedup()` correctly implements the spec: lowercase → strip non-alphanumeric chars → spaces to underscores. ✓
- `update_index_status()` INSERT matches all `index_status` columns in `DATA-MODELS.md §1.3`. ✓

**Separation of concerns:**
- Sources handle URL enumeration and HTTP fetching only — no parsing, segmentation, or DB writes. ✓
- `_http.py` is a pure HTTP utility (retry, robots.txt, error handling). ✓
- `canonical/names.py` and `canonical/sessions.py` handle text normalization only — no I/O. ✓
- `checkpoints/store.py` is a self-contained SQLite abstraction — no HTTP or PG imports. ✓
- `indexer.py` handles DB writes and Meilisearch pushes only — takes dependencies via constructor, no HTTP imports. ✓
- `main.py` is the orchestrator: wires all layers, owns environment variable reading and connection setup. ✓

**HTTP error handling per F01 spec (PHASES.md Phase 2):**
- 4xx (excl. 429) → `logger.warning` + return `None` (caller skips). ✓
- 5xx → exponential backoff, up to `MAX_RETRIES_5XX=3` retries, then return `None`. ✓
- 429 → infinite exponential backoff (`while True` loop), never return `None`. ✓
- robots.txt → `RobotsChecker` fetches per-domain on first request, caches result; disallowed URLs skipped with warning. ✓

**Sync/async pattern (ingestion):**
The ingestion pipeline uses async I/O for HTTP (httpx AsyncClient) and synchronous calls for PostgreSQL (psycopg2) and Meilisearch (meilisearch.Client). This is an intentional design per ARCHITECTURE.md §2 ("psycopg2 (ingestion)"). For a single-purpose CLI tool, blocking the event loop on DB/Meilisearch writes is acceptable — only HTTP benefits from async concurrency. No architecture violation. ✓

**`MEILISEARCH_MASTER_KEY` boundary:**
`main.py` uses `MEILISEARCH_MASTER_KEY` for the ingestion meilisearch client — correct per NNG-2 and DEPLOYMENT.md §2.3 ("master key used only during ingestion"). ✓
