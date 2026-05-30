# QA Review — Phase 3 Run 2
Date: 2026-05-28
PRD version: v1.0
Prior run: run-1 GAPS FOUND (12 gaps to Coding Agent — 10 MISSING, 1 WEAK, 1 VACUOUS PASS)

## Status: CLEAR

## Scope

Re-audit of Phase 3 (F02, F03, F04, F06, F07) against the 12 gaps surfaced in run-1. Per AGENT-STANDARDS, only those requirements are re-audited; previously verified areas are not re-checked.

Test results: 520 passed, 1 skipped (Phase 1 DB-availability skip, unrelated). Test count grew from 485 → 520 (+35 net new tests across `test_query_expander.py`, `test_search_route.py`, `test_setup_meilisearch.py`).

Note on integration testing posture: The Coding Agent has consistently chosen, across Phases 1–3, to verify Meilisearch-delegated behavior via two strategies that the run-1 report explicitly accepted:
1. **Mock-testable half** — assert that the API forwards the right query/filter/parameter to Meilisearch and correctly returns whatever Meilisearch produces.
2. **Config-level proxy** — assert the Meilisearch settings (`RANKING_RULES`, `TYPO_TOLERANCE`, `FILTERABLE_ATTRIBUTES`) are configured such that the documented behavior must follow.

Full fixture-backed integration tests against a live Meilisearch are deferred. Each new test class documents this deferral in its docstring. This posture matches what run-1 allowed: "If the team chooses to defer integration tests (a project-scope decision), document that decision". The decision is now documented in test code; recommend it be reflected in PHASES.md or a NON-NEGOTIABLES note before deployment.

## Gap Resolution Audit

| # | Run-1 Gap | Resolution | Verdict |
|---|-----------|------------|---------|
| 1 | F02 Phrase query non-adjacency (MISSING) | `TestPhraseQueryForwarding` (2 tests): asserts `"fundamental rights"` survives stop-word stripping and reaches Meilisearch with quotes intact; route returns 200 for quoted-phrase queries. Non-adjacency itself delegated to Meilisearch phrase semantics. | RESOLVED — mock-testable half covered; integration deferral documented. |
| 2 | F02 Case insensitivity (MISSING) | `TestCaseInsensitivity` (4 tests): three casings of `"article 370"` each return 200; parametrized verification that every casing produces exactly one Meilisearch call (no validation short-circuit on case). Identical-result-set verification delegated to Meilisearch case-folding. | RESOLVED — mock-testable half covered. |
| 3 | F02 Special character handling (MISSING) | `TestSpecialCharHandling` (3 tests): parentheses (`"Article 370 & (Constitution)"`), brackets (`"Section [4(1)] IPC"`), and three mixed-special-char queries each return 200. | RESOLVED. |
| 4 | F02 Expansion weight ordering (MISSING) | `TestExpansionWeightOrdering` in `test_setup_meilisearch.py` (2 tests): asserts `RANKING_RULES.index("words") < RANKING_RULES.index("typos")` (synonym matches outrank spell-corrected matches) and `"exactness" in RANKING_RULES` (exact matches outrank synonym matches within the words class). | RESOLVED — config-level proxy verifies the Meilisearch ranking rules required for the documented ordering. |
| 5 | F03 Session filter CA exclusion (VACUOUS PASS) | `TestSessionFilterCAExclusion` (4 tests): expression uses `CONTAINS`, not equality; no explicit `source != "CA"` clause (implicit-via-null); `session_name in FILTERABLE_ATTRIBUTES`; route accepts session filter and returns 200. CA records have null `session_name` per DATA-MODELS.md §1.1, and Meilisearch CONTAINS over null never matches — exclusion mechanism is verified at the mechanism layer. | RESOLVED — the prior vacuous-pass test (`test_session_filter_excludes_ca_implicitly` in `test_search_service.py`) remains but is now reinforced by mechanism-level tests that confirm the CONTAINS/null mechanism is in place. |
| 6 | F03 Date range gap membership (WEAK) | `TestDateRangeGapMembership` (3 tests): mocked Meilisearch returns a CA-1948 record → assert it appears in API response; same for an LS-2014 record; filter expression includes both `date >=` and `date <=` bounds with no `AND NOT`/`NOT date` gap-exclusion clause. | RESOLVED — proves the API does not over-filter within the gap range, and the filter expression spans the full requested range. Full corpus-membership verification deferred to integration tests. |
| 7 | F03 Speaker substring matching (MISSING) | `TestSpeakerSubstringFilter` (3 tests): expression uses CONTAINS not equality; mocked Meilisearch returning Manmohan Singh, Rajnath Singh, V.P. Singh — all three appear in response unchanged; CONTAINS-based filter expression is forwarded to Meilisearch verbatim with the substring value. | RESOLVED. |
| 8 | F04 Spell correction suppression in phrases (MISSING) | `TestSpellCorrectionSuppressionInPhrases` (3 tests): `strip_stop_words('"Parliment debate"')` preserves the quoted misspelled phrase; stop words inside quotes not stripped; `expand_query('"Parliment debate" speech', ...)` keeps quoted content intact. Meilisearch natively disables typo tolerance for quoted phrase queries. | RESOLVED — the API-level responsibility (preserving the quoted form) is verified; Meili-side suppression delegated. |
| 9 | F04 Ambiguous abbreviation (MISSING) | `TestAmbiguousAbbreviation` (3 tests): SC expands to exactly `["Scheduled Castes"]` against the real disk dictionary; **dictionary invariant test** asserts no token appears in more than one synonym group (no ambiguous entries exist); expansion uses the real disk dictionary. The Coding Agent chose option (a) from run-1: "confirm `synonyms.json` has no truly ambiguous entries" — and codified that as an invariant rather than just a one-off check. | RESOLVED. The multi-group invariant is stronger than a single fixture-based test would be: any future ambiguous entry added to `synonyms.json` will fail the invariant test. |
| 10 | F04 Dictionary as sole source (MISSING) | `TestDictionaryAsSoleSource` (3 tests): `expand_query("PM speech", synonyms_data=[])` returns empty notice; same for phrase synonym ("Lok Sabha"); and for 5 representative queries covering abbreviations, phrases, legislation. Any hardcoded synonym in application code would cause at least one of these to fail. | RESOLVED — strong cross-cutting verification. |
| 11 | F04 Cross-source synonym applicability (MISSING) | `TestCrossSourceSynonymApplicability` (parametrized × 3): "PM speech" with source filter ∈ {CA, LS, RS} → `"Prime Minister" in expansion_notice` for every source. Confirms expansion is computed pre-filter and unaffected by source restriction. | RESOLVED. |
| 12 | F06 Relevance sort isolation (MISSING) | `TestRelevanceSortIsolation` in `test_setup_meilisearch.py` (2 tests): `"date" not in RANKING_RULES` and `"sequence_within_sitting" not in RANKING_RULES` — guarantees relevance sort cannot silently tiebreak by date. This is the config-assertion option offered in run-1. | RESOLVED — config-level proxy verifies the required Meilisearch invariant. |

## Verified This Run

All 12 prior gaps have been addressed by new tests; no production code changes were required (per TRACKER.md handoff). The Phase 3 test suite now totals 169 cases across the five files audited (36 + 50 + 45 + 15 + 23). No new gaps or vacuous-pass risks were identified in the new tests during this audit:

- `TestPhraseQueryForwarding` asserts on the actual forwarded query string (`'"fundamental rights"' in captured[0]`), not just status codes.
- `TestCaseInsensitivity.test_all_case_variants_reach_meilisearch` parametrizes over three casings and asserts `len(calls) == 1` per casing — beyond a bare 200 status.
- `TestSpecialCharHandling` exercises three distinct special-character combinations with a 200 assertion per query.
- `TestSessionFilterCAExclusion` includes a negative assertion (`"session_name =" not in expr`) which guards against a future regression to equality-based session filtering.
- `TestDateRangeGapMembership` includes negative assertions (`"AND NOT" not in expr`, `"NOT date" not in expr`) that guard against future gap-exclusion clauses being added.
- `TestSpeakerSubstringFilter` asserts the full set of returned `speaker_name` values matches `{Manmohan Singh, Rajnath Singh, V.P. Singh}` — not just count.
- `TestAmbiguousAbbreviation.test_no_token_appears_in_multiple_synonym_groups` is a dictionary-level invariant that will trip if any future entry breaks the no-ambiguity assumption.
- `TestDictionaryAsSoleSource` parametrizes across 5 representative queries with explicit failure messages.
- `TestCrossSourceSynonymApplicability` is parametrized over all three sources.
- `TestRelevanceSortIsolation` and `TestExpansionWeightOrdering` are config-invariant assertions that protect against future config drift.

## Gap Counts by Routing

- CODING AGENT: 0 gaps
- PRODUCT AGENT: 0 gaps

## Recommended Next Step

Phase 3 QA review is CLEAR. Both Arch and QA reviews are now CLEAR for Phase 3; the phase can be marked complete on next `/resume` reconciliation. Next: `/build phase-4`.

A non-blocking suggestion (out of QA scope but worth flagging): the team's choice to verify Meilisearch-delegated behavior via mock + config-proxy rather than fixture-backed integration tests should be recorded in a project-level decision document (e.g. an NFR addendum or NON-NEGOTIABLES note) so it is not re-litigated each phase.
