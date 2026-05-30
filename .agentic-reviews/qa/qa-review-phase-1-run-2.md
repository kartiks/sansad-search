# QA Review — Phase 1 Run 2
Date: 2026-05-28
PRD version: v1.0
Prior run: run-1 GAPS FOUND — 22 gaps (12 MISSING, 7 MISSING synonyms coverage, 2 WEAK, 1 VACUOUS PASS); all routed to Coding Agent.

## Status: GAPS FOUND

## Gaps

| # | Feature | Requirement | Gap type | Routes to | Notes |
|---|---------|-------------|----------|-----------|-------|
| 1 | F01 / Q+A segmenter | Language Case 3 (bilingual): `full_text_en` must contain BOTH original English portions AND translated Hindi portions | WEAK | CODING AGENT | `tests/segmenters/test_qa_segmenter.py::TestQaLanguageHandling::test_case3_bilingual_exchange` uses an OR assertion: `"rural employment in English" in r["full_text_en"] or "translated Hindi portion" in r["full_text_en"]`. Test spec requires both portions present. The test passes if only one part is captured, masking a bug where the English original or the translation is silently dropped. Fix: split into two separate `assert` statements (or replace `or` with `and`) so both strings must be in `full_text_en` for the test to pass. |

---

## Run-1 Gap Resolution

All 22 run-1 gaps were addressed. Verification of each:

| Run-1 gap | Resolution status |
|-----------|-----------------|
| HTML parser: short_notice_question detection | RESOLVED — `test_short_notice_question` added; PASSED |
| PDF parser: OCR fallback invocation | RESOLVED — `test_ocr_branch_triggered_for_blank_page` uses mock, asserts `_ocr_page` called, `pages[0]["ocr"] is True`, OCR text in raw_text; PASSED |
| PDF parser: ocr_low_confidence=True for low-confidence pages | RESOLVED — `test_ocr_low_confidence_true_when_confidence_below_threshold` uses `OCR_CONFIDENCE_THRESHOLD - 1.0`, asserts `ocr_low_confidence is True`; PASSED |
| PDF parser: test_accepts_bytes_input vacuous | RESOLVED — test now also asserts `result["source"] == "LS"`; PASSED |
| Speech segmenter: case 2 weak (Devanagari absent check) | RESOLVED — test now asserts translation text present AND verifies no Devanagari chars via Unicode range check; PASSED |
| Speech segmenter: case 3 weak (both portions present) | RESOLVED — test now uses two separate asserts for original English and translated portion; PASSED |
| Speech segmenter: speaker_role not tested | RESOLVED — `test_speaker_role_member_for_regular_member` asserts `== "member"`; `test_speaker_role_field_present_in_output` asserts field present and non-null; PASSED |
| Q+A segmenter: multiple supplementaries completeness | RESOLVED — `test_all_supplementaries_captured` exercises 3 supplementary rounds, verifies content from all three in full_text_en via distinct keyword checks per round; PASSED |
| Q+A segmenter: language case 2 (Hindi+translation) | RESOLVED — `test_case2_hindi_with_translation` asserts `is_translated=True`, no Devanagari, translation text present; PASSED |
| Q+A segmenter: language case 3 (bilingual) | PARTIAL — test added and passing, but assertion uses OR (see gap #1 above) |
| Q+A segmenter: unstarred questioner field | RESOLVED — `test_unstarred_questioner_names_has_exactly_one_element` asserts list with exactly 1 element, not "Unknown"; PASSED |
| Schema: qa_exchanges unique dedup_key | RESOLVED — `test_schema_has_dedup_key_unique_qa_exchanges` added; PASSED |
| setup_meilisearch.py: no tests | RESOLVED — `TestLoadSynonyms` covers structure, bidirectionality (PM↔Prime Minister, Lok Sabha↔House of People), no self-expansion, and full exhaustive bidirectional check across all groups; `TestIndexConfiguration` validates all constants against DATA-MODELS.md; `oneTypo` corrected from 5 to 4; PASSED |
| F04: Part III rights | RESOLVED — `test_fundamental_rights_three_way_same_group` verifies all three terms in same group; PASSED |
| F04: amendment ↔ constitutional amendment | RESOLVED — `test_amendment_constitutional_amendment` and `test_amendment_same_group`; PASSED |
| F04: preamble to the Constitution | RESOLVED — `test_preamble_same_group`; PASSED |
| F04: Directive Principles short form | RESOLVED — `test_dpsp_three_way_same_group`; PASSED |
| F04: Question Hour ↔ question period | RESOLVED — `test_question_hour_question_period` and `test_question_hour_same_group`; PASSED |
| F04: calling attention motion | RESOLVED — `test_calling_attention_same_group`; PASSED |
| F04: adjournment short form | RESOLVED — `test_adjournment_same_group`; PASSED |
| F04: Other Backward Communities | RESOLVED — `test_obc_other_backward_communities`; PASSED |
| F04: Right to Information Act | RESOLVED — `test_rti_right_to_information_act`; PASSED |
| F04: Right to Education Act | RESOLVED — `test_rte_right_to_education_act`; PASSED |

---

## Verified

All requirements verified in run-1 remain verified. The following were confirmed clean in run-2:

**F01 / HTML parser:** date parsing (6 formats), proceeding type detection (all 9 types including short_notice_question now), source validation, subject/session_name/raw_text/source_url extraction, script tag exclusion, empty HTML, fixture-based tests.

**F01 / PDF parser:** source validation, CA/LS sources, volume, source URL, digital text extraction, OCR fallback path (mocked), ocr_low_confidence flag (True and False cases), OCR confidence on page entry, page numbering, proceeding_type_hint, date from first page, multi-page join, bytes input.

**F01 / Speech segmenter:** unattributed exclusion (5 strings), presiding officer exclusion (9 strings), zero hour not unattributed, all 4 language cases (with Devanagari-absent checks in case 2 and both-portions checks in case 3), speaker_role=member, speaker_name_unresolved=True initially, ocr_low_confidence propagation, sequence 1-based, same-member-twice, metadata propagation, CA source, empty text, fixture-based.

**F01 / Q+A segmenter:** starred basics (number, type, source/date, full_text, multiple questions, questioner list), multiple supplementaries completeness (3 rounds), language cases 1, 2, and 4 fully verified; case 3 PARTIAL (see gap #1); unstarred basics + exactly-1-questioner; validation (invalid source/type, empty text); fixture-based.

**F01 / Schema:** existence, all 3 tables, all required columns, UNIQUE dedup_key on both speeches and qa_exchanges, date index, GIN questioner_names index; PostgreSQL execution test present and correctly skipped.

**F01 / setup_meilisearch.py:** `_load_synonyms` structure, bidirectionality (specific pairs and exhaustive all-groups check), no self-expansion, nonexistent-file error; index constants: name, searchable/filterable/sortable attributes, ranking rules order, pagination maxTotalHits=10000, typo tolerance enabled, oneTypo=4, twoTypos=9, disabled on structural attributes.

**F04 / Synonyms:** all 5 categories present; all groups ≥2 terms; all legislative body terms and same-group checks; all constitutional terminology including 3-way groups and amendment pair; all parliamentary procedure including Question Hour/question period, calling attention motion, adjournment short form; all 16 abbreviation pairs including OBC→Other Backward Communities; all legislation including RTI/RTE Act forms; MGNREGA/NREGA same-group; bidirectionality structural check.

---

## Test execution summary

203 passed, 1 skipped (test_schema_executes_against_postgres — correctly skipped, no TEST_DATABASE_URL), 1 warning (urllib3/LibreSSL compatibility, harmless). No failures.
