# Test Spec 01: Data Ingestion

Supplements the feature spec. Does not repeat acceptance criteria or edge cases already stated there.

## Date Range Boundary

- Records dated exactly 2014-01-01 are included in scope; records dated 2013-12-31 are excluded
- Scope is fixed at 2014-01-01, not a rolling window recalculated at run time

## Deduplication

- When the same proceeding is available as both HTML and PDF, exactly one record is created; the HTML-sourced record is retained
- Duplicate detection must use the compound key (source + date + sitting_number + proceeding_type + speaker_name + sequence_within_sitting, or question_number for Q+A); a match on all key fields results in a skip, not a second insert
- A member speaking twice in the same sitting must produce two separate indexed records with distinct sequence_within_sitting values; they must not be merged

## Resumability

- Checkpoint granularity is per source document (not per individual record); a document is checkpointed only after all its records are successfully indexed
- A document that was partially processed when ingestion was interrupted must be fully reprocessed on resume, with no duplicate records created for the portion that was already indexed
- Record count after a clean run equals record count after an interrupted-then-resumed run against the same corpus

## Starred Question Completeness

- A starred Q+A unit must include every supplementary question and ministerial response present in the source record, not just the first supplementary exchange
- If supplementary exchanges are paginated or split across multiple pages in the source, all pages must be fetched and combined into a single record

## Language Handling

- When a speech is delivered in Hindi and the official English translation is present in the record (marked "[Translation]" or equivalent), `full_text_en` must contain the translation text, not the Devanagari text and not null
- When no translation is available, `full_text_en` must be null — not an empty string, not the Devanagari text
- `is_translated` must be true whenever `full_text_en` contains any translated content; false when the text is original English throughout
- For a bilingual speech, `full_text_en` must contain both the original English portions and the translated Hindi portions, concatenated in order

## Unattributed and Presiding Officer Speech

- The strings "SEVERAL HON. MEMBERS", "AN HON. MEMBER", "SOME HON. MEMBERS" must never appear as a `speaker_name` value in any indexed record
- Speeches by the Speaker (LS) and Chairman/Vice-Chairman (RS) made in their presiding capacity must not appear as standalone indexed records; `speaker_role: presiding_officer` records must not be present as searchable units

## OCR-Flagged Records

- Records flagged with `ocr_low_confidence: true` must appear in the search index; they must not be silently dropped
- `ocr_low_confidence` must be false for records sourced from digital (non-scanned) PDFs and HTML

## Zero Hour Attribution

- Zero hour speeches must carry the individual member's name in `speaker_name`; the string "ZERO HOUR" must not appear as a `speaker_name` value

## Speaker Name Canonicalization

- A speaker appearing as "Shri Narendra Modi", "Narendra Modi", and "N. Modi" across different records must produce identical `speaker_name` values in all three indexed records
- Honorific prefixes (Shri, Smt., Dr., Prof., Adv., Kumari) must be stripped; the canonical form must not begin with any of these strings
- A name not found in the canonical names dictionary must produce `speaker_name_unresolved: true`; the raw name as found in the source must be stored in `speaker_name` (not null, not empty)
- A name successfully resolved from the dictionary must produce `speaker_name_unresolved: false`

## Session Name Canonicalization

- Session name variants for the same session ("Budget Session, 2023", "Budget Session 2023", "BUDGET SESSION 2023") must produce an identical `session_name` value across all indexed records from that session
- CA records must have `session_name: null`; any non-null `session_name` on a CA record is a bug

## Missing Date Handling

- A source document with no parseable date must produce zero indexed records from that document and one logged error entry; it must not cause ingestion to halt for subsequent documents

## Progress Log Integrity

- The completion summary record count must match the actual number of records retrievable from the search index after ingestion completes
- The error log must include the source URL for every skipped document; a skipped document with no URL reference in the log is a bug
