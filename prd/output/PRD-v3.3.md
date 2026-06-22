# SansadSearch — Product Requirements Document

**Version:** 3.3  
**Date:** 2026-06-22  
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
- LS data scope: 1947-08-15 to present (elibrary.sansad.in provides 2019+ coverage; Internet Archive provides earlier records); RS data scope: 1947-08-15 to present, post-2018 records currently unavailable pending an accessible source

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

Stage 1 does not write to `speeches`, `qa_exchanges`, or the checkpoint store. It does not update `index_status`.

##### Stage 2 (process) flow

1. Read `raw_documents` rows for the selected corpus; apply `--date-from`/`--date-to` window if provided
2. Skip documents already checkpointed as processed in the checkpoint store (`processed_documents`)
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

- **Rate limiting:** ingestion must comply with robots.txt on sansad.in and rajyasabha.gov.in; minimum inter-request delay to be specified at architecture stage → flag in NFR
- **Storage:** full-text corpus of 12+ years of parliamentary proceedings is substantial → flag in NFR for architecture sizing
- **Processing time:** bulk ingestion is a long-running operation expected to take hours; exact time budget not specified for v1 but progress logging is required → flag in NFR
- **Resumability:** ingestion must checkpoint per source document and support safe re-runs → flag in NFR as a reliability requirement

#### Test Spec F01

Supplements the feature spec. Does not repeat acceptance criteria or edge cases already stated there.

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

#### Snippet Size Parameter

The search API accepts an optional `snippet_size` parameter (integer, words) that sets the target length of result snippets (snippet rendering is defined in Feature 05).

- Omitted, non-integer, or non-numeric value → operator-configurable default (default 100 words); no error surfaced; search executes
- Accepted range: 20–1000 words
- Out-of-range numeric value clamped to nearest bound (below 20 → 20; above 1000 → 1000); no error surfaced; search executes
- The default is operator-configurable as a deployment setting (see NFR PERF-4)
- The web UI exposes no control for this parameter; it relies on the default. The parameter exists for programmatic API consumers.
- Exact API field name and wire format are an architecture-stage decision; `snippet_size` is the conceptual name.

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
- A search with no `snippet_size` returns snippets at the configured default size (default 100 words)
- A search with `snippet_size=300` returns snippets targeting 300 words
- A search with `snippet_size=5` is clamped to 20; a search with `snippet_size=5000` is clamped to 1000
- A search with a non-integer or non-numeric `snippet_size` falls back to the default and still returns results

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
- **Snippet size payload:** the `snippet_size` parameter increases response payload at larger values; a maximum bound is required so the response time target still holds at the largest permitted size → see NFR PERF-4

#### Test Spec F02

Supplements the feature spec. Does not repeat acceptance criteria or edge cases already stated there.

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

**Snippet Size Clamp Boundaries**
- `snippet_size=20` and `snippet_size=1000` must be accepted as-is (the bounds are inclusive; neither is clamped)
- `snippet_size=19` must clamp to 20; `snippet_size=1001` must clamp to 1000
- `snippet_size=0` and a negative `snippet_size` must clamp to 20 — they must NOT be treated as invalid and fall back to the default
- A non-integer numeric value such as `snippet_size=100.5` must fall back to the default (100); it must not be truncated or rounded to an integer
- A present-but-empty `snippet_size` value must fall back to the default

---

### F03: Search Filters

#### Description

Filters allow users to narrow search results by legislative body, date range, speaker, session, and proceeding type. All filters are combinable with each other and with the search query. Filter state persists across query refinements on the results page and is only reset by an explicit clear action.

#### User Flows

**Applying filters:**
1. User is on the results page with an active search query
2. User selects one or more filter values (body, date range, speaker, session, proceeding type)
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

**1. Legislative body**
- Multi-select: CA, Lok Sabha, Rajya Sabha
- Default: all three selected (no body restriction)
- Any combination of one, two, or all three is valid

**2. Date range**
- Two inputs: From date and To date
- Both are optional; leaving one or both empty applies no date bound on that side
- Date range is constrained to the indexed scope:
  - When only CA is selected in the body filter: picker restricts to 1946-01-01 – 1950-12-31
  - When only LS and/or RS is selected: minimum selectable date is 1947-08-15
  - When CA and LS/RS are both selected: full range 1946-01-01 to present is selectable; records from each body are included within their respective indexed scope
- From date must not be later than To date; if it is, an inline validation message is shown and the filter is not applied

**3. Speaker**
- Free text input; case-insensitive substring match against the canonical `speaker_name` field
- Matches speaker names containing the entered string anywhere in the name
- Empty field: no speaker filter applied
- Note: speaker names in the index are canonicalized (honorifics stripped, variants resolved); users searching "Dr. Ambedkar" should enter "Ambedkar" for reliable results; a note to this effect is shown near the field
- No autocomplete in v1

**4. Session**
- Free text input; case-insensitive substring match against `session_name`
- Matches sessions whose name contains the entered string (e.g., "Budget" matches "Budget Session 2023")
- Empty field: no session filter applied
- CA records have null `session_name` and will not match any session filter query; when a session filter is active, CA records are excluded from results
- No autocomplete in v1

**5. Subject**
- Free text input; case-insensitive substring match against the `subject` field
- Matches records whose subject contains the entered string anywhere
- Empty field: no subject filter applied
- No autocomplete in v1

**6. Proceeding type**
- Multi-select: Debate, Starred Question, Unstarred Question, Zero Hour, Short Notice Question, Calling Attention, Short Duration Discussion, Adjournment Motion, Private Member Bill
- Default: all types selected (no type restriction)
- Available options are constrained by the legislative body selection:
  - When only CA is selected: only "Debate" is available; all other options are disabled
  - When LS and/or RS is selected (alone or with CA): all options are available
- A user selecting types that do not exist for a selected body will simply receive no results from that body for those types; no error is shown

#### Filter Combination Logic

All active filters are ANDed together and ANDed with the search query. A record must satisfy all active filter constraints to appear in results.

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

- Feature 01: canonical `speaker_name` and `session_name` fields in the index
- Feature 02: search query execution that accepts filter constraints

#### NFR Implications

None beyond what is already captured for Feature 02 (search response time target applies to filtered queries as well).

#### Test Spec F03

Supplements the feature spec. Does not repeat acceptance criteria or edge cases already stated there.

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

**Filter Persistence Across Query Refinements**
- After applying a Rajya Sabha body filter and refining the search query, the result set must contain only RS records; the body filter must not silently reset to "all bodies"
- The active filter indicator on the results page must still show the RS filter as active after query refinement

**Zero-Selection Validation**
- Deselecting all bodies and submitting must show a validation message and not execute a search; the previous result set must remain visible
- Deselecting all proceeding types and submitting must show a validation message and not execute a search; the previous result set must remain visible

**Date Validation Ordering**
- Setting From = 2022-06-01 and To = 2021-01-01 (From after To) must show an inline validation error and must not modify the displayed result set

**Subject Filter Substring Matching**
- A subject filter value that is a substring of a longer subject (e.g., "Water" matching a record with subject "Water Resources Management") must produce a match; an exact-only match implementation is a bug
- A subject filter value containing only whitespace must be treated as an empty filter; the result set must be identical to the unfiltered result set

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

The dictionary covers parliamentary domain synonyms (bidirectional). See the section file for the full dictionary listing.

#### Spell Correction

Edit-distance based correction; phonetic matching for proper nouns. Corrected terms added as OR alternatives at lower weight than synonyms. Terms shorter than 4 characters are exempt from spell correction.

#### Acceptance Criteria

- A query for "PM" returns records containing "Prime Minister" at a lower relevance weight than records containing "PM"
- A query for "fundamental rights" returns records containing "basic rights" at a lower relevance weight than records containing "fundamental rights"
- A query for "Parliment" (misspelled) returns records containing "Parliament" at a reduced weight
- A quoted phrase query ("fundamental rights") applies phrase-level synonyms only; individual term synonyms are not applied to terms inside the quotes
- A query string containing U+201C or U+201D curly quotes around a phrase is treated as a phrase query equivalent to the same phrase enclosed in ASCII straight double quotes
- Terms shorter than 4 characters are not spell-corrected
- Synonyms and spell corrections apply to LS, RS, and CA records equally
- The synonym dictionary file is the only source of synonym definitions; no synonyms are hardcoded elsewhere in the application

#### Dependencies

- Feature 02: the search execution model that consumes expansion output and applies relevance weights

#### Test Spec F04

**Curly Quote Normalization**
- A query string containing U+201C (") and U+201D (") around a phrase must result in those characters being converted to ASCII straight double quotes before the query is transmitted to Meilisearch; U+201C and U+201D must not appear in the query string sent to the search engine

**Bidirectionality**
- A query for "House of the People" must expand to include "Lok Sabha" at synonym weight; a query for "Lok Sabha" must expand to include "House of the People" at synonym weight
- Bidirectionality must hold for all synonym pairs in the dictionary

**Phrase Synonym Isolation**
- A query for "fundamental rights" (unquoted multi-term) must expand using the phrase synonym "basic rights"; it must NOT additionally expand "fundamental" as a standalone term or "rights" as a standalone term
- A query for "rights" alone must not expand to "fundamental rights" via the phrase synonym

**Spell Correction Suppression in Phrases**
- A quoted phrase query containing a misspelled term must not apply spell correction; the phrase must be searched verbatim

**Short Term Exemption**
- A query term of 1, 2, or 3 characters must not trigger spell correction
- A query term of exactly 4 characters must be eligible for spell correction

**Correction Weight Below Synonym Weight**
- For a query where both a synonym expansion and a spell correction match the same record, the synonym match contribution must be higher than the spell correction match contribution

**Ambiguous Abbreviation Expansion**
- A query for "SC" must generate expansions for both "Scheduled Castes" and any other known expansions; all expansions must appear in results at reduced weight

**Dictionary as Sole Source**
- Introducing a synonym relationship only hardcoded in application logic (not in the dictionary file) must cause a test to fail

**Substring Non-Expansion**
- A query term "MGNREGA" must not trigger the "PM" → "Prime Minister" synonym expansion because "PM" appears as a substring; expansion must only apply to exact full-term matches

---

### F05: Result Display

#### Description

Each search result is displayed as a card showing the record's metadata, a contextual text snippet with matched terms highlighted, and a link to the original source document. Results are displayed in a paginated list.

#### Result Card: Speech Record

| Field | Source | Notes |
|-------|--------|-------|
| Speaker name | `speaker_name` | Canonical form |
| Party / group | `speaker_party` | Shown if available |
| Constituency or state | `speaker_constituency_or_state` | Shown if available; omitted for CA records |
| Legislative body | `source` | "Constituent Assembly", "Lok Sabha", or "Rajya Sabha" |
| Proceeding type | `proceeding_type` | Human-readable label |
| Date | `date` | DD Month YYYY |
| Time of day | `time_of_day` | HH:MM near date; omitted when null |
| Session | `session_name` | Shown if available; omitted for CA records |
| Subject / agenda item | `subject` | |
| Text snippet | derived from `full_text_en` | Sized to the effective snippet size (default 100 words); query terms highlighted |
| Language badge | `lang_original` | `hi`→"Hindi original"; `mixed`→"Mixed language"; `en`→no badge |
| Source link | `source_url` | "View source" link; new tab |

#### Result Card: Q+A Exchange Record

| Field | Source | Notes |
|-------|--------|-------|
| Question number | `question_number` | "Q. [number]" |
| Subject | `subject` | |
| Proceeding type | `proceeding_type` | |
| Legislative body | `source` | |
| Date | `date` | DD Month YYYY |
| Time of day | `time_of_day` | HH:MM; omitted when null |
| Session | `session_name` | |
| Questioner | `questioner_names` (primary) | "+N others" if co-signatories present |
| Questioner party | `questioner_party` | |
| Minister and ministry | `minister_name`, `ministry` | "Answered by [Minister Name], [Ministry]" |
| Text snippet | derived from `full_text_en` | Sized to the effective snippet size (default 100 words); query terms highlighted |
| Language badge | `lang_original` | |
| Source link | `source_url` | "View source" link; new tab |

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

- Passage from the highest-density match region, targeting the **effective snippet size** — the per-request `snippet_size` from Feature 02 if supplied (clamped to 20–1000 words), else the operator-configurable default (default 100 words); the search engine's crop length is driven by the effective snippet size; query terms highlighted
- Full text shown (no padding) when `full_text_en` has fewer words than the effective snippet size
- Snippet may be shorter than the effective snippet size when the matched passage is near the start or end of `full_text_en`
- Null `full_text_en`: "This speech was delivered in Hindi. No English text is available."
- Q+A supplementary match: "From supplementary exchange" label shown

#### Pagination

- 20 results per page; exact count to 9,999; "10,000+" above that
- URL reflects current page number

#### Acceptance Criteria

- Every result card: body, proceeding type, date, subject, snippet with highlighted terms, working source link
- Records with `full_text_en: null` show untranslated-speech message
- Language badges per `lang_original`; `en` = no badge
- Result count at top; paginated URLs load correct pages
- `speaker_name_unresolved: true` records display raw name

#### Test Spec F05

**Snippet from Supplementary Exchange**
- When the highest-relevance match for a starred Q+A is in a supplementary exchange, the snippet must be drawn from it and the "From supplementary exchange" label must be present

**Result Count Threshold**
- 9,999 results → exact count; 10,000 results → "10,000+"; 0 results → "0 results" (with no-results message also present)

**Untranslated Speech Snippet Placeholder**
- `full_text_en: null` → defined message in snippet area; not empty or absent; all other metadata still renders

**HTML Sanitisation in Snippet**
- `full_text_en` containing HTML tags must render as plain text; script tags must not execute

**Page URL Persistence**
- Page 3 URL in a new session must load page 3 of that query; URL must encode query and page number

**Co-Signatory Display**
- 1 questioner → no "+N others"; 3 co-signatories → "+3 others"

**Language Badge**
- `hi` → "Hindi original" badge (no other badge); `mixed` → "Mixed language"; `en` → badge element absent from DOM

**Time of Day Display**
- `time_of_day: "14:35"` → "14:35" near date; not reformatted; `time_of_day: null` → no element rendered

**Snippet Size**
- No `snippet_size` supplied → default-sized snippet of 100 words (not the legacy 200)
- `full_text_en` longer than the effective snippet size → snippet cropped to approximately that size (unless passage is near start/end); shorter than the effective snippet size → full text shown, no words omitted, no padding

---

### F06: Sorting

#### Description

Three sort modes: Relevance (default), Chronological, Reverse chronological. Sort state persists across query refinements.

#### Sort Options

| Option | Order |
|--------|-------|
| Relevance (default) | Descending relevance score |
| Chronological | Ascending date; secondary: `sequence_within_sitting` ascending |
| Reverse chronological | Descending date; secondary: `sequence_within_sitting` descending |

#### Acceptance Criteria

- Three sort options on results page; default is Relevance
- Changing sort re-orders without changing count or clearing filters
- Sort persists across query refinements
- Date sorts use `sequence_within_sitting` as secondary key

#### Test Spec F06

**Secondary Sort Key**
- Two records with the same date must be ordered by `sequence_within_sitting` ascending in chronological mode, descending in reverse-chronological

**Relevance Sort Isolation**
- Switching to relevance sort must not preserve date-based order as a tiebreaker

**Sort Persistence Across Refinement**
- After setting Chronological and refining query, sort control shows Chronological and results are in that order

**Result Count Invariance**
- Changing sort must not change the result count

**Default Sort on New Search**
- Every new search must default to Relevance regardless of prior sort state

---

### F07: Indexing Status Panel

#### Description

Read-only panel showing per-source record counts, date coverage, and last ingestion timestamp.

#### Displayed Information

| Item | Description |
|------|-------------|
| Total records indexed | All sources combined |
| Per-source record count | CA, Lok Sabha, Rajya Sabha |
| Per-source date coverage | Earliest and latest indexed date per source |
| Last ingestion run | Most recent run completion timestamp |

#### Display Surfaces

**Homepage Status Strip:** condensed per-source counts and last updated date below the search box.

**Full Indexing Status Panel:** detailed view with date coverage; accessible via footer "Index status" link.

#### Acceptance Criteria

- Homepage strip: per-source counts and last updated date; zero-record sources shown as "0 [Body] records"
- Full panel: total, per-source counts, date coverage, last updated; zero-record sources show "0 records – not yet indexed"
- Counts reflect actual index state; not hardcoded

#### Test Spec F07

**Pre-computed Summary — Not Live Query**
- Panel must not query the search index at page load; disabling the search index must not break the status display

**Never-Run State**
- Fresh deployment "Last updated" must display "Never"

**Zero-Source Row Format**
- Full panel: zero-record source → "0 records – not yet indexed" (no date range, no placeholder date)
- Strip: zero-record source → "0 [Body] records" (not omitted)

**Count Accuracy**
- Total displayed must equal sum of three per-source counts

**Ingestion Timestamp**
- "Last updated" must not change on page load, search run, or any event other than ingestion pipeline completion

---

### F08: Search History

#### Description

Cookie-based recent searches (10 entries, 30-day expiry) and saved searches (20 entries, persistent). No server-side storage.

#### Recent Searches

- Auto-recorded on every search submission; max 10; duplicate query updates timestamp only
- Re-run executes with default filters

#### Saved Searches

- Explicit user action from results page; max 20; persistent cookie
- Stores: name (default = query, editable to 60 chars), query text, active filter state (including subject), save timestamp
- Re-run restores stored query + filter state with default sort

#### Acceptance Criteria

- Every submitted query added to recent searches
- Duplicate query → single entry with latest timestamp
- Saved searches restore query and filter state exactly
- Save disabled (with message) at 20-entry limit
- All history features work without authentication; no server-side storage

#### Test Spec F08

**Duplicate Query Deduplication**
- Same query submitted 3 times → exactly 1 entry with third-submission timestamp

**FIFO Rotation at Limit**
- 10 entries + 11th distinct query → oldest removed; list stays at 10

**Recent Search Re-runs with Default Filters**
- Re-running a recent search ignores any filters that were active at original submission

**Saved Search Filter Restoration**
- Saved search with body = RS, proceeding type = Starred, date from = 2020-01-01 → restores those exact filter selections on re-run

**Save Disabled at Limit**
- 20 saved searches → save action visibly disabled; no 21st entry can be created by any means

**Same Query Saved Twice**
- Two saves of same query → two separate entries; second does not overwrite first

**Cookie-Disabled Behaviour**
- Cookies blocked → recent and saved searches not shown; no error message; search functions normally

**Saved Search Name Length**
- 60-char name accepted; 61-char name rejected without losing the save action

**Stale Filter Value in Saved Search**
- Unrecognised proceeding type in saved search → search executes ignoring that value; no error

---

### F09: Detail Page

#### Description

Full-record detail page at `/record/:id` with complete text, all metadata, and inline adjacent sitting navigation.

#### Route and API

- **Frontend route:** `/record/:id`
- **API:** `GET /api/record/{id}` — 404 if not found; `GET /api/record/{id}/adjacent` — batch of adjacent records from the same sitting

#### User Flows

- Arriving from results: full text + metadata + adjacent controls + "Back to results" link
- Direct access: same but shows "Search" link (homepage) instead of "Back to results"
- Adjacent loading: "Load 5 previous" prepends; "Load 5 next" appends; URL stays at focal record's `/record/:id`

#### Full Text Display

- `full_text_en` rendered as paragraphs; null → "This record was delivered in Hindi. No English text is available."

#### Metadata Fields

All non-null fields shown; null fields omitted silently (no placeholder).

#### Adjacent Speech Loading

- "Load 5 previous" / "Load 5 next" load up to 5 records from same sitting (same `source` + `date` + `sitting_number`) in the respective direction
- Controls are disabled (not hidden) at sitting boundaries
- After each load, control re-evaluates enabled/disabled state based on remaining records
- Loaded records display: speaker (or questioner/minister), date, subject, proceeding type, full text

#### Acceptance Criteria

- Valid id loads correct record; unknown id → 404 page
- Full `full_text_en` as paragraphs; null → defined message
- All non-null metadata shown; null fields omitted
- Load controls work as specified; URL stays at focal record
- Back nav: "Back to results" from in-app; "Search" link from direct access

#### Test Spec F09

**Lok Sabha Term Display**
- `lok_sabha_number: 17` → "17th Lok Sabha"; 21 → "21st"; 22 → "22nd"; 23 → "23rd"
- RS record → no "Lok Sabha" text in metadata DOM

**Inline Adjacent Loading**
- "Load 5 next" → no page navigation; URL unchanged
- After loading 5 with 3 remaining: control enabled; after loading those 3: control disabled
- "Load 5 previous" prepends above focal record; focal record remains in DOM

**Back Navigation Detection**
- In-app navigation → "Back to results"; direct URL paste → "Search" (no "Back to results")

**Null Full Text Area**
- `full_text_en: null` → defined message in text area; not empty/absent; other metadata still renders

**page_reference Formatting**
- `page_reference: 42` → "PDF page 42"; null → no page reference element

**sequence_within_sitting Display**
- "[N] of [M]" where M is actual count from same source + date + sitting_number; not hardcoded

**404 Handling**
- `/record/nonexistent-id` → "Record not found" page; not blank or JS error

---

### F10: Debug Mode

#### Description

Developer diagnostic mode activated via `?debug=1`. Per-result 4-section panel and global 5-section search trace with lazy DB fetches.

#### Activation

`?debug=1` on any search results URL. Applies for that page view only.

#### Per-Result Debug Panel

Four collapsible sections (all collapsed by default):
1. **Scoring details** — `_rankingScore`, `_rankingScoreDetails` from search response
2. **Document in index** — full Meilisearch document from search response
3. **Processed record** — lazy fetch from `GET /api/debug/processed/{id}`
4. **Raw document** — lazy fetch from `GET /api/debug/raw/{id}`

#### Global Search Debug Panel

Five collapsible sections:
1. Processed query
2. API request
3. API response
4. Meilisearch request
5. Meilisearch response

#### Backend Requirements

When `debug=1` on search endpoint: include `_rankingScore`, `_rankingScoreDetails`, full document fields, and debug envelope in API response.

New endpoints (no auth):
- `GET /api/debug/processed/{id}` — full row from `speeches`/`qa_exchanges`; 404 if not found
- `GET /api/debug/raw/{id}` — full row from `raw_documents` linked to this record; 404 if not found

#### Acceptance Criteria

- `?debug=1` activates debug mode; removal deactivates
- Every result card shows "Debug" toggle in debug mode; no toggle in normal mode
- Global debug panel rendered only in debug mode
- Scoring/Document sections use initial search response data (no additional requests)
- Processed record: exactly one fetch on first expand; no re-fetch on subsequent expands
- Raw document: same lazy-fetch behaviour; independent of Processed record
- 404 from debug endpoints → error message in that section; other sections unaffected
- No `/api/debug/*` calls in normal mode

#### Test Spec F10

**Activation Isolation**
- Page without `?debug=1` → zero `/api/debug/*` calls; debug on one tab does not affect others

**Lazy Fetch Caching**
- Expand → collapse → expand Processed record → exactly 1 call, not 2
- Raw document for result A and result B → 2 separate calls (one per id)
- Expanding Processed must not trigger Raw fetch, and vice versa

**Normal Mode Regression**
- No debug toggle elements in DOM in normal mode (not just hidden)
- Meilisearch requests in normal mode must not include `_rankingScore`/`_rankingScoreDetails`

**404 Handling in Debug Sections**
- Processed 404 → error in that section; Scoring, Document in index, Raw unaffected
- Raw 404 → error in that section; other sections unaffected

**Section Independence**
- Collapsing global panel does not collapse per-result panels; each section independently togglable

---

## 4. Non-Functional Requirements

**PERF-1: Search response time**
Search results within 2 seconds at p95, full corpus with query expansion active.

**PERF-2: Detail page response time**
Full page load (record fetch + adjacent-neighbour fetch) within 500ms at p95.

**PERF-3: Debug mode SLA exemption**
PERF-1 and PERF-2 do not apply when `?debug=1` is active.

**PERF-4: Snippet size bound**
The search API `snippet_size` parameter is bounded to 20–1000 words; out-of-range numeric values are clamped to the nearest bound; missing/non-integer/non-numeric values fall back to the default. Default is 100 words and is operator-configurable as a deployment setting. The maximum bound exists so PERF-1 (≤2s p95) holds at `snippet_size=1000` across the full corpus.

**INF-R1: Ingestion resumability**
Resumable from per-document checkpoint; re-run produces identical final record count with no duplicates.

**SEC-1: Debug mode data exposure**
Debug mode exposes full database records and Meilisearch internals via unauthenticated endpoints. Deliberate for v1. Review required before production use with sensitive data.

**INF-S1: Corpus storage sizing**
Storage architecture must be sized for full corpus before build begins.

**INF-RL1: Government website rate limiting**
Comply with robots.txt on constitutionofindia.net, elibrary.sansad.in, and the Internet Archive. HTTP 429 → exponential backoff and retry.

**INF-P1: Bulk ingestion duration**
No max time constraint; real-time progress logging required; must run unattended.

**SCALE-1: Concurrent search load**
Search must meet PERF-1 under concurrent load; concurrency targets are architecture-stage deliverable.

**PRIV-1: No server-side storage of user search data**
All history is cookie-only client-side; no server-side persistence of queries or history.

---

## 5. Future Features

Features explicitly deferred from v1.

- **Full parliamentary history:** extend LS coverage back to 1952; restore RS post-2018 coverage when accessible source identified
- **Ongoing ingestion:** scheduled pipeline for new parliamentary sessions
- **Hindi search:** index Hindi-language text and support Devanagari queries
- **User authentication and cross-device sync**
- **Autocomplete / search-as-you-type**
- **Faceted result counts**
- **Related results / "More like this"**
- **Member profile pages**
- **Mobile UI**
- **Public API**
- **Admin interface for synonym dictionary**
- **Ingestion monitoring dashboard**

---

*Generated: 2026-06-22 | PRD v3.3 | Changes from v3.2: F02 — added Snippet Size Parameter (`snippet_size`, 20–1000 words, clamped, default 100, operator-configurable); F05 — snippet generalized from fixed ≥200-word minimum to effective snippet size (default 100); NFR — added PERF-4 (snippet size bound)*
