# QA Review — Phase 1 Run 1
Date: 2026-05-28
PRD version: v1.0
Prior run: first review

## Status: GAPS FOUND

## Gaps

| # | Feature | Requirement | Gap type | Routes to | Notes |
|---|---------|-------------|----------|-----------|-------|
| 1 | F01 / HTML parser | Proceeding type detection must handle all LS/RS types including short notice questions | MISSING | CODING AGENT | `test_detect_proceeding_type` covers 7 types + default but omits `short_notice_question`. Add a test in `tests/parsers/test_html_parser.py::TestDetectProceedingType` asserting `_detect_proceeding_type("Short Notice Question on...")` returns `"short_notice_question"`. |
| 2 | F01 / PDF parser | OCR fallback invoked when page has no embedded text; scanned pages flagged | MISSING | CODING AGENT | No test verifies OCR is attempted for pages with no embedded text, nor that `ocr_low_confidence=True` is produced for low-confidence OCR output. `test_ocr_low_confidence_false_for_digital_pdf` covers the False case only. Add tests using a mock or a scanned-page fixture: one test verifying the OCR branch is triggered, one verifying `ocr_low_confidence=True` is set when confidence is below `OCR_CONFIDENCE_THRESHOLD`. |
| 3 | F01 / PDF parser | `test_accepts_bytes_input` asserts nothing meaningful | VACUOUS PASS | CODING AGENT | `tests/parsers/test_pdf_parser.py::TestParsePdf::test_accepts_bytes_input` only asserts `isinstance(result, dict)`. Passes even if the function returns an empty dict. Strengthen to assert at minimum that `result["source"]` equals the passed source. |
| 4 | F01 / Speech segmenter | Case 2 (Hindi + translation): `full_text_en` must contain translation text, not Devanagari | WEAK | CODING AGENT | `tests/segmenters/test_speech_segmenter.py::TestLanguageHandling::test_case2_hindi_with_translation` checks `full_text is not None` and a loose `"translation" in full_text.lower() or "English" in full_text`. Test spec requires: "full_text_en must contain the translation text, not the Devanagari text and not null." Strengthen: assert Devanagari characters are absent from the returned `full_text`, and the English translation text is present. |
| 5 | F01 / Speech segmenter | Case 3 (bilingual): `full_text_en` must contain both original English and translated Hindi portions in order | WEAK | CODING AGENT | `tests/segmenters/test_speech_segmenter.py::TestLanguageHandling::test_case3_bilingual_concatenated` only checks `full_text is not None`. Test spec requires both original English portions and translated Hindi portions are concatenated in order. Strengthen: assert both a known English string ("The first part is in English") and the translated English portion ("translated portion") are present in `full_text`. |
| 6 | F01 / Speech segmenter | `speaker_role` field must be set correctly (member / minister) | MISSING | CODING AGENT | No test verifies `speaker_role` is populated in speech unit output. `test_metadata_propagated_to_speeches` checks source, date, session_name, proceeding_type, subject — but not `speaker_role`. Add a test that a regular member speech sets `speaker_role == "member"`, and (if the segmenter can detect it) that a speaker name containing "MINISTER" sets `speaker_role == "minister"`. |
| 7 | F01 / Q+A segmenter | Starred Q+A must capture ALL supplementary exchanges, not just the first | MISSING | CODING AGENT | Test spec (Starred Question Completeness): "A starred Q+A unit must include every supplementary question and ministerial response present in the source record, not just the first supplementary exchange." No test exercises a starred question with two or more supplementary rounds. Add a test in `test_qa_segmenter.py` with text containing e.g. three supplementary exchanges and assert `full_text_en` contains content from all three supplementaries. |
| 8 | F01 / Q+A segmenter | Language Case 2 (Hindi with translation) in Q+A exchanges | MISSING | CODING AGENT | Phase 1 stop condition requires all four language handling cases covered for both segmenters. Q+A `TestQaLanguageHandling` covers Case 1 (English) and Case 4 (Hindi-only). Add a test for Case 2: Q+A text with Hindi + `[Translation]` marker → `is_translated=True`, `full_text_en` is non-null and contains translation text, Devanagari absent. |
| 9 | F01 / Q+A segmenter | Language Case 3 (bilingual) in Q+A exchanges | MISSING | CODING AGENT | Same gap as #8 for Case 3. Add a test for a bilingual Q+A exchange (mixed Hindi/English with translation markers) → `is_translated=True`, `full_text_en` contains both original English and translated Hindi portions. |
| 10 | F01 / Q+A segmenter | Unstarred record must use `questioner_name` field (or single-element form) per feature spec | MISSING | CODING AGENT | Feature spec: "No `questioner_names` array needed; single `questioner_name` field" for unstarred. `test_unstarred_produces_record` and `test_unstarred_question_number` only check `len(result)>=1` and `question_number`. Add a test that explicitly checks the questioner field on an unstarred record — its name, type, and content — to confirm the segmenter sets it correctly. |
| 11 | F01 / Schema | `qa_exchanges` UNIQUE dedup_key constraint not explicitly tested | WEAK | CODING AGENT | `test_schema_has_dedup_key_unique_speeches` checks that "dedup_key" and "UNIQUE" appear anywhere in schema.sql; since both appear in the speeches table, this test would pass even if qa_exchanges lacked the constraint. The schema currently has it (line 63: `dedup_key VARCHAR(500) UNIQUE NOT NULL`), but no test specifically verifies it. Add an assertion that checks "UNIQUE" appears in the `qa_exchanges` table block specifically. |
| 12 | F01 / setup_meilisearch.py | No unit tests at all | MISSING | CODING AGENT | Phase 1 scope includes `setup_meilisearch.py` and the stop condition requires it configures the index correctly. Zero tests exist. At minimum, add: (a) unit test for `_load_synonyms()` — pure function, no Meilisearch dependency — verifying it returns bidirectional word→synonyms pairs for all groups; (b) constant validation test asserting `SEARCHABLE_ATTRIBUTES`, `FILTERABLE_ATTRIBUTES`, and `PAGINATION["maxTotalHits"]` match DATA-MODELS.md 2.3 spec; (c) test that `TYPO_TOLERANCE["minWordSizeForTypos"]["oneTypo"]` is 4 (per Phase 3 spec: terms fewer than 4 chars exempt — current value is 5, which also exempts 4-char terms, contradicting the test spec requirement that 4-char terms must be eligible). |
| 13 | F04 / Synonyms | "Part III rights" term not verified in any test | MISSING | CODING AGENT | Feature spec: "fundamental rights ↔ basic rights ↔ Part III rights". `test_fundamental_rights` checks "fundamental rights" and "basic rights" but not "Part III rights". Term IS present in synonyms.json line 12. Add assertion `"Part III rights" in terms` to `TestConstitutionalTerminology.test_fundamental_rights`, and a grouping check that all three appear in the same group. |
| 14 | F04 / Synonyms | "amendment" ↔ "constitutional amendment" pair not tested | MISSING | CODING AGENT | Feature spec lists this as a constitutional terminology group. No test checks for "amendment" or "constitutional amendment". Add a test in `TestConstitutionalTerminology` asserting both terms are present and in the same synonym group. Both terms are present in synonyms.json (line 14). |
| 15 | F04 / Synonyms | "preamble to the Constitution" not tested | MISSING | CODING AGENT | Feature spec: "Preamble ↔ preamble to the Constitution". `test_preamble_present` only checks "Preamble". Add assertion for "preamble to the Constitution" and a same-group check. Term is present in synonyms.json (line 15). |
| 16 | F04 / Synonyms | "Directive Principles" short form not tested | MISSING | CODING AGENT | Feature spec: "Directive Principles ↔ DPSP ↔ Directive Principles of State Policy". `test_dpsp_present` checks "DPSP" and "Directive Principles of State Policy" but not "Directive Principles" (short form). Add assertion and a same-group check for all three. Term is present in synonyms.json (line 13). |
| 17 | F04 / Synonyms | "Question Hour" ↔ "question period" pair not tested | MISSING | CODING AGENT | Feature spec lists this parliamentary procedure pair. No test covers it. Add a test in `TestParliamentaryProcedure` asserting both terms present and in the same group. Both are in synonyms.json (line 25). |
| 18 | F04 / Synonyms | "calling attention motion" (expanded form) not tested | MISSING | CODING AGENT | Feature spec: "calling attention ↔ calling attention motion". `test_calling_attention_present` checks only "calling attention". Add assertion for "calling attention motion" and a same-group check. Term is in synonyms.json (line 23). |
| 19 | F04 / Synonyms | "adjournment" (short form paired with "adjournment motion") not tested | MISSING | CODING AGENT | Feature spec: "adjournment motion ↔ adjournment". `test_adjournment_motion_present` checks only "adjournment motion". Add assertion for "adjournment" and a same-group check. Term is in synonyms.json (line 24). |
| 20 | F04 / Synonyms | "Other Backward Communities" (third OBC expansion) not tested | MISSING | CODING AGENT | Feature spec: "OBC ↔ Other Backward Classes ↔ Other Backward Communities". `test_abbreviation_expansion` for OBC only checks `("OBC", "Other Backward Classes")`. Add assertion that "Other Backward Communities" is in the same OBC group. Term is in synonyms.json (line 35). |
| 21 | F04 / Synonyms | "Right to Information Act" (third RTI expansion) not tested | MISSING | CODING AGENT | Feature spec: "RTI ↔ Right to Information ↔ Right to Information Act". `test_legislation_expansion` for RTI only checks `("RTI", "Right to Information")`. Add assertion for "Right to Information Act" in same group. Term is in synonyms.json (line 49). |
| 22 | F04 / Synonyms | "Right to Education Act" (third RTE expansion) not tested | MISSING | CODING AGENT | Feature spec: "RTE ↔ Right to Education ↔ Right to Education Act". Same gap as #21. Add assertion for "Right to Education Act" in same group. Term is in synonyms.json (line 50). |

---

## Verified

Requirements with adequate test coverage confirmed in this phase:

**F01 / HTML parser**
- Date parsing: long-form, ordinal, ISO, no-date, invalid-day, scope boundary 2014-01-01 included, 2013-12-31 extracted correctly
- Proceeding type detection: starred_question, unstarred_question, zero_hour, calling_attention, adjournment_motion, short_duration_discussion, private_member_bill, default (debate)
- CA source raises ValueError (HTML parser is LS/RS only)
- date, subject, source_url, session_name, raw_text extraction all verified
- Script tags excluded from raw_text
- Empty HTML returns valid dict with null date
- Fixture-based tests: LS debate, RS starred question, LS unstarred question

**F01 / PDF parser**
- CA, LS sources validated; invalid source ("XX") raises ValueError
- volume preserved for CA; None for LS
- source_url preserved
- Digital embedded text extraction verified
- `ocr_low_confidence=False` for digital PDFs
- Pages list length and 1-based page_num
- Digital pages have `ocr=False, ocr_confidence=None`
- proceeding_type_hint applied
- Date extracted from first page
- Raw text joins all pages
- page_reference is 1-based

**F01 / Speech segmenter**
- Unattributed exclusion: SEVERAL HON. MEMBERS, AN HON. MEMBER, SOME HON. MEMBERS, HON. MEMBERS, MEMBERS
- ZERO HOUR not treated as unattributed (per test spec)
- Presiding officer exclusion: MR. SPEAKER, THE SPEAKER, MADAM SPEAKER, THE DEPUTY SPEAKER, MR. CHAIRMAN, THE CHAIRMAN, THE DEPUTY CHAIRMAN, THE PRESIDENT, MR. PRESIDENT
- Named member not flagged as presiding officer
- Language case 1 (English verbatim): `is_translated=False`, `has_untranslated=False`, non-null `full_text_en`
- Language case 2/3 basic flags: `is_translated=True` when translation marker present; non-null full_text_en
- Language case 4 (Hindi-only): `full_text_en=None` (not empty string), `has_untranslated=True`, `is_translated=False`
- Same member speaking twice produces two records with distinct sequence_within_sitting
- sequence_within_sitting is 1-based
- Metadata propagation: source, date, session_name, proceeding_type, subject
- CA source preserved (with volume, null session_name)
- speaker_name stored raw (unresolved) — `speaker_name_unresolved=True` in Phase 1
- ocr_low_confidence propagated to speech records
- Empty text returns empty list; only-unattributed text returns empty list
- Fixture-based: LS debate with named speakers, unattributed excluded, presiding officer excluded

**F01 / Q+A segmenter**
- Starred: record produced, question_number extracted, proceeding_type preserved, source/date propagated, full_text_en non-null for English exchange, multiple questions in one document produce N records with correct question_numbers, questioner_names is a list
- Unstarred: record produced, proceeding_type correct, question_number extracted
- Validation: CA source raises ValueError, invalid proceeding_type raises ValueError, empty text returns empty list
- Language handling: Case 1 (English, `is_translated=False`), Case 4 (Hindi-only, `full_text_en=None`, `has_untranslated=True`)
- Fixture-based: RS starred (question_number=12, source=RS), LS unstarred (question_number=458)

**F01 / Schema**
- File exists
- speeches, qa_exchanges, index_status tables present
- dedup_key + UNIQUE present; all required speeches columns; all required QA columns
- idx_speeches_date index; GIN index on questioner_names
- PostgreSQL execution test present (correctly skipped when TEST_DATABASE_URL not set)

**F04 / Synonyms**
- JSON is valid; all 5 categories present; all groups are lists with ≥2 terms
- Legislative bodies: Lok Sabha, House of the People, Lower House, Rajya Sabha, Council of States, Upper House, Parliament, both Houses, Constituent Assembly, CA — all present and grouping verified for LS/HoP and RS/CoS pairs
- Constitutional: fundamental rights + basic rights, DPSP + Directive Principles of State Policy, Preamble
- Parliamentary procedure: starred question/oral question, unstarred question/written question, zero-hour variants, private member bill variants, calling attention, adjournment motion, division/vote
- All 16 abbreviation pairs (PM, CM, SC, ST, SC/ST, OBC→Other Backward Classes, EWS, GST, CAG, CBI, ED, FIR, PIL, Art., Sec., Cl.)
- SC and SC/ST in separate groups
- All 9 legislation terms (RTI→Right to Information, RTE→Right to Education, MGNREGA + NREGA in same group + full name, POCSO, IPC, CrPC, BNS, BNSS)
- Bidirectionality: structural check (all groups ≥2 terms)

---

## Test execution summary

161 passed, 1 skipped (test_schema_executes_against_postgres — correctly skipped, no TEST_DATABASE_URL). No failures. No unexpected skips.
