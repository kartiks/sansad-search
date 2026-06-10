# SansadSearch — Product Requirements Document

**Version:** 3.1  
**Date:** 2026-06-09  
**Git tag:** —  
**Generated from:** /prd/sections/

---

## Table of Contents

1. [Overview](#1-overview)
2. [Objectives](#2-objectives)
3. [Functional Requirements](#3-functional-requirements)
   - [F01: Data Ingestion](#f01-data-ingestion)
   - [F02: Full-text Search](#f02-full-text-search)
   - [F03: Search Filters](#f03-search-filters)
   - [F04: Query Expansion](#f04-query-expansion)
   - [F05: Result Display](#f05-result-display)
   - [F06: Sorting](#f06-sorting)
   - [F07: Indexing Status Panel](#f07-indexing-status-panel)
   - [F08: Search History](#f08-search-history)
   - [F09: Detail Page](#f09-detail-page)
   - [F10: Debug Mode](#f10-debug-mode)
4. [Non-Functional Requirements](#4-non-functional-requirements)
5. [Future Features](#5-future-features)

---

## 1. Overview

### Product

SansadSearch is a web-based full-text search application over Indian parliamentary records. It enables users to search the proceedings of the Constituent Assembly of India (1946–1950), historical Lok Sabha debates and questions, and available Rajya Sabha records, by keyword, speaker, date range, legislative body, subject, and proceeding type.

### Data Scope (v1)

| Source | Coverage | Base URL |
|--------|----------|----------|
| Constituent Assembly debates | All 12 volumes, 1946–1950 | constitutionofindia.net |
| Lok Sabha debates and questions | 1947-08-15 to present; elibrary.sansad.in covers 2019-01-01 to present | Internet Archive; elibrary.sansad.in DSpace 7 |
| Rajya Sabha debates and questions | 1947-08-15 to present; post-2018 records currently unavailable | Internet Archive only |

### Indexed Record Types

Two units are indexed:

**Speech** — one member's individual contribution to a debate or special proceeding. Stores: speaker identity, party, constituency/state, date, session, subject/agenda item, full English text, and a reference to the source document.

**Q+A exchange** — a complete question-and-answer unit:
- Starred question: main question, minister's formal answer, all supplementary questions (with member attribution), and minister's responses to supplementaries
- Unstarred question: question text and written answer (laid on the table)

### v1 Constraints

- Web application only; mobile version is future scope
- English-language text only; Hindi-language portions of proceedings are not indexed in v1
- Fully public, anonymous — no user authentication required
- Cookie-based search history and saved searches (no sign-in required)
- One-time bulk ingestion; no scheduled or ongoing updates in v1
- LS data scope: 1947-08-15 to present; RS data scope: 1947-08-15 to present, post-2018 records currently unavailable pending an accessible source

### Target Users

- Researchers and academics studying Indian legislative history and constitutional development
- Journalists and analysts covering Indian politics and governance
- Lawyers and legal professionals researching legislative intent
- Law students and educators
- Engaged citizens tracking parliamentary debates and questions

---

## 2. Objectives

1. Make Indian parliamentary records discoverable through full-text keyword search across all three source corpora.
2. Serve both domain experts (who search using precise parliamentary terminology) and general users (who search in plain language) without requiring expertise.
3. Enable filtering by date range, legislative body, speaker, session, subject, and proceeding type so users can narrow large result sets to relevant records.
4. Display results with enough context — speaker identity, session, subject, and a passage snippet — that users can assess relevance without opening the source document.
5. Provide verifiable citations: every result links directly to the authoritative source document for that record.
6. Index the Constituent Assembly debates in full, giving researchers access to the complete constitutional drafting record in searchable form.

---

## 3. Functional Requirements

---

### F01: Data Ingestion

#### Description

The ingestion pipeline fetches, parses, segments, and indexes parliamentary records from three sources: Constituent Assembly debates, Lok Sabha records, and Rajya Sabha records. In v1 it is a one-time bulk operation. It must be resumable: an interrupted run continues from the last successful document checkpoint without reprocessing already-indexed records or creating duplicates.

The pipeline is implemented as a two-stage process. Stage 1 (fetch) downloads source documents and writes raw content to a `raw_documents` store. Stage 2 (process) reads from that store and produces indexed `speeches`/`qa_exchanges` records. The two stages can be run together or independently via the `--stage` flag.

#### Two-Stage Pipeline

##### Stage control

| `--stage` value | Behavior |
|-----------------|----------|
| `fetch` | Stage 1 only: discover and download source documents; write to `raw_documents` |
| `process` | Stage 2 only: read from `raw_documents`; parse, segment, and index |
| `all` | Stage 1 then Stage 2 sequentially for each source (default) |

##### Stage 1 (fetch) flow

1. Discover documents for the selected corpus(es)
2. Check `raw_documents` PK for each `canonical_doc_id`; skip if already present
3. Fetch new documents from source with rate limiting
4. Extract text and metadata
5. Apply date-window gate when `--date-from`/`--date-to` are provided: write to `raw_documents` only if the document's date falls within the window; skip out-of-window documents
6. Write raw content (extracted text + metadata JSON) to `raw_documents`

Stage 1 does not write to `speeches`, `qa_exchanges`, or the SQLite checkpoint store. It does not update `index_status`.

##### Stage 2 (process) flow

1. Read `raw_documents` rows for the selected corpus; apply `--date-from`/`--date-to` window if provided
2. Skip documents already checkpointed as processed in the SQLite `processed_documents` store
3. Segment each document into speech and Q+A exchange units
4. Apply adjacent speech merging to speech units (see Adjacent Speech Merging section)
5. Canonicalize speaker names and session names
6. Index each unit into `speeches`/`qa_exchanges`
7. Checkpoint the document in `processed_documents` after all its records are successfully indexed

`index_status` is updated only at the end of Stage 2, not at the end of Stage 1.

##### Date filtering

`--date-from YYYY-MM-DD` and `--date-to YYYY-MM-DD` scope both stages:

- **Stage 1:** only documents whose parsed date falls within the window are written to `raw_documents`; out-of-window documents are skipped after parsing
- **Stage 2:** only `raw_documents` rows with dates within the window are read and processed

When neither flag is provided, both stages operate on the full corpus without date restriction.

#### User Flows

**Initial bulk ingestion:**
1. Operator runs ingestion with a source selector (CA | LS | RS | all), `--stage fetch|process|all` (default `all`), and optional `--date-from`/`--date-to` to restrict the date window applied to both stages
2. System enumerates all records in scope for the specified source(s) — building a list of documents/pages to fetch
3. System fetches each document with rate limiting and robots.txt compliance
4. System parses fetched content (HTML or PDF) to extract text and metadata
5. System segments content into speech units and Q+A exchange units; applies adjacent speech merging to speech units
6. System indexes each unit with full metadata into the search index
7. System logs progress in real time: document processed, records indexed, errors, skipped
8. On completion, system prints a summary: total records indexed per source, total errors, total skipped

**Resuming an interrupted run:**
1. Operator re-runs the same ingestion command
2. System checks progress log; skips documents already successfully processed
3. System continues from first unprocessed document
4. Final summary reflects total state across both runs (no double-counting)

#### Data Sources and Scope

| Source | Content | Date scope | Format | Base URL |
|--------|---------|------------|--------|----------|
| Constituent Assembly | Plenary debates | All 12 volumes, 1946–1950 | HTML | constitutionofindia.net |
| Lok Sabha | Debates and questions | 1947-08-15 to present | Pre-OCR plain text (_djvu.txt); Tika-extracted PDF text | Internet Archive _djvu.txt pre-OCR text; elibrary.sansad.in DSpace 7 Text of Debates English (2019-01-01 to present) |
| Rajya Sabha | Debates and questions | 1947-08-15 to present | Pre-OCR plain text (_djvu.txt) | Internet Archive (see RS coverage note below) |

**RS coverage note:** The Rajya Sabha provider chain currently contains Internet Archive only. `sansad.in/rs` was removed because it is JavaScript-rendered and not crawlable; `rsdebate.nic.in` was removed because it is unresponsive. RS coverage therefore reflects what Internet Archive holds, which does not currently extend to post-2018 records. The provider chain is designed to be extended — adding a new RS provider restores coverage for the periods it serves without requiring changes to this spec.

#### Proceeding Types Indexed

**Constituent Assembly:** plenary debate speeches only (no question hour exists in CA records).

**Lok Sabha and Rajya Sabha:**
- Debate speeches
- Starred questions (full exchange: main question, minister's answer, all supplementary questions with member attribution, minister's responses to supplementaries)
- Unstarred questions (question text and written answer)
- Zero hour speeches
- Short notice questions
- Calling attention motions
- Short duration discussions
- Adjournment motions
- Private member bills (debate speeches on private member bills)

#### Indexed Record Fields

##### Speech unit

| Field | Description |
|-------|-------------|
| `id` | Stable UUID assigned at ingest; preserved across re-runs via ON CONFLICT DO NOTHING on the deduplication key |
| `source` | CA \| LS \| RS |
| `proceeding_type` | debate \| zero_hour \| short_duration_discussion \| calling_attention \| adjournment_motion \| private_member_bill |
| `date` | Date of sitting (YYYY-MM-DD) |
| `session_name` | E.g. "Budget Session 2023"; null for CA |
| `session_number` | Official session number; null for CA |
| `sitting_number` | Sitting number within session |
| `subject` | Agenda item or debate title this speech belongs to |
| `speaker_name` | Member's full name as it appears in the record |
| `speaker_party` | Party or group affiliation |
| `speaker_constituency_or_state` | Constituency (LS), state (RS), or null (CA) |
| `speaker_role` | member \| minister \| presiding_officer |
| `full_text_en` | Full English text of the speech; for merged speeches, the concatenation of all segment texts joined with `\n\n`; see Language Handling below |
| `segments` | JSONB array of speech text segments; each element: `{"text": "...", "segment_index": N}` (0-based); single-element array for speeches that were not merged with any adjacent speech |
| `lang_original` | Language of the original speech before translation: `en` (English), `hi` (Hindi), or `mixed` (genuinely bilingual — alternates between Hindi and English in both directions; predominantly Hindi speeches with only translation fragments are classified `hi`); derived from Language Handling cases: case 1→`en`; cases 2 and 4→`hi`; case 3→`mixed` if genuinely alternating, `hi` if predominantly Hindi with translation fragments |
| `time_of_day` | Time the speech began, as HH:MM (24-hour); extracted from HTML sources only; null for Internet Archive pre-OCR text and PDF sources |
| `word_count` | Integer word count of `full_text_en` computed at ingest; null if `full_text_en` is null |
| `is_translated` | true if `full_text_en` contains or includes official English translation of Hindi portions |
| `has_untranslated_content` | true if any portion of the speech could not be indexed due to absent translation |
| `speaker_name_unresolved` | true if `speaker_name` could not be matched to a canonical form in the names dictionary |
| `source_url` | URL of the original source document. For LS records: the Internet Archive URL. For RS records: the Internet Archive URL (current chain contains Internet Archive only). For CA records: the constitutionofindia.net URL. Null if no accessible URL can be derived for the record. |
| `page_reference` | Page number in source PDF; null for HTML sources |
| `sequence_within_sitting` | Integer position of this speech within the sitting's proceedings, derived from document order (1-based); for merged speeches, the position of the first segment in the merge group |
| `volume` | CA volume number (1–12); null for LS/RS |
| `lok_sabha_number` | Lok Sabha term number (e.g., 17 for the 17th Lok Sabha); INTEGER; extracted from source data at ingestion time; null for RS and CA records |

##### Q+A exchange unit (starred question)

| Field | Description |
|-------|-------------|
| `id` | Stable UUID assigned at ingest; preserved across re-runs via ON CONFLICT DO NOTHING on the deduplication key |
| `source` | LS \| RS |
| `proceeding_type` | starred_question |
| `date` | Date of sitting |
| `session_name` | E.g. "Budget Session 2023" |
| `session_number` | Official session number |
| `sitting_number` | Sitting number within session |
| `question_number` | Official question number |
| `subject` | Question subject/title |
| `questioner_names` | Primary questioner and co-signatories (array) |
| `questioner_party` | Party affiliation of primary questioner |
| `minister_name` | Name of the minister who answered the question; extracted from the minister's response section in the source document; must never be set to question preamble text (e.g., "Will the minister of [Ministry] be pleased to state…"); if the minister's name is not identifiable from the response section, set to "Minister of [Ministry]" using the value of the `ministry` field |
| `ministry` | Ministry responsible |
| `full_text_en` | Full text of the complete exchange: main question + answer + all supplementaries with attribution; English only, translated as needed |
| `lang_original` | Language of the original exchange before translation: `en`, `hi`, or `mixed`; same derivation rules as speech units |
| `time_of_day` | Time the question was called, as HH:MM (24-hour); extracted from HTML sources only; null for Internet Archive pre-OCR text and PDF sources |
| `word_count` | Integer word count of `full_text_en` computed at ingest; null if `full_text_en` is null |
| `is_translated` | true if any portion was translated from Hindi |
| `has_untranslated_content` | true if any portion could not be indexed due to absent translation |
| `source_url` | URL of the original source document. For LS records: the Internet Archive URL. For RS records: the Internet Archive URL (current chain contains Internet Archive only). Null if no accessible URL can be derived. |
| `page_reference` | Page number in source PDF; null for HTML sources |
| `sequence_within_sitting` | Integer position of this Q+A exchange within the sitting's proceedings, derived from document order (1-based); shared sequence space with speech units within the same sitting |
| `lok_sabha_number` | Lok Sabha term number (e.g., 17 for the 17th Lok Sabha); INTEGER; extracted from source data at ingestion time; null for RS records |

##### Q+A exchange unit (unstarred question)

Same fields as starred question except:
- `proceeding_type`: unstarred_question
- `full_text_en`: question text and written answer only (no supplementaries)
- No `questioner_names` array needed; single `questioner_name` field

The `source_url`, `minister_name`, and `lok_sabha_number` rules above apply equally to unstarred questions.

#### Language Handling

Official parliamentary records include English translations of speeches delivered in Hindi. The pipeline applies the following rules in order:

1. **Speech in English:** store verbatim in `full_text_en`; `is_translated: false`
2. **Speech in Hindi with official English translation present:** store the translation in `full_text_en`; `is_translated: true`
3. **Bilingual speech (switches between Hindi and English):** store all English text — both original English portions and translated Hindi portions — in `full_text_en`; `is_translated: true`
4. **Hindi speech with no translation available:** `full_text_en: null`; `has_untranslated_content: true`; record is still indexed (metadata remains searchable)

Translations in official records are typically marked inline as "[Translation]" or equivalent notation.

#### Adjacent Speech Merging

During Stage 2 processing, consecutive speeches by the same speaker within the same sitting are merged into a single `speeches` record. This applies to speech units only; Q+A exchange units are never merged.

##### Merge conditions

All of the following must be true for two consecutive speeches to be candidates for merging:
- Same `speaker_name`
- Same sitting (same `source` + `date` + `sitting_number`)
- Same `proceeding_type`
- Consecutive in document order with no break signal between them

##### Break signals

Any of the following appearing in the source document between two speeches by the same speaker prevents merging:
- A speech or interjection by a different speaker
- A section heading (H1, H2, H3 tag or equivalent structural heading element in the parsed HTML)
- A procedural entry: a new question number heading, a block header (e.g., "QUESTIONS", "STARRED QUESTIONS", "STARRED QUESTION NO. X"), or a formal procedural marker (e.g., "The House adjourned for lunch", "The House then adjourned")

##### Merged record structure

- The merged record stores individual speech texts as an ordered JSONB array in the `segments` field; each element: `{"text": "...", "segment_index": N}` where N is 0-based
- `full_text_en` = all segment texts joined with `\n\n` (double newline)
- `word_count` = total word count of the combined `full_text_en`
- `sequence_within_sitting` = document-order position of the first segment in the merge group
- An unmerged speech has a single-element `segments` array

#### CA Field-Level Parsing Rules

These rules apply to Constituent Assembly records only.

##### Date field

The URL slug is the authoritative date source for CA records. URL format: `DD-MMM-YYYY` (e.g. `09-dec-1946`). The parser must parse this slug directly and set `date` to ISO format `YYYY-MM-DD`. HTML-based date extraction (title, h1, metadata divs) must be skipped entirely for CA records — even when `parse_html` returns a date value, it must be discarded. The current ca.py uses the URL as a fallback only when `parse_html` returns `date=None`; this rule supersedes that: for CA, the URL date is always applied.

##### Subject field

Each CA speech record's `subject` must be set to the nearest preceding standalone bold section header in the sitting page body.

**Section header definition:** A standalone bold topic label (e.g. "Government of India (Amendment) Bill", "New Article 67-A") appearing between speech entries in the debate body. Speaker names also appear bold or strong in source HTML, but inside speech grid rows — these must not be treated as section headers.

**Assignment rule:** Walk the parsed DOM in document order. When a standalone bold section header is encountered, set it as the current topic. Assign that topic to all subsequent speech records until the next section header is encountered.

**Fallback:** If no section header precedes the first speech of the sitting, the subject for those speeches falls back to the first item in the page's table of contents. The TOC is a `<ul>` above the debate body containing `<li><a href="#ID">Topic</a></li>` items. The implementation must verify at build time whether those anchor IDs correspond to `id=` attributes on body elements and use that mapping if available.

#### Records Not Indexed as Standalone Units

The following are not indexed as standalone searchable records:
- Unattributed speech: "SEVERAL HON. MEMBERS", "AN HON. MEMBER", "SOME HON. MEMBERS", and similar
- Presiding officer interventions: speeches by the Speaker (Lok Sabha) or Chairman/Vice-Chairman (Rajya Sabha) made in their presiding capacity
- Procedural interruptions: points of order, rulings, and division votes

These may appear as part of the `full_text_en` of a surrounding Q+A exchange unit (e.g., presiding officer directing the house during a starred question) but are not separately indexed.

#### Canonicalization

##### Speaker names

Speaker names in source records appear in multiple variants across sittings and sessions (honorific prefixes, abbreviated forms, ordering variants, transliteration differences). All speaker names must be canonicalized to a consistent form at ingestion time.

Canonicalization rules:
- Strip honorific prefixes: Shri, Smt., Dr., Prof., Adv., Kumari, and any other titles present in the source records
- Resolve abbreviation variants and ordering variants (e.g., "Modi, Narendra" → "Narendra Modi") using a canonical names dictionary
- The canonical names dictionary maps known name variants to a single canonical full name; it must be seeded from official Lok Sabha and Rajya Sabha member lists and the CA member list
- If a speaker name is not found in the canonical names dictionary, store the raw name as found in the source record and set `speaker_name_unresolved: true`
- Unresolved names are indexed and searchable; they are flagged for manual dictionary updates

##### Session names

Session names in source records may appear in inconsistent formats across sources (e.g., "Budget Session, 2023" vs "Budget Session 2023" vs "Budget Session (Second Part) 2023"). Canonicalize to a consistent format: "[Session Type] Session [Year]" with multi-part sessions appended as "(Part [N])" where applicable. Example canonical forms: "Budget Session 2023", "Monsoon Session 2022", "Budget Session 2023 (Part 2)".

CA records have no session name; `session_name` is null for all CA records.

#### Deduplication

When the same proceeding is available as both HTML and PDF from the source site, the HTML version is preferred. Only one record is created per unique speech or Q+A exchange. Duplicate detection key: source + date + sitting_number + proceeding_type + speaker_name + sequence_within_sitting (or question_number for Q+A units). For merged speech records, `sequence_within_sitting` in the dedup key is the position of the first segment in the merge group. The sequence_within_sitting field is required because a member may speak multiple times in the same sitting on the same agenda item with intervening speakers.

#### Acceptance Criteria

- All 12 volumes of CA debates are ingested; speeches indexed per individual member contribution
- All LS records dated 1947-08-15 or later available in the LS provider chain are ingested across all proceeding types listed above
- RS records are ingested from all providers in the RS provider chain; coverage reflects what those providers make accessible
- Every indexed record has: id, source, proceeding_type, date, subject, full_text_en (or null with has_untranslated_content flag), source_url, lang_original
- `id` is a stable UUID that does not change across re-runs for the same record
- `word_count` is present and non-null for all records where `full_text_en` is not null; null where `full_text_en` is null
- `time_of_day` is present (HH:MM) for HTML-sourced records where the sitting page includes time; null for all IA pre-OCR and PDF-sourced records
- Starred Q+A records include the complete exchange: main question + answer + all supplementary questions and responses
- Re-running ingestion on a fully indexed corpus produces zero new records and zero duplicate records
- Progress log is written in real time; a completion summary is printed at the end
- Ingestion can be scoped to a single source (CA only, LS only, RS only) for targeted re-runs
- `--stage fetch` writes raw content to `raw_documents` without producing any `speeches` or `qa_exchanges` records
- `--stage process` reads from `raw_documents` and produces indexed records without fetching from source
- Re-running Stage 1 against an already-fetched corpus writes zero new `raw_documents` rows (PK dedup skips all)
- `--stage fetch --date-from X --date-to Y` writes only documents with dates within that range to `raw_documents`; documents outside the window are skipped after parsing
- `--stage all --date-from X --date-to Y` produces `speeches`/`qa_exchanges` records only for dates within the specified range
- LS speech and Q+A records have `lok_sabha_number` populated with the correct Lok Sabha term number; RS and CA records have `lok_sabha_number: null`
- `minister_name` never contains question preamble text (e.g., "Will the minister of [Ministry] be pleased to state…"); Q+A records where the minister's name is not identifiable from the response section have `minister_name` set to "Minister of [Ministry]"
- For LS records, `source_url` is the Internet Archive URL; for RS records, `source_url` is the Internet Archive URL; for CA records, `source_url` is the constitutionofindia.net URL
- Adjacent speeches by the same speaker with no break signal between them are merged into a single record; the merged record's `segments` array contains one element per original speech; `full_text_en` is the concatenation of all segment texts separated by `\n\n`
- Adjacent speeches by the same speaker separated by a different speaker's speech, a section heading, or a procedural entry are stored as separate records with distinct `sequence_within_sitting` values

#### Edge Cases

- Speeches entirely in Hindi with no available translation: indexed with metadata only; `full_text_en: null`
- Missing speaker attribution in source record: index with `speaker_name: null`; do not skip the record
- Missing date: log as an error and skip the record (date is required for filtering)
- HTTP 4xx errors (excluding 429): log and skip; do not retry
- HTTP 5xx errors: retry up to 3 times with exponential backoff; log and skip if all retries fail
- HTTP 429 (rate limited): back off with exponential delay and retry; do not skip
- Malformed or unparseable HTML/PDF: log parsing error with document URL; skip
- Records outside the date scope appearing within an in-scope document: skip those records; continue processing in-scope records in the same document
- Q+A record where the minister's name is not present in the response section: `minister_name` is set to "Minister of [Ministry]" using the value of the `ministry` field; must never be set to question preamble text such as "Will the minister of [Ministry] be pleased to state…"
- Merged speech where some segments have English text and others do not (e.g., first segment in English, subsequent segment in Hindi with no translation): `full_text_en` must include the available English segments; `has_untranslated_content` must be set to true; `full_text_en` must not be null solely because one segment lacked a translation

#### Dependencies

None. This is the foundational feature.

#### NFR Implications

- **Rate limiting:** ingestion must comply with robots.txt on elibrary.sansad.in and the Internet Archive; minimum inter-request delay to be specified at architecture stage → flag in NFR
- **Storage:** full-text corpus of parliamentary proceedings across all three sources is substantial → flag in NFR for architecture sizing
- **Processing time:** bulk ingestion is a long-running operation expected to take hours; exact time budget not specified for v1 but progress logging is required → flag in NFR
- **Resumability:** ingestion must checkpoint per source document and support safe re-runs → flag in NFR as a reliability requirement

#### Test Requirements

*(from Test Spec 01)*

**Date Range Boundary**
- LS records dated exactly 1947-08-15 are included in scope; LS records dated 1947-08-14 are excluded
- RS records dated exactly 1947-08-15 are included in scope; RS records dated 1947-08-14 are excluded
- Scope boundaries are fixed constants, not rolling windows recalculated at run time

**Deduplication**
- When the same proceeding is available as both HTML and PDF, exactly one record is created; the HTML-sourced record is retained
- Duplicate detection must use the compound key (source + date + sitting_number + proceeding_type + speaker_name + sequence_within_sitting, or question_number for Q+A); a match on all key fields results in a skip, not a second insert
- Two speeches by the same speaker in the same sitting with a different speaker's speech between them must produce two separate indexed records with distinct sequence_within_sitting values
- Two consecutive speeches by the same speaker in the same sitting with no intervening speaker, section heading, or procedural entry must produce a single merged record whose `segments` array contains two elements; the merged record's `full_text_en` must contain the text of both original speeches separated by `\n\n`

**Resumability**
- Checkpoint granularity is per source document (not per individual record); a document is checkpointed only after all its records are successfully indexed
- A document that was partially processed when ingestion was interrupted must be fully reprocessed on resume, with no duplicate records created for the portion that was already indexed
- Record count after a clean run equals record count after an interrupted-then-resumed run against the same corpus

**Starred Question Completeness**
- A starred Q+A unit must include every supplementary question and ministerial response present in the source record, not just the first supplementary exchange
- If supplementary exchanges are paginated or split across multiple pages in the source, all pages must be fetched and combined into a single record

**Language Handling**
- When a speech is delivered in Hindi and the official English translation is present in the record (marked "[Translation]" or equivalent), `full_text_en` must contain the translation text, not the Devanagari text and not null
- When no translation is available, `full_text_en` must be null — not an empty string, not the Devanagari text
- `is_translated` must be true whenever `full_text_en` contains any translated content; false when the text is original English throughout
- For a bilingual speech, `full_text_en` must contain both the original English portions and the translated Hindi portions, concatenated in order

**Unattributed and Presiding Officer Speech**
- The strings "SEVERAL HON. MEMBERS", "AN HON. MEMBER", "SOME HON. MEMBERS" must never appear as a `speaker_name` value in any indexed record
- Speeches by the Speaker (LS) and Chairman/Vice-Chairman (RS) made in their presiding capacity must not appear as standalone indexed records; `speaker_role: presiding_officer` records must not be present as searchable units

**Zero Hour Attribution**
- Zero hour speeches must carry the individual member's name in `speaker_name`; the string "ZERO HOUR" must not appear as a `speaker_name` value

**Speaker Name Canonicalization**
- A speaker appearing as "Shri Narendra Modi", "Narendra Modi", and "N. Modi" across different records must produce identical `speaker_name` values in all three indexed records
- Honorific prefixes (Shri, Smt., Dr., Prof., Adv., Kumari) must be stripped; the canonical form must not begin with any of these strings
- A name not found in the canonical names dictionary must produce `speaker_name_unresolved: true`; the raw name as found in the source must be stored in `speaker_name` (not null, not empty)
- A name successfully resolved from the dictionary must produce `speaker_name_unresolved: false`

**Session Name Canonicalization**
- Session name variants for the same session ("Budget Session, 2023", "Budget Session 2023", "BUDGET SESSION 2023") must produce an identical `session_name` value across all indexed records from that session
- CA records must have `session_name: null`; any non-null `session_name` on a CA record is a bug

**Missing Date Handling**
- A source document with no parseable date must produce zero indexed records from that document and one logged error entry; it must not cause ingestion to halt for subsequent documents

**CA Date Parsing**
- A CA record whose URL slug parses to a different date than what `parse_html` would return must store the URL-derived date, not the HTML-derived date; the HTML date must never appear in the indexed record
- A CA record must never have a null `date` caused by HTML parse failure when the URL slug is present and parseable; URL slug parse failure is the only condition under which a CA record's date may be missing (in which case the record is skipped per the missing-date edge case)

**CA Subject Assignment**
- Two speech records from the same sitting that fall under the same bold section header must have identical `subject` values
- A speech record that follows a new section header in document order must not retain the `subject` value from the previous section header
- The first speech record in a sitting where no bold section header precedes it must have `subject` set to the text of the first item in the sitting page's TOC `<ul>`; it must not be null, empty, or set to a section header from later in the page

**Stage 1 Date Window Gate**
- A document dated exactly on `date_from` must be written to `raw_documents`; a document dated one day before `date_from` must not be written
- A document dated exactly on `date_to` must be written to `raw_documents`; a document dated one day after `date_to` must not be written
- When neither `--date-from` nor `--date-to` is specified, Stage 1 must write all discovered documents to `raw_documents` regardless of date

**Minister Name Extraction**
- A Q+A record whose source document contains only the question preamble "Will the minister of [Ministry] be pleased to state…" and no explicit minister name in the response section must have `minister_name` set to "Minister of [Ministry]" — not the preamble text itself
- A Q+A record with an explicit minister name attribution in the response section must have `minister_name` set to that name, not the preamble text
- No indexed Q+A record may have a `minister_name` value that begins with "Will the"

**Source URL Rules**
- An LS record (regardless of which provider fetched it) must have `source_url` set to an Internet Archive URL (archive.org domain)
- An RS record must have `source_url` set to an Internet Archive URL (archive.org domain); the current RS chain contains Internet Archive only
- A CA record must have `source_url` containing "constitutionofindia.net"

**Adjacent Speech Merging**
- Two consecutive speeches by the same speaker with a section heading (H-tag) between them in the source HTML must produce two separate records, not a merged record
- Two consecutive speeches by the same speaker with a procedural block header (e.g., "STARRED QUESTIONS", "STARRED QUESTION NO. X") between them must produce two separate records
- Three consecutive speeches by the same speaker with no break signal between any of them must produce a single merged record whose `segments` array contains three elements
- A merged record's `segments` array elements must be ordered by document position (segment_index 0 is the earliest in the document)

**Progress Log Integrity**
- The completion summary record count must match the actual number of records retrievable from the search index after ingestion completes
- The error log must include the source URL for every skipped document; a skipped document with no URL reference in the log is a bug

---

### F02: Full-text Search

#### Description

The core search interface. Users enter keyword queries; the system executes full-text search across the indexed corpus and returns a ranked result list. Query expansion — synonyms and spell corrections — is integrated into the search execution model, with expanded terms carrying reduced relevance weights. Feature 04 defines the synonym dictionary and correction rules that feed this feature.

#### User Flows

**Standard search:**
1. User arrives at homepage; a prominent search box is visible
2. User types a query (minimum 2 characters) and presses Enter or clicks Search
3. System executes search with query expansion and returns a ranked result list
4. User can apply filters (Feature 03), change sort order (Feature 06), and inspect individual results (Feature 05)

**Refinement:**
1. User on results page modifies the query in the persistent search box and resubmits
2. New search executes; results page updates; active filter selections persist across query refinements
3. Filters are only reset by an explicit "clear filters" action (Feature 03)

**No results:**
1. Search executes; no records match
2. System shows explicit no-results state with suggestion to try fewer terms, different terms, or remove filters if any are active

**Invalid query:**
1. User submits query shorter than 2 characters, or submits with an empty box
2. System shows inline validation message; no search is executed

#### Search Execution Model

##### Fields searched

Queries execute across all of the following fields:

| Field | Description |
|-------|-------------|
| `full_text_en` | Full text of the speech or Q+A exchange |
| `subject` | Debate title or question subject |
| `speaker_name` | Name of the member or minister |
| `minister_name` | Name of the answering minister (Q+A records) |
| `ministry` | Ministry responsible (Q+A records) |

##### Term matching and query expansion

- **Single-term query:** the term is expanded with synonyms and spell corrections (see Feature 04); the expanded set is evaluated as OR across all variants; original term scores at full weight; synonyms at reduced weight; spell corrections at lower weight still
- **Multi-term query:** AND logic applies across original term groups; all original terms must be present in a matching record (or covered by expansions); within each term group, OR logic applies across the original term and its expanded variants
- **Phrase query (double-quoted):** the exact phrase is matched first at full weight; phrase-level synonyms from Feature 04 are added as OR alternatives at reduced weight; individual term expansions within the phrase are not applied separately
- A record matching all original terms outranks a record matching only synonym expansions; a synonym match outranks a spell-correction match

##### Relevance ranking factors

Applied in combined scoring (not strict hierarchy — all factors contribute to a single relevance score):

1. **Original term coverage:** fraction of original query terms matched in the record (vs. covered only by expansions)
2. **Field match location:** match in `speaker_name`, `subject`, `minister_name`, or `ministry` contributes more to the score than a match only in `full_text_en`
3. **Expansion match type:** synonym match contributes more than spell-correction match
4. **Term frequency and passage relevance:** within `full_text_en`, higher term frequency and denser co-occurrence of query terms contribute positively

##### Default search scope

All sources (CA + LS + RS) are included by default. Users narrow scope via filters (Feature 03).

#### Acceptance Criteria

- Search box is visible and accessible on the homepage
- A persistent search box pre-populated with the current query appears at the top of the results page
- Queries of 2 or more non-whitespace characters execute and return results
- Queries shorter than 2 non-whitespace characters display an inline validation message; no search is executed
- Empty submission displays an inline validation message; no search is executed
- A record matching all original query terms ranks above a record matching only synonym expansions for the same query
- A phrase query (double-quoted) returns only records where that exact word sequence is present; records containing the individual words non-adjacently do not match the phrase query
- Search is case-insensitive: "Fundamental Rights" and "fundamental rights" return identical result sets
- No-results state shows a clear message and suggestions; it is not an error page
- Search response time: ≤2 seconds at p95 across the full indexed corpus

#### UI Behavior

- Homepage: full-width search box with a Search button; no autocomplete in v1
- Results page: compact search box at top pre-filled with current query; results list below
- Inline validation messages appear below the search box; no modal or page redirect
- No-results state: shown in the results area with message and suggestions

#### Edge Cases

- Query consisting only of stop words (e.g., "the and or in"): strip stop words; if nothing remains after stripping, show the same validation message as an empty query
- Query exceeding 500 characters: truncate to 500 characters and execute; no error shown to the user
- Special characters (punctuation, brackets, symbols) in query: strip or escape before execution; must not cause a search error or empty result due to parsing failure
- Identical query resubmission: execute again; do not serve a cached stale result set
- Search backend error (infrastructure failure): display an explicit error state ("Search is temporarily unavailable") in the results area with a retry option; do not show an empty results list or a blank page

#### Dependencies

- Feature 01: indexed corpus must exist
- Feature 04: synonym dictionary and spell-correction rules (search degrades gracefully to exact-match if Feature 04 is not yet available, but full expansion behaviour requires Feature 04)

#### NFR Implications

- **Response time:** ≤2 seconds at p95; query expansion increases scoring computation — architecture must account for this → update NFR
- **Scalability:** search must remain within response time target under concurrent user load → flag for architecture sizing

#### Test Requirements

*(from Test Spec 02)*

**Phrase Query Non-Adjacency**
- A record containing "fundamental" and "rights" separated by other words must NOT match a phrase query for `"fundamental rights"`; only records where those words appear consecutively and in that order must match

**Field Boost vs. Term Frequency**
- Given two records where record A contains the query term once in `speaker_name` and record B contains the query term ten times in `full_text_en` only, record A must rank higher than record B

**Expansion Weight Ordering**
- For the same query and the same record, a match on the original term must produce a higher relevance score than a match on a synonym; a synonym match must produce a higher relevance score than a spell-correction match
- This ordering must hold even when term frequency in `full_text_en` is higher for the lower-ranked expansion variant

**AND Logic With Partial Expansion Coverage**
- A record matching original term 1 and only a synonym expansion of term 2 must rank lower than a record matching both original terms
- A record matching only synonym expansions for all query terms must rank lower than a record matching at least one original term

**Case Insensitivity**
- Queries "article 370", "Article 370", "ARTICLE 370", and "Article 370" must return identical result sets in identical rank order
- Speaker names in mixed case in the index must be matched regardless of the case used in the query

**Stop Word Boundary**
- A query of "the right to speech" must execute as a search for "right speech" (stop words stripped); the result set must not differ from a direct query for "right speech"
- A query consisting entirely of stop words (e.g., "the and or") must show the validation message, not an empty result list

**Query Truncation**
- A query of exactly 501 characters must be truncated to 500 characters before execution; the truncated query must execute without error
- The truncated query must not expose the truncation to the user (no error message, no truncation indicator)

**Special Character Handling**
- A query containing parentheses, brackets, quotation marks, or boolean operators as literal characters (not as phrase delimiters) must not cause a search error; results must be returned or a no-results state shown
- A query of only special characters must be treated as an empty query and show the validation message

**Refinement Filter Persistence**
- When the user modifies the query on the results page and resubmits, any active filter selections from Feature 03 must persist; the new result set must reflect the new query AND the previously active filters
- Only an explicit "clear filters" action (Feature 03) resets filters to defaults

---

### F03: Search Filters

#### Description

Filters allow users to narrow search results by legislative body, date range, speaker, session, subject, and proceeding type. All filters are combinable with each other and with the search query. Filter state persists across query refinements on the results page and is only reset by an explicit clear action.

#### User Flows

**Applying filters:**
1. User is on the results page with an active search query
2. User selects one or more filter values (body, date range, speaker, session, subject, proceeding type)
3. System re-executes the search with the filter constraints applied; result list updates
4. Active filters are visually indicated; result count reflects the filtered set

**Clearing filters:**
1. User clicks "Clear filters" (clears all filters at once) or removes an individual filter value
2. System re-executes the search without the cleared constraint(s); result list updates

**Filter persistence:**
1. User refines the search query while filters are active
2. Active filter selections persist; new results reflect the updated query AND the existing filters
3. Filters are only reset by an explicit clear action — not by query refinement

**No results with active filters:**
1. Active filters eliminate all results for the current query
2. System shows the no-results state (Feature 02) with an additional "clear filters" suggestion

#### Filter Dimensions

##### 1. Legislative body
- Multi-select: CA, Lok Sabha, Rajya Sabha
- Default: all three selected (no body restriction)
- Any combination of one, two, or all three is valid

##### 2. Date range
- Two inputs: From date and To date
- Both are optional; leaving one or both empty applies no date bound on that side
- Date range is constrained to the indexed scope:
  - When only CA is selected in the body filter: picker restricts to 1946-01-01 – 1950-12-31
  - When only LS and/or RS is selected: minimum selectable date is 1947-08-15
  - When CA and LS/RS are both selected: full range 1946-01-01 to present is selectable; records from each body are included within their respective indexed scope
- From date must not be later than To date; if it is, an inline validation message is shown and the filter is not applied

##### 3. Speaker
- Free text input; case-insensitive substring match against the canonical `speaker_name` field
- Matches speaker names containing the entered string anywhere in the name
- Empty field: no speaker filter applied
- Note: speaker names in the index are canonicalized (honorifics stripped, variants resolved); users searching "Dr. Ambedkar" should enter "Ambedkar" for reliable results; a note to this effect is shown near the field
- No autocomplete in v1

##### 4. Session
- Free text input; case-insensitive substring match against `session_name`
- Matches sessions whose name contains the entered string (e.g., "Budget" matches "Budget Session 2023")
- Empty field: no session filter applied
- CA records have null `session_name` and will not match any session filter query; when a session filter is active, CA records are excluded from results
- No autocomplete in v1

##### 5. Subject
- Free text input; case-insensitive substring match against the `subject` field
- Matches records whose subject contains the entered string anywhere
- Empty field: no subject filter applied
- No autocomplete in v1

##### 6. Proceeding type
- Multi-select: Debate, Starred Question, Unstarred Question, Zero Hour, Short Notice Question, Calling Attention, Short Duration Discussion, Adjournment Motion, Private Member Bill
- Default: all types selected (no type restriction)
- Available options are constrained by the legislative body selection:
  - When only CA is selected: only "Debate" is available; all other options are disabled
  - When LS and/or RS is selected (alone or with CA): all options are available
- A user selecting types that do not exist for a selected body will simply receive no results from that body for those types; no error is shown

#### Filter Combination Logic

All active filters are ANDed together and ANDed with the search query. A record must satisfy all active filter constraints to appear in results.

Examples:
- Body = Rajya Sabha AND Date = 2020–2022 AND Proceeding type = Starred Question: returns only RS starred questions from that date range
- Speaker = "Ambedkar": returns all record types from all bodies where `speaker_name` contains "Ambedkar" (primarily CA records)
- Session = "Monsoon": returns all records from any session whose name contains "Monsoon" (LS/RS only; CA excluded)

#### Acceptance Criteria

- All six filter dimensions are available on the results page
- Subject filter applies a case-insensitive substring match against the `subject` field; empty value applies no subject restriction
- Each filter can be set independently or in any combination
- Active filters are visibly indicated on the results page (e.g., filter chips or highlighted state)
- A "clear filters" control resets all filters to their defaults in a single action
- Individual filter values can be removed without clearing all filters
- Filter state persists when the user refines the query; only an explicit clear resets filters
- Date range From > To shows a validation message; filter is not applied
- Proceeding type options disable correctly when only CA is selected in the body filter
- Session filter active: CA records are excluded from the result set
- Result count displayed on the results page reflects the filtered set, not the total unfiltered count

#### Edge Cases

- All proceeding types deselected: show validation message ("Select at least one proceeding type"); do not execute search with zero types selected
- All legislative bodies deselected: show validation message ("Select at least one source"); do not execute search with zero bodies selected
- Speaker filter with no matching canonical name in the index: show no-results state; do not error
- Session filter value that partially matches multiple sessions (e.g., "Session 2022" matches Monsoon Session 2022, Budget Session 2022, Winter Session 2022): all matching sessions are included in results
- Date range spans years with no indexed records (e.g., between the end of CA proceedings and the first LS/RS sittings, or RS years not covered by the current provider chain): result set is the union of records that exist within the range from each indexed source; no error is shown for the gaps

#### Dependencies

- Feature 01: canonical `speaker_name`, `session_name`, and `subject` fields in the index
- Feature 02: search query execution that accepts filter constraints

#### NFR Implications

None beyond what is already captured for Feature 02 (search response time target applies to filtered queries as well).

#### Test Requirements

*(from Test Spec 03)*

**Session Filter Excludes CA Records**
- When a session filter is active (any non-empty value), CA records must be absent from the result set even if CA is selected in the body filter and the query would otherwise match CA records

**Date Range Gap**
- A date range spanning the gap between CA proceedings and LS/RS sittings (e.g., 1951-01-01 to 1951-12-31, after CA ended and before Parliament was constituted) must return zero results without error
- A date range that spans records from multiple sources with a gap between them must return the union of records from each source within the range; no error must be shown for the gap years

**Proceeding Type Constraint When Only CA Is Selected**
- When CA is the only selected body, selecting any proceeding type other than "Debate" must produce zero results, not an error; the disabled state of the non-Debate options is a UI concern but the filter must still be functionally correct (no results, no crash)

**Speaker Substring Matching**
- A speaker filter value of "Singh" must match records attributed to any canonicalized speaker name containing "Singh" (e.g., "Manmohan Singh", "Rajnath Singh", "V.P. Singh")
- A speaker filter value containing only whitespace must be treated as an empty filter (no speaker restriction applied)

**Subject Filter Substring Matching**
- A subject filter value that is a substring of a longer subject (e.g., "Water" matching a record with subject "Water Resources Management") must produce a match; an exact-only match implementation is a bug
- A subject filter value containing only whitespace must be treated as an empty filter; the result set must be identical to the unfiltered result set

**Filter Persistence Across Query Refinements**
- After applying a Rajya Sabha body filter and refining the search query, the result set must contain only RS records; the body filter must not silently reset to "all bodies"
- The active filter indicator on the results page must still show the RS filter as active after query refinement

**Zero-Selection Validation**
- Deselecting all bodies and submitting must show a validation message and not execute a search; the previous result set must remain visible
- Deselecting all proceeding types and submitting must show a validation message and not execute a search; the previous result set must remain visible

**Date Validation Ordering**
- Setting From = 2022-06-01 and To = 2021-01-01 (From after To) must show an inline validation error and must not modify the displayed result set

**Combined Filter AND Logic**
- A query with body = LS, proceeding type = Starred Question, speaker = "Jairam Ramesh" must return only records satisfying all three constraints simultaneously; a LS debate speech by "Jairam Ramesh" must not appear; a RS starred question by "Jairam Ramesh" must not appear

---

### F04: Query Expansion

#### Description

Query expansion augments user queries with synonyms and spell corrections before search execution, improving recall for users who search with different terminology than what appears in the indexed records. Expanded terms are OR alternatives carrying reduced relevance weights — see Feature 02 for how weights are integrated into result ranking. The expansion dictionary is seeded with parliamentary domain-specific terms and maintained as a static file in the codebase; updates require a re-deployment.

#### Query Preprocessing

Before synonym expansion and spell correction, the query string is normalized:

- U+201C (") and U+201D (") curly double quotes are converted to ASCII straight double quotes (`"`)

This ensures that phrase queries typed on macOS and iOS — which auto-substitute typographic curly quotes for `"` — are correctly interpreted as phrase search syntax by Meilisearch, which uses ASCII straight double quotes to delimit phrase queries.

#### Synonym Dictionary

##### Coverage

The dictionary covers the following categories of parliamentary domain synonyms. Synonyms are bidirectional: if A expands to B, B also expands to A.

**Legislative bodies**
- "Lok Sabha" ↔ "House of the People" ↔ "Lower House"
- "Rajya Sabha" ↔ "Council of States" ↔ "Upper House"
- "Parliament" ↔ "both Houses" (phrase-level synonym for contexts referencing joint sessions)
- "Constituent Assembly" ↔ "CA" (abbreviation only; not expanded to other phrases)

**Constitutional terminology**
- "fundamental rights" ↔ "basic rights" ↔ "Part III rights"
- "Directive Principles" ↔ "DPSP" ↔ "Directive Principles of State Policy"
- "amendment" ↔ "constitutional amendment" (phrase-level, for queries about constitutional changes)
- "Preamble" ↔ "preamble to the Constitution"

**Parliamentary procedure**
- "starred question" ↔ "oral question"
- "unstarred question" ↔ "written question"
- "zero hour" ↔ "zero-hour"
- "private member bill" ↔ "private member's bill"
- "calling attention" ↔ "calling attention motion"
- "adjournment motion" ↔ "adjournment"
- "Question Hour" ↔ "question period"
- "division" ↔ "vote" (in parliamentary voting context)

**Common abbreviations expanded to full forms**
- "PM" ↔ "Prime Minister"
- "CM" ↔ "Chief Minister"
- "SC" ↔ "Scheduled Castes" (single-term; not expanded when "SC/ST" is used together)
- "ST" ↔ "Scheduled Tribes" (single-term)
- "SC/ST" ↔ "Scheduled Castes and Scheduled Tribes" (phrase-level)
- "OBC" ↔ "Other Backward Classes" ↔ "Other Backward Communities"
- "EWS" ↔ "Economically Weaker Sections"
- "GST" ↔ "Goods and Services Tax"
- "CAG" ↔ "Comptroller and Auditor General"
- "CBI" ↔ "Central Bureau of Investigation"
- "ED" ↔ "Enforcement Directorate"
- "FIR" ↔ "First Information Report"
- "PIL" ↔ "Public Interest Litigation"
- "Art." ↔ "Article" (for constitutional article references)
- "Sec." ↔ "Section"
- "Cl." ↔ "Clause"

**Well-known legislation (short title ↔ full title)**
- "RTI" ↔ "Right to Information" ↔ "Right to Information Act"
- "RTE" ↔ "Right to Education" ↔ "Right to Education Act"
- "MGNREGA" ↔ "NREGA" ↔ "Mahatma Gandhi National Rural Employment Guarantee Act"
- "POCSO" ↔ "Protection of Children from Sexual Offences"
- "IPC" ↔ "Indian Penal Code"
- "CrPC" ↔ "Code of Criminal Procedure"
- "BNS" ↔ "Bharatiya Nyaya Sanhita"
- "BNSS" ↔ "Bharatiya Nagarik Suraksha Sanhita"

##### Phrase synonyms vs. single-term synonyms

Phrase synonyms (e.g., "fundamental rights" ↔ "basic rights") apply only when the user's query contains the full phrase or when the user submits a phrase query (quoted or unquoted multi-word sequence matching the phrase). Single-term synonyms (e.g., "PM" ↔ "Prime Minister") apply to individual query terms.

Multi-word synonyms are not broken into individual terms for expansion. "Fundamental rights" as a phrase synonym does not cause "fundamental" alone to expand to anything, nor "rights" alone.

##### Dictionary maintenance

The dictionary is a static structured file (e.g., JSON or YAML) maintained in the codebase. Adding or modifying synonyms requires updating the file and redeploying. The dictionary file is the single source of truth; no runtime editing in v1.

#### Spell Correction

##### Scope

Spell correction applies to individual query terms. It does not apply within phrase queries (quoted terms are matched verbatim; spell correction is suppressed inside quotes).

##### Correction method

Edit-distance based correction: terms within a configurable edit distance from indexed vocabulary are offered as corrections. Phonetic matching is applied additionally for proper nouns (member names, place names) where character-level edit distance is insufficient.

##### Correction behaviour

- A corrected term is added as an OR alternative at a lower weight than synonym expansions
- The original (possibly misspelled) term is still included in the query at full weight; if the original term happens to match records exactly, those matches are returned
- Correction is applied silently — no "did you mean?" prompt is shown in v1; corrections appear in results without user notification
- Over-correction risk: very short terms (fewer than 4 characters) are exempt from spell correction to avoid spurious matches

#### Acceptance Criteria

- A query string containing U+201C or U+201D curly quotes around a phrase is treated as a phrase query equivalent to the same phrase enclosed in ASCII straight double quotes
- A query for "PM" returns records containing "Prime Minister" at a lower relevance weight than records containing "PM"
- A query for "fundamental rights" returns records containing "basic rights" at a lower relevance weight than records containing "fundamental rights"
- A query for "Parliment" (misspelled) returns records containing "Parliament" at a reduced weight
- A quoted phrase query ("fundamental rights") applies phrase-level synonyms only; individual term synonyms are not applied to terms inside the quotes
- Terms shorter than 4 characters are not spell-corrected
- Synonyms and spell corrections apply to LS, RS, and CA records equally
- The synonym dictionary file is the only source of synonym definitions; no synonyms are hardcoded elsewhere in the application

#### Edge Cases

- Ambiguous abbreviation ("SC" in a legal context vs. "SC" as Supreme Court): expand to all known expansions; ranking determines which is more relevant to the query context
- User queries a term that is itself a synonym expansion of another term (e.g., user searches "House of the People"): expands bidirectionally to include "Lok Sabha" at reduced weight
- Dictionary term that is a substring of a longer query term: expansion applies only to exact term matches, not substring matches (e.g., "PM" does not expand within "MGNREPM")
- Spell correction produces a correction that is also in the synonym dictionary: apply both — the correction is an OR alternative at correction weight; the correction's synonym is a further OR alternative at synonym weight

#### Dependencies

- Feature 02: the search execution model that consumes expansion output and applies relevance weights

#### NFR Implications

None beyond what is captured in Feature 02 (response time target must account for expansion computation).

#### Test Requirements

*(from Test Spec 04)*

**Curly Quote Normalization**
- A query string containing U+201C (") and U+201D (") curly double quotes around a phrase must result in those characters being converted to ASCII straight double quotes before the query is transmitted to Meilisearch; U+201C and U+201D must not appear in the query string sent to the search engine

**Bidirectionality**
- A query for "House of the People" must expand to include "Lok Sabha" at synonym weight; a query for "Lok Sabha" must expand to include "House of the People" at synonym weight
- Bidirectionality must hold for all synonym pairs in the dictionary; a synonym that expands A→B must also expand B→A

**Phrase Synonym Isolation**
- A query for "fundamental rights" (unquoted multi-term) must expand using the phrase synonym "basic rights"; it must NOT additionally expand "fundamental" as a standalone term or "rights" as a standalone term via any single-term synonym entries
- A query for "rights" alone must not expand to "fundamental rights" via the phrase synonym; phrase synonyms must only apply when the full phrase is present in the query

**Spell Correction Suppression in Phrases**
- A quoted phrase query containing a misspelled term (e.g., `"Parliment debate"`) must not apply spell correction; the phrase must be searched verbatim and return results only for that exact sequence

**Short Term Exemption**
- A query term of 1, 2, or 3 characters must not trigger spell correction; the term must be searched as-is with no corrected alternatives added
- A query term of exactly 4 characters must be eligible for spell correction

**Correction Weight Below Synonym Weight**
- For a query where both a synonym expansion and a spell correction match the same record, the synonym match contribution to the relevance score must be higher than the spell correction match contribution; they must not produce equal scores

**Ambiguous Abbreviation Expansion**
- A query for "SC" must generate expansions for both "Scheduled Castes" and any other known expansions in the dictionary; all expansions must appear in results at reduced weight; the absence of any defined expansion for "SC" is a bug

**Dictionary as Sole Source**
- Introducing a synonym relationship that is only hardcoded in application logic (not present in the dictionary file) must cause a test to fail; all synonym relationships must be derivable solely from the dictionary file

**Substring Non-Expansion**
- A query term "MGNREGA" must not trigger the "PM" → "Prime Minister" synonym expansion because "PM" appears as a substring; expansion must only apply to exact full-term matches

---

### F05: Result Display

#### Description

Each search result is displayed as a card showing the record's metadata, a contextual text snippet with matched terms highlighted, and a link to the original source document. Results are displayed in a paginated list. The display gives users enough context to assess relevance without opening the source document.

#### Result Card: Speech Record

Displayed fields, in order:

| Field | Source | Notes |
|-------|--------|-------|
| Speaker name | `speaker_name` | Canonical form |
| Party / group | `speaker_party` | Shown if available |
| Constituency or state | `speaker_constituency_or_state` | Shown if available; omitted for CA records |
| Legislative body | `source` | Displayed as "Constituent Assembly", "Lok Sabha", or "Rajya Sabha" |
| Proceeding type | `proceeding_type` | Human-readable label (see label map below) |
| Date | `date` | Formatted as DD Month YYYY |
| Time of day | `time_of_day` | Shown as HH:MM near the date field when not null; omitted silently when null |
| Session | `session_name` | Shown if available; omitted for CA records |
| Subject / agenda item | `subject` | The debate title or agenda item this speech belongs to |
| Text snippet | derived from `full_text_en` | ≥200 words of context around the highest-relevance match; query terms highlighted |
| Language badge | `lang_original` | `hi`→"Hindi original"; `mixed`→"Mixed language"; `en`→no badge shown |
| Source link | `source_url` | "View source" link; opens in a new tab |

#### Result Card: Q+A Exchange Record

Displayed fields, in order:

| Field | Source | Notes |
|-------|--------|-------|
| Question number | `question_number` | Displayed as "Q. [number]" |
| Subject | `subject` | Question subject/title |
| Proceeding type | `proceeding_type` | "Starred Question" or "Unstarred Question" or other Q+A type label |
| Legislative body | `source` | "Lok Sabha" or "Rajya Sabha" |
| Date | `date` | Formatted as DD Month YYYY |
| Time of day | `time_of_day` | Shown as HH:MM near the date field when not null; omitted silently when null |
| Session | `session_name` | Shown if available |
| Questioner | `questioner_names` (primary) | First named questioner; additional questioners shown as "+N others" if co-signatories present |
| Questioner party | `questioner_party` | Shown if available |
| Minister and ministry | `minister_name`, `ministry` | "Answered by [Minister Name], [Ministry]" |
| Text snippet | derived from `full_text_en` | ≥200 words of context around the highest-relevance match; query terms highlighted |
| Language badge | `lang_original` | `hi`→"Hindi original"; `mixed`→"Mixed language"; `en`→no badge shown |
| Source link | `source_url` | "View source" link; opens in a new tab |

#### Proceeding Type Labels

| `proceeding_type` value | Displayed label |
|------------------------|-----------------|
| debate | Debate |
| starred_question | Starred Question |
| unstarred_question | Unstarred Question |
| zero_hour | Zero Hour |
| short_notice_question | Short Notice Question |
| calling_attention | Calling Attention |
| short_duration_discussion | Short Duration Discussion |
| adjournment_motion | Adjournment Motion |
| private_member_bill | Private Member Bill |

#### Snippet Generation

- Snippet is a passage of at least 200 words extracted from `full_text_en`, chosen from the passage with the highest density of query term matches; the Meilisearch crop length must be configured to produce this minimum
- Query terms (original and expanded matches) are highlighted in the snippet
- If `full_text_en` contains fewer than 200 words, the full text is shown as the snippet (no truncation of content shorter than the minimum)
- If the matched passage is near the start or end of `full_text_en`, the snippet may be shorter than 200 words
- If the record has `full_text_en: null` (untranslated Hindi speech): snippet area shows the message "This speech was delivered in Hindi. No English text is available." in place of a snippet; `has_untranslated_content` is the trigger
- For Q+A records, if the match is in a supplementary exchange rather than the main question/answer, the snippet is drawn from the supplementary exchange; a label "From supplementary exchange" is shown

#### Pagination

- 20 results per page
- Result count displayed at the top of the list:
  - Exact count for up to 9,999 results (e.g., "47 results", "3,241 results")
  - Approximate count for 10,000 or more (e.g., "10,000+ results")
- Pagination controls show: previous page, next page, current page number, and total page count (if ≤ 500 pages); for result sets exceeding 500 pages, total page count is not shown
- URL reflects current page number so that results pages are shareable and bookmarkable

#### Acceptance Criteria

- Every result card displays: body, proceeding type, date, subject, snippet with highlighted terms, and a working source link
- "View source" opens the original document in a new browser tab
- Snippet highlights all matched query terms (original terms and expanded matches)
- Records with `full_text_en: null` display the untranslated-speech message in place of a snippet; they do not display an empty or blank snippet area
- Records with `lang_original: hi` show the "Hindi original" badge; records with `lang_original: mixed` show the "Mixed language" badge; records with `lang_original: en` show no badge
- Records with `time_of_day` not null display the time as HH:MM near the date; records with `time_of_day: null` display no time field and no placeholder
- Result count is shown at the top of the result list
- Paginated result sets: navigating to a specific page via URL (direct link or bookmarked URL) loads the correct page of results
- `speaker_name_unresolved: true` records display the raw name as stored; no error or blank in the speaker name field

#### Edge Cases

- Record with missing `speaker_party` or `speaker_constituency_or_state`: those fields are simply omitted from the card; no placeholder text shown
- Record with `speaker_name: null` (unresolved attribution): speaker name area shows "Speaker unknown"
- Snippet contains HTML or special characters from source document: characters are escaped/sanitised before display; must not render as HTML
- Source URL is missing or broken: "View source" link is not shown; no broken link is displayed

#### Dependencies

- Feature 01: indexed records with all metadata fields
- Feature 02: search execution providing ranked results and match position data for snippet extraction

#### NFR Implications

None beyond Feature 02's response time target, which covers end-to-end time to result list rendered.

#### Test Requirements

*(from Test Spec 05)*

**Snippet from Supplementary Exchange**
- When the highest-relevance match for a starred Q+A record is in a supplementary exchange (not the main Q+A), the displayed snippet must be drawn from the supplementary exchange and the "From supplementary exchange" label must be present; a snippet from the main Q+A must not be shown instead

**Result Count Threshold**
- A result set of exactly 9,999 records must display an exact count ("9,999 results"), not the approximate form
- A result set of exactly 10,000 records must display the approximate form ("10,000+ results"), not an exact count
- A result set of exactly 0 records must display "0 results", not the no-results state message (the no-results state message is for when no records match the query; "0 results" appears when the count is computed but is zero — these are the same situation, but the count display and the no-results message must both be present)

**Untranslated Speech Snippet Placeholder**
- A record with `full_text_en: null` must display the "This speech was delivered in Hindi. No English text is available." message in the snippet area
- The snippet area for such records must not be empty, blank, or absent — the placeholder message is required
- A record with `full_text_en: null` must still display all other metadata fields normally (body, date, speaker, subject, source link)

**HTML Sanitisation in Snippet**
- A `full_text_en` value containing HTML tags (e.g., `<b>`, `<script>`, `&amp;`) must render as plain text in the snippet; tags must not be interpreted as HTML; script tags must not execute

**Page URL Persistence**
- Navigating to page 3 of results, copying the URL, and opening it in a new browser session must load page 3 of the same search results without requiring re-entry of the query
- The URL must encode both the query and the page number; a URL missing either parameter must default to page 1 of the query results

**Co-Signatory Display**
- A starred question with exactly 1 questioner must not show the "+N others" label
- A starred question with 3 co-signatories (4 total including primary) must show "+3 others" next to the primary questioner's name

**Language Badge**
- A record with `lang_original: hi` must display the "Hindi original" badge; no other badge or label relating to language must appear on that card
- A record with `lang_original: mixed` must display the "Mixed language" badge
- A record with `lang_original: en` must display no language badge; the badge element must be absent from the DOM, not merely hidden

**Time of Day Display**
- A record with `time_of_day: "14:35"` must display "14:35" near the date field; the value must not be reformatted (e.g. not "2:35 PM")
- A record with `time_of_day: null` must not render any time-of-day element — no placeholder, no empty field, no "—"

**Speaker Name Unresolved Display**
- A record with `speaker_name_unresolved: true` must display the raw name stored in `speaker_name` without any error indicator or blank; the display must be identical in format to a resolved name

**Snippet Minimum Size**
- A record whose `full_text_en` contains more than 400 words must produce a snippet of at least 400 words; the snippet must not be truncated to fewer words unless the matched passage is within 400 words of the start or end of the text
- A record whose `full_text_en` contains fewer than 400 words must display the full text as the snippet; no words may be omitted

---

### F06: Sorting

#### Description

Users can sort search results by relevance, chronological order (oldest first), or reverse chronological order (newest first). The default sort is relevance. Sort state persists across query refinements and is only reset when the user explicitly changes it.

#### Sort Options

| Option | Order | Description |
|--------|-------|-------------|
| Relevance (default) | Descending relevance score | Records ranked by the combined relevance score from Feature 02; highest-scoring first |
| Chronological | Ascending date | Oldest records first; secondary sort by `sequence_within_sitting` ascending for records on the same date |
| Reverse chronological | Descending date | Newest records first; secondary sort by `sequence_within_sitting` descending for records on the same date |

#### User Flows

**Changing sort order:**
1. User is on the results page with an active search and result list
2. User selects a sort option from the sort control
3. Result list re-orders; result count does not change; all active filters remain in place
4. The selected sort option is visually indicated as active

**Sort persistence:**
1. User changes sort to "Chronological" then refines the search query
2. Sort selection persists; new results are displayed in chronological order

#### Acceptance Criteria

- Three sort options are available on the results page: Relevance, Chronological, Reverse chronological
- Default sort on every new search is Relevance
- Changing sort re-orders results without changing the result count or clearing filters
- Sort selection persists across query refinements
- Chronological and reverse-chronological sorts use date as the primary key and `sequence_within_sitting` as the secondary key
- Relevance sort uses the relevance score from Feature 02; records are not additionally sorted by date in relevance mode

#### Edge Cases

- All results share the same date (e.g., single-sitting filter): chronological and reverse-chronological both use `sequence_within_sitting` as the effective sort key; results are ordered by their position within that sitting
- Relevance sort with query expansion: records matching only expanded terms appear lower in relevance order than those matching original terms; this is governed by the scoring model in Feature 02, not by the sort control

#### Dependencies

- Feature 02: relevance scores used for the relevance sort option
- Feature 01: `date` and `sequence_within_sitting` fields used for date-based sort options

#### NFR Implications

None beyond the response time target in Feature 02.

#### Test Requirements

*(from Test Spec 06)*

**Secondary Sort Key**
- Two records with the same date must be ordered by `sequence_within_sitting` ascending in chronological mode and descending in reverse-chronological mode; date alone is insufficient as a sort key when records share a date

**Relevance Sort Isolation**
- Switching from chronological to relevance sort must reorder results by relevance score; the previous date-based order must not be preserved as a tiebreaker within equal-relevance groups (tiebreaking within relevance sort is undefined and must not silently default to date order)

**Sort Persistence Across Refinement**
- User sets sort to "Chronological", then edits the query and resubmits; the sort control must still show "Chronological" as active; new results must be in chronological order

**Result Count Invariance**
- Changing sort order must not change the result count displayed; the count before and after a sort change must be identical for the same query and filter state

**Default Sort on New Search**
- Every new search (fresh query submission from homepage or results page with a cleared query) must default to Relevance sort, regardless of the sort option that was active in the previous search session

---

### F07: Indexing Status Panel

#### Description

A read-only panel displaying the current state of the search index: total records indexed, a per-source breakdown with date coverage, and the date of the last ingestion run. Gives users transparency about what data is available before or after a search. In v1, the index is populated by a one-time bulk load (Feature 01); the status panel reflects the actual state of the index at any given time, including partial loads.

#### Displayed Information

| Item | Description |
|------|-------------|
| Total records indexed | Count of all indexed records across all sources |
| Per-source record count | Separate count for CA, Lok Sabha, and Rajya Sabha |
| Per-source date coverage | Earliest and latest indexed date for each source |
| Last ingestion run | Date the ingestion pipeline last completed or was last run |

##### Display format

```
Search Index Status

Total records indexed: [N]

Constituent Assembly      [N] records    1946–1950
Lok Sabha                 [N] records    [Earliest date] – [Latest date]
Rajya Sabha               [N] records    [Earliest date] – [Latest date]

Last updated: [DD Month YYYY]
```

Counts use thousands separators (e.g., "1,234,567"). If a source has not yet been indexed, its row shows "0 records – not yet indexed" rather than a date range.

#### Data Source

The status panel reads from a summary record written by the ingestion pipeline (Feature 01) at the end of each run. The summary record stores: per-source record counts, per-source earliest and latest indexed dates, and the ingestion run timestamp. The panel does not query the search index directly at page load; it reads the pre-computed summary.

#### Display Surfaces

##### Homepage Status Strip

A condensed summary shown on the homepage, below the search box, giving users a quick overview of index scope before searching. Shows per-source record counts and the last ingestion date. Does not show per-source date coverage. Sources with zero indexed records are still shown in the strip; their count displays as "0 [Body] records".

Format: `[N] Constituent Assembly records · [N] Lok Sabha records · [N] Rajya Sabha records · Last updated: [DD Month YYYY]`

##### Full Indexing Status Panel

The detailed view of index state, accessible from the results page via a persistent footer link labelled "Index status". Displays the full format described in the Displayed Information section above, including per-source date coverage and the "0 records – not yet indexed" row format for sources with zero records.

#### Acceptance Criteria

- The homepage strip displays per-source record counts and the last updated date
- The full indexing status panel displays total record count, per-source counts, per-source date coverage, and last updated date
- Counts and dates reflect the actual state of the index; they are not hardcoded
- Homepage strip: a source with zero indexed records is shown as "0 [Body] records" in the strip; it is not omitted
- Full panel: a source with zero indexed records shows "0 records – not yet indexed" without a date range
- Last updated date reflects the most recent ingestion run completion timestamp, not the current date
- Both surfaces are read-only; no user interaction is required or available beyond viewing

#### Edge Cases

- Ingestion pipeline has never been run (fresh deployment): panel shows all sources as "0 records – not yet indexed" and last updated as "Never"
- Ingestion ran but encountered errors and indexed fewer records than expected: panel shows the actual indexed count, not an expected count; no error or warning is displayed in the panel
- Per-source date coverage spans a gap (e.g., some months missing from the middle of the date range): the displayed range is the earliest and latest indexed date; the panel does not indicate internal gaps
- Summary record is malformed or unreadable: the panel displays a "Status unavailable" message in place of the counts and dates; it does not crash or show partial/corrupted data

#### Dependencies

- Feature 01: ingestion pipeline that writes the summary record the panel reads from

#### NFR Implications

None. The panel reads a pre-computed summary; no real-time index query is performed.

#### Test Requirements

*(from Test Spec 07)*

**Pre-computed Summary — Not Live Query**
- The panel must not issue a query to the search index at page load; it must read from the pre-computed summary record written by the ingestion pipeline; a test that disables the search index must still show the last known status data without error

**Never-Run State**
- On a fresh deployment where ingestion has never been run, the "Last updated" field must display "Never", not a null value, blank, or a default date

**Zero-Source Row Format**
- In the full panel, a source with zero indexed records must display "0 records – not yet indexed" with no date range; displaying an empty date range string or a placeholder date (e.g., "Jan 1970") is a bug
- In the homepage strip, a source with zero indexed records must still appear in the strip showing "0 [Body] records"; it must not be omitted

**Count Accuracy**
- The total records count displayed must equal the sum of the three per-source counts; a discrepancy between the total and the sum is a bug

**Ingestion Timestamp**
- The "Last updated" date must reflect the ingestion run completion timestamp; it must not update when the page is loaded, when a search is run, or at any other time other than after an ingestion pipeline run

---

### F08: Search History

#### Description

Cookie-based recent searches and saved searches. No sign-in is required. All data is stored client-side in cookies; nothing is sent to the server. Recent searches are recorded automatically when a query is submitted. Saved searches are explicitly bookmarked by the user and persist until deleted. Both are accessible from the homepage and the results page.

#### Recent Searches

##### Storage and limits
- Automatically recorded each time a search query is submitted (regardless of whether any results were returned)
- Maximum 10 entries stored; when the limit is exceeded, the oldest entry is removed
- Duplicate queries: if the same query string is submitted again, the existing entry is updated to the most recent timestamp; only one entry per unique query string is maintained
- Cookie lifetime: 30 days from the most recent submission; entries older than 30 days are not displayed
- What is stored per entry: query text and submission timestamp; filter state is not stored with recent searches

##### Actions
- Click a recent search entry to re-run that query (with default filters and default sort — not with any previously active filter state)
- Delete an individual recent search entry
- Clear all recent searches at once

#### Saved Searches

##### Storage and limits
- Explicitly saved by the user from the results page
- Maximum 20 saved searches stored
- When the 20-entry limit is reached, the user must delete an existing saved search before a new one can be saved; the save action is disabled with an explanatory message when at the limit
- No expiry; saved searches persist until the user deletes them
- Cookie lifetime: persistent (no expiry date set on the cookie); persists until cookie is cleared by the browser

##### What is stored per saved search
- Name: defaults to the query text; user can rename to a custom label (max 60 characters)
- Query text
- Active filter state at the time of saving (legislative body, date range, speaker, session, subject, proceeding type selections)
- Save timestamp

##### Actions
- Save the current search (query + active filters) from the results page
- Re-run a saved search: re-executes the stored query with the stored filter state and default sort
- Rename a saved search (edit the name label)
- Delete a saved search

#### Cookie Storage Constraints

- Recent searches and saved searches are stored in separate cookies
- Total cookie data for both combined must not exceed 4KB; if stored data approaches this limit, recent searches are trimmed first (oldest removed) before saved searches are affected
- If cookies are disabled in the browser, recent and saved search features are silently unavailable; the rest of the application functions normally with no error shown

#### Acceptance Criteria

- Every submitted search query is added to recent searches automatically
- Recent searches list shows at most 10 entries, ordered by most recent first
- Submitting a duplicate query updates the timestamp and position of the existing entry; it does not create a second entry
- Saved searches store and restore query text and filter state exactly; re-running a saved search produces the same filter-active result set as if the user had manually set those filters
- Saved search name defaults to the query text and is editable up to 60 characters
- Saving is disabled (with message) when 20 saved searches exist
- Deleting a recent or saved search removes it immediately without page reload
- All history features work without user authentication; no data is sent to the server

#### Edge Cases

- Cookie storage near capacity: oldest recent searches are removed silently to free space; saved searches are not removed automatically
- User clears browser cookies: all recent and saved search data is lost; application continues to function; no error shown
- Saved search references filter values that are no longer valid (e.g., a proceeding type that was renamed): the saved search still executes with the stored filter state; invalid filter values are silently ignored (treated as "not set") rather than causing an error
- Same query saved twice: allowed; user may give them different names; they appear as two separate entries
- Very long query text (up to 500 characters, the search truncation limit): stored and displayed as-is in the saved/recent list; display is truncated visually if the label is too long, but the full query is preserved for re-execution

#### Dependencies

- Feature 02: search execution that accepts a query string
- Feature 03: filter state model that saved searches restore

#### NFR Implications

- **Privacy:** all search history data is stored client-side in cookies only; no search queries or filter selections are persisted server-side in v1 → note in NFR

#### Test Requirements

*(from Test Spec 08)*

**Duplicate Query Deduplication**
- Submitting the same query string three times must result in exactly one entry in recent searches, with the timestamp of the third submission; not two or three entries

**FIFO Rotation at Limit**
- With 10 recent searches already stored, submitting an 11th (distinct) query must remove the oldest entry and add the new one; the list must remain at exactly 10 entries; the oldest entry must not reappear after the new submission

**Recent Search Re-runs with Default Filters**
- Re-running a recent search must execute with all filters at their defaults, regardless of what filters were active when that query was originally submitted; the recent search entry does not capture filter state

**Saved Search Filter Restoration**
- A saved search created with body = Rajya Sabha, proceeding type = Starred Question, date from = 2020-01-01 must restore exactly those filter selections when re-run; the result set must be equivalent to manually setting those same filters for that query

**Save Disabled at Limit**
- With exactly 20 saved searches stored, the save action must be visibly disabled and show an explanatory message; attempting to trigger the save action by any means must not create a 21st entry

**Same Query Saved Twice**
- Saving the same query text twice must create two separate saved search entries; the second save must not overwrite or merge with the first

**Cookie-Disabled Behaviour**
- When cookies are blocked, recent searches and saved searches must not be shown; no error message about cookies must be displayed to the user; the search box and results must function normally

**Saved Search Name Length**
- A saved search name of exactly 60 characters must be accepted; a name of 61 characters must be rejected (input truncated or validation shown) without losing the save action

**Stale Filter Value in Saved Search**
- Re-running a saved search that contains an unrecognised proceeding type value (e.g., from a future schema change) must execute the search ignoring that filter value; it must not throw an error or prevent the search from running

---

### F09: Detail Page

#### Description

A full-record detail page displaying the complete text and all metadata for a single indexed record. Accessible via a stable URL. Provides inline adjacent speech loading within the same sitting and back navigation to the results page.

#### Route and API

- **Frontend route:** `/record/:id`
- **API endpoint:** `GET /api/record/{id}` — fetches a single document by record `id`; returns 404 if not found

#### User Flows

**Arriving from search results:**
1. User clicks a result card
2. Browser navigates to `/record/:id`
3. Detail page loads: full text rendered as paragraphs, all metadata fields shown, inline adjacent loading controls shown
4. "Back to results" link is present; clicking it returns to the search results page (preserving query and pagination state)

**Direct access (bookmarked or shared URL):**
1. User opens `/record/:id` directly
2. Detail page loads as above
3. "Search" link to homepage is shown in place of "Back to results"

**Adjacent loading:**
1. User clicks "Load 5 previous" or "Load 5 next" control
2. Up to 5 adjacent records from the same sitting are loaded inline — prepended above (for previous) or appended below (for next) the currently shown records — without page navigation
3. URL remains at `/record/:id` of the focal record
4. "Same sitting" is defined as: same `source` + same `date` + same `sitting_number`; Q+A exchange records and speech records share the sequence space
5. If more records remain in that direction after the load, the control stays enabled; when no more records exist in that direction, the control becomes disabled
6. User may continue clicking to progressively expand the view in either direction

#### Full Text Display

- `full_text_en` is rendered as paragraphs (not a truncated snippet)
- If `full_text_en` is null: display the message "This record was delivered in Hindi. No English text is available." in the text area; no blank or empty area

#### Metadata Fields Displayed

All fields are shown explicitly. Fields that are null or not applicable for the record type are omitted silently (no placeholder label shown for null fields), except where noted below.

| Field | Display label | Notes |
|-------|--------------|-------|
| `source` | Legislative body | "Constituent Assembly", "Lok Sabha", or "Rajya Sabha" |
| `lok_sabha_number` | Lok Sabha term | Displayed as "[N]th/st/nd/rd Lok Sabha" with the correct ordinal suffix (e.g., "17th Lok Sabha", "21st Lok Sabha"); shown only for LS records; omitted for RS and CA records |
| `proceeding_type` | Proceeding type | Human-readable label per F05 label map |
| `date` | Date | DD Month YYYY |
| `time_of_day` | Time | HH:MM; omitted when null |
| `session_name` | Session | Omitted when null |
| `session_number` | Session number | Omitted when null |
| `sitting_number` | Sitting number | |
| `volume` | Volume | CA only; omitted for LS/RS |
| `subject` | Subject | |
| `speaker_name` | Speaker | Speech records only |
| `speaker_role` | Role | Speech records only; shown as human-readable label |
| `speaker_party` | Party | Omitted when null |
| `speaker_constituency_or_state` | Constituency / State | Omitted when null; omitted for CA records |
| `speaker_name_unresolved` | — | When true, display "(name unresolved)" as a note next to `speaker_name`; not shown when false |
| `question_number` | Question number | Q+A records only; displayed as "Q. [number]" |
| `questioner_names` | Questioner(s) | Q+A records only |
| `questioner_party` | Questioner party | Q+A records only; omitted when null |
| `minister_name` | Minister | Q+A records only |
| `ministry` | Ministry | Q+A records only |
| `lang_original` | Language | "English", "Hindi", or "Bilingual" — always shown |
| `is_translated` | Translation | "Includes official English translation" — shown only when true |
| `has_untranslated_content` | Untranslated content | "Some content unavailable in English" — shown only when true |
| `page_reference` | PDF page | Shown as "PDF page [N]" when not null; omitted when null |
| `word_count` | Word count | Shown as "[N] words" when not null; omitted when null |
| `sequence_within_sitting` | Position in sitting | Shown as "[N] of [total]" where total is the count of records in the same sitting |
| `source_url` | Source | "View source" link opening in a new tab; omitted when null |

#### Adjacent Speech Loading

Rather than navigating to a new URL for each adjacent record, the detail page loads adjacent records inline on the same page.

- Above the focal record: a "Load 5 previous" control
- Below the focal record: a "Load 5 next" control
- "Load 5 previous" is disabled (not hidden) when the focal record has the lowest `sequence_within_sitting` in the sitting; "Load 5 next" is disabled when the focal record has the highest
- Clicking "Load 5 previous" loads up to 5 records with the next-lower `sequence_within_sitting` values, prepended above the current lowest-loaded record
- Clicking "Load 5 next" loads up to 5 records with the next-higher `sequence_within_sitting` values, appended below the current highest-loaded record
- After a batch load, if more records remain in that direction, the control stays enabled; if no more remain, it becomes disabled
- Each loaded adjacent record displays: speaker name (or questioner/minister for Q+A records), date, subject, proceeding type, and full text
- Adjacent records are determined from the same sitting: same `source` + `date` + `sitting_number`, ordered by `sequence_within_sitting`
- The page URL does not change when adjacent records are loaded; it remains at `/record/:id` of the focal record

#### Back Navigation

- When the user arrived from a search results page (navigated via in-app link): show "Back to results" link that returns to the referring results page
- When the page is accessed directly (direct URL, bookmark, or external link): show "Search" link pointing to the homepage

#### Acceptance Criteria

- `/record/:id` loads the correct record for any valid `id`; returns a 404 page for an unknown `id`
- Full `full_text_en` is displayed as paragraphs; null `full_text_en` shows the defined message
- All non-null metadata fields are displayed; null fields are omitted with no placeholder
- `page_reference` is shown as "PDF page [N]" when present; omitted when null
- `lok_sabha_number` is displayed as "[N]th/st/nd/rd Lok Sabha" for LS records; omitted for RS and CA records
- `source_url` renders as a "View source" link when present; omitted when null
- Clicking "Load 5 next" appends up to 5 next sitting records inline below the focal record without page navigation; the URL remains at the focal record's `/record/:id`
- Clicking "Load 5 previous" prepends up to 5 previous sitting records inline above the focal record without page navigation
- Each loaded adjacent record displays speaker name (or questioner/minister for Q+A), date, subject, proceeding type, and full text
- After loading a batch, if more records remain in that direction, the load control stays enabled; when no more exist, the control is disabled
- Load controls are disabled (not hidden) at sitting boundaries; both are disabled when the sitting contains only one record
- "Back to results" is shown when arriving from search; "Search" link when accessed directly

#### Edge Cases

- Record with `full_text_en: null`: text area shows the defined message; all metadata fields still display normally
- Record at sequence boundary: the boundary-side load control is disabled; the opposite-direction control behaves normally
- Only one record in the sitting: both "Load 5 previous" and "Load 5 next" are disabled
- `source_url` is null: "View source" link is not shown; no broken link rendered
- Direct URL access with no referrer: "Search" link shown; no "Back to results" link
- `id` not found: 404 response; frontend renders a "Record not found" page
- Fewer than 5 records remain in a direction: load control loads however many are available (1–4) and then becomes disabled
- Adjacent load API call fails (network error or server error): an error message is shown in place of the loaded records; the load control returns to its pre-click enabled state (re-clickable); existing loaded records are not affected

#### Dependencies

- Feature 01: indexed records with `id`, `sequence_within_sitting`, `lok_sabha_number`, and all metadata fields
- Feature 02: search index accessible by document `id`

#### NFR Implications

- **Performance:** detail page full load including the initial record fetch must meet the PERF-2 target; adjacent batch loads after the initial page load are not subject to PERF-2 → see `04-non-functional-requirements.md`

#### Test Requirements

*(from Test Spec 09)*

**Lok Sabha Term Display**
- A record with `lok_sabha_number: 17` must display "17th Lok Sabha"; a record with `lok_sabha_number: 21` must display "21st Lok Sabha"; a record with `lok_sabha_number: 22` must display "22nd Lok Sabha"; a record with `lok_sabha_number: 23` must display "23rd Lok Sabha" — the ordinal suffix must be correct for each value
- An RS record must not render any element with the text "Lok Sabha" in the metadata area; the `lok_sabha_number` field must be entirely absent from the DOM

**Inline Adjacent Loading**
- Clicking "Load 5 next" must not trigger a page navigation; the URL must remain `/record/:id` of the focal record after the click
- After "Load 5 next" loads 5 records and 3 more remain, the "Load 5 next" control must be enabled; after a subsequent click that loads those 3, the control must be disabled
- Clicking "Load 5 previous" must prepend records above the focal record, not replace it; the focal record must remain in the DOM after any number of adjacent loads
- When the focal record is the only record in its sitting, both load controls must be disabled simultaneously; neither must be hidden or absent from the DOM

**Back Navigation Detection**
- A record opened via in-app navigation from the results page must show "Back to results"; the link must navigate back to the results page without re-executing the search
- A record opened by pasting its URL directly into a new tab must show "Search" (to homepage) and must not show "Back to results"

**Null Full Text Area**
- A record with `full_text_en: null` must render the defined message in the text area; the text area must not be empty, blank, or absent
- The same record must still render all non-null metadata fields; the null `full_text_en` must not suppress other field rendering

**page_reference Formatting**
- A record with `page_reference: 42` must display "PDF page 42"; arbitrary integer values must be formatted as "PDF page [N]" with no additional text
- A record with `page_reference: null` must show no page reference label or value — not "PDF page —" or "PDF page null"

**sequence_within_sitting Display**
- The "position in sitting" display must show "[N] of [M]" where M is the actual count of records sharing the same `source` + `date` + `sitting_number`; M must not be hardcoded or estimated

**404 Handling**
- A request to `/record/nonexistent-id` must render a "Record not found" page; it must not render a blank page, a JS error, or a partially loaded detail page

---

### F10: Debug Mode

#### Description

Debug mode is a developer and diagnostic facility that exposes internal search scoring, index data, and database records for each search result. It is activated via a URL parameter and requires no authentication. When active, each result card shows an expandable debug panel, and a global search debug panel appears at the top of the results list.

#### Activation

Debug mode is activated by appending `?debug=1` to any search results URL. It applies for the duration of that page view. Removing the parameter deactivates debug mode.

#### User Flows

**Activating debug mode:**
1. User appends `?debug=1` to a search results URL (or constructs a URL with the parameter)
2. Page loads in debug mode: a global debug panel appears above the results; each result card shows a "Debug" toggle

**Inspecting a result:**
1. User clicks the "Debug" toggle on a result card
2. The debug panel expands, showing 4 collapsible sections (all collapsed by default):
   - Scoring details
   - Document in index
   - Processed record
   - Raw document
3. User expands a section by clicking its header
4. Scoring details and Document in index render immediately (data loaded with search response)
5. Processed record and Raw document each trigger a network request on first expand; data renders when the request returns
6. Sections can be independently collapsed and re-expanded; subsequent expands of Processed record or Raw document use the previously fetched data (no re-fetch)

**Inspecting overall search behavior:**
1. User clicks to expand a section in the global search debug panel
2. Content renders from data captured at search time (no additional requests)

#### Per-Result Debug Panel

When debug mode is active, each result card displays a "Debug" toggle. Expanding it reveals four collapsible sections:

##### 1. Scoring details

Meilisearch ranking score data for this result, included in the search response when debug mode is active:
- `_rankingScore`: the overall relevance score (0.0–1.0)
- `_rankingScoreDetails`: per-rule breakdown (words, typo, proximity, attribute, exactness, and any custom ranking rules configured)
- All score fields returned by Meilisearch for this document are shown; the set of fields depends on the configured ranking rules

##### 2. Document in index

The full Meilisearch document for this result as stored in the search index, included in the search response when debug mode is active. Displays every field present in the index document.

##### 3. Processed record

The full row from `speeches` or `qa_exchanges` in PostgreSQL corresponding to this result. Fetched lazily from `GET /api/debug/processed/{id}` on first expand of this section. Displays every column in the row, including `segments` (JSONB).

##### 4. Raw document

The full row from `raw_documents` in PostgreSQL from which this record was processed. Fetched lazily from `GET /api/debug/raw/{id}` on first expand of this section. Displays every column in the row, including the full extracted text content.

#### Global Search Debug Panel

Shown above the result list when debug mode is active. Contains five collapsible sections (all collapsed by default):

##### 1. Processed query

The query as transformed by the search service before submission to Meilisearch: after synonym expansion, stopword filtering, and any other query transformations applied. Sourced from the debug envelope in the API response.

##### 2. API request

The exact HTTP request sent from the frontend to the backend search API: method, URL, query parameters, and request body (if any).

##### 3. API response

The full HTTP response from the backend search API: status code, response headers, and response body. The body includes the debug envelope alongside the normal result payload.

##### 4. Meilisearch request

The exact HTTP request sent from the backend to Meilisearch: method, URL, and request body as captured by the backend. Sourced from the debug envelope in the API response.

##### 5. Meilisearch response

The full HTTP response body received from Meilisearch by the backend. Sourced from the debug envelope in the API response.

#### Backend Requirements

When `debug=true` (or `debug=1`) is present as a query parameter on the search endpoint:
- Include `_rankingScore` and `_rankingScoreDetails` in each Meilisearch search hit
- Include the full document fields in each Meilisearch search hit (no field masking)
- Include a debug envelope in the API response containing: the processed/expanded query string, the Meilisearch request (method + URL + body), and the full Meilisearch response body

New lazy-fetch endpoints (no authentication required):
- `GET /api/debug/processed/{id}` — returns the full PostgreSQL row from `speeches` or `qa_exchanges` for the given `id`; returns 404 if not found
- `GET /api/debug/raw/{id}` — returns the full PostgreSQL row from `raw_documents` corresponding to the record with the given `id`; returns 404 if no raw document is linked to this record

#### Acceptance Criteria

- Appending `?debug=1` to a search results URL activates debug mode; removing the parameter returns to normal mode
- In debug mode, every result card shows a "Debug" toggle; no debug toggle appears when debug mode is inactive
- The global search debug panel is visible above the result list in debug mode; it is not rendered when debug mode is inactive
- Scoring details and Document in index sections render without additional network requests (data is in the initial search response)
- Processed record section triggers exactly one `GET /api/debug/processed/{id}` request on first expand; subsequent expands of the same section produce no additional requests
- Raw document section triggers exactly one `GET /api/debug/raw/{id}` request on first expand; subsequent expands produce no additional requests
- Processed record and Raw document sections are independent: expanding one does not fetch the other
- All 4 per-result sections and all 5 global sections are individually collapsible and expandable
- `GET /api/debug/processed/{id}` returns 404 for an unknown id; the UI shows an error message in that section rather than leaving it blank or crashing
- `GET /api/debug/raw/{id}` returns 404 if no raw document is linked; the UI shows an error message in that section
- No calls to `/api/debug/*` endpoints occur when debug mode is inactive

#### Edge Cases

- Result with no `_rankingScoreDetails` returned by Meilisearch (e.g., Meilisearch version does not support it): Scoring details section shows whatever score fields are present; section is not hidden
- Result whose raw document has been deleted from `raw_documents` after processing: `GET /api/debug/raw/{id}` returns 404; the Raw document section displays an appropriate message ("Raw document not available")
- Very large raw document (full HTML of a parliamentary session): the Raw document section renders the full content; no truncation; the user scrolls within the section

#### Dependencies

- Feature 01: `speeches`, `qa_exchanges`, and `raw_documents` tables; the link between a processed record and its raw document
- Feature 02: search endpoint must support the `debug` parameter and produce the debug envelope

#### NFR Implications

- **Security:** Debug mode exposes internal data (full database records, raw source documents, internal query details) via unauthenticated endpoints; see `04-non-functional-requirements.md` SEC-1
- **Performance:** PERF-1 and PERF-2 response time targets do not apply in debug mode; see PERF-3

#### Test Requirements

*(from Test Spec 10)*

**Activation Isolation**
- A page load without `?debug=1` must produce zero calls to `/api/debug/processed/*` or `/api/debug/raw/*` endpoints — not even prefetched or background calls
- A page load with `?debug=1` must not activate debug mode on other open tabs or sessions that do not have the parameter in their URL

**Lazy Fetch Caching**
- Expanding the Processed record section, collapsing it, and expanding it again must result in exactly one total call to `/api/debug/processed/{id}`, not two
- Expanding the Raw document section for result A and then expanding the Raw document section for result B must result in two separate calls (one per result id), not one shared call
- Expanding Processed record for a result must not trigger a call to `/api/debug/raw/{id}` for that result, and vice versa

**Normal Mode Regression**
- In normal mode (no `?debug=1`), the DOM must contain no debug toggle elements, no debug panel containers, and no global debug panel element — not merely hidden with CSS
- Meilisearch search requests made in normal mode must not include `_rankingScore` or `_rankingScoreDetails` in the attributes to retrieve — confirmed by inspecting the request body or the API response for the absence of these fields

**404 Handling in Debug Sections**
- When `GET /api/debug/processed/{id}` returns 404, the Processed record section must display an error message; the rest of the debug panel (Scoring details, Document in index, Raw document) must continue to function normally
- When `GET /api/debug/raw/{id}` returns 404, the Raw document section must display an error message; other sections must be unaffected

**Section Independence**
- Collapsing the global debug panel must not collapse any per-result debug panel, and vice versa
- Each of the five global sections must be independently togglable; expanding one must not collapse another
- Each of the four per-result sections must be independently togglable

---

## 4. Non-Functional Requirements

### Performance

**PERF-1: Search response time**
Search results must be returned within 2 seconds at p95, measured from query submission to full result list rendered in the browser, across the full indexed corpus. This target applies with query expansion active (synonyms + spell corrections). Architecture must account for the additional scoring computation introduced by query expansion.

**PERF-2: Detail page response time**
The detail page must complete full page load — including the record fetch and the adjacent-neighbour fetch — within 500ms at p95.

### Reliability

**INF-R1: Ingestion resumability**
The bulk ingestion pipeline must be resumable from a per-document checkpoint. An interrupted run re-run against the same corpus must produce an identical final record count with no duplicates. Safe re-runs are a hard requirement, not a best-effort goal.

### Security

**SEC-1: Debug mode data exposure**
Debug mode (`?debug=1`) exposes full database records (speeches, qa_exchanges, raw_documents rows), internal query details, and Meilisearch request/response payloads via unauthenticated endpoints (`GET /api/debug/processed/{id}` and `GET /api/debug/raw/{id}`). This is a deliberate choice for v1. Any deployment handling sensitive or access-controlled parliamentary data must review whether unauthenticated debug access is acceptable before enabling this feature in production.

### Storage

**INF-S1: Corpus storage sizing**
The full-text corpus (CA full record + LS and RS records across all indexed sources) is large. Storage architecture must be sized accordingly before build begins. Exact sizing is an architecture-stage deliverable.

### Rate Limiting and Compliance

**INF-RL1: Government website rate limiting**
The ingestion pipeline must comply with robots.txt on constitutionofindia.net, elibrary.sansad.in, and the Internet Archive. Minimum inter-request delay must be specified at architecture stage. HTTP 429 responses must trigger exponential backoff and retry, not a skip.

### Processing

**INF-P1: Bulk ingestion duration**
Bulk ingestion is a long-running operation. No maximum time constraint is specified for v1, but real-time progress logging is required. The operation must not require human supervision to complete.

### Scalability

**SCALE-1: Concurrent search load**
Search must remain within the PERF-1 response time target under concurrent user load. Exact concurrency targets are an architecture-stage deliverable.

### Debug Mode Performance

**PERF-3: Debug mode SLA exemption**
PERF-1 and PERF-2 response time targets do not apply when debug mode is active (`?debug=1`). Debug mode responses include large additional payloads — full Meilisearch documents, full database rows, and complete raw source documents — and are exempt from all response time SLAs.

### Privacy

**PRIV-1: No server-side storage of user search data**
Search queries, filter selections, and search history are not persisted server-side in v1. All search history (recent searches and saved searches) is stored client-side in browser cookies only. No user identifiers are created or stored.

---

## 5. Future Features

Features explicitly deferred from v1. Not in scope for any v1 build phase.

### Data Scope Expansion

- **Full parliamentary history:** extend LS coverage back to 1952 across all accessible sources; restore RS post-2018 coverage when an accessible source is identified; extend RS coverage to include all available historical records
- **Ongoing ingestion:** scheduled pipeline to ingest new parliamentary sessions automatically as they are published

### Language Support

- **Hindi search:** index Hindi-language text and support queries in Hindi (Devanagari); requires separate tokenisation, stop-word lists, and synonym dictionary

### User Accounts and Personalisation

- **User authentication:** sign-in with persistent cross-device search history and saved searches
- **Cross-device sync:** saved searches accessible from any device when signed in (replaces cookie-only storage)
- **Search alerts:** notify users (email or in-app) when new records matching a saved search are indexed

### Search Experience

- **Autocomplete / search-as-you-type:** show query suggestions and speaker name completions as the user types in the search box
- **Faceted result counts:** show the count of results per filter value (e.g., "Lok Sabha (1,234), Rajya Sabha (567)") in the filter panel
- **Related results / "More like this":** surface records thematically similar to a result the user is viewing
- **Member profile pages:** dedicated page per member showing all their indexed speeches and questions

### Platform

- **Mobile UI:** responsive layout optimised for small screens; the web application is currently desktop-only
- **Public API:** REST or GraphQL API exposing search and record retrieval for third-party integrations

### Administration

- **Admin interface for synonym dictionary:** in-application UI for adding and editing query expansion synonyms without requiring a code deployment
- **Ingestion monitoring dashboard:** real-time visibility into ingestion pipeline progress and error rates for operators

---

## Footer

Generated: 2026-06-09  
PRD version: 3.1  
Sections compiled from: /prd/sections/01-overview.md, 02-objectives.md, 03-functional-requirements/*, 04-non-functional-requirements.md, 05-future-features.md  
Features: F01–F10  
Previous version: 3.0  
