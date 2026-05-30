# QA Review — Phase 4 Run 1
Date: 2026-05-29
PRD version: v1.0
Prior run: first review

## Status: GAPS FOUND

## Scope note

Phase 4 is the frontend phase (F02 frontend, F05, F06 frontend, F07 frontend). Automated coverage is Vitest + Testing Library (jsdom) — 142 frontend tests passing, 12 files. Backend regression (520 passed, 1 skipped) is the Phase 1–3 safety net and was not re-audited per QA guardrails.

Many Phase 4 "Stop when" criteria are visual/responsive/in-browser (layout widths, breakpoints, hover states, highlight colours, sticky header, skeleton shimmer styling). These are not assertable in jsdom and are verified manually per the build spec — their absence from automated tests is expected and is not logged as a gap. Gaps below are limited to behavioural requirements that a unit/component test can and should cover.

No vacuous passes detected. All 142 frontend assertions verify concrete behaviour (text content, attributes, call arguments, URL state) rather than mere existence/non-throwing — with the snippet-sanitisation exception noted below.

## Gaps
| Feature | Requirement | Gap type | Routes to | Notes |
|---------|-------------|----------|-----------|-------|
| F05 | HTML in snippet must render as plain text; script tags must not execute (F05 edge case + test spec 05 "HTML Sanitisation in Snippet") | WEAK | CODING AGENT | `SpeechCard.test.jsx` (the `renders HTML inside snippet as plain text` case) and `QACard.test.jsx` (`does not execute HTML in snippet`) both feed input that is **already escaped** (`'&lt;script&gt;alert(1)&lt;/script&gt; The <mark>PM</mark> spoke.'`). Both cards render the snippet via `dangerouslySetInnerHTML` (`SpeechCard.jsx:77`, `QACard.jsx:116`). The tests therefore only confirm React renders pre-escaped entities as text — they never exercise the `dangerouslySetInnerHTML` path against **raw/unescaped** HTML, so they cannot catch a regression where a raw `<script>`/`<b>` reaches the card. The QACard case is weaker still: it asserts only `container.querySelector('script')` is null, not the rendered text. A faithful test must feed raw unescaped tags (`<script>alert(1)</script>`, `<b>x</b>`, `&amp;`) and assert no script executes and tags appear as literal text. Note the architectural contract is that the Phase-3 backend strips all HTML except `<mark>`; if the card relies on that contract, the test should still verify the card's behaviour against raw input (or the contract should be made explicit), since the current tests give false confidence about the card's own safety. |
| F02 | Results page presents a persistent search box pre-populated with the current query (F02 acceptance criterion + UI behavior) | MISSING | CODING AGENT | Implemented at `Results.jsx:43` (`inputValue` initialised to `urlQuery`; input `value={inputValue}` at `Results.jsx:137`) but no test asserts it. `Results.test.jsx` exercises refinement (changing the input) and the result-count line text, but never asserts that on load `results-search-input` has value equal to the URL query. Add a test: render `/search?q=fundamental+rights&page=1` and assert `getByTestId('results-search-input')` has value `fundamental rights`. |
| F07 | A source with zero indexed records displays "0 records – not yet indexed" with no date range; per-source date coverage shown (F07 feature spec + test spec 07 "Zero-Source Row Format") | MISSING | PRODUCT AGENT | No test covers the zero-source row format. The fresh-deploy test in `Home.test.jsx` (`renders "Never" for last_updated when null`) passes `count: 0` sources but asserts only `Last updated: Never`. The implemented status strip (`Home.jsx:13` `formatStatusStrip`) renders `"0 Constituent Assembly records · …"` and omits per-source date coverage entirely — it does not produce the spec's `"0 records – not yet indexed"` string or any per-source date range. This is a discrepancy between the F07 spec/test-spec display format and the condensed homepage strip actually built. Product must clarify whether the homepage strip must honour the F07 per-source "0 records – not yet indexed" format and per-source date coverage, or whether the condensed strip (counts + last-updated only) is the accepted Phase 4 representation, before a meaningful test can be written. |
| F05 | Query term appearing in a highlighted metadata field (e.g., speaker name) and in the snippet is highlighted independently in both (F05 edge case) | EDGE CASE | PRODUCT AGENT | This edge case states metadata fields are highlighted, but the F05 displayed-fields tables, snippet-generation section, and acceptance criteria specify highlighting only in the snippet. The cards render `speaker_name`/`subject` as plain text (`SpeechCard.jsx:58-67`, `QACard.jsx:73-92`) and the Phase-3 backend wraps `<mark>` in the snippet only. The edge case contradicts the rest of F05. Product must resolve whether metadata-field highlighting is required (and update the test spec accordingly) before this can be tested or built; routing a test for an unconfirmed behaviour to Coding would be premature. |
| F05 | A URL missing the page parameter defaults to page 1 of the query results (test spec 05 "Page URL Persistence") | MISSING | CODING AGENT | Implemented via `clampPage(params.get('page') || '1')` at `Results.jsx:30-34`, and direct `/search?q=X&page=3` is tested. The complementary case — `/search?q=X` with no `page` param loads page 1 (POST body `page === 1`) — is not asserted. Low severity (behaviour is implemented and indirectly relied upon). Add a test rendering `/search?q=rights` (no page) and asserting the search request body `page === 1`. |

## Verified

The following requirements have adequate, non-vacuous test coverage confirmed this phase:

**F02 (frontend)**
- Homepage search box visible (wordmark, tagline, input) — `Home.test.jsx`
- Inline validation: empty submission and `< 2` non-whitespace chars show "Enter at least 2 characters to search." and do not navigate; message dismisses on resumed typing — `Home.test.jsx`, `Results.test.jsx`
- Refinement keeps user on `/search` and updates `q=` — `Results.test.jsx`
- No-results state shown distinctly from error — `Results.test.jsx`
- Direct `/search` with no query redirects home — `Results.test.jsx`
- Request body construction: default filters omitted, narrowed filters serialised, page clamped `≥ 1`, sort defaults to relevance, network/HTTP errors surfaced — `useSearch.test.js`

**F05 (result display)**
- Speech card: metadata row (proceeding badge, body, date, session), speaker, subject, `<mark>`-highlighted snippet, View source new-tab attributes (`target=_blank`, `rel` incl. `noopener`) — `SpeechCard.test.jsx`
- Speech edge cases: `speaker_name: null` → "Speaker unknown"; missing party/constituency omitted with no placeholder; party-only shown; `full_text_en: null` → untranslated placeholder with all metadata still shown; `is_translated` indicator shown/omitted; `source_url: null` omits link; `speaker_name_unresolved` shows raw name with no error indicator; CA record omits session line — `SpeechCard.test.jsx`
- Q+A card: metadata, subject, `Q.` question number, questioner row with party, "Answered by [Minister], [Ministry]" single line, snippet, View source — `QACard.test.jsx`
- Co-signatory display: 1 questioner → no "+N others"; 4 total → "+3 others" (incl. `formatQuestionerNames` unit) — `QACard.test.jsx`
- Supplementary-exchange prefix shown when flag set, omitted when false — `QACard.test.jsx`
- ResultCard dispatch by `record_type` (speech/qa/null) — `ResultCard.test.jsx`
- Result count thresholds: exact for `≤ 9,999` (incl. boundary 9,999), "10,000+ results" at exactly 10,000 and above, "0 results" for zero, empty/"0 results" + empty-state both present — `Pagination.test.jsx`, `Results.test.jsx`
- Pagination: Previous/Next, disabled at first/last page, current-page `is-current` + `aria-current`, page-list ellipsis logic, `onPageChange` call args, total-page hint hidden above 500-page threshold and shown within it — `Pagination.test.jsx`
- URL page persistence: page change writes `page=N`; direct `/search?q=X&page=3` loads page 3 (body `page === 3`, `query === 'rights'`) — `Results.test.jsx`

**F06 (sorting)**
- Three sort options exposed with Relevance first/default — `constants.test.js`
- Defaults to Relevance when no `sort` param; `chronological` and `reverse_chronological` round-trip via URL and into POST body — `Results.test.jsx`
- Changing sort updates URL, re-fetches with new sort, and does not change the result count — `Results.test.jsx`
- Sort persists across query refinement — `Results.test.jsx`

**F07 (indexing status — frontend)**
- Homepage status strip renders counts with thousands separators, body labels, and formatted last-updated date — `Home.test.jsx`
- `last_updated: null` → "Last updated: Never" — `Home.test.jsx`
- "Status unavailable" on fetch rejection and on `status: 'unavailable'` payload (degraded path does not crash) — `Home.test.jsx`
- Results page renders persistent "Index status" footer link — `Results.test.jsx`

**Shared infrastructure**
- Constants: full F05 proceeding-type label map + null/unknown fallbacks, source labels, default arrays, sort options, canonical text strings — `constants.test.js`
- FilterState: defaults (all sources/types, null date/speaker/session), fresh-object isolation, default detection, validations (empty sources, empty types, From > To, From == To allowed), `toApiFilters` divergence-only serialisation + trimming — `filterState.test.js`
- Expansion notice: parse/format/`hasExpansion`, "Also searching for: a, b" — `expansionNotice.test.js`, `Results.test.jsx`
- Loading state shows exactly 5 skeleton cards; SkeletonCard shimmer blocks + `aria-hidden` — `Results.test.jsx`, `SkeletonCard.test.jsx`
- Error state with Retry re-issues fetch — `Results.test.jsx`
- Toast: message render, falsy → null, 3s auto-dismiss (+ custom duration boundary), `role=status` — `Toast.test.jsx`
