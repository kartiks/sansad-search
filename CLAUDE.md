# SansadSearch

Full-text search over Indian Constituent Assembly, Lok Sabha and Rajya Sabha debates and questions.

## Layout

- `app/ingest/` — ingestion CLI. Stage 1 fetches and parses source documents into the `raw_documents` table; Stage 2 segments them into speeches / Q+A records, writes PostgreSQL and pushes to Meilisearch.
  - `sources/` — per-corpus orchestrators (`ca.py`, `ls.py`, `rs.py`) and `providers/` (Internet Archive, elibrary.sansad.in DSpace 7, constitutionofindia.net, …)
  - `parsers/`, `segmenters/`, `canonical/` (speaker names, session names), `indexer.py`, `checkpoints/`
- `app/api/` — FastAPI backend. Search runs against Meilisearch; record detail, status and debug read PostgreSQL.
- `app/ui/` — Vite + React frontend, deployed on Vercel (`vercel.json` proxies `/api` to the backend).
- `app/db/schema.sql` — PostgreSQL schema.
- `docs/` — product requirements (`PRD.md`), `ARCHITECTURE.md`, `DATA-MODELS.md`, `DEPLOYMENT.md` (setup and operations runbooks), `UI-UX-SPEC.md`, `test-specs/`, and `DOMAIN-NOTES.md` (parliamentary procedure background).

## Commands

Run from `app/` unless noted.

```bash
.venv/bin/python -m pytest                      # backend tests
uvicorn api.main:app --reload --port 8000       # API
python -m ingest.setup_meilisearch              # configure the search index
python -m ingest.main --source ca|ls|rs|all [--stage fetch|process|all] [--date-from YYYY-MM-DD --date-to YYYY-MM-DD]
python -m ingest.main --source all --reindex-from-db
```

Frontend, from `app/ui/`: `npm run dev`, `npx vitest run`, `npm run build`.

Env vars (`app/.env`): `DATABASE_URL`, `MEILISEARCH_URL`, `MEILISEARCH_MASTER_KEY` (ingestion only — never on the API service), `MEILISEARCH_SEARCH_KEY` (API). See `docs/DEPLOYMENT.md` for the full list.

## Notes

- Keep `docs/` in sync when behaviour changes (API contract, data model, ingestion sources).
- Ingestion must stay rate-limited and robots.txt-compliant; it is a CLI / cron job, never an API route.
- Tests mock all network access; don't add tests that hit live sources.
