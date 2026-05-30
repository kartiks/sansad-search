# QA Review — Phase 4 Run 2
Date: 2026-05-29
PRD version: v1.1
Prior run: run-1 GAPS FOUND (5 gaps — 3 Coding: F05 HTML sanitisation WEAK, F02 results search-box pre-pop MISSING, F05 page-default MISSING; 2 Product: F07 zero-source row format, F05 metadata-field highlighting edge case)

## Status: GAPS FOUND

## Scope note

Re-audit of the 5 run-1 gaps plus the PRD v1.1 scope addition (full F07 indexing status panel — `pages/IndexingStatusPage.jsx`). Automated coverage is Vitest + Testing Library (jsdom): 163 frontend tests passing across 14 files (up from 142/12). Backend regression (Phase 1–3, 520 passed / 1 skipped) is the safety net and was not re-audited or re-run per QA guardrails (frontend-only rework; no Python runner in environment).

Visual/responsive/in-browser criteria (layout widths, breakpoints, hover, highlight colours, sticky header, shimmer styling) remain out of jsdom scope and are verified manually per the build spec — not logged as gaps.

No vacuous passes detected. All 163 assertions verify concrete behaviour (text content, attributes, call arguments, URL/POST-body state) — the run-1 snippet-sanitisation false-confidence finding is now resolved (see below).

## Re-audit of run-1 gaps

- **F05 HTML sanitisation (was WEAK → Coding):** RESOLVED. `lib/sanitizeSnippet.js` independently escapes `&`/`<`/`>` then re-enables only `<mark>`/`</mark>`. `SpeechCard.jsx:78` and `QACard.jsx:117` now route the snippet through `sanitizeSnippet` before `dangerouslySetInnerHTML`. `sanitizeSnippet.test.js` feeds **raw unescaped** payloads (`<script>alert(1)</script>`, `<img src=x onerror=alert(1)>`, `<b>x</b>`, `Tom & Jerry`) and asserts literal-text output plus `<mark>` preservation. The card's own safety is now verified rather than relying implicitly on the Phase-3 backend contract.
- **F02 results search-box pre-population (was MISSING → Coding):** RESOLVED. `Results.test.jsx:359` renders `/search?q=fundamental+rights&page=1` and asserts `results-search-input` `toHaveValue('fundamental rights')`.
- **F05 page-default with no `page` param (was MISSING → Coding):** RESOLVED. `Results.test.jsx:339` renders `/search?q=rights` (no page) and asserts POST body `page === 1` and `query === 'rights'`.
- **F07 zero-source row format (was MISSING → Product):** RESOLVED at spec + build. PRD v1.1 split F07 into the condensed homepage strip (counts + last-updated only) and the full panel (per-source date coverage + `"0 records – not yet indexed"`). Full panel built and tested: `IndexingStatusPage.test.jsx:113` asserts `"0 records – not yet indexed"` with negative assertions excluding `1970` and any date-range pattern; fresh-deploy all-zero + `"Last updated: Never"` tested at `:134`. Homepage-strip side tested at `Home.test.jsx:219` (`"0 Constituent Assembly records"` not omitted).
- **F05 metadata-field highlighting edge case (was EDGE CASE → Product):** RESOLVED at spec. PRD v1.1 removed the contradictory edge case from `05-result-display.md`. The spec no longer asserts metadata-field highlighting (snippet-only highlighting stands), so no test is required.

Contract check: the new panel's fixture shape (`status`, `total_records`, `sources.{ca,ls,rs}.{count,date_from,date_to}`, `last_updated`) matches `app/api/routes/status.py` (`_populated_response` / `_never_run_response` / `{"status":"unavailable"}`) exactly — tests verify against the real backend contract.

## Gaps
| Feature | Requirement | Gap type | Routes to | Notes |
|---------|-------------|----------|-----------|-------|
| F07 | Full indexing status panel is accessible via the persistent "Index status" footer link in Results.jsx (F07 feature spec "Full Indexing Status Panel" + Phase 4 build item) | WEAK | CODING AGENT | Low severity. `Results.jsx:304` renders `<Link to="/index-status" data-testid="index-status-link">Index status</Link>` and `main.jsx:21` registers the `/index-status` route — wiring is correct. But the only test (`Results.test.jsx:445`) asserts `getByTestId('index-status-link')` `toBeInTheDocument()` — existence only. It does not assert the link's destination (`href`/`to` === `/index-status`) or its label text ("Index status"). A regression pointing the footer link elsewhere, or changing its label, would not be caught; the navigation seam binding the two F07 surfaces is the one untested link. The full panel itself is fully unit-tested in isolation, so risk is low. Add an assertion: `expect(screen.getByTestId('index-status-link')).toHaveAttribute('href', '/index-status')` (and optionally `toHaveTextContent('Index status')`). |

## Verified

Run-2 confirms adequate, non-vacuous coverage for all of the following (run-1 Verified set carried forward where unchanged):

**F05 (result display)**
- Snippet sanitisation now genuinely verified against raw/unescaped HTML (`<script>`, `<img onerror>`, `<b>`, `&`) with `<mark>` preserved — `sanitizeSnippet.test.js`; both cards wired through it — `SpeechCard.test.jsx`, `QACard.test.jsx`
- Speech card metadata/speaker/subject/`<mark>` snippet/View-source new-tab attrs; edge cases (`speaker_name: null` → "Speaker unknown"; missing party/constituency omitted; `full_text_en: null` placeholder with metadata retained; `is_translated` indicator; `source_url: null` omits link; `speaker_name_unresolved` raw name; CA omits session) — `SpeechCard.test.jsx`
- Q+A card metadata/subject/`Q.`/questioner/co-signatory `+N others` (1 → none, 4 → "+3 others")/minister line/supplementary-exchange prefix — `QACard.test.jsx`
- Result count thresholds (exact ≤ 9,999 incl. 9,999; "10,000+" at ≥ 10,000; "0 results" + empty state) — `Pagination.test.jsx`, `Results.test.jsx`
- Pagination controls, current-page `aria-current`, ellipsis logic, > 500-page total-count suppression — `Pagination.test.jsx`
- URL page persistence: direct `/search?q=X&page=3` → page 3; **no-page URL → page 1** (run-1 gap resolved); **search box pre-populated from URL query** (run-1 gap resolved) — `Results.test.jsx`

**F02 (frontend)** — homepage search box; inline validation (empty / `< 2` chars, dismiss on typing); refinement stays on `/search`; no-results vs error distinct; direct `/search` redirects home; request-body construction — `Home.test.jsx`, `Results.test.jsx`, `useSearch.test.js`

**F06 (sorting)** — three options (Relevance first/default); URL round-trip for chronological/reverse; sort change re-fetches without changing count; persists across refinement — `constants.test.js`, `Results.test.jsx`

**F07 (indexing status — frontend)**
- Homepage strip: counts with separators, body labels, formatted last-updated; `null` → "Never"; "Status unavailable" on rejection and on `status:'unavailable'`; zero-count source shown as "0 [Body] records" not omitted — `Home.test.jsx`
- Full panel (`IndexingStatusPage`): "Search Index Status" header; total with separators; per-source CA/LS/RS rows with counts + `Mon YYYY – Mon YYYY` coverage; zero-source "0 records – not yet indexed" with no date range; fresh-deploy all-zero + "Never"; total = sum of per-source counts; reads from GET /api/status (asserts `fetch('/api/status')`, not a live index query); "Status unavailable" for `status:'unavailable'`, fetch failure, and malformed/missing-sources payloads (counts/table suppressed) — `IndexingStatusPage.test.jsx`

**Shared infrastructure** — constants label maps + fallbacks/canonical text; FilterState defaults/validations/`toApiFilters`; expansion-notice parse/format; 5-skeleton loading state; error+Retry re-issue; Toast render/auto-dismiss/`role=status` — `constants.test.js`, `filterState.test.js`, `expansionNotice.test.js`, `SkeletonCard.test.jsx`, `Toast.test.jsx`, `ResultCard.test.jsx`
