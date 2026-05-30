# QA Review — Phase 2 Run 2
Date: 2026-05-28
PRD version: v1.0
Prior run: run-1 GAPS FOUND — 13 gaps (7 MISSING, 1 VACUOUS PASS, 4 WEAK, 1 mislabeled); all routed to Coding Agent.

## Status: CLEAR

## Gaps

| Feature | Requirement | Gap type | Routes to | Notes |
|---------|-------------|----------|-----------|-------|

(No gaps. All Phase 2 requirements covered with adequate test coverage, no vacuous passes, no weak assertions on flagged tests.)

---

## Run-1 Gap Resolution

All 13 run-1 gaps verified RESOLVED. Re-audit per gap:

| # | Run-1 gap | Resolution status |
|---|-----------|-------------------|
| 1 | Error log must include source URL for skipped documents | RESOLVED — `test_missing_date_produces_exactly_one_error_log` lines 218-220 now: `assert any("http://example.com/nodatehtml" in r.getMessage() for r in error_records)` with descriptive failure message. PASSED. |
| 2 | Completion summary printed at end of run | RESOLVED — new `TestCompletionSummary::test_completion_summary_emitted` (lines 339-366) runs `_async_main` and asserts "Ingestion complete", "Total indexed", and "Errors" all appear in INFO log messages. PASSED. |
| 3 | Completion summary count matches actual index count | RESOLVED — new `test_completion_summary_counts_match_indexed` (lines 368-407) seeds `indexer.counts["CA"] = 7`, captures the indexer reference, runs `_async_main`, then asserts `"Total indexed"` line contains `str(total)` derived from `sum(indexer.counts.values())`. Strong: failure surfaces if summary count drifts from indexer state. PASSED. |
| 4 | OCR-flagged records (`ocr_low_confidence=True`) must be indexed, not silently dropped | RESOLVED — new `TestIndexerIndexRecord::test_ocr_flagged_record_indexed` (lines 304-321) builds a speech with `ocr_low_confidence=True`, asserts `index_record` returns True, AND inspects `cursor.execute.call_args[0][1]` at the `_SPEECH_COLUMNS.index("ocr_low_confidence")` position to verify the value is True in the INSERT tuple. PASSED. |
| 5 | Interrupted+resumed total must equal clean run total | RESOLVED — new `TestIndexerResumeability::test_interrupted_then_resumed_matches_clean_run` (lines 399-441) actually simulates interrupt-mid-corpus: (a) processes records[:3] with store A (count=3), (b) reopens store A and processes all 5 records (only 2 new, since 0-2 are checkpointed), (c) clean run on fresh store with all 5 (count=5), then asserts `interrupted_count + resumed_count == clean_count`. The 3+2=5 chain exercises the exact resumability invariant from the test spec. PASSED. |
| 6 | `--date-override` propagated to LSSource/RSSource as date_from | RESOLVED — two new tests in `TestDateOverride` (lines 273-334) patch `ingest.main.LSSource` / `RSSource` with capture-classes that record `__init__` kwargs, invoke `_run_source(... date_override=date(2020, 6, 1))`, and assert the captured `date_from` equals the override. PASSED. |
| 7 | `--source ls` and `--source rs` argument values | RESOLVED — new `TestParseArgs::test_all_valid_source_values_accepted` parametrized over `["ca", "ls", "rs", "all"]` (4 collected tests) confirms all four are accepted; new `test_invalid_source_raises` confirms `--source foo` exits. PASSED. |
| 8 | VACUOUS: `test_update_index_status_inserts_row` only checks `execute.called` | RESOLVED — test (lines 444-468) now inspects `cursor.execute.call_args[0][0]` for `"INSERT INTO index_status"` substring, AND inspects the parameters tuple at indices 1, 2, 5, 8 asserting `total_records=900`, `ca_count=100`, `ls_count=500`, `rs_count=300` with descriptive failure messages. Each assertion catches a different drift; no longer vacuous. PASSED. |
| 9 | WEAK: `test_processes_html_speech_document` doesn't verify indexing | RESOLVED — test (lines 148-185) now asserts `stats["indexed"] >= 1` with descriptive failure message: "A valid speech document must produce at least one indexed record". A segmenter regression that produces zero records would now fail. PASSED. |
| 10 | WEAK: `test_indexed_record_produces_info_log` doesn't verify content | RESOLVED — test (lines 261-268) now asserts `any(url in r.getMessage() or "indexed" in r.getMessage().lower() for r in info_records)` with descriptive failure message. Generic INFO logs no longer pass. PASSED. |
| 11 | MISLABELED: `test_unattributed_speech_excluded_by_segmenter_not_indexer` | RESOLVED in two parts: (a) renamed to `test_dedup_key_handles_none_speaker_name` so the name matches the assertion (lines 642-646); (b) added new `test_segmenter_excludes_unattributed_speech` (lines 648-669) that actually invokes `segment_speeches` with a raw_record containing only `SEVERAL HON. MEMBERS` and `AN HON. MEMBER`, asserts `len(speeches) == 0`. The segmenter-vs-indexer division of responsibility is now genuinely verified. PASSED. |
| 12 | WEAK: `test_reindex_pushes_all_speeches_and_qa` checks only `total >= 1` | RESOLVED — test (lines 472-549) now loads 2 speech rows + 2 QA rows, asserts `total == 4` (exact, not `>=`), collects all docs from `add_documents.call_args_list`, asserts `len(pushed_docs) == 4`, and for each pushed doc asserts each of the 6 excluded fields (`page_reference`, `ocr_low_confidence`, `has_untranslated_content`, `session_number`, `created_at`, `dedup_key`) is absent. PASSED. |
| 13 | MISSING: Language cases 2 and 3 at indexer integration level | RESOLVED — two new tests in `TestLanguageHandlingIntegration`: (a) `test_is_translated_true_for_hindi_with_translation` (case 2, lines 587-609) asserts `is_translated=True`, `has_untranslated_content=False`, and `full_text_en` equals the translation text at the correct INSERT tuple positions; (b) `test_bilingual_speech_is_translated_true_with_full_text` (case 3, lines 611-636) asserts `is_translated=True` and `full_text_en` equals the bilingual string (containing both original English and translated portion markers) at the INSERT position. All four language cases now verified at indexer integration. PASSED. |

---

## Verified

All Phase 2 verification from run-1 stands and is strengthened. Areas now confirmed clean:

**F01 / sources** — _http.py (retry logic, 429-never-skipped, robots.txt cached and tolerant of network errors), ca.py (12 unique HTTPS PDFs, robots-disallowed and 404 skipped), ls.py + rs.py (proceeding-type inference, 2014-01-01 boundary, HTML preferred over PDF, robots integration, index-fetch failure handling).

**F01 / canonical** — names.py (all 6 spec honorifics, three-variants-identical, unresolved-flag, raw-name-preserved); sessions.py (CA→None, variants-identical, multi-part Part 1/Part 2 normalization, LS/RS parity).

**F01 / checkpoints** — store.py (URL and dedup tracking, persistence across open/close, resume skips checkpointed URLs, context manager open/close).

**F01 / indexer.py** — dedup key (format, same-member-different-sequence, normalized speaker, None→unknown), build_meili_document (excluded fields absent, None values omitted), index_record (speech+QA, duplicate skip, missing-date skip, per-source counts, same-member-twice-different-records, **OCR-flagged record indexed with INSERT-position verification**), flush (batch send, empty zero, auto-flush at MEILI_BATCH_SIZE), resumability (rerun zero new + **interrupted+resumed=clean total**), update_index_status (**SQL and parameters fully verified**), reindex_from_db (**2+2 rows, total=4 exact, excluded fields absent from pushed docs**), language handling integration (**all 4 cases** with INSERT-position verification), segmenter excludes unattributed speech (real test).

**F01 / main.py** — argument parsing (all 4 source values + invalid rejection, date-override, reindex flag), canonicalize_record (honorific, unresolved flag, session, CA→None, None speaker), process_document (skips no-date with **error log including URL**, processes valid HTML with **indexed >= 1 assertion**), progress logging (**INFO log content references URL or 'indexed'**), **date-override propagated to both LSSource and RSSource**, **completion summary emitted with per-source totals + errors + skipped, and total matches indexer.counts**.

**Phase 1 regression** — all Phase 1 tests carry forward, passing in 360/361 collected items.

---

## Test execution summary

360 passed, 1 skipped (test_schema_executes_against_postgres — correctly skipped, no TEST_DATABASE_URL), 1 warning (urllib3/LibreSSL, harmless). Net +14 tests vs run-1 (+10 new method definitions; +4 parametrize cases). No failures, no unexpected skips, no remaining vacuous or weak assertions on flagged tests.

---

## Phase Completion Recommendation

Both reviews on Phase 2 latest runs are now CLEAR:
- Arch Review: run-4 CLEAR
- QA Review: run-2 CLEAR

Phase 2 is eligible to be marked Complete during the next `/resume` reconciliation. Build is unblocked to proceed to Phase 3.
