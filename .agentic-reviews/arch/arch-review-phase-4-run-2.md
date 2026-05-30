# Arch Review — Phase 4 Run 2
Date: 2026-05-29
PRD version: v1.1
Prior run: run-1 CLEAR — 2 minor doc gaps (main.jsx and index.css absent from ARCHITECTURE.md section 3 folder spec; record_type "qa" value undocumented in DATA-MODELS.md 2.2). Both were deferred to Coding Agent's judgment; run-1 also escalated whether to add main.jsx/index.css to the folder spec (user decision pending).

## Status: CLEAR

## Gaps
| File | Issue | Severity | Non-Negotiable violated? |
|------|-------|----------|--------------------------| 
| `arch/ARCHITECTURE.md` section 3 | `lib/sanitizeSnippet.js` is absent from the documented folder structure. Added by the rework build as the XSS sanitization utility for result card snippets (escapes all HTML, re-enables only `<mark>`). | Minor | No |
| `arch/ARCHITECTURE.md` section 3 | `lib/statusFormat.js` is absent from the documented folder structure. Added by the rework build as a shared formatting helper used by both `Home.jsx` (StatusStrip) and `IndexingStatusPage.jsx` (full panel). | Minor | No |
| `arch/ARCHITECTURE.md` section 3 | `pages/IndexingStatusPage.jsx` is absent from the documented folder structure. Added by the rework build as the full F07 indexing status panel (scope extension confirmed in TRACKER.md PLAN handoff). | Minor | No |
| `arch/ARCHITECTURE.md` section 3 | `main.jsx` route list documents two routes (`/ → Home`, `/search → Results`) and a catch-all redirect. A third route (`/index-status → IndexingStatusPage`) was added by the rework build and is not reflected in the documented description. | Minor | No |

Severity:
- Critical: non-negotiable violated; must fix before next phase
- Major: significant pattern deviation; should fix before next phase
- Minor: small inconsistency; does not block next phase. Deferred to Coding Agent's judgment — fix opportunistically during the next build session for this area of the codebase.

## Escalations
1. **Ratify `lib/statusFormat.js` as a shared utility module?** — The Coding Agent extracted F07 date/count formatting into `lib/statusFormat.js` and imports it from both `Home.jsx` (StatusStrip) and `IndexingStatusPage.jsx`. ARCHITECTURE.md section 3 does not document a shared formatting utility pattern for `lib/`; existing `lib/` entries are `cookie.js`, `filterState.js`, `expansionNotice.js`, and `constants.js` — all data/state utilities, not display formatters. The extraction is architecturally sound (single source of truth for display logic shared across pages), but the pattern is new and undocumented. Decision needed: ratify `lib/statusFormat.js` as a legitimate `lib/` module and add it to ARCHITECTURE.md section 3, or treat display-only formatters as an implementation detail not requiring explicit documentation?

## Verified

**Non-Negotiables (all 8 confirmed for new Phase 4 additions):**
- NN1 (PostgreSQL as primary store): `IndexingStatusPage.jsx` reads only from `GET /api/status`. No direct PostgreSQL client imported in any frontend file. ✓
- NN2 (Meilisearch as search engine): No direct Meilisearch client call in any new file. `IndexingStatusPage.jsx` uses only the `/api/status` endpoint. ✓
- NN3 (query expansion server-side only): `sanitizeSnippet.js` and `statusFormat.js` contain no synonym lookup or query preprocessing logic. ✓
- NN4 (synonyms.json sole source): Not applicable; no synonym logic in any new frontend file. ✓
- NN5 (index_status sole source for F07): `IndexingStatusPage.jsx` calls `fetch(STATUS_ENDPOINT)` where `STATUS_ENDPOINT = '/api/status'`. No direct Meilisearch document count query. The `isUsable()` guard correctly treats `status !== 'ok'` and missing `sources` as unavailable — consistent with the API contract in DATA-MODELS.md 3.2. ✓
- NN6 (cookie-only for F08): No cookie logic in any new file. ✓
- NN7 (ingestion CLI only): No ingestion trigger in any new file. ✓
- NN8 (React SPA, no SSR): `IndexingStatusPage.jsx` uses `useEffect` + `useState` (client-side rendering). No server-side rendering. ✓

**Storage abstraction:** `sanitizeSnippet.js`, `statusFormat.js`, and `IndexingStatusPage.jsx` import no storage SDKs, filesystem modules, PostgreSQL clients, or Meilisearch clients. All external data access is via `fetch()` to the API layer. ✓

**API patterns:**
- `IndexingStatusPage.jsx` calls `GET /api/status`: response handling correctly maps `status: 'ok'` + `sources` present → populated table; fetch failure → `failed = true` → unavailable message; `status !== 'ok'` or missing `sources` → `isUsable()` returns false → unavailable message. All three DATA-MODELS.md 3.2 response variants handled correctly. ✓
- Per-source fields consumed: `src.count`, `src.date_from`, `src.date_to` — all present in DATA-MODELS.md 3.2 response schema. `total_records` and `last_updated` top-level fields consumed correctly. ✓

**Key Data Flows:** `IndexingStatusPage.jsx` is a new consumer of the existing Index status (F07) flow (`Browser → GET /api/status → asyncpg query on index_status table → Browser`), already documented in ARCHITECTURE.md section 4. No new API route and no change to any core lib file. No update to the Key Data Flows table was required. ✓

**Separation of concerns:**
- `lib/sanitizeSnippet.js`: pure function, no React, no API calls. Takes a raw string, returns a sanitized string. ✓
- `lib/statusFormat.js`: pure functions, no React, no API calls. `formatCount`, `formatLongDate`, `formatMonthYear`, `formatCoverage` operate on primitive inputs. ✓
- `pages/IndexingStatusPage.jsx`: orchestrates state via `useEffect`/`useState` and renders data. Inline `fetch(STATUS_ENDPOINT)` matches the established pattern from `Home.jsx`'s `StatusStrip` (no `useStatus.js` hook is defined in ARCHITECTURE.md section 3; the inline pattern is accepted for thin single-endpoint consumers). ✓
- `SpeechCard.jsx` and `QACard.jsx`: both import `sanitizeSnippet` from `lib/` (pure utility import). No architectural boundary crossed. ✓
- `Results.jsx` footer link: `<Link to="/index-status">` — correct use of React Router client-side navigation; no storage or API access added. ✓

**Folder structure:** All new files are placed in architecturally correct directories:
- `lib/sanitizeSnippet.js` → `lib/` (pure utility; matches `lib/` pattern) ✓
- `lib/statusFormat.js` → `lib/` (pure utility; matches `lib/` pattern) ✓
- `pages/IndexingStatusPage.jsx` → `pages/` (full page component; matches `pages/` pattern) ✓
- File extensions correct: `.js` for lib utilities, `.jsx` for page component. ✓

**DATA-MODELS.md alignment:**
- `IndexingStatusPage.jsx` zero-record rendering: `count === 0` → "0 records – not yet indexed" with no date range. Matches DATA-MODELS.md 3.2 zero-record response (count: 0, date_from: null, date_to: null). ✓
- `formatLongDate(null)` returns "Never" → matches "last_updated: null" (ingestion never run) response variant. ✓
- `formatCoverage(date_from, date_to)` with both present → "Mon YYYY – Mon YYYY" display. DATA-MODELS.md 3.2 returns `date_from`/`date_to` as ISO date strings; the "Mon YYYY" display format is not specified in DATA-MODELS.md (see Escalations — ratification of statusFormat.js pattern). ✓

**`sanitizeSnippet` integration:** `SpeechCard.jsx` and `QACard.jsx` both pass `result.snippet` through `sanitizeSnippet()` before `dangerouslySetInnerHTML`. The function escapes all `&`, `<`, `>` then re-enables only `<mark>` and `</mark>`. This correctly implements the F05 edge case requirement ("HTML in snippet rendered as plain text; script tags do not execute") while preserving query-term highlighting. `sanitizeSnippet(null)` returns `''` — safe for `dangerouslySetInnerHTML`. ✓

**React Router routing:** `main.jsx` now defines three explicit routes: `/ → Home`, `/search → Results`, `/index-status → IndexingStatusPage`, plus catch-all `Navigate to /`. The `/index-status` route is wired correctly; `Results.jsx` footer uses `<Link to="/index-status">` (client-side navigation, not a hard `<a href>`). ✓
