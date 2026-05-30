# QA Review — Phase 1 Run 3
Date: 2026-05-28
PRD version: v1.0
Prior run: run-2 GAPS FOUND — 1 WEAK assertion (Q+A Case 3 bilingual test used OR instead of AND); routed to Coding Agent.

## Status: CLEAR

## Gaps

| Feature | Requirement | Gap type | Routes to | Notes |
|---------|-------------|----------|-----------|-------|

(No gaps. All requirements from F01 parsers/segmenters/schema/setup_meilisearch and F04 synonyms.json have adequate test coverage.)

---

## Run-2 Gap Resolution

| Run-2 gap | Resolution status |
|-----------|-----------------|
| Q+A segmenter Case 3 bilingual test used OR (only one of original English or translated Hindi portion needed to be present) | RESOLVED — `tests/segmenters/test_qa_segmenter.py::TestQaLanguageHandling::test_case3_bilingual_exchange` lines 297–300 now use two separate `assert` statements: `assert "rural employment in English" in r["full_text_en"]` AND `assert "translated Hindi portion" in r["full_text_en"]`. Each has a descriptive failure message. Both must be present for the test to pass, correctly enforcing the test spec requirement that bilingual exchanges contain both portions concatenated. Test PASSES, confirming the implementation produces both portions in full_text_en. |

---

## Verified

All Phase 1 requirements continue to have adequate coverage. Summary by area:

**F01 / HTML parser** — date parsing across formats; proceeding type detection for all 9 LS/RS types (debate, starred, unstarred, zero_hour, short_notice_question, calling_attention, short_duration_discussion, adjournment_motion, private_member_bill); source validation (CA raises); subject, session_name, raw_text, source_url extraction; script tag exclusion; empty HTML; fixture-based tests for LS debate, LS unstarred, RS starred.

**F01 / PDF parser** — source validation (XX raises); CA and LS sources; volume preserved/null; source URL; digital text extraction; OCR fallback branch triggered for blank pages (mocked); ocr_low_confidence True for low-confidence OCR pages, False for digital pages; OCR confidence stored per page; page numbering 1-based; multi-page text join; proceeding_type_hint; date from first page; bytes input.

**F01 / Speech segmenter** — unattributed exclusion (5 strings); presiding officer exclusion (9 strings); ZERO HOUR not unattributed; all 4 language cases (Case 2 verifies Devanagari absent + translation text present; Case 3 verifies both English original AND translated portion present); speaker_role=member; speaker_role field always present and non-null; speaker_name_unresolved=True initially; ocr_low_confidence propagation; same-member-twice produces 2 records with distinct sequences; sequence 1-based; metadata propagation; CA source; empty text / only-unattributed return empty list; fixture-based debate test.

**F01 / Q+A segmenter** — starred basics (question number, type, source/date, full_text non-null, multiple questions, questioner list); multiple supplementaries completeness (3 rounds, content from all 3 verified); language Cases 1 (English, is_translated=False), 2 (Hindi+translation, Devanagari absent), 3 (bilingual, both portions present), 4 (Hindi-only, full_text_en=None + has_untranslated=True); unstarred basics + exactly-1-questioner; validation (invalid source/type, empty text); fixture-based tests.

**F01 / Schema** — file exists; speeches, qa_exchanges, index_status tables; dedup_key UNIQUE on both speeches and qa_exchanges (separately tested); all required columns on both tables; idx_speeches_date index; GIN index on questioner_names; PostgreSQL execution test present (correctly skipped when TEST_DATABASE_URL not set).

**F01 / setup_meilisearch.py** — `_load_synonyms()` structure (list of {word, synonyms} dicts, synonyms are string lists, no self-expansion, file-not-found raises); bidirectionality specifically verified for PM↔Prime Minister and Lok Sabha↔House of People; exhaustive bidirectionality across all groups in synonyms.json; index constants match DATA-MODELS.md 2.3 (INDEX_NAME, SEARCHABLE_ATTRIBUTES order, FILTERABLE_ATTRIBUTES coverage, SORTABLE_ATTRIBUTES, RANKING_RULES order, PAGINATION.maxTotalHits=10000); typo tolerance enabled with oneTypo=4 (4-char terms eligible per spec), twoTypos=9, disabled on date/source/proceeding_type/source_url.

**F04 / Synonyms** — JSON valid; all 5 categories present; all groups ≥2 terms; legislative bodies (all 10 terms + Lok Sabha/House of People and Rajya Sabha/Council of States grouping); constitutional terminology (fundamental rights three-way group including Part III rights; DPSP three-way group including short form; amendment ↔ constitutional amendment; Preamble ↔ preamble to the Constitution); parliamentary procedure (starred/oral, unstarred/written, zero-hour, private member bill, Question Hour↔question period, calling attention motion, adjournment short form, division/vote); all 16 abbreviation pairs plus OBC → Other Backward Communities and SC/SC-ST separation; all legislation including RTI/RTE Act forms and MGNREGA/NREGA same-group; bidirectionality structural check.

---

## Test execution summary

203 passed, 1 skipped (test_schema_executes_against_postgres — correctly skipped, no TEST_DATABASE_URL), 1 warning (urllib3/LibreSSL, harmless). No failures, no unexpected skips, no vacuous passes remaining.

---

## Phase Completion Recommendation

Both reviews on Phase 1 latest runs are now CLEAR:
- Arch Review: run-2 CLEAR
- QA Review: run-3 CLEAR

Phase 1 is eligible to be marked Complete during the next `/resume` reconciliation. Build is unblocked to proceed to Phase 2.
