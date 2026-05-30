# QA Review — Phase 3 Run 1
Date: 2026-05-28
PRD version: v1.0
Prior run: first review

## Status: GAPS FOUND

## Scope

Phase 3 implements the Search API: F02 (search), F03 (filters), F04 (query expansion), F06 (sorting), F07 (indexing status). Files under audit:
- `app/api/routes/search.py`, `app/api/routes/status.py`
- `app/api/services/query_expander.py`, `app/api/services/search.py`
- Tests: `app/tests/api/test_query_expander.py` (27), `test_search_route.py` (30), `test_search_service.py` (53), `test_status_route.py` (15) — 125 new test cases.

Test results: 485 passed, 1 skipped (`test_schema.py` skip is a Phase 1 DB-availability case, irrelevant to Phase 3). No failures.

Note on test approach: All Phase 3 tests use mocked Meilisearch and mocked asyncpg pool — no fixture-backed Meilisearch instance is exercised. PHASES.md Phase 3 exit criteria explicitly call for "all F02, F03, F04, F06, and F07 test requirements pass at the API level using fixture data pre-loaded into a local Meilisearch instance". Several requirements below cannot be verified meaningfully without that integration layer; they are flagged accordingly.

## Gaps

| Feature | Requirement | Gap type | Routes to | Notes |
|---------|-------------|----------|-----------|-------|
| F02 | Phrase query non-adjacency — a record containing `fundamental` and `rights` separated by other words must NOT match a phrase query for `"fundamental rights"` (test spec § Phrase Query Non-Adjacency) | MISSING | CODING AGENT | No test (unit or integration) verifies phrase-query non-adjacency. The query expander preserves quoted phrases (`strip_stop_words` `test_quoted_phrase_preserved`) but no test confirms the quoted phrase is forwarded to Meilisearch as a phrase query, nor that non-adjacent matches are excluded. Add a fixture-backed integration test in `app/tests/api/` that loads two records (one with adjacent "fundamental rights", one with the words separated) and asserts the phrase query returns only the adjacent record. |
| F02 | Case insensitivity — queries `"article 370"`, `"Article 370"`, `"ARTICLE 370"` must return identical result sets in identical rank order (feature spec § Acceptance Criteria; test spec § Case Insensitivity) | MISSING | CODING AGENT | The query expander lowercases tokens internally (`_tokenize`) but no API-level test asserts that varying query case yields identical responses. Add a test that issues the same query in three casings and asserts equal `total` and equal `results` order. With fixtures this should run against Meilisearch; with mocks at minimum assert the search query forwarded to Meilisearch is normalized identically across casings. |
| F02 | Special character handling — queries containing parentheses, brackets, quotation marks, or boolean operators as literal characters must not cause a search error (feature spec § Edge Cases; test spec § Special Character Handling) | MISSING | CODING AGENT | `test_special_chars_only_returns_400` only covers the special-chars-only validation path. No test confirms a mixed query like `"Article 370 & (Constitution)"` or `"Section [4(1)]"` executes without error and reaches Meilisearch. Add a route-level test that posts such queries and asserts 200 with no Meilisearch parsing failure. |
| F02 | A record matching all original query terms ranks above a record matching only synonym expansions for the same query (feature spec § Acceptance Criteria; test spec § Expansion Weight Ordering; PHASES.md exit criteria) | MISSING | CODING AGENT | No test verifies the weight ordering original > synonym > spell-correction. The Coding Agent relies entirely on Meilisearch's synonym scoring, but no fixture test exists to confirm the configured behavior. Add an integration test with two fixture records — one containing the original term, one containing only a synonym — that asserts the original-term record ranks first when both are searched. |
| F03 | Session filter active → CA records must be absent from the result set (feature spec § Acceptance Criteria; test spec § Session Filter Excludes CA Records) | VACUOUS PASS | CODING AGENT | `test_session_filter_excludes_ca_implicitly` only asserts `'session_name CONTAINS "Budget"' in expr` — it does not exercise any record retrieval, so the requirement "CA records must be absent from the result set" is unverified. The test's docstring acknowledges the reliance on Meilisearch behavior but the actual exclusion is never tested. Add a fixture-backed test that indexes one CA record (null `session_name`) and one LS record (non-null `session_name`), applies a session filter, and asserts the CA record is excluded. |
| F03 | Date range gap (1948-01-01 to 2015-12-31) must return CA records from 1948-1950 AND LS/RS records from 2014-2015 with no error and no records from gap years (test spec § Date Range Gap; PHASES.md exit criteria) | WEAK | CODING AGENT | `test_date_range_gap_no_error` asserts only `status_code == 200` with empty mock results. It does not verify (a) CA records in 1948–1950 are included, (b) LS/RS records in 2014–2015 are included, or (c) no records from 1951–2013 appear. Add a fixture-backed test with at least three records across the date boundary and assert correct membership of the result set. |
| F03 | Speaker substring filter — `"Singh"` matches Manmohan Singh, Rajnath Singh, V.P. Singh (test spec § Speaker Substring Matching) | MISSING | CODING AGENT | `test_speaker_filter` only asserts the filter expression string is constructed. No test verifies the substring semantics. Add a fixture-backed test that indexes multiple speakers containing "Singh" and asserts all three are returned for a speaker filter of `"Singh"`. |
| F04 | Spell correction must NOT apply inside quoted phrase queries (test spec § Spell Correction Suppression in Phrases) | MISSING | CODING AGENT | No test exists for this requirement. `strip_stop_words` preserves quoted phrases but no test asserts that a quoted misspelled term (e.g. `"Parliment debate"`) is searched verbatim with no correction. Add a test asserting Meilisearch receives the quoted form (with `attributesToSearchOn` or equivalent) and no typo tolerance is applied. |
| F04 | Ambiguous abbreviation — `"SC"` must generate expansions for ALL known dictionary expansions (test spec § Ambiguous Abbreviation Expansion) | MISSING | CODING AGENT | `test_sc_expands` only verifies expansion to `Scheduled Castes` against a single-pair fixture. No test loads the real `synonyms.json`, finds an ambiguous abbreviation (if multiple defined), and asserts all expansions appear in `expansion_notice`. Either confirm `synonyms.json` has no truly ambiguous entries (and update the test spec) or add a multi-expansion test against the real dictionary. |
| F04 | Dictionary is sole source of synonyms — a hardcoded synonym in application logic (not in `synonyms.json`) must cause a test to fail (test spec § Dictionary as Sole Source) | MISSING | CODING AGENT | No test enforces this invariant. `test_expand_query_uses_disk_synonyms` confirms disk loading works, but does not detect a hypothetical hardcoded synonym. Add a test that asserts every expansion produced by `expand_query` (over a sample query set) can be traced back to an entry in `synonyms.json` — i.e. expansion behavior with an empty `synonyms_data=[]` produces no expansions for any query. |
| F04 | Synonyms apply to LS, RS, and CA records equally (feature spec § Acceptance Criteria) | MISSING | CODING AGENT | No test verifies cross-source applicability. Add a fixture-backed test that indexes one record per source with the same synonym-triggering term and asserts all three appear in results when the abbreviated form is queried. |
| F06 | Relevance sort isolation — switching from chronological to relevance must reorder by score; date-based order must not silently persist as a tiebreaker (test spec § Relevance Sort Isolation; PHASES.md exit criteria) | MISSING | CODING AGENT | `test_sort_relevance_no_sort_key` asserts only that the `sort` parameter is omitted from the Meilisearch call. No test verifies that the relevance-only response does not exhibit date-ordering as an implicit tiebreaker. With fixtures, index two records with equal relevance and different dates, switch from chronological to relevance, and assert the order does not match the prior chronological order. Without fixtures, document that Meilisearch's default ranking rules from `setup_meilisearch.py` exclude `date` from ranking rules (this is verifiable as a config assertion). |

## Notes on Verified Areas

The following requirements have adequate test coverage and are confirmed in this run:

**F02 — Full-text Search**
- Validation: empty query, single-char query, special-chars-only query → 400 with `query_too_short`
- Validation: all-stop-words query → 400 with `query_only_stopwords`
- Stop-words mixed with real terms passes
- Query truncation: 501-char query executes without error; 500-char boundary executes
- Response shape includes `total`, `total_display`, `page`, `total_pages`, `per_page`, `expansion_notice`, `results`
- `total_display`: comma-formatted below 10,000; "10,000+" at and above 10,000
- Snippet contains `<mark>` tags around matched terms; HTML-escaped before mark wrapping
- Snippet from supplementary section detected for Q+A records (`snippet_from_supplementary: true`)
- Null `full_text_en` produces no `snippet` / `snippet_from_supplementary` keys (matches DATA-MODELS.md 3.1)
- 503 response on Meilisearch failure with bare top-level error body shape

**F03 — Search Filters**
- All five filter dimensions present in `FilterInput` (sources, proceeding_types, date_from, date_to, speaker, session)
- Validation: empty `sources` array → 400 `sources_empty`
- Validation: empty `proceeding_types` array → 400 `proceeding_types_empty`
- Validation: `date_from > date_to` → 400 `date_range_invalid`; equal dates pass; only-`date_from` passes
- Whitespace-only speaker and session values produce no filter clause
- All active filter dimensions joined with ` AND ` in the Meilisearch filter expression (6-part expression has 5 ANDs)
- CA-only with non-Debate proceeding type does not error (route returns 200; expression sent to Meilisearch)
- Page parameter forwarded to Meilisearch

**F04 — Query Expansion**
- Stop-word stripping: `"the right to speech"` → `"right speech"`; all-stop-words returns flag; quoted phrases preserved
- Bidirectionality: PM↔Prime Minister, Lok Sabha↔House of the People↔Lower House, MGNREGA↔NREGA↔full name
- Phrase synonym detection consumes all tokens of the phrase, preventing double expansion
- Partial phrase ("rights" alone) does not trigger phrase synonym
- Substring non-expansion: `"MGNREGA"` does not trigger `"PM"` expansion; `"scheduled"` does not trigger `"SC"`
- Already-in-query terms are excluded from `expansion_notice`
- Synonyms loaded from disk (`data/synonyms.json`); cached after first load
- Short term exemption configured (`minWordSizeForTypos.oneTypo == 4`) — verified in `tests/test_setup_meilisearch.py` (Phase 1)

**F06 — Sorting**
- `relevance` → empty sort param list (Meilisearch default ranking)
- `chronological` → `["date:asc", "sequence_within_sitting:asc"]` (secondary key present)
- `reverse_chronological` → `["date:desc", "sequence_within_sitting:desc"]` (secondary key present)
- Default sort in `SearchRequest` is `relevance`
- Invalid sort value rejected by Pydantic validator

**F07 — Indexing Status**
- Populated response: `status: "ok"`, `total_records`, all three source blocks with count + date_from + date_to, `last_updated` as ISO timestamp
- Total equals sum of per-source counts (asserted by arithmetic comparison)
- Never-run response: row is None → all counts 0, all dates null, `last_updated: null`
- Unavailable response: DB exception → `{"status": "unavailable"}` at HTTP 200 (not 503)
- Status route reads from PostgreSQL only — verified by asserting Meilisearch failure does not affect status response
- Zero-count source with null date_from/date_to handled correctly in populated response
- Last updated reflects DB timestamp, not request time

## Gap Counts by Routing

- CODING AGENT: 12 gaps (10 MISSING, 1 WEAK, 1 VACUOUS PASS)
- PRODUCT AGENT: 0 gaps

## Recommended Next Step

Address the 12 gaps above. The majority require fixture-backed integration tests against a local Meilisearch instance — this aligns with PHASES.md Phase 3 exit criteria explicitly stating "API level using fixture data pre-loaded into a local Meilisearch instance". If the team chooses to defer integration tests (a project-scope decision), document that decision and downgrade the verification claims for the affected requirements; the current mocked-only suite cannot verify Meilisearch-delegated behavior.
