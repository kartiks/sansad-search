# Deployment — SansadSearch

**PRD version:** v3.2
**Generated:** 2026-05-28 (v1.0); updated 2026-05-29 (v1.1); updated 2026-05-30 (ingestion source redesign — per-source base-URL overrides; Internet Archive bulk path; reconciled to PRD v1.2: OCR removed, no Tesseract dependency); reviewed 2026-05-31 for PRD v1.3 — no deployment-relevant changes (RS-via-IA citation rule is an ingestion-logic change only; no new env vars, dependencies, or infrastructure); updated 2026-06-01 — added §6 Operations (full clean reindex and Meilisearch-only reindex runbooks); updated 2026-06-01 for PRD v2.0 — §6.3 schema migration for F01 new columns/indexes + re-ingestion; no new env vars, dependencies, or infrastructure (F09 detail endpoint reuses the existing Railway Postgres pool); updated 2026-06-03 — raw document store: §3.3/§3.5/§6.1 updated for `raw_documents`; §6.4 selective re-processing runbook added; no new env vars, dependencies, or infrastructure; updated 2026-06-05 — post-deploy production fixes: `app/ui/vercel.json` proxy+SPA rewrites documented (§3.2); `app/.python-version` Railway/Nixpacks pin documented (§3.1); `app/ui/.npmrc` legacy-peer-deps documented (§3.2); `VITE_API_URL` removed from §2.2 (not used in production — API calls proxied via vercel.json); §4 Vercel row updated; updated 2026-06-06 for PRD v3.0 — §6.6 schema migration for F01 new columns (`lok_sabha_number`, `segments`, `canonical_doc_id`) + full re-ingestion; no new env vars, dependencies, or infrastructure (F09 adjacent endpoint and F10 debug endpoints reuse the existing Railway Postgres pool and Meilisearch client; debug mode is exempt from response-time SLAs per NFR PERF-3 and is an unauthenticated v1 choice per NFR SEC-1); reviewed 2026-06-09 for PRD v3.1 — no deployment-relevant changes (F03 subject filter, F04 curly quote normalization, F05 cropLength reduction, F08 subject in saved search state are all ingestion-logic and application-code changes only; no new env vars, dependencies, or infrastructure); updated 2026-06-12 — ingestion checkpoint store moved from local SQLite to PostgreSQL and the pipeline made deployable as a Railway Cron Job: §1 hosting table + §2.3 + §3.3/§3.5 updated; new §3.7 (Railway Cron Job deployment) and §6.7 (SQLite→PostgreSQL backfill migration — no re-ingestion); §6.1 (TRUNCATE includes the two checkpoint tables, `rm …db` step removed), §6.4 Step 3 (SQL DELETE replaces the sqlite3 snippet), and §6.5 (`clear_corpus.py` — `--target sqlite` renamed to `--target checkpoints`) updated. **No new env vars, cloud providers, or infrastructure beyond the existing Railway project**; reviewed 2026-06-14 (PRD v3.2 — wording-only diff, no deployment-relevant change; header bumped v3.1→v3.2; verification pass fixed three doc defects: §6.3 PRD-v2.0-migration body had been displaced below §6.5 and was relocated under its header; §6.6 F05 snippet figure corrected to note cropLength ≥400 at v3.0 / ≥200 at v3.1)

---

## 1. Hosting Platform

| Component | Platform | Rationale |
|-----------|----------|-----------|
| FastAPI API | Railway | Managed Python deployment; same platform as PostgreSQL; straightforward env var config |
| PostgreSQL | Railway (managed) | Co-located with the API; managed backups; no separate Postgres host to manage |
| Ingestion pipeline | Railway (Cron Job) — or local CLI | Standalone scheduled job in the **same** Railway project as the API and PostgreSQL; runs to completion and exits (no always-on Worker — a Worker restarts on exit and re-runs the pipeline endlessly). All checkpoint state is in PostgreSQL, so the job is stateless between runs and resumable. May also be run as a plain CLI on an operator's machine. See §3.7 |
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

No build-time environment variables are required for the Vercel deployment. In production, API calls are proxied through the `/api/:path*` rewrite in `app/ui/vercel.json` — the frontend makes relative `/api/...` requests and Vercel forwards them to Railway. `VITE_API_URL` is not used in production.

For local development, `VITE_API_URL` is set in `app/ui/.env.local` — see §5.4.

### 2.3 Ingestion pipeline (local CLI **or** Railway Cron Job)

The same env vars apply whether the pipeline runs locally or as a Railway Cron Job (§3.7). On the Cron Job service they are set in the Railway service environment; locally they come from `app/.env` (§5.4).

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Required | PostgreSQL connection string. On the Railway Cron Job service this is **the same Railway PostgreSQL** the API uses — reference the shared Postgres so checkpoints, `raw_documents`, and the record tables are one database. Locally, the Railway connection string with SSL |
| `MEILISEARCH_URL` | Required | Meilisearch Cloud instance URL |
| `MEILISEARCH_MASTER_KEY` | Required | Meilisearch master API key; used only during ingestion and Meilisearch setup. **Set on the Cron Job service, never on the API service** (see the warning below) — the API runs with the search-only key |
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

**Required file:** `app/.python-version` (content: `3.12`) — pins the Python version for Railway's Nixpacks build. Without it, Nixpacks may select a different Python version and the build may fail.

Railway performs a zero-downtime deploy on each push to the connected git branch.

### 3.2 Frontend (Vercel)

Vercel auto-detects the Vite project from `ui/package.json`. Configure in Vercel project settings:

```
Root directory:    app/ui
Build command:     npm run build
Output directory:  dist
```

**Required files committed to the repo (within `app/ui/`):**

- `vercel.json` — configures two rewrites: (1) `/api/:path*` → Railway API URL (proxies all frontend API calls at runtime; eliminates cross-origin requests in production); (2) `/(.*) → /index.html` (React Router SPA catch-all for direct URL and deep-link navigation). The destination URL in the proxy rule must match the Railway service URL:

  ```json
  {
    "rewrites": [
      {
        "source": "/api/:path*",
        "destination": "https://sansad-search-dev-api-production.up.railway.app/api/:path*"
      },
      {
        "source": "/(.*)",
        "destination": "/index.html"
      }
    ]
  }
  ```
- `.npmrc` — sets `legacy-peer-deps=true`; resolves npm peer dependency conflicts during `npm install` on Vercel.

No Vercel environment variables are required. Vercel rebuilds and deploys on each push to the connected branch.

### 3.3 Database schema init (one-time)

Run once against the Railway PostgreSQL instance before the first ingestion:

```bash
psql $DATABASE_URL -f app/db/schema.sql
```

`app/db/schema.sql` contains the `CREATE TABLE` statements for `speeches`, `qa_exchanges`, `raw_documents`, `index_status`, and the two ingestion checkpoint tables `processed_documents` and `ingestion_dedup_keys` (DATA-MODELS §1.6/§1.7), with all indexes.

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

Stage 1 writes to Railway PostgreSQL (`raw_documents` table) and the Meilisearch index is not touched until Stage 2. Stage 2 reads from `raw_documents`, writes to `speeches`/`qa_exchanges`, and pushes to Meilisearch Cloud. Stage 2 progress is tracked in the `processed_documents` PostgreSQL table (DATA-MODELS §1.6) for resumability — **there is no local checkpoint file**. Re-running resumes from the last checkpoint.

The same command can run unattended in the cloud as a **Railway Cron Job** (§3.7) — the move of all checkpoint state into PostgreSQL is what makes this possible.

Ingestion duration is unbounded (PRD INF-P1). The operator does not need to supervise; real-time progress is logged to stdout.

### 3.6 Re-indexing Meilisearch from PostgreSQL

If the Meilisearch index needs to be rebuilt (schema change, index corruption, plan migration):

```bash
cd app
python -m ingest.indexer --reindex-from-db
```

This reads all records from `speeches` and `qa_exchanges` in PostgreSQL and pushes them to Meilisearch in batches. Does not re-scrape any source websites. Does not update the checkpoint store.

---

### 3.7 Deploying the ingestion pipeline as a Railway Cron Job

The pipeline can run unattended in the cloud as a **Railway Cron Job** in the same Railway project as the API and PostgreSQL. This is possible because all checkpoint state now lives in PostgreSQL (no local file). Non-Negotiable #7 is preserved — a Cron Job is a CLI process, not an API route; there is still no `/api/ingest` endpoint.

**Service type — Cron Job, not Worker.** Railway restarts a Worker (always-on) service whenever its process exits; the ingestion pipeline exits `0` on completion, which would cause an always-on Worker to re-run it endlessly. A **Cron Job** runs the start command to completion on its schedule and does not restart between runs.

**Setup:**

1. In the existing Railway project, add a new service from the same repo (root directory `app/`, same Nixpacks build as the API — `app/.python-version` pins Python 3.12, §3.1).
2. Set the service type to **Cron Job** and define a schedule (cron expression). For a v1 one-time bulk backfill, use an infrequent schedule and trigger runs manually from the Railway dashboard, or a schedule matched to the cadence you actually want; v1 ingestion is a bulk backfill, not a continuous sync (PRD INF-P1 / overview "one-time bulk operation").
3. Set the start command:
   ```
   python -m ingest.main --source all
   ```
   (Scope per corpus or date window with `--source`/`--date-from`/`--date-to` as needed — see §3.5.)
4. Set environment variables on this service (§2.3): `DATABASE_URL` referencing the **shared** Railway PostgreSQL, `MEILISEARCH_URL`, and `MEILISEARCH_MASTER_KEY`.

**Resumability.** If a run is interrupted (or hits a Railway execution-time limit), the next run resumes from the PostgreSQL checkpoint (`processed_documents`) with no duplicates (`INF-R1`). No local state is lost between runs because there is no local state.

**Long-run consideration (INF-P1).** Bulk ingestion is unbounded and long-running. Confirm the Railway plan permits the expected run duration for a Cron Job; if a single run cannot complete within platform limits, split the backfill by corpus and/or date window across multiple scheduled runs — each run advances the PostgreSQL checkpoint, so successive runs make forward progress. Progress is logged to stdout (visible in Railway service logs).

> ⚠️ **`MEILISEARCH_MASTER_KEY` now lives on a deployed service.** It was previously only on an operator's machine. It must be set on the **Cron Job** service (which needs write/admin access to push documents and configure the index) and must **never** be set on the **API** service, which runs with the search-only `MEILISEARCH_SEARCH_KEY` (§2.1). Keeping the two services' environments separate preserves the existing key-isolation guarantee (ARCHITECTURE §6 Integration Points).

---

## 4. Infrastructure Dependencies

| Dependency | Required for | Notes |
|------------|-------------|-------|
| Railway PostgreSQL | API (status endpoint), Ingestion | Must be provisioned before first deploy and before first ingestion run |
| Meilisearch Cloud instance | API (all search), Ingestion | Must be set up and configured (`setup_meilisearch.py` run) before first ingestion |
| Vercel project | Frontend | Connected to the repo; `app/ui/vercel.json` configures API proxy and SPA routing |
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

Use when PostgreSQL data is stale, corrupt, or incomplete — wipes all state and re-ingests from source. (There is no longer a local checkpoint file to delete — all checkpoint state is in PostgreSQL and is wiped by the `TRUNCATE` in Step 1.)

**Step 1 — Truncate PostgreSQL tables (records + both checkpoint tables)**

```bash
psql $DATABASE_URL -c "TRUNCATE TABLE speeches, qa_exchanges, raw_documents, processed_documents, ingestion_dedup_keys, index_status RESTART IDENTITY CASCADE;"
```

All six tables must be truncated together. `raw_documents` holds the Stage 1 checkpoint — truncating it forces Stage 1 to re-fetch every source document. `processed_documents` and `ingestion_dedup_keys` hold the Stage 2 checkpoint (formerly the local SQLite file) — truncating them forces Stage 2 to re-segment and re-insert every record. `RESTART IDENTITY` resets primary-key sequences. `CASCADE` handles any foreign-key constraints.

**Step 2 — Delete all documents from the Meilisearch index**

```bash
curl -X DELETE "$MEILISEARCH_URL/indexes/parliamentary_records/documents" \
  -H "Authorization: Bearer $MEILISEARCH_MASTER_KEY"
```

This issues a Meilisearch task. The index itself (settings, synonyms, ranking rules) is preserved — only documents are deleted. Wait for the task to complete before starting ingestion; poll `$MEILISEARCH_URL/tasks/{taskUid}` or check the Meilisearch Cloud dashboard.

**Step 3 — Run full ingestion**

```bash
cd app
python -m ingest.main --source all
```

Ingests all corpora (CA, LS, RS) from source. Progress is logged to stdout; checkpoint rows are recreated in the `processed_documents`/`ingestion_dedup_keys` PostgreSQL tables as documents are processed. The run is resumable: if interrupted, re-run the same command to continue from the last checkpoint.

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

**Step 3 — Delete `processed_documents` entries for the scope**

`processed_documents` is now a PostgreSQL table (DATA-MODELS §1.6), so this is a single SQL statement against the same database — no separate SQLite file, no Python. Scope precisely by joining to `raw_documents.date` (this table has no date column of its own):

```sql
-- Re-process all LS records for 2024 — clear the matching Stage 2 checkpoints:
DELETE FROM processed_documents pd
USING raw_documents r
WHERE pd.canonical_doc_id = r.canonical_doc_id
  AND pd.corpus = r.corpus
  AND pd.corpus = 'LS'
  AND r.date BETWEEN '2024-01-01' AND '2024-12-31';
```

To clear a full corpus: `DELETE FROM processed_documents WHERE corpus = 'LS';`

`ingestion_dedup_keys` is **not** cleared here. Selective re-processing relies on clearing `processed_documents` plus the authoritative `UNIQUE(dedup_key)` `ON CONFLICT DO NOTHING` guard on `speeches`/`qa_exchanges` — after Step 1 deletes the canonical rows for the scope, Stage 2 re-inserts them regardless of the (stale) dedup-key pre-filter. This matches the prior SQLite behavior; the correctness invariant the `store.py` rewrite must preserve is recorded in ARCHITECTURE §8 item 7.

**Step 4 — Re-run Stage 2**

```bash
cd app
python -m ingest.main --source ls --stage process --date-from 2024-01-01 --date-to 2024-12-31
```

Stage 2 reads from `raw_documents` for the given scope, re-segments, re-canonicalizes, and re-indexes. Stage 1 fetch cost is not paid again.

---

### 6.5 Selective corpus clear (`clear_corpus.py`)

`app/scripts/clear_corpus.py` automates steps 1–3 of §6.4 (and the equivalent clearing steps from §6.1) — deleting data across PostgreSQL (record tables **and** the checkpoint tables) and Meilisearch for a corpus and optional date range before a re-run. There is no longer a separate SQLite store; the checkpoint clear is now a PostgreSQL `DELETE`.

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

# Explicit per-store control: clear only the Stage 2 checkpoint for RS
python scripts/clear_corpus.py --corpus rs --target checkpoints
```

**`--stage` semantics (recommended for most operations):**

| `--stage` | PG record tables cleared | PG checkpoint tables cleared | Meilisearch | Use when |
|-----------|--------------------------|------------------------------|-------------|----------|
| `process` | `speeches`, `qa_exchanges` | `processed_documents` | yes | Re-running Stage 2 from existing raw docs |
| `fetch` | `speeches`, `qa_exchanges`, `raw_documents` | `processed_documents`, `ingestion_dedup_keys` | yes | Re-fetching from source (both stages re-run) |

`--stage process` clears `processed_documents` only (not `ingestion_dedup_keys`) — re-insertion correctness comes from the `ON CONFLICT` guard after the `speeches`/`qa_exchanges` rows are deleted (see §6.4 Step 3, ARCHITECTURE §8 item 7). `--stage fetch` is a full corpus wipe, so it clears both checkpoint tables.

**`--target` flag (explicit per-store control):**

| `--target` | What is cleared |
|------------|----------------|
| `pg` | `speeches`, `qa_exchanges`, `raw_documents` (record tables) |
| `checkpoints` | `processed_documents` (and `ingestion_dedup_keys` when no date scope is given — a date-scoped clear touches `processed_documents` only) |
| `meili` | Meilisearch documents (delete-by-filter) |
| `all` | All stores: record tables + checkpoint tables + Meilisearch (same as `--stage fetch`) |

> **Flag rename (2026-06-12):** `--target sqlite` → `--target checkpoints`. The store is no longer SQLite. The Coding Agent must update the `argparse` choices, the branch handling this target, the `--help` text, and any tests referencing `--target sqlite` (see "Implementation tasks for /build" at the end of this file).

**All flags:**

| Flag | Required | Description |
|------|----------|-------------|
| `--corpus` | Yes | `ca`, `ls`, `rs`, or `all` |
| `--stage` | One of these two | `fetch` or `process` — stage-based preset (mutually exclusive with `--target`) |
| `--target` | One of these two | `pg`, `checkpoints`, `meili`, or `all` — explicit per-store control |
| `--date-from` | No | Clear records from this date (inclusive, YYYY-MM-DD) |
| `--date-to` | No | Clear records up to this date (inclusive, YYYY-MM-DD) |
| `--dry-run` | No | Report counts without deleting anything |

**Checkpoint date-scoped delete:** when `--date-from`/`--date-to` are given, the `processed_documents` clear is a single PostgreSQL `DELETE … USING raw_documents` joined on `(canonical_doc_id, corpus)` and filtered by `raw_documents.date` (the form shown in §6.4 Step 3). Because both tables are now in the same database, this is one atomic statement — the earlier two-step "resolve `canonical_doc_ids` from `raw_documents`, then delete from SQLite" dance is gone. Run the `processed_documents` delete **before** any `raw_documents` delete (i.e. before `--stage fetch`/`--target pg` removes the rows the join depends on), so the date filter still resolves.

**Meilisearch:** uses the delete-by-filter API (`POST /indexes/parliamentary_records/documents/delete`) and polls the returned `taskUid` until the task succeeds.

**Environment variables required (per store):**

| Variable | Required for |
|----------|-------------|
| `DATABASE_URL` | `pg` and `checkpoints` (both are PostgreSQL now) |
| `MEILISEARCH_URL` | `meili` |
| `MEILISEARCH_MASTER_KEY` | `meili` |

After running, follow §6.4 Step 4 (or §6.1 Step 4) to re-ingest.

---

### 6.6 PRD v3.0 migration (F01 new columns + source_url correction + F05/F09/F10)

PRD v3.0 adds three columns to `speeches` (`lok_sabha_number`, `segments`, `canonical_doc_id`) and two to `qa_exchanges` (`lok_sabha_number`, `canonical_doc_id`), and **corrects `source_url`** for all LS and RS records (Non-Negotiable #9 reversal: IA item URL instead of `eparlib_document_url`/`rsdebate.nic.in`). The new column values and the corrected `source_url`/`minister_name`/merged `segments` are **not derivable from stored data** — they require re-parsing and re-segmenting the source documents — so applying v3.0 means a schema migration **followed by a full re-ingestion**.

**Step 1 — Apply the schema changes.** On a fresh database, re-run `app/db/schema.sql` (§3.3). On an existing database, apply the additive migration:

```sql
ALTER TABLE speeches
  ADD COLUMN lok_sabha_number INTEGER,
  ADD COLUMN segments JSONB,
  ADD COLUMN canonical_doc_id TEXT;

ALTER TABLE qa_exchanges
  ADD COLUMN lok_sabha_number INTEGER,
  ADD COLUMN canonical_doc_id TEXT;
```

All five columns are nullable with no default — re-ingestion populates them (LS records get `lok_sabha_number`; speech records get `segments`; both tables get `canonical_doc_id` linking to the source `raw_documents` row). No new indexes are required: `canonical_doc_id` is resolved only after an `id` primary-key lookup (then a `raw_documents` composite-PK lookup), `lok_sabha_number` is neither filtered nor sorted, and `segments` is display/diagnostic only. `schema.sql` declares all five columns inline for fresh installs.

**Step 2 — Full clean reindex.** Because the new fields require re-parsing **and** existing `source_url`/`minister_name` values are now incorrect **and** speech records are structurally changed by Adjacent Speech Merging, run the full clean reindex (§6.1) so every record is re-ingested with v3.0 values and a fresh, stable `id`. A Meilisearch-only reindex (§6.2) is **not** sufficient — it would only re-push existing rows that still carry the old `source_url` and lack the new columns. The §6.1 `TRUNCATE` already lists all six tables (incl. `raw_documents` and the two checkpoint tables), so Stage 1 re-fetch and Stage 2 re-segmentation both occur.

**No new env vars, dependencies, or infrastructure.** The F09 `GET /api/record/{id}/adjacent` range endpoint and the F10 debug endpoints (`POST /api/search?debug=1`, `GET /api/debug/processed/{id}`, `GET /api/debug/raw/{id}`) all reuse the existing Railway PostgreSQL pool and the existing Meilisearch client. Debug mode adds no service and is exempt from response-time SLAs (NFR PERF-3). Debug endpoints are unauthenticated by deliberate v1 choice (NFR SEC-1) — **review before exposing a production instance that holds sensitive data.** The F05 snippet-size change (`cropLength`, ≥400 words at v3.0; reduced to ≥200 at v3.1) is a query-time Meilisearch parameter in `api/services/search.py`; no index re-configuration via `setup_meilisearch.py` is required for it.

---

### 6.7 Checkpoint-store migration (local SQLite → PostgreSQL) — **no re-ingestion**

Use when migrating an **existing** populated deployment off the local SQLite checkpoint file. Unlike the v2.0/v3.0 migrations above, this is **not** a re-ingestion. The two checkpoint tables hold *derived* state, fully reconstructable from the canonical record tables (`speeches`/`qa_exchanges`) already in PostgreSQL — so the existing corpus, `raw_documents`, and the Meilisearch index are all left untouched. A full clean reindex here would be wasteful and is unnecessary.

**Why a backfill is sufficient:** `ingestion_dedup_keys` is an exact 1:1 mirror of the `UNIQUE(dedup_key)` constraint, so every key reconstructs from `speeches`/`qa_exchanges`. `processed_documents` reconstructs by joining those rows to `raw_documents` on `(canonical_doc_id, corpus)`. `canonical_doc_id` is populated on all current rows (the v3.0 full re-ingestion guaranteed this).

**Step 1 — Create the two checkpoint tables.** On a fresh database, `schema.sql` (§3.3) already creates them. On the existing database, apply the additive migration:

```sql
CREATE TABLE processed_documents (
  canonical_doc_id TEXT        NOT NULL,
  corpus           VARCHAR(2)  NOT NULL CHECK (corpus IN ('CA','LS','RS')),
  provider         VARCHAR(50),
  fetch_url        TEXT,
  processed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (canonical_doc_id, corpus)
);
CREATE INDEX idx_processed_documents_corpus ON processed_documents(corpus);

CREATE TABLE ingestion_dedup_keys (
  dedup_key VARCHAR(500) NOT NULL,
  corpus    VARCHAR(2)   NOT NULL CHECK (corpus IN ('CA','LS','RS')),
  PRIMARY KEY (dedup_key, corpus)
);
CREATE INDEX idx_ingestion_dedup_keys_corpus ON ingestion_dedup_keys(corpus);
```

**Step 2 — Backfill from the canonical record tables.** Idempotent (`ON CONFLICT DO NOTHING`); safe to re-run:

```sql
-- processed_documents: one row per (document, corpus) that produced ≥1 record.
INSERT INTO processed_documents (canonical_doc_id, corpus, provider, fetch_url, processed_at)
SELECT DISTINCT s.canonical_doc_id, s.source, r.provider, r.fetch_url, NOW()
FROM speeches s
JOIN raw_documents r
  ON r.canonical_doc_id = s.canonical_doc_id AND r.corpus = s.source
WHERE s.canonical_doc_id IS NOT NULL
UNION
SELECT DISTINCT q.canonical_doc_id, q.source, r.provider, r.fetch_url, NOW()
FROM qa_exchanges q
JOIN raw_documents r
  ON r.canonical_doc_id = q.canonical_doc_id AND r.corpus = q.source
WHERE q.canonical_doc_id IS NOT NULL
ON CONFLICT (canonical_doc_id, corpus) DO NOTHING;

-- ingestion_dedup_keys: exact mirror of the UNIQUE(dedup_key) constraint.
INSERT INTO ingestion_dedup_keys (dedup_key, corpus)
SELECT dedup_key, source FROM speeches
UNION
SELECT dedup_key, source FROM qa_exchanges
ON CONFLICT (dedup_key, corpus) DO NOTHING;
```

**Step 3 — Delete the local SQLite file** (it is no longer read):

```bash
rm -f app/data/ingestion_checkpoints.db
```

**Verification (optional):** `SELECT count(*) FROM ingestion_dedup_keys;` should equal `SELECT count(*) FROM speeches` + `SELECT count(*) FROM qa_exchanges`.

**Known, harmless caveat.** A source document that was processed but yielded **zero** records (e.g. a text-less PDF) has no `speeches`/`qa_exchanges` rows, so it is not reconstructed into `processed_documents`. The next Stage 2 run will re-process it once — re-parsing it to zero records again. This is idempotent (no duplicates, `INF-R1` preserved) and costs only one redundant parse.

**No new env vars, dependencies, or infrastructure.** This migration runs entirely against the existing Railway PostgreSQL.

---

## 7. Implementation tasks for /build

This change is specified entirely by the arch docs but spans code outside the `/arch` boundary. A `/build` session must implement the following (paths under `app/`):

1. **`db/schema.sql`** — add `CREATE TABLE` + index statements for `processed_documents` and `ingestion_dedup_keys` exactly as in §6.7 Step 1 (DATA-MODELS §1.6/§1.7 are the authority for columns, PK, and indexes).
2. **`ingest/checkpoints/store.py`** — rewrite from SQLite to PostgreSQL (psycopg2, reusing the ingestion DSN / `DATABASE_URL`; same connection-resilience pattern as `indexer.py`). Implement the query patterns in DATA-MODELS §1.6/§1.7. **Preserve the dedup-mirror correctness invariant in ARCHITECTURE §8 item 7** — the mirror is a pre-filter; `ON CONFLICT (dedup_key) DO NOTHING` on `speeches`/`qa_exchanges` is the authoritative guard. Remove all `sqlite3` usage and the `data/ingestion_checkpoints.db` path.
3. **`scripts/clear_corpus.py`** — rename `--target sqlite` → `--target checkpoints` (argparse choices, branch logic, `--help`); the checkpoints clear is now a PostgreSQL `DELETE` (corpus-scoped, or the §6.4 `DELETE … USING raw_documents` join when date-scoped); `--stage fetch` clears both checkpoint tables, `--stage process` clears `processed_documents` only (§6.5). Update the per-store env-var requirements (`DATABASE_URL` now covers checkpoints).
4. **Remove the SQLite file from `.gitignore`** (and any `data/` runtime-dir creation specific to it) if present.
5. **Tests** — update/replace any test referencing the SQLite store, `--target sqlite`, or `data/ingestion_checkpoints.db`. Add: (a) Stage 2 resumability over the PostgreSQL `processed_documents` table (interrupt → resume → identical count, no duplicates — `INF-R1`); (b) the §8-item-7 regression test (clear `speeches`/`qa_exchanges` + `processed_documents` for a scope, leave `ingestion_dedup_keys`, re-run Stage 2, assert rows re-created); (c) `clear_corpus.py --target checkpoints` issues the PostgreSQL delete.
6. **Migration** — operators on an existing deployment run §6.7 (create tables + backfill + delete SQLite file); **no re-ingestion**. Fresh deployments get the tables from `schema.sql`.
7. **Deployment** — provision the Railway **Cron Job** service per §3.7 (same project, shared `DATABASE_URL`, `MEILISEARCH_URL`, `MEILISEARCH_MASTER_KEY`; start command `python -m ingest.main --source all`).

**Routing note (not a /build task):** PRD F01 (lines 115/120) still names "the SQLite checkpoint store" / "the SQLite `processed_documents` store." Making those storage-agnostic is a Product Agent change — run `/spec`. It does not block this build (the product requirement, `INF-R1` resumability, is medium-agnostic and unchanged).
