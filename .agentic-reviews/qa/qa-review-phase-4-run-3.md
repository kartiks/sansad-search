# QA Review — Phase 4 Run 3
Date: 2026-05-29
PRD version: v1.1
Prior run: run-2 GAPS FOUND (1 gap — F07 "Index status" footer link test WEAK: asserted existence only, not destination or label; routed to Coding Agent)

## Status: CLEAR

## Scope note

Re-audit of the single run-2 gap per QA re-run guardrails (re-audit any requirement that appeared as a gap to confirm it is addressed without introducing new gaps). No other requirements re-audited — run-2 confirmed adequate coverage for all F02/F05/F06/F07 frontend requirements, and Phase 1–3 backend regression remains the safety net (not re-run; frontend-only rework, no Python runner in environment).

Automated coverage unchanged in count: Vitest + Testing Library (jsdom), 163 frontend tests passing across 14 files (`test-results-phase-4.txt`, 11:24:38). The run-2 fix strengthened an existing assertion rather than adding a test, so the total is stable at 163.

Visual/responsive/in-browser criteria (layout widths, breakpoints, hover, highlight colours, sticky header, shimmer styling) remain out of jsdom scope and are verified manually per the build spec — not logged as gaps.

No vacuous passes detected.

## Re-audit of run-2 gap

- **F07 "Index status" footer link — destination/label assertion (was WEAK → Coding): RESOLVED.** `Results.test.jsx:445` ("renders an \"Index status\" link") now asserts three things on the resolved `index-status-link`: `toBeInTheDocument()`, `toHaveAttribute('href', '/index-status')`, and `toHaveTextContent('Index status')`. The destination and label are now both verified, so a regression repointing the footer link or relabelling it would fail the test. The test exercises the real render path: the `renderResults()` helper defaults to `/search?q=rights&page=1` (`Results.test.jsx:17`), which renders the results view (not the home redirect), so the footer Link is actually mounted. Source wiring confirmed against the assertions: `Results.jsx:304` renders `<Link to="/index-status" data-testid="index-status-link">Index status</Link>` (React Router resolves `to` to the `href` attribute the test checks), and `main.jsx:21` registers `<Route path="/index-status" element={<IndexingStatusPage />} />`. The navigation seam binding the two F07 surfaces (homepage strip / Results footer → full panel) is now the asserted behaviour, not just an existence check. No new gap introduced by the change.

## Gaps

None.

## Verified

Run-3 confirms the run-2 gap is closed. The full Phase 4 Verified set from run-2 is carried forward unchanged (no requirements regressed; the only delta is the strengthened footer-link assertion above):

**F05 (result display)** — snippet sanitisation verified against raw/unescaped HTML (`<script>`, `<img onerror>`, `<b>`, `&`) with `<mark>` preserved (`sanitizeSnippet.test.js`), both cards wired through it (`SpeechCard.test.jsx`, `QACard.test.jsx`); Speech card metadata/speaker/subject/`<mark>` snippet/View-source attrs and all edge cases (null speaker → "Speaker unknown"; missing party/constituency omitted; null `full_text_en` placeholder; `is_translated`; null `source_url` omits link; `speaker_name_unresolved` raw name; CA omits session); Q+A card metadata/subject/`Q.`/questioner/`+N others`/minister line/supplementary prefix; result count thresholds (≤9,999 exact, "10,000+", "0 results" empty state); pagination controls/`aria-current`/ellipsis/>500-page suppression; URL page persistence incl. no-page→page 1 and search-box pre-population from query.

**F02 (frontend)** — homepage search box; inline validation (empty / <2 chars, dismiss on typing); refinement stays on `/search`; no-results vs error distinct; direct `/search` redirects home; request-body construction (`Home.test.jsx`, `Results.test.jsx`, `useSearch.test.js`).

**F06 (sorting)** — three options (Relevance default/first); URL round-trip; sort change re-fetches without changing count; persists across refinement (`constants.test.js`, `Results.test.jsx`).

**F07 (indexing status — frontend)** — homepage strip (counts with separators, body labels, formatted last-updated, null→"Never", "Status unavailable" on rejection and `status:'unavailable'`, zero-count source shown not omitted); full panel `IndexingStatusPage` ("Search Index Status" header, total with separators, per-source CA/LS/RS rows with counts + `Mon YYYY – Mon YYYY` coverage, zero-source "0 records – not yet indexed" with no date range, fresh-deploy all-zero + "Never", total = sum of per-source counts, reads from `GET /api/status`, "Status unavailable" for unavailable/fetch-failure/malformed payloads); **footer-link navigation seam now asserts destination + label** (this run).

**Shared infrastructure** — constants label maps + fallbacks; FilterState defaults/validations/`toApiFilters`; expansion-notice parse/format; 5-skeleton loading state; error+Retry re-issue; Toast render/auto-dismiss/`role=status` (`constants.test.js`, `filterState.test.js`, `expansionNotice.test.js`, `SkeletonCard.test.jsx`, `Toast.test.jsx`, `ResultCard.test.jsx`).
