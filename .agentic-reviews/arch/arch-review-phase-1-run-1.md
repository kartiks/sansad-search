# Arch Review — Phase 1 Run 1
Date: 2026-05-28
PRD version: v1.0
Prior run: first review

## Status: GAPS FOUND

## Gaps

| File | Issue | Severity | Non-Negotiable violated? |
|------|-------|----------|--------------------------|
| `app/api/main.py` | `allow_origins=["*"]` hardcodes a wildcard origin instead of reading the `ALLOWED_ORIGINS` environment variable. `DEPLOYMENT.md §2.1` declares `ALLOWED_ORIGINS` as a **Required** env var ("Comma-separated list of allowed CORS origins"). The variable is never read anywhere in the codebase. Production deployments will allow requests from any origin. Fix: read `os.environ.get("ALLOWED_ORIGINS", "")`, split on commas, and pass the list to `allow_origins`. Fall back to `["*"]` only if the variable is absent and the environment is explicitly dev. | Major | No |
| `app/api/lib/meilisearch_client.py` | Uses synchronous `meilisearch.Client`. `ARCHITECTURE.md §3` describes this file as "Shared Meilisearch **async** client (singleton, search key)". The `meilisearch-python` package provides `meilisearch.AsyncClient` for this purpose. Calling the synchronous client from async FastAPI route handlers (Phase 3) will block the event loop on every search request. Fix: replace `meilisearch.Client` with `meilisearch.AsyncClient` and update `get_client()` to return the async variant. This must be resolved before Phase 3 implements search routes that call this client. | Major | No |
| `app/` folder structure | `app/db/schema.sql` resides in an `app/db/` subdirectory that does not appear in `ARCHITECTURE.md §3` (Folder Structure). `DEPLOYMENT.md §3.3` does reference `app/db/schema.sql` explicitly, but `ARCHITECTURE.md §3` is the authoritative folder structure and is silent on `db/`. Fix: add `db/schema.sql` to the folder structure in `ARCHITECTURE.md §3`. No code change required; this is a documentation gap only. | Minor | No |
| `app/pyproject.toml` | `requires-python = ">=3.9"` contradicts `ARCHITECTURE.md §2` which specifies Python 3.12 as the targeted runtime. A developer installing on Python 3.9–3.11 will not receive a clear error and may encounter runtime failures (e.g. `asyncpg` behavior differences, type annotation syntax). Fix: set `requires-python = ">=3.12"`. | Minor | No |

## Escalations

None. All gaps have clear fixes with no architectural conflict.

## Verified

- **Non-Negotiables (all 8):** Correctly followed for Phase 1 scope.
  - NNG-1 (PostgreSQL as primary store): `schema.sql` defines `speeches`, `qa_exchanges`, `index_status` tables exactly per `DATA-MODELS.md §1`. `db.py` uses asyncpg for the API layer only. No storage SDK imported outside the designated lib files.
  - NNG-2 (Meilisearch as search engine): `meilisearch_client.py` and `setup_meilisearch.py` correctly use the Meilisearch Python client. No alternative search backend referenced.
  - NNG-3 (Query expansion server-side only): No synonym or expansion logic exists in the frontend files produced in Phase 1. The `setup_meilisearch.py` correctly places synonym loading in the ingest layer, not in any frontend code.
  - NNG-4 (`data/synonyms.json` sole synonym source): `setup_meilisearch.py` reads exclusively from `data/synonyms.json` at the correct path (`Path(__file__).parent.parent / "data" / "synonyms.json"`). No synonym definitions hardcoded elsewhere.
  - NNG-5 (`index_status` sole source for F07): `index_status` table defined correctly in schema. No Meilisearch document count queries in any Phase 1 code.
  - NNG-6 (Cookie-only for F08): F08 is out of Phase 1 scope. No server-side user data introduced.
  - NNG-7 (Ingestion pipeline local CLI only): No `/api/ingest` endpoint or equivalent created. `setup_meilisearch.py` and parsers/segmenters are CLI/library code only.
  - NNG-8 (React SPA, no SSR): `app/ui/` correctly wires Vite + React 18 with no SSR configuration.
- **Storage abstraction:** `html_parser.py`, `pdf_parser.py`, `speech.py`, `qa.py` import no database or search SDKs. All storage interactions are confined to `api/lib/db.py` (asyncpg), `api/lib/meilisearch_client.py` (meilisearch client), and `ingest/setup_meilisearch.py` (ingest-side, acceptable).
- **`schema.sql` vs `DATA-MODELS.md`:** All columns, types, constraints, and indexes for `speeches`, `qa_exchanges`, and `index_status` match `DATA-MODELS.md §§1.1–1.3` exactly. GIN index on `questioner_names TEXT[]` present. `gen_random_uuid()` used correctly (requires `pgcrypto` extension; `CREATE EXTENSION IF NOT EXISTS "pgcrypto"` is present).
- **Meilisearch index configuration (`setup_meilisearch.py`):** `searchableAttributes`, `filterableAttributes`, `sortableAttributes`, `rankingRules`, `typoTolerance`, and `pagination.maxTotalHits` all match `DATA-MODELS.md §2.3` exactly.
- **Synonym synonym structure:** `_load_synonyms()` correctly converts JSON groups into the `{word: [synonyms]}` format required by the Meilisearch synonyms API. Full-replace semantics via `update_synonyms()` match the architectural decision.
- **Separation of concerns:** Parsers produce raw dicts; segmenters consume raw dicts and produce structured unit dicts. No premature canonicalization or indexing in Phase 1 components.
- **`MEILISEARCH_MASTER_KEY` vs `MEILISEARCH_SEARCH_KEY` boundary:** `setup_meilisearch.py` correctly uses `MEILISEARCH_MASTER_KEY`. `meilisearch_client.py` correctly uses `MEILISEARCH_SEARCH_KEY`. Key boundary preserved.
- **Folder structure (implemented files):** All Phase 1 files placed in correct directories per `ARCHITECTURE.md §3`. `api/routes/__init__.py` and `api/services/__init__.py` stub files correctly scaffold the structure for Phase 3. `ingest/canonical/`, `ingest/checkpoints/`, `ingest/sources/` stub `__init__.py` files correctly scaffold for Phase 2.
- **FastAPI skeleton:** Lifespan hooks for asyncpg pool init/teardown correctly wired. CORS middleware present.
- **Tech stack alignment:** FastAPI 0.111.0, React 18, Vite 5, asyncpg, psycopg2-binary, meilisearch-python, httpx, BeautifulSoup4, PyMuPDF, pytesseract, python-dotenv — all match `ARCHITECTURE.md §2`.
- **Frontend deps:** `react-router-dom` v6 and `js-cookie` both present in `package.json` per `ARCHITECTURE.md §2`.
- **Language handling (speech segmenter):** All four cases (English, translated Hindi, bilingual, Hindi-only) correctly implemented in `_detect_language_handling()` with appropriate `full_text_en`, `is_translated`, `has_untranslated_content` values.
- **Exclusion rules (speech segmenter):** Unattributed speech patterns (`SEVERAL HON. MEMBERS`, etc.) and presiding officer patterns correctly detected and excluded.
- **Key Data Flows:** Synonym deploy flow (`synonyms.json → setup_meilisearch.py → Meilisearch API`) correctly implemented and matches `ARCHITECTURE.md §4`.
