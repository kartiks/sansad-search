# Feature 01: Data Ingestion

## Description

The ingestion pipeline fetches, parses, segments, and indexes parliamentary records from three sources: Constituent Assembly debates, Lok Sabha records, and Rajya Sabha records. In v1 it is a one-time bulk operation. It must be resumable: an interrupted run continues from the last successful document checkpoint without reprocessing already-indexed records or creating duplicates.

The pipeline is implemented as a two-stage process. Stage 1 (fetch) downloads source documents and writes raw content to a `raw_documents` store. Stage 2 (process) reads from that store and produces indexed `speeches`/`qa_exchanges` records. The two stages can be run together or independently via the `--stage` flag.

## Two-Stage Pipeline

### Stage control

| `--stage` value | Behavior |
|-----------------|----------|
| `fetch` | Stage 1 only: discover and download source documents; write to `raw_documents` |
| `process` | Stage 2 only: read from `raw_documents`; parse, segment, and index |
| `all` | Stage 1 then Stage 2 sequentially for each source (default) |

### Stage 1 (fetch) flow

1. Discover documents for the selected corpus(es)
2. Check `raw_documents` PK for each `canonical_doc_id`; skip if already present
3. Fetch new documents from source with rate limiting
4. Extract text and metadata
5. Apply date-window gate when `--date-from`/`--date-to` are provided: write to `raw_documents` only if the document's date falls within the window; skip out-of-window documents
6. Write raw content (extracted text + metadata JSON) to `raw_documents`

Stage 1 does not write to `speeches`, `qa_exchanges`, or the SQLite checkpoint store. It does not update `index_status`.

### Stage 2 (process) flow

1. Read `raw_documents` rows for the selected corpus; apply `--date-from`/`--date-to` window if provided
2. Skip documents already checkpointed as processed in the SQLite `processed_documents` store
3. Segment each document into speech and Q+A exchange units
4. Apply adjacent speech merging to speech units (see Adjacent Speech Merging section)
5. Canonicalize speaker names and session names
6. Index each unit into `speeches`/`qa_exchanges`
7. Checkpoint the document in `processed_documents` after all its records are successfully indexed

`index_status` is updated only at the end of Stage 2, not at the end of Stage 1.

### Date filtering

`--date-from YYYY-MM-DD` and `--date-to YYYY-MM-DD` scope both stages:

- **Stage 1:** only documents whose parsed date falls within the window are written to `raw_documents`; out-of-window documents are skipped after parsing
- **Stage 2:** only `raw_documents` rows with dates within the window are read and processed

When neither flag is provided, both stages operate on the full corpus without date restriction.

## User Flows

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

## Data Sources and Scope

| Source | Content | Date scope | Format | Base URL |
|--------|---------|------------|--------|----------|
| Constituent Assembly | Plenary debates | All 12 volumes, 1946–1950 | HTML | constitutionofindia.net |
| Lok Sabha | Debates and questions | 1947-08-15 to present | Pre-OCR plain text (_djvu.txt); Tika-extracted PDF text | Internet Archive _djvu.txt pre-OCR text; elibrary.sansad.in DSpace 7 Text of Debates English (2019-01-01 to present) |
| Rajya Sabha | Debates and questions | 1947-08-15 to present | Pre-OCR plain text (_djvu.txt) | Internet Archive (see RS coverage note below) |

**RS coverage note:** The Rajya Sabha provider chain currently contains Internet Archive only. `sansad.in/rs` was removed because it is JavaScript-rendered and not crawlable; `rsdebate.nic.in` was removed because it is unresponsive. RS coverage therefore reflects what Internet Archive holds, which does not currently extend to post-2018 records. The provider chain is designed to be extended — adding a new RS provider restores coverage for the periods it serves without requiring changes to this spec.

## Proceeding Types Indexed

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

## Indexed Record Fields

### Speech unit

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

### Q+A exchange unit (starred question)

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

### Q+A exchange unit (unstarred question)

Same fields as starred question except:
- `proceeding_type`: unstarred_question
- `full_text_en`: question text and written answer only (no supplementaries)
- No `questioner_names` array needed; single `questioner_name` field

The `source_url`, `minister_name`, and `lok_sabha_number` rules above apply equally to unstarred questions.

## Language Handling

Official parliamentary records include English translations of speeches delivered in Hindi. The pipeline applies the following rules in order:

1. **Speech in English:** store verbatim in `full_text_en`; `is_translated: false`
2. **Speech in Hindi with official English translation present:** store the translation in `full_text_en`; `is_translated: true`
3. **Bilingual speech (switches between Hindi and English):** store all English text — both original English portions and translated Hindi portions — in `full_text_en`; `is_translated: true`
4. **Hindi speech with no translation available:** `full_text_en: null`; `has_untranslated_content: true`; record is still indexed (metadata remains searchable)

Translations in official records are typically marked inline as "[Translation]" or equivalent notation.

## Adjacent Speech Merging

During Stage 2 processing, consecutive speeches by the same speaker within the same sitting are merged into a single `speeches` record. This applies to speech units only; Q+A exchange units are never merged.

### Merge conditions

All of the following must be true for two consecutive speeches to be candidates for merging:
- Same `speaker_name`
- Same sitting (same `source` + `date` + `sitting_number`)
- Same `proceeding_type`
- Consecutive in document order with no break signal between them

### Break signals

Any of the following appearing in the source document between two speeches by the same speaker prevents merging:
- A speech or interjection by a different speaker
- A section heading (H1, H2, H3 tag or equivalent structural heading element in the parsed HTML)
- A procedural entry: a new question number heading, a block header (e.g., "QUESTIONS", "STARRED QUESTIONS", "STARRED QUESTION NO. X"), or a formal procedural marker (e.g., "The House adjourned for lunch", "The House then adjourned")

### Merged record structure

- The merged record stores individual speech texts as an ordered JSONB array in the `segments` field; each element: `{"text": "...", "segment_index": N}` where N is 0-based
- `full_text_en` = all segment texts joined with `\n\n` (double newline)
- `word_count` = total word count of the combined `full_text_en`
- `sequence_within_sitting` = document-order position of the first segment in the merge group
- An unmerged speech has a single-element `segments` array

## CA Field-Level Parsing Rules

These rules apply to Constituent Assembly records only.

### Date field

The URL slug is the authoritative date source for CA records. URL format: `DD-MMM-YYYY` (e.g. `09-dec-1946`). The parser must parse this slug directly and set `date` to ISO format `YYYY-MM-DD`. HTML-based date extraction (title, h1, metadata divs) must be skipped entirely for CA records — even when `parse_html` returns a date value, it must be discarded. The current ca.py uses the URL as a fallback only when `parse_html` returns `date=None`; this rule supersedes that: for CA, the URL date is always applied.

### Subject field

Each CA speech record's `subject` must be set to the nearest preceding standalone bold section header in the sitting page body.

**Section header definition:** A standalone bold topic label (e.g. "Government of India (Amendment) Bill", "New Article 67-A") appearing between speech entries in the debate body. Speaker names also appear bold or strong in source HTML, but inside speech grid rows — these must not be treated as section headers.

**Assignment rule:** Walk the parsed DOM in document order. When a standalone bold section header is encountered, set it as the current topic. Assign that topic to all subsequent speech records until the next section header is encountered.

**Fallback:** If no section header precedes the first speech of the sitting, the subject for those speeches falls back to the first item in the page's table of contents. The TOC is a `<ul>` above the debate body containing `<li><a href="#ID">Topic</a></li>` items. The implementation must verify at build time whether those anchor IDs correspond to `id=` attributes on body elements and use that mapping if available.

## Records Not Indexed as Standalone Units

The following are not indexed as standalone searchable records:
- Unattributed speech: "SEVERAL HON. MEMBERS", "AN HON. MEMBER", "SOME HON. MEMBERS", and similar
- Presiding officer interventions: speeches by the Speaker (Lok Sabha) or Chairman/Vice-Chairman (Rajya Sabha) made in their presiding capacity
- Procedural interruptions: points of order, rulings, and division votes

These may appear as part of the `full_text_en` of a surrounding Q+A exchange unit (e.g., presiding officer directing the house during a starred question) but are not separately indexed.

## Canonicalization

### Speaker names

Speaker names in source records appear in multiple variants across sittings and sessions (honorific prefixes, abbreviated forms, ordering variants, transliteration differences). All speaker names must be canonicalized to a consistent form at ingestion time.

Canonicalization rules:
- Strip honorific prefixes: Shri, Smt., Dr., Prof., Adv., Kumari, and any other titles present in the source records
- Resolve abbreviation variants and ordering variants (e.g., "Modi, Narendra" → "Narendra Modi") using a canonical names dictionary
- The canonical names dictionary maps known name variants to a single canonical full name; it must be seeded from official Lok Sabha and Rajya Sabha member lists and the CA member list
- If a speaker name is not found in the canonical names dictionary, store the raw name as found in the source record and set `speaker_name_unresolved: true`
- Unresolved names are indexed and searchable; they are flagged for manual dictionary updates

### Session names

Session names in source records may appear in inconsistent formats across sources (e.g., "Budget Session, 2023" vs "Budget Session 2023" vs "Budget Session (Second Part) 2023"). Canonicalize to a consistent format: "[Session Type] Session [Year]" with multi-part sessions appended as "(Part [N])" where applicable. Example canonical forms: "Budget Session 2023", "Monsoon Session 2022", "Budget Session 2023 (Part 2)".

CA records have no session name; `session_name` is null for all CA records.

## Deduplication

When the same proceeding is available as both HTML and PDF from the source site, the HTML version is preferred. Only one record is created per unique speech or Q+A exchange. Duplicate detection key: source + date + sitting_number + proceeding_type + speaker_name + sequence_within_sitting (or question_number for Q+A units). For merged speech records, `sequence_within_sitting` in the dedup key is the position of the first segment in the merge group. The sequence_within_sitting field is required because a member may speak multiple times in the same sitting on the same agenda item with intervening speakers.

## Acceptance Criteria

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

## Edge Cases

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

## Dependencies

None. This is the foundational feature.

## NFR Implications

- **Rate limiting:** ingestion must comply with robots.txt on sansad.in and rajyasabha.gov.in; minimum inter-request delay to be specified at architecture stage → flag in NFR
- **Storage:** full-text corpus of 12+ years of parliamentary proceedings is substantial → flag in NFR for architecture sizing
- **Processing time:** bulk ingestion is a long-running operation expected to take hours; exact time budget not specified for v1 but progress logging is required → flag in NFR
- **Resumability:** ingestion must checkpoint per source document and support safe re-runs → flag in NFR as a reliability requirement
