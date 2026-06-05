# Deployment — SansadSearch

**PRD version:** v2.0
**Generated:** 2026-05-28 (v1.0); updated 2026-05-29 (v1.1); updated 2026-05-30 (ingestion source redesign — per-source base-URL overrides; Internet Archive bulk path; reconciled to PRD v1.2: OCR removed, no Tesseract dependency); reviewed 2026-05-31 for PRD v1.3 — no deployment-relevant changes (RS-via-IA citation rule is an ingestion-logic change only; no new env vars, dependencies, or infrastructure); updated 2026-06-01 — added §6 Operations (full clean reindex and Meilisearch-only reindex runbooks); updated 2026-06-01 for PRD v2.0 — §6.3 schema migration for F01 new columns/indexes + re-ingestion; no new env vars, dependencies, or infrastructure (F09 detail endpoint reuses the existing Railway Postgres pool); updated 2026-06-03 — raw document store: §3.3/§3.5/§6.1 updated for `raw_documents`; §6.4 selective re-processing runbook added; no new env vars, dependencies, or infrastructure

---

## 1. Hosting Platform

| Component | Platform | Rationale |
|-----------|----------|-----------|
| FastAPI API | Railway | Managed Python deployment; same platform as PostgreSQL; straightforward env var config |
| PostgreSQL | Railway (managed) | Co-located with the API; managed backups; no separate Postgres host to manage |
| React SPA | Vercel | CDN-edge static file serving; zero-config Vite build integration |
| Search engine | Meilisearch Cloud | Fully managed; no search infrastructure to provision |

---

## 2. Environment Variables

### 2.1 API (Railway — runtime)

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Required | Railway PostgreSQL connection string (auto-injected by Railway when Postgres is provisioned in the same project) |
| `MEILISEARCH_URL` | Required | Meilisearch Cloud instance URL (e.g. `https://xxx.meilisearch.io`) |
| `MEILISEARCH_SEARCH_KEY` | Required | Meilisearch search-only API key; used by the API at runtime; never grants write or admin access |
| `ALLOWED_ORIGINS` | Required | Comma-separated list of allowed CORS origins (e.g. `https://sansadsearch.vercel.app,http://localhost:5173`) |
| `PORT` | Optional | HTTP port; Railway injects this automatically; defaults to 8000 |

### 2.2 Frontend (Vercel — build-time)

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_API_URL` | Required | FastAPI API base URL (e.g. `https://sansadsearch-api.up.railway.app`); baked into the static build at deploy time |

### 2.3 Ingestion pipeline (local — operator's machine)

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Required | PostgreSQL connection string (Railway connection string with SSL) |
| `MEILISEARCH_URL` | Required | Meilisearch Cloud instance URL |
| `MEILISEARCH_MASTER_KEY` | Required | Meilisearch master API key; used only during ingestion and Meilisearch setup; never deployed to the API |
| `INGESTION_RATE_LIMIT_DELAY_MS` | Optional | Inter-request delay in ms for source fetching; default 2000 |
| `COI_BASE_URL` | Optional | constitutionofindia.net base (CA provider); default in code. Override only if the host changes |
| `IA_BASE_URL` | Optional | Internet Archive base (`https://archive.org`); LS/RS preferred bulk path; default in code |
| `EPARLIB_BASE_URL` | Optional | eparlib.sansad.in base (LS DSpace fallback); default in code. Item IDs preserved from the legacy `eparlib.nic.in` host |
| `RSDEBATE_BASE_URL` | Optional | rsdebate.nic.in base (RS DSpace fallback); default in code |
| `SANSAD_RS_BASE_URL` | Optional | sansad.in base for the `/rs/debates/officials` RS HTML front end; default in code |

Per-source base URLs are **overrides, not document URLs** — document URLs are always discovered at runtime from listing/browse pages (ARCHITECTURE.md §5 "Listing-page-driven discovery"). These env vars exist only to re-point a provider if a host migrates.

`MEILISEARCH_MASTER_KEY` must never be set as an environment variable on the Railway API service. The search-only `MEILISEARCH_SEARCH_KEY` is used at runtime.

---

## 3. Build and Deploy Process

### 3.1 API (Railway)

Railway detects the Python project from `pyproject.toml`. The build and start commands are configured in Railway's service settings:

```
Build command:  pip install -r requirements.txt
Start command:  uvicorn api.main:app --host 0.0.0.0 --port $PORT
```

Railway auto-injects `DATABASE_URL` when the PostgreSQL plugin is added to the project. All other env vars are set manually in the Railway service environment.

Railway performs a zero-downtime deploy on each push to the connected git branch.

### 3.2 Frontend (Vercel)

Vercel auto-detects the Vite project from `ui/package.json`. Configure in Vercel project settings:

```
Root directory:    app/ui
Build command:     npm run build
Output directory:  dist
```

`VITE_API_URL` is set as a Vercel environment variable. Vercel rebuilds and deploys on each push to the connected branch.

### 3.3 Database schema init (one-time)

Run once against the Railway PostgreSQL instance before the first ingestion:

```bash
psql $DATABASE_URL -f app/db/schema.sql
```

`app/db/schema.sql` contains the `CREATE TABLE` statements for `speeches`, `qa_exchanges`, `raw_documents`, and `index_status` with all indexes.

### 3.4 Meilisearch setup (one-time, and on synonym updates)

Run from the operator's machine before the first ingestion or after any `synonyms.json` update:

```bash
cd app
python -m ingest.setup_meilisearch
```

This script:
1. Creates the `parliamentary_records` index if it does not exist
2. Configures `searchableAttributes`, `filterableAttributes`, `sortableAttributes`, `rankingRules`, `typoTolerance`, and `pagination.maxTotalHits`
3. Loads `data/synonyms.json` and pushes all synonym pairs to the Meilisearch synonyms API (full replace, not incremental)

Requires `MEILISEARCH_URL` and `MEILISEARCH_MASTER_KEY` in the local environment.

### 3.5 Bulk ingestion (one-time, operator's machine)

```bash
cd app
# Run both stages end-to-end (default — fetch, parse, segment, index):
python -m ingest.main --source all

# Run Stage 1 only (fetch + parse → raw_documents):
python -m ingest.main --source all --stage fetch

# Run Stage 2 only (segment + index from raw_documents):
python -m ingest.main --source all --stage process

# Stage 2 for a date range (selective re-processing — requires prior Stage 1 for that scope):
python -m ingest.main --source ls --stage process --date-from 2024-01-01 --date-to 2024-12-31
```

`--source` options: `ca`, `ls`, `rs`, `all`. Applies to both stages. `--stage` options: `fetch`, `process`, `all` (default `all`). `--date-from`/`--date-to` apply to Stage 2 only — they scope which rows are read from `raw_documents`; Stage 1 ignores them.

Stage 1 writes to Railway PostgreSQL (`raw_documents` table) and the Meilisearch index is not touched until Stage 2. Stage 2 reads from `raw_documents`, writes to `speeches`/`qa_exchanges`, and pushes to Meilisearch Cloud. The local `data/ingestion_checkpoints.db` SQLite file tracks Stage 2 progress for resumability. Re-running resumes from the last checkpoint.

Ingestion duration is unbounded (PRD INF-P1). The operator does not need to supervise; real-time progress is logged to stdout.

### 3.6 Re-indexing Meilisearch from PostgreSQL

If the Meilisearch index needs to be rebuilt (schema change, index corruption, plan migration):

```bash
cd app
python -m ingest.indexer --reindex-from-db
```

This reads all records from `speeches` and `qa_exchanges` in PostgreSQL and pushes them to Meilisearch in batches. Does not re-scrape any source websites. Does not update the checkpoint store.

---

## 4. Infrastructure Dependencies

| Dependency | Required for | Notes |
|------------|-------------|-------|
| Railway PostgreSQL | API (status endpoint), Ingestion | Must be provisioned before first deploy and before first ingestion run |
| Meilisearch Cloud instance | API (all search), Ingestion | Must be set up and configured (`setup_meilisearch.py` run) before first ingestion |
| Vercel project | Frontend | Connected to the repo; `VITE_API_URL` env var set |
| Internet Archive (archive.org) | Ingestion (preferred LS/RS bulk path) | Remote; no provisioning. Pre-OCR `_djvu.txt` + metadata JSON over HTTP. For IA-missing items the pipeline falls back to embedded-text extraction from the DSpace PDF (no OCR) |
| Source sites (constitutionofindia.net, eparlib.sansad.in, rsdebate.nic.in, sansad.in/rs) | Ingestion (per-corpus providers) | Remote; no provisioning. Rate-limited, robots.txt-compliant HTTP reads |
| PyMuPDF system deps | Ingestion only (direct DSpace PDF fallback; embedded-text extraction, no OCR) | Installed via `pip install PyMuPDF`; no additional system deps required on most platforms |

---

## 5. Local Development Setup

### 5.1 Prerequisites

- Python 3.12+
- Node.js 20+
- PostgreSQL 16 (local instance, or use the Railway connection string directly)
- A Meilisearch instance — either a local Meilisearch binary or a Meilisearch Cloud dev instance

### 5.2 Python environment

```bash
cd app
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 5.3 Frontend

```bash
cd app/ui
npm install
```

### 5.4 Environment variables

Create `app/.env` (not committed):

```env
DATABASE_URL=postgresql://localhost/sansadsearch
MEILISEARCH_URL=http://localhost:7700
MEILISEARCH_MASTER_KEY=local_dev_master_key
MEILISEARCH_SEARCH_KEY=local_dev_search_key
ALLOWED_ORIGINS=http://localhost:5173
```

Create `app/ui/.env.local` (not committed):

```env
VITE_API_URL=http://localhost:8000
```

### 5.5 Start services

**API:**
```bash
cd app
uvicorn api.main:app --reload --port 8000
```

**Frontend:**
```bash
cd app/ui
npm run dev
```

Frontend dev server runs on `http://localhost:5173` and proxies API calls to `http://localhost:8000`.

### 5.6 Running ingestion locally

Requires a local or remote PostgreSQL instance and a local or cloud Meilisearch instance. Set environment variables as above, then:

```bash
# First-time: set up Meilisearch index
python -m ingest.setup_meilisearch

# Run ingestion (CA only for development)
python -m ingest.main --source ca
```

---

## 6. Operations

### 6.1 Full clean reindex

Use when PostgreSQL data is stale, corrupt, or incomplete — wipes all state and re-ingests from source.

**Step 1 — Clear the ingestion checkpoint store**

```bash
rm app/data/ingestion_checkpoints.db
```

This SQLite file is local to the operator's machine. Deleting it forces the pipeline to treat every document as unseen.

**Step 2 — Truncate PostgreSQL tables**

```bash
psql $DATABASE_URL -c "TRUNCATE TABLE speeches, qa_exchanges, raw_documents, index_status RESTART IDENTITY CASCADE;"
```

All four tables must be truncated together. `raw_documents` holds the Stage 1 checkpoint — truncating it forces Stage 1 to re-fetch every source document. `RESTART IDENTITY` resets primary-key sequences. `CASCADE` handles any foreign-key constraints.

**Step 3 — Delete all documents from the Meilisearch index**

```bash
curl -X DELETE "$MEILISEARCH_URL/indexes/parliamentary_records/documents" \
  -H "Authorization: Bearer $MEILISEARCH_MASTER_KEY"
```

This issues a Meilisearch task. The index itself (settings, synonyms, ranking rules) is preserved — only documents are deleted. Wait for the task to complete before starting ingestion; poll `$MEILISEARCH_URL/tasks/{taskUid}` or check the Meilisearch Cloud dashboard.

**Step 4 — Run full ingestion**

```bash
cd app
python -m ingest.main --source all
```

Ingests all corpora (CA, LS, RS) from source. Progress is logged to stdout; a fresh `ingestion_checkpoints.db` is created automatically. The run is resumable: if interrupted, re-run the same command to continue from the last checkpoint.

---

### 6.2 Meilisearch-only reindex

Use when PostgreSQL data is intact but the Meilisearch index is stale, corrupt, or has been deleted (e.g. after a plan migration, index setting change, or accidental deletion). Does not re-scrape any source websites.

```bash
cd app
python -m ingest.indexer --reindex-from-db
```

Reads all records from `speeches` and `qa_exchanges` in PostgreSQL and pushes them to Meilisearch in batches. Does not modify the checkpoint store or PostgreSQL data. See §3.6 for full details.

If the Meilisearch index settings need to be re-applied first (e.g. after deleting the index entirely), run `python -m ingest.setup_meilisearch` before the reindex (§3.4).

---

### 6.3 PRD v2.0 migration (F01 new fields + F09)

---

### 6.4 Selective re-processing (Stage 2 only)

Use when `raw_documents` contains fetched content but the segmented output in `speeches`/`qa_exchanges` needs to be regenerated for a scope — without re-fetching source documents. Typical scenarios: segmentation logic changed; a parser fix applies to a date range; an indexer schema change affects a subset of records.

**Clearing is mandatory before re-running Stage 2.** Stage 2 inserts with `ON CONFLICT DO NOTHING`. Running Stage 2 without clearing first produces no changes to already-indexed records.

**Step 1 — Delete records from PostgreSQL for the scope**

```sql
-- Example: re-process all LS records for 2024
DELETE FROM speeches   WHERE source = 'LS' AND date BETWEEN '2024-01-01' AND '2024-12-31';
DELETE FROM qa_exchanges WHERE source = 'LS' AND date BETWEEN '2024-01-01' AND '2024-12-31';
```

Match the `source` and date range to the `--source`/`--date-from`/`--date-to` values you will use in Step 4.

**Step 2 — Delete Meilisearch documents for the scope**

```bash
curl -X POST "$MEILISEARCH_URL/indexes/parliamentary_records/documents/delete" \
  -H "Authorization: Bearer $MEILISEARCH_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"filter": "source = \"LS\" AND date >= \"2024-01-01\" AND date <= \"2024-12-31\""}'
```

Wait for the task to complete before proceeding (poll `$MEILISEARCH_URL/tasks/{taskUid}` or check the Meilisearch Cloud dashboard).

**Step 3 — Delete SQLite `processed_documents` entries for the scope**

```python
import sqlite3
db = sqlite3.connect('data/ingestion_checkpoints.db')
# Scope to corpus + processed_at date range matching the records you cleared above:
db.execute("""
    DELETE FROM processed_documents
    WHERE corpus = 'LS'
    AND processed_at >= '2024-01-01'
    AND processed_at < '2025-01-01'
""")
db.commit()
db.close()
```

To clear a full corpus: `DELETE FROM processed_documents WHERE corpus = 'LS';`

**Step 4 — Re-run Stage 2**

```bash
cd app
python -m ingest.main --source ls --stage process --date-from 2024-01-01 --date-to 2024-12-31
```

Stage 2 reads from `raw_documents` for the given scope, re-segments, re-canonicalizes, and re-indexes. Stage 1 fetch cost is not paid again.

---

### 6.5 Selective corpus clear (`clear_corpus.py`)

`app/scripts/clear_corpus.py` automates steps 1–3 of §6.4 (and the equivalent clearing steps from §6.1) — deleting data across PG, SQLite, and Meilisearch for a corpus and optional date range before a re-run.

Either `--stage` or `--target` must be given; they are mutually exclusive.

```bash
cd app

# Dry-run: print counts without deleting anything
python scripts/clear_corpus.py --corpus ls --stage process --dry-run

# Clear Stage 2 output for LS (leaves raw_documents intact — use before re-running Stage 2)
python scripts/clear_corpus.py --corpus ls --stage process

# Clear Stage 2 output for LS for a date range only
python scripts/clear_corpus.py --corpus ls --stage process --date-from 2024-01-01 --date-to 2024-12-31

# Clear all stores including raw_documents (use before re-fetching from source)
python scripts/clear_corpus.py --corpus ls --stage fetch

# Clear all corpora, Stage 2 output only
python scripts/clear_corpus.py --corpus all --stage process

# Explicit per-store control: clear only the Meilisearch index for RS
python scripts/clear_corpus.py --corpus rs --target meili
```

**`--stage` semantics (recommended for most operations):**

| `--stage` | PG tables cleared | SQLite | Meilisearch | Use when |
|-----------|-------------------|--------|-------------|----------|
| `process` | `speeches`, `qa_exchanges` | `processed_documents` | yes | Re-running Stage 2 from existing raw docs |
| `fetch` | `speeches`, `qa_exchanges`, `raw_documents` | `processed_documents` | yes | Re-fetching from source (both stages re-run) |

**`--target` flag (explicit per-store control):**

| `--target` | What is cleared |
|------------|----------------|
| `pg` | `speeches`, `qa_exchanges`, `raw_documents` |
| `sqlite` | `processed_documents` |
| `meili` | Meilisearch documents (delete-by-filter) |
| `all` | All three stores (same as `--stage fetch`) |

**All flags:**

| Flag | Required | Description |
|------|----------|-------------|
| `--corpus` | Yes | `ca`, `ls`, `rs`, or `all` |
| `--stage` | One of these two | `fetch` or `process` — stage-based preset (mutually exclusive with `--target`) |
| `--target` | One of these two | `pg`, `sqlite`, `meili`, or `all` — explicit per-store control |
| `--date-from` | No | Clear records from this date (inclusive, YYYY-MM-DD) |
| `--date-to` | No | Clear records up to this date (inclusive, YYYY-MM-DD) |
| `--dry-run` | No | Report counts without deleting anything |

**SQLite date-scoped delete:** when `--date-from`/`--date-to` are given, the script resolves the affected `canonical_doc_ids` from PG `raw_documents` first, then deletes those rows from `processed_documents`. This lookup always happens before any PG deletions so `--stage fetch` (which clears `raw_documents`) does not produce an empty SQLite result.

**Meilisearch:** uses the delete-by-filter API (`POST /indexes/parliamentary_records/documents/delete`) and polls the returned `taskUid` until the task succeeds.

**Environment variables required (per store):**

| Variable | Required for |
|----------|-------------|
| `DATABASE_URL` | `pg`; also `sqlite` when `--date-from`/`--date-to` are given |
| `MEILISEARCH_URL` | `meili` |
| `MEILISEARCH_MASTER_KEY` | `meili` |

After running, follow §6.4 Step 4 (or §6.1 Step 4) to re-ingest.

---

PRD v2.0 adds columns to both record tables (`lang_original`, `time_of_day`, `word_count` on both; `sequence_within_sitting` on `qa_exchanges`) plus two composite sitting indexes for F09 adjacent navigation. The new field values are **not derivable from stored data** — they require re-parsing the source documents — so applying v2.0 means a schema migration **followed by a full re-ingestion**.

**Step 1 — Apply the schema changes.** On a fresh database, re-run `app/db/schema.sql` (§3.3). On an existing database, apply the additive migration:

```sql
ALTER TABLE speeches
  ADD COLUMN lang_original VARCHAR(5) NOT NULL DEFAULT 'en'
    CHECK (lang_original IN ('en','hi','mixed')),
  ADD COLUMN time_of_day VARCHAR(5),
  ADD COLUMN word_count INTEGER;

ALTER TABLE qa_exchanges
  ADD COLUMN lang_original VARCHAR(5) NOT NULL DEFAULT 'en'
    CHECK (lang_original IN ('en','hi','mixed')),
  ADD COLUMN time_of_day VARCHAR(5),
  ADD COLUMN word_count INTEGER,
  ADD COLUMN sequence_within_sitting INTEGER;

CREATE INDEX idx_speeches_sitting ON speeches(source, date, sitting_number, sequence_within_sitting);
CREATE INDEX idx_qa_sitting ON qa_exchanges(source, date, sitting_number, sequence_within_sitting);
```

The `DEFAULT 'en'` on `lang_original` exists only to satisfy `NOT NULL` for any pre-existing rows; re-ingestion overwrites it with the correctly derived value. `schema.sql` itself declares the column without a default (re-ingestion always sets it explicitly).

**Step 2 — Full clean reindex.** Because the new fields require re-parsing, run the full clean reindex (§6.1) so every record is re-ingested with the v2.0 fields populated and a fresh, stable `id`. A Meilisearch-only reindex (§6.2) is **not** sufficient — it would only re-push existing rows that still lack the new values.

**No new env vars, dependencies, or infrastructure.** The F09 `GET /api/record/{id}` endpoint reuses the existing Railway PostgreSQL connection pool (`api/lib/db.py`). PERF-2 (detail page ≤500ms p95) is satisfied by the `id` primary-key lookup plus the `idx_*_sitting` composite indexes for the adjacent-neighbour query; no caching layer or additional service is required.
