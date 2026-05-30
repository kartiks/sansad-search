# Arch Review — Phase 1 Run 2
Date: 2026-05-28
PRD version: v1.0
Prior run: run-1 GAPS FOUND — 2 Major (CORS wildcard; sync Meilisearch client), 2 Minor (db/ folder missing from ARCHITECTURE.md §3; pyproject.toml requires-python too broad)

## Status: CLEAR

## Gaps

No gaps found.

## Escalations

None.

## Verified

**Run-1 gap resolution — all 4 confirmed fixed:**

- **Gap 1 resolved (`app/api/main.py`):** `_allowed_origins()` reads `ALLOWED_ORIGINS` env var, splits on commas, filters blank entries, and falls back to `["*"]` only when the variable is absent or empty. Correctly called at `add_middleware()` registration time. Production deployments with `ALLOWED_ORIGINS` set will receive a properly scoped origin list.
- **Gap 2 resolved (`app/api/lib/meilisearch_client.py`):** `meilisearch.AsyncClient` used throughout (`_client` type annotation, instantiation, and return type all updated). Singleton pattern intact. `MEILISEARCH_SEARCH_KEY` boundary preserved. Phase 3 search routes can call async Meilisearch methods without blocking the event loop.
- **Gap 3 resolved (`arch/ARCHITECTURE.md §3`):** `db/schema.sql` entry added to the folder structure with correct description. ARCHITECTURE.md §3 and DEPLOYMENT.md §3.3 are now consistent.
- **Gap 4 resolved (`app/pyproject.toml`):** `requires-python = ">=3.12"` matches ARCHITECTURE.md §2 Python 3.12 target.

**Carried forward from run-1 — all still verified:**

- **Non-Negotiables (all 8):** No changes to any non-negotiable-governed code in this rework. All 8 remain correctly followed.
- **Storage abstraction:** No storage SDK imports outside `api/lib/db.py`, `api/lib/meilisearch_client.py`, and `ingest/setup_meilisearch.py`. No regressions introduced by the four targeted fixes.
- **`schema.sql` vs `DATA-MODELS.md`:** Unchanged. All columns, types, constraints, and indexes for `speeches`, `qa_exchanges`, and `index_status` match `DATA-MODELS.md §§1.1–1.3` exactly.
- **Meilisearch index configuration:** `setup_meilisearch.py` unchanged. All settings match `DATA-MODELS.md §2.3`.
- **Synonym source-of-truth:** `setup_meilisearch.py` reads exclusively from `data/synonyms.json`. No hardcoded synonyms anywhere.
- **`MEILISEARCH_MASTER_KEY` / `MEILISEARCH_SEARCH_KEY` boundary:** Unchanged and correct.
- **Separation of concerns:** Parsers and segmenters import no storage or search SDKs. No changes to these files.
- **Folder structure:** All Phase 1 files in correct locations. ARCHITECTURE.md §3 now matches the on-disk `app/db/` directory.
- **FastAPI skeleton:** Lifespan hooks unchanged and correct. CORS middleware fix does not alter startup sequence.
- **Tech stack alignment:** Requirements unchanged.
- **Frontend SPA shell:** `package.json`, `vite.config.js`, `index.html` unchanged.
- **Language handling and exclusion rules (segmenters):** Unchanged and correct.
- **Key Data Flows:** All flows in ARCHITECTURE.md §4 correctly implemented for Phase 1 scope.
