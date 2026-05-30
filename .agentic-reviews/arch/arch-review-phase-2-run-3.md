# Arch Review — Phase 2 Run 2
Date: 2026-05-28
PRD version: v1.0
Prior run: run-2 CLEAR — no gaps; confirmed _http.py documented in ARCHITECTURE.md §3

## Status: CLEAR

## Gaps

No gaps found.

## Escalations

None.

## Verified

No code or architecture changes since run-2. All prior verification findings carry forward unchanged.

**Non-Negotiables (all 8):** Unchanged and correctly followed.
- NNG-1 (PostgreSQL as primary store): `indexer.py` writes to `speeches`/`qa_exchanges` via psycopg2; `reindex_from_db()` reads from PostgreSQL, never re-scrapes; `update_index_status()` writes to `index_status` on completion. ✓
- NNG-2 (Meilisearch as search engine): Ingestion uses synchronous `meilisearch.Client` (correct for CLI). No alternative backend. ✓
- NNG-3 (Query expansion server-side only): No synonym/expansion logic in any Phase 2 file. ✓
- NNG-4 (`synonyms.json` sole synonym source): No synonym loading or hardcoding in Phase 2. ✓
- NNG-5 (`index_status` sole source for F07): `update_index_status()` writes one row per run. No Meilisearch document count queries. ✓
- NNG-6 (Cookie-only for F08): Not touched. ✓
- NNG-7 (Ingestion CLI only): `main.py` is a local CLI script. No API trigger endpoint. ✓
- NNG-8 (React SPA, no SSR): Not touched. ✓

**Storage abstraction:** `psycopg2` and `meilisearch.Client` instantiated only in `ingest/main.py`. `indexer.py` takes both as constructor args — no direct storage SDK imports. `sqlite3` confined to `checkpoints/store.py`. All source, canonical, and parser/segmenter modules import no storage SDKs. ✓

**Folder structure:** `ARCHITECTURE.md §3` accurately documents all Phase 2 files including `ingest/sources/_http.py`. ✓

**DATA-MODELS.md alignment:** `_SPEECH_COLUMNS`, `_QA_COLUMNS`, `_MEILI_EXCLUDED`, dedup key format, and `index_status` INSERT all match DATA-MODELS.md §§1.1–1.4 and §2.2 exactly. ✓

**Key Data Flows:** Bulk ingestion and re-indexing flows correctly implemented end-to-end. ARCHITECTURE.md §4 accurately describes both flows. ✓

**Separation of concerns:** Sources → HTTP only; canonical → text normalization only; checkpoints → SQLite abstraction only; indexer → DB/Meilisearch writes only; main.py → orchestration. ✓

**HTTP error handling:** 4xx/5xx/429/robots.txt per F01 spec. ✓

**`MEILISEARCH_MASTER_KEY` boundary:** Ingestion uses master key; API uses search key. ✓
