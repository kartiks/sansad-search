# Deployment — SansadSearch

**PRD version:** v1.3
**Generated:** 2026-05-28 (v1.0); updated 2026-05-29 (v1.1); updated 2026-05-30 (ingestion source redesign — per-source base-URL overrides; Internet Archive bulk path; reconciled to PRD v1.2: OCR removed, no Tesseract dependency); reviewed 2026-05-31 for PRD v1.3 — no deployment-relevant changes (RS-via-IA citation rule is an ingestion-logic change only; no new env vars, dependencies, or infrastructure)

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

`app/db/schema.sql` contains the `CREATE TABLE` statements for `speeches`, `qa_exchanges`, and `index_status` with all indexes.

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
python -m ingest.main --source all
```

Source selector options: `ca`, `ls`, `rs`, `all`. Optionally pass `--date-override` to override the end date for LS/RS fetching.

The pipeline writes to both Railway PostgreSQL (over the network) and Meilisearch Cloud (over the network). The local `data/ingestion_checkpoints.db` SQLite file tracks progress for resumability. Re-running the same command resumes from the last checkpoint.

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
