# Arch Review — Phase 4 Run 1
Date: 2026-05-29
PRD version: v1.0
Prior run: first review

## Status: CLEAR

## Gaps
| File | Issue | Severity | Non-Negotiable violated? |
|------|-------|----------|--------------------------| 
| `arch/ARCHITECTURE.md` (section 3) | `main.jsx` and `index.css` are absent from the documented folder structure. `main.jsx` is the SPA entry point and defines all routing; its omission makes the folder listing incomplete. Coding Agent added both as required to render the app. | Minor | No |
| `arch/DATA-MODELS.md` (section 2.2) | Meilisearch document schema shows `"record_type": "speech"` but does not document `"record_type": "qa"` for Q+A exchange documents. The indexer correctly sets `"qa"` (confirmed: `indexer.py` line 315); `ResultCard.jsx` dispatches on this value. The value is implemented correctly but undocumented in the arch spec. | Minor | No |

Severity:
- Critical: non-negotiable violated; must fix before next phase
- Major: significant pattern deviation; should fix before next phase
- Minor: small inconsistency; does not block next phase. Deferred to Coding Agent's judgment — fix opportunistically during the next build session for this area of the codebase.

## Escalations
1. **Ratify `main.jsx` and `index.css` in ARCHITECTURE.md?** — These are standard Vite+React SPA boilerplate files. The Coding Agent added them as required to render the app. ARCHITECTURE.md section 3 currently lists `index.html`, `package.json`, and `vite.config.js` but not these two files. Decision needed: should they be added to the documented folder structure, or treated as implicit SPA boilerplate not requiring explicit listing? If the latter, the minor gap above is dismissed. If the former, update ARCHITECTURE.md section 3 to add `src/main.jsx` (SPA entry point; defines React Router routes) and `src/index.css` (CSS custom properties; global base styles).

## Verified

**Non-Negotiables (all 8 confirmed):**
- NN1 (PostgreSQL as primary store): Phase 4 is read-only frontend; no PostgreSQL access from any frontend file. ✓
- NN2 (Meilisearch as search engine): All search calls go through `POST /api/search`; no direct Meilisearch client in any frontend file. ✓
- NN3 (query expansion server-side only): `expansionNotice.js` only parses the `expansion_notice` array returned by the API for display purposes. No synonym lookup, stop-word logic, or expansion computation in the frontend. ✓
- NN4 (synonyms.json sole source): Not applicable to frontend; no synonym logic in frontend. ✓
- NN5 (index_status sole source for F07): `Home.jsx` fetches `GET /api/status`; no direct Meilisearch document count query from the frontend. ✓
- NN6 (cookie-only for F08): F08 not implemented in Phase 4. Bookmark buttons are non-functional placeholders. No server-side user data stored. ✓
- NN7 (ingestion CLI only): No ingestion code or API trigger in any frontend file. ✓
- NN8 (React SPA, no SSR): `main.jsx` uses `ReactDOM.createRoot` (client-side rendering). Vite build produces static files. `BrowserRouter` confirms client-side routing. ✓

**Storage abstraction:** No frontend file imports any storage SDK, filesystem module, PostgreSQL client, or Meilisearch client. All external calls are through `fetch()` to the API layer. ✓

**API patterns:**
- `useSearch.js` POST `/api/search`: request body shape (`query`, `sort`, `page`, optional `filters`) matches DATA-MODELS.md 3.1 exactly. `toApiFilters()` correctly omits default filter state. AbortController used for request cancellation on re-render. Error response handling distinguishes network errors from HTTP errors. ✓
- `Home.jsx` GET `/api/status`: response handling correctly maps `status: 'ok'` to the populated display, zero-record case to zero counts, and non-ok status to "Status unavailable". Matches DATA-MODELS.md 3.2. ✓

**Key Data Flows:** Phase 4 introduced no new API routes or changes to core lib files. The Search request and Index status (F07) flows were already documented in ARCHITECTURE.md section 4 and match the frontend implementation. No update to the table was required. ✓

**Separation of concerns:** Layering is correct throughout. `lib/` modules are pure utilities (no API calls). `hooks/useSearch.js` is the sole location for `POST /api/search` calls. `pages/` orchestrate hooks and components. `components/` render data without making API calls directly. The one exception is `StatusStrip` inside `Home.jsx` which inlines a `fetch('/api/status')` call — this is consistent with the architecture (no `useStatus.js` hook is defined in ARCHITECTURE.md section 3; the inline pattern is acceptable for a homepage-only widget). ✓

**Folder structure:** All Phase 4 files are placed in the correct locations per ARCHITECTURE.md section 3. `pages/`, `hooks/`, `lib/`, and `components/` directories match the spec. File extensions match (`.jsx` for components/pages, `.js` for hooks/lib). ✓

**DATA-MODELS.md alignment:**
- `ResultCard.jsx` dispatch: checks `record_type === 'qa'` — confirmed correct against `indexer.py` line 315 which sets `"qa"` for Q+A exchange records when pushing to Meilisearch. ✓
- `SpeechCard.jsx` and `QACard.jsx` field usage: all fields consumed match DATA-MODELS.md 3.1 response schema. `speaker_name_unresolved` is handled correctly (raw name displayed, no error indicator). `snippet` null/undefined check covers absent field per spec. `questioner_names` array handled via `formatQuestionerNames` with correct "+N others" logic. ✓
- `filterState.js` / `toApiFilters`: maps `FilterState` to API filters shape; `sources`, `proceeding_types`, `date_from`, `date_to`, `speaker`, `session` match DATA-MODELS.md 3.1 request body. ✓

**React Router setup:** `main.jsx` uses `BrowserRouter` with two explicit routes (`/` → Home, `/search` → Results) and a catch-all `Navigate` to `/`. Matches the two-page SPA architecture. ✓

**`js-cookie` dependency:** Present in `package.json`; not used in Phase 4 code. Pre-installed per Phase 1 foundation (cookie management listed as a Phase 1 dependency). ✓
