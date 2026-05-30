# Feature 01: Data Ingestion

## Description

The ingestion pipeline fetches, parses, segments, and indexes parliamentary records from three sources: Constituent Assembly debates, Lok Sabha records, and Rajya Sabha records. In v1 it is a one-time bulk operation. It must be resumable: an interrupted run continues from the last successful document checkpoint without reprocessing already-indexed records or creating duplicates.

## User Flows

**Initial bulk ingestion:**
1. Operator runs ingestion with a source selector (CA | LS | RS | all) and optional date override
2. System enumerates all records in scope for the specified source(s) — building a list of documents/pages to fetch
3. System fetches each document with rate limiting and robots.txt compliance
4. System parses fetched content (HTML or PDF) to extract text and metadata
5. System segments content into speech units and Q+A exchange units
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
| Lok Sabha | Debates and questions | 2014-01-01 to present | Pre-OCR plain text (_djvu.txt); PDF | eparlib.sansad.in (primary); Internet Archive _djvu.txt pre-OCR text (fallback) |
| Rajya Sabha | Debates and questions | 2014-01-01 to present | HTML and PDF | sansad.in/rs HTML (primary); Internet Archive; rsdebate.nic.in DSpace (fallback) |

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
| `full_text_en` | Full English text of the speech; see Language Handling below |
| `is_translated` | true if `full_text_en` contains or includes official English translation of Hindi portions |
| `has_untranslated_content` | true if any portion of the speech could not be indexed due to absent translation |
| `speaker_name_unresolved` | true if `speaker_name` could not be matched to a canonical form in the names dictionary |
| `source_url` | URL of the original HTML page or PDF; for LS records fetched from Internet Archive, always set to the corresponding eparlib.sansad.in document URL; for RS records fetched from Internet Archive, always set to the corresponding rsdebate.nic.in document URL (derived from the DSpace handle) |
| `page_reference` | Page number in source PDF; null for HTML sources |
| `sequence_within_sitting` | Integer position of this speech within the sitting's proceedings, derived from document order (1-based) |
| `volume` | CA volume number (1–12); null for LS/RS |

### Q+A exchange unit (starred question)

| Field | Description |
|-------|-------------|
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
| `minister_name` | Minister answering |
| `ministry` | Ministry responsible |
| `full_text_en` | Full text of the complete exchange: main question + answer + all supplementaries with attribution; English only, translated as needed |
| `is_translated` | true if any portion was translated from Hindi |
| `has_untranslated_content` | true if any portion could not be indexed due to absent translation |
| `source_url` | URL of the original document; for LS records fetched from Internet Archive, always set to the corresponding eparlib.sansad.in document URL; for RS records fetched from Internet Archive, always set to the corresponding rsdebate.nic.in document URL (derived from the DSpace handle) |
| `page_reference` | Page number in source PDF; null for HTML sources |

### Q+A exchange unit (unstarred question)

Same fields as starred question except:
- `proceeding_type`: unstarred_question
- `full_text_en`: question text and written answer only (no supplementaries)
- No `questioner_names` array needed; single `questioner_name` field

## Language Handling

Official parliamentary records include English translations of speeches delivered in Hindi. The pipeline applies the following rules in order:

1. **Speech in English:** store verbatim in `full_text_en`; `is_translated: false`
2. **Speech in Hindi with official English translation present:** store the translation in `full_text_en`; `is_translated: true`
3. **Bilingual speech (switches between Hindi and English):** store all English text — both original English portions and translated Hindi portions — in `full_text_en`; `is_translated: true`
4. **Hindi speech with no translation available:** `full_text_en: null`; `has_untranslated_content: true`; record is still indexed (metadata remains searchable)

Translations in official records are typically marked inline as "[Translation]" or equivalent notation.

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

When the same proceeding is available as both HTML and PDF from the source site, the HTML version is preferred. Only one record is created per unique speech or Q+A exchange. Duplicate detection key: source + date + sitting_number + proceeding_type + speaker_name + sequence_within_sitting (or question_number for Q+A units). The sequence_within_sitting field is required because a member may speak multiple times in the same sitting on the same agenda item.

## Acceptance Criteria

- All 12 volumes of CA debates are ingested; speeches indexed per individual member contribution
- All LS and RS records dated 2014-01-01 or later are ingested across all proceeding types listed above
- Every indexed record has: source, proceeding_type, date, subject, full_text_en (or null with has_untranslated_content flag), source_url
- Starred Q+A records include the complete exchange: main question + answer + all supplementary questions and responses
- Re-running ingestion on a fully indexed corpus produces zero new records and zero duplicate records
- Progress log is written in real time; a completion summary is printed at the end
- Ingestion can be scoped to a single source (CA only, LS only, RS only) for targeted re-runs

## Edge Cases

- Speeches entirely in Hindi with no available translation: indexed with metadata only; `full_text_en: null`
- Missing speaker attribution in source record: index with `speaker_name: null`; do not skip the record
- Missing date: log as an error and skip the record (date is required for filtering)
- HTTP 4xx errors (excluding 429): log and skip; do not retry
- HTTP 5xx errors: retry up to 3 times with exponential backoff; log and skip if all retries fail
- HTTP 429 (rate limited): back off with exponential delay and retry; do not skip
- Malformed or unparseable HTML/PDF: log parsing error with document URL; skip
- RS record fetched from Internet Archive with no derivable DSpace handle: set `source_url` to null; log a warning; do not use the archive.org URL
- Records outside the date scope appearing within an in-scope document: skip those records; continue processing in-scope records in the same document

## Dependencies

None. This is the foundational feature.

## NFR Implications

- **Rate limiting:** ingestion must comply with robots.txt on sansad.in and rajyasabha.gov.in; minimum inter-request delay to be specified at architecture stage → flag in NFR
- **Storage:** full-text corpus of 12+ years of parliamentary proceedings is substantial → flag in NFR for architecture sizing
- **Processing time:** bulk ingestion is a long-running operation expected to take hours; exact time budget not specified for v1 but progress logging is required → flag in NFR
- **Resumability:** ingestion must checkpoint per source document and support safe re-runs → flag in NFR as a reliability requirement
