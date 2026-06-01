# SansadSearch — Product Requirements Document

**Version:** 2.0
**Date:** 2026-06-01
**Git tag:** (set at commit time)

---

## Table of Contents

1. [Overview](#overview)
2. [Objectives](#objectives)
3. [Functional Requirements](#functional-requirements)
   - [F01: Data Ingestion](#f01-data-ingestion)
   - [F02: Full-text Search](#f02-full-text-search)
   - [F03: Search Filters](#f03-search-filters)
   - [F04: Query Expansion](#f04-query-expansion)
   - [F05: Result Display](#f05-result-display)
   - [F06: Sorting](#f06-sorting)
   - [F07: Indexing Status Panel](#f07-indexing-status-panel)
   - [F08: Search History](#f08-search-history)
   - [F09: Detail Page](#f09-detail-page)
4. [Non-Functional Requirements](#non-functional-requirements)
5. [Future Features](#future-features)

---

## Overview

SansadSearch is a web-based full-text search application over Indian parliamentary records. It enables users to search the proceedings of the Constituent Assembly of India (1946–1950) and the last 12 years of Lok Sabha and Rajya Sabha debates and questions by keyword, speaker, date range, legislative body, and proceeding type.

### Data Scope (v1)

| Source | Coverage | Base URL |
|--------|----------|----------|
| Constituent Assembly debates | All 12 volumes, 1946–1950 | constitutionofindia.net |
| Lok Sabha debates and questions | 2014–2026 (16th–18th Lok Sabha) | eparlib.sansad.in (primary); Internet Archive (fallback) |
| Rajya Sabha debates and questions | 2014–2026 | sansad.in/rs (primary); Internet Archive; rsdebate.nic.in (fallback) |

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
- Data scope limited to CA full record + last 12 years of LS/RS; full historical records are future scope

### Target Users

- Researchers and academics studying Indian legislative history and constitutional development
- Journalists and analysts covering Indian politics and governance
- Lawyers and legal professionals researching legislative intent
- Law students and educators
- Engaged citizens tracking parliamentary debates and questions

---

## Objectives

1. Make Indian parliamentary records discoverable through full-text keyword search across all three source corpora.
2. Serve both domain experts (who search using precise parliamentary terminology) and general users (who search in plain language) without requiring expertise.
3. Enable filtering by date range, legislative body, speaker, and proceeding type so users can narrow large result sets to relevant records.
4. Display results with enough context — speaker identity, session, subject, and a passage snippet — that users can assess relevance without opening the source document.
5. Provide verifiable citations: every result links directly to the authoritative source document for that record.
6. Index the Constituent Assembly debates in full, giving researchers access to the complete constitutional drafting record in searchable form.

---

## Functional Requirements

---

### F01: Data Ingestion

#### Description

The ingestion pipeline fetches, parses, segments, and indexes parliamentary records from three sources: Constituent Assembly debates, Lok Sabha records, and Rajya Sabha records. In v1 it is a one-time bulk operation. It must be resumable: an interrupted run continues from the last successful document checkpoint without reprocessing already-indexed records or creating duplicates.

#### User Flows

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

#### Data Sources and Scope

| Source | Content | Date scope | Format | Base URL |
|--------|---------|------------|--------|----------|
| Constituent Assembly | Plenary debates | All 12 volumes, 1946–1950 | HTML | constitutionofindia.net |
| Lok Sabha | Debates and questions | 2014-01-01 to present | Pre-OCR plain text (_djvu.txt); PDF | eparlib.sansad.in (primary); Internet Archive _djvu.txt pre-OCR text (fallback) |
| Rajya Sabha | Debates and questions | 2014-01-01 to present | HTML and PDF | sansad.in/rs HTML (primary); Internet Archive; rsdebate.nic.in DSpace (fallback) |

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
| `full_text_en` | Full English text of the speech; see Language Handling below |
| `lang_original` | Language of the original speech before translation: `en` (English), `hi` (Hindi), or `mixed` (genuinely bilingual — alternates between Hindi and English in both directions; predominantly Hindi speeches with only translation fragments are classified `hi`); derived from Language Handling cases: case 1→`en`; cases 2 and 4→`hi`; case 3→`mixed` if genuinely alternating, `hi` if predominantly Hindi with translation fragments |
| `time_of_day` | Time the speech began, as HH:MM (24-hour); extracted from HTML sources only; null for Internet Archive pre-OCR text and PDF sources |
| `word_count` | Integer word count of `full_text_en` computed at ingest; null if `full_text_en` is null |
| `is_translated` | true if `full_text_en` contains or includes official English translation of Hindi portions |
| `has_untranslated_content` | true if any portion of the speech could not be indexed due to absent translation |
| `speaker_name_unresolved` | true if `speaker_name` could not be matched to a canonical form in the names dictionary |
| `source_url` | URL of the original HTML page or PDF; for LS records fetched from Internet Archive, always set to the corresponding eparlib.sansad.in document URL; for RS records fetched from Internet Archive, always set to the corresponding rsdebate.nic.in document URL (derived from the DSpace handle) |
| `page_reference` | Page number in source PDF; null for HTML sources |
| `sequence_within_sitting` | Integer position of this speech within the sitting's proceedings, derived from document order (1-based) |
| `volume` | CA volume number (1–12); null for LS/RS |

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
| `minister_name` | Minister answering |
| `ministry` | Ministry responsible |
| `full_text_en` | Full text of the complete exchange: main question + answer + all supplementaries with attribution; English only, translated as needed |
| `lang_original` | Language of the original exchange before translation: `en`, `hi`, or `mixed`; same derivation rules as speech units |
| `time_of_day` | Time the question was called, as HH:MM (24-hour); extracted from HTML sources only; null for Internet Archive pre-OCR text and PDF sources |
| `word_count` | Integer word count of `full_text_en` computed at ingest; null if `full_text_en` is null |
| `is_translated` | true if any portion was translated from Hindi |
| `has_untranslated_content` | true if any portion could not be indexed due to absent translation |
| `source_url` | URL of the original document; for LS records fetched from Internet Archive, always set to the corresponding eparlib.sansad.in document URL; for RS records fetched from Internet Archive, always set to the corresponding rsdebate.nic.in document URL (derived from the DSpace handle) |
| `page_reference` | Page number in source PDF; null for HTML sources |
| `sequence_within_sitting` | Integer position of this Q+A exchange within the sitting's proceedings, derived from document order (1-based); shared sequence space with speech units within the same sitting |

##### Q+A exchange unit (unstarred question)

Same fields as starred question except:
- `proceeding_type`: unstarred_question
- `full_text_en`: question text and written answer only (no supplementaries)
- No `questioner_names` array needed; single `questioner_name` field

#### Language Handling

Official parliamentary records include English translations of speeches delivered in Hindi. The pipeline applies the following rules in order:

1. **Speech in English:** store verbatim in `full_text_en`; `is_translated: false`
2. **Speech in Hindi with official English translation present:** store the translation in `full_text_en`; `is_translated: true`
3. **Bilingual speech (switches between Hindi and English):** store all English text — both original English portions and translated Hindi portions — in `full_text_en`; `is_translated: true`
4. **Hindi speech with no translation available:** `full_text_en: null`; `has_untranslated_content: true`; record is still indexed (metadata remains searchable)

Translations in official records are typically marked inline as "[Translation]" or equivalent notation.

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

When the same proceeding is available as both HTML and PDF from the source site, the HTML version is preferred. Only one record is created per unique speech or Q+A exchange. Duplicate detection key: source + date + sitting_number + proceeding_type + speaker_name + sequence_within_sitting (or question_number for Q+A units). The sequence_within_sitting field is required because a member may speak multiple times in the same sitting on the same agenda item.

#### Acceptance Criteria

- All 12 volumes of CA debates are ingested; speeches indexed per individual member contribution
- All LS and RS records dated 2014-01-01 or later are ingested across all proceeding types listed above
- Every indexed record has: id, source, proceeding_type, date, subject, full_text_en (or null with has_untranslated_content flag), source_url, lang_original
- `id` is a stable UUID that does not change across re-runs for the same record
- `word_count` is present and non-null for all records where `full_text_en` is not null; null where `full_text_en` is null
- `time_of_day` is present (HH:MM) for HTML-sourced records where the sitting page includes time; null for all IA pre-OCR and PDF-sourced records
- Starred Q+A records include the complete exchange: main question + answer + all supplementary questions and responses
- Re-running ingestion on a fully indexed corpus produces zero new records and zero duplicate records
- Progress log is written in real time; a completion summary is printed at the end
- Ingestion can be scoped to a single source (CA only, LS only, RS only) for targeted re-runs

#### Edge Cases

- Speeches entirely in Hindi with no available translation: indexed with metadata only; `full_text_en: null`
- Missing speaker attribution in source record: index with `speaker_name: null`; do not skip the record
- Missing date: log as an error and skip the record (date is required for filtering)
- HTTP 4xx errors (excluding 429): log and skip; do not retry
- HTTP 5xx errors: retry up to 3 times with exponential backoff; log and skip if all retries fail
- HTTP 429 (rate limited): back off with exponential delay and retry; do not skip
- Malformed or unparseable HTML/PDF: log parsing error with document URL; skip
- RS record fetched from Internet Archive with no derivable DSpace handle: set `source_url` to null; log a warning; do not use the archive.org URL
- Records outside the date scope appearing within an in-scope document: skip those records; continue processing in-scope records in the same document

#### Dependencies

None. This is the foundational feature.

#### NFR Implications

- **Rate limiting:** ingestion must comply with robots.txt on sansad.in and rajyasabha.gov.in; minimum inter-request delay to be specified at architecture stage → flag in NFR
- **Storage:** full-text corpus of 12+ years of parliamentary proceedings is substantial → flag in NFR for architecture sizing
- **Processing time:** bulk ingestion is a long-running operation expected to take hours; exact time budget not specified for v1 but progress logging is required → flag in NFR
- **Resumability:** ingestion must checkpoint per source document and support safe re-runs → flag in NFR as a reliability requirement

#### Test Requirements (F01)

- Records dated exactly 2014-01-01 are included in scope; records dated 2013-12-31 are excluded
- Scope is fixed at 2014-01-01, not a rolling window recalculated at run time
- When the same proceeding is available as both HTML and PDF, exactly one record is created; the HTML-sourced record is retained
- Duplicate detection must use the compound key; a match on all key fields results in a skip, not a second insert
- A member speaking twice in the same sitting must produce two separate indexed records with distinct sequence_within_sitting values; they must not be merged
- Checkpoint granularity is per source document; a document is checkpointed only after all its records are successfully indexed
- A document that was partially processed when ingestion was interrupted must be fully reprocessed on resume, with no duplicate records created for the portion already indexed
- Record count after a clean run equals record count after an interrupted-then-resumed run against the same corpus
- A starred Q+A unit must include every supplementary question and ministerial response present in the source record, not just the first
- When a speech is delivered in Hindi and the official English translation is present, `full_text_en` must contain the translation text, not the Devanagari text and not null
- When no translation is available, `full_text_en` must be null — not an empty string, not the Devanagari text
- `is_translated` must be true whenever `full_text_en` contains any translated content; false when the text is original English throughout
- "SEVERAL HON. MEMBERS", "AN HON. MEMBER", "SOME HON. MEMBERS" must never appear as a `speaker_name` value
- Speeches by the Speaker (LS) and Chairman/Vice-Chairman (RS) made in their presiding capacity must not appear as standalone indexed records
- Zero hour speeches must carry the individual member's name in `speaker_name`; "ZERO HOUR" must not appear as a `speaker_name` value
- A speaker appearing under multiple name variants must produce identical `speaker_name` values across all indexed records
- Honorific prefixes must be stripped; the canonical form must not begin with Shri, Smt., Dr., Prof., Adv., or Kumari
- CA records must have `session_name: null`; any non-null `session_name` on a CA record is a bug
- A source document with no parseable date must produce zero indexed records from that document and one logged error entry; it must not halt ingestion for subsequent documents
- The completion summary record count must match the actual number of records retrievable from the search index after ingestion completes
- **CA date:** A CA record whose URL slug parses to a different date than what `parse_html` would return must store the URL-derived date; the HTML date must never appear in the indexed record
- **CA date:** A CA record must never have a null `date` caused by HTML parse failure when the URL slug is present and parseable
- **CA subject:** Two speech records from the same sitting that fall under the same bold section header must have identical `subject` values
- **CA subject:** A speech record that follows a new section header in document order must not retain the `subject` value from the previous section header
- **CA subject:** The first speech in a sitting with no preceding bold section header must have `subject` set to the text of the first TOC `<ul>` item; it must not be null, empty, or set to a later section header

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

Fields searched: `full_text_en`, `subject`, `speaker_name`, `minister_name`, `ministry`

- Single-term query: expanded with synonyms and spell corrections (Feature 04); OR across variants; original at full weight; synonyms at reduced weight; corrections at lower weight
- Multi-term query: AND across original term groups; OR across each term's expansions
- Phrase query (double-quoted): exact phrase matched first at full weight; phrase-level synonyms at reduced weight; individual term expansions not applied within phrase

Relevance ranking factors (combined scoring): original term coverage; field match location (speaker/subject/minister/ministry > full_text_en); expansion match type (synonym > spell-correction); term frequency and passage density.

Default search scope: all sources (CA + LS + RS).

#### Acceptance Criteria

- Search box visible and accessible on homepage
- Persistent search box pre-populated with current query on results page
- Queries ≥ 2 non-whitespace characters execute and return results
- Queries < 2 non-whitespace characters or empty submission show inline validation; no search executed
- A record matching all original query terms ranks above one matching only synonym expansions
- Phrase query returns only records where the exact word sequence is present
- Search is case-insensitive
- No-results state shows a clear message and suggestions
- Search response time: ≤2 seconds at p95 across the full indexed corpus

#### UI Behavior

- Homepage: full-width search box with Search button; no autocomplete in v1
- Results page: compact search box at top pre-filled with current query; results list below
- Inline validation messages appear below the search box
- No-results state shown in the results area with message and suggestions

#### Edge Cases

- Query of only stop words: strip stop words; if nothing remains, show validation message as empty query
- Query > 500 characters: truncate to 500 and execute; no error shown
- Special characters: strip or escape before execution; must not cause error
- Identical query resubmission: execute again; do not serve cached result
- Search backend error: display "Search is temporarily unavailable" with retry option

#### Dependencies

- Feature 01: indexed corpus
- Feature 04: synonym dictionary and spell-correction rules

#### NFR Implications

- Response time: ≤2 seconds at p95; query expansion increases scoring computation
- Scalability: response time target must hold under concurrent user load

#### Test Requirements (F02)

- A record containing query terms separated by other words must NOT match a phrase query for those terms as a phrase
- Given record A with query term once in `speaker_name` and record B with query term ten times in `full_text_en`, A must rank higher
- Match on original term > synonym match > spell-correction match in relevance score, even when term frequency differs
- Record matching original term 1 and synonym expansion of term 2 must rank below record matching both original terms
- Queries in any case permutation must return identical result sets in identical rank order
- A query of only stop words must show the validation message, not an empty result list
- Query of exactly 501 characters must be truncated to 500 and execute without error, with no truncation indicator shown
- Special character-only query must be treated as empty and show validation message
- After query refinement on results page, active filter selections from Feature 03 must persist

---

### F03: Search Filters

#### Description

Filters allow users to narrow search results by legislative body, date range, speaker, session, and proceeding type. All filters are combinable with each other and with the search query. Filter state persists across query refinements and is only reset by an explicit clear action.

#### User Flows

**Applying filters:** User selects filter values; system re-executes search with constraints; active filters visually indicated.

**Clearing filters:** User clicks "Clear filters" or removes individual value; search re-executes without that constraint.

**Filter persistence:** Active filters persist across query refinements; only explicit clear resets them.

**No results with active filters:** No-results state shown with "clear filters" suggestion.

#### Filter Dimensions

1. **Legislative body** — Multi-select: CA, Lok Sabha, Rajya Sabha; default: all three selected
2. **Date range** — From and To dates; both optional; constrained to indexed scope per body selection; From > To shows validation
3. **Speaker** — Free text; case-insensitive substring match against `speaker_name`; no autocomplete in v1
4. **Session** — Free text; case-insensitive substring match against `session_name`; CA records excluded when any session filter is active
5. **Proceeding type** — Multi-select: Debate, Starred Question, Unstarred Question, Zero Hour, Short Notice Question, Calling Attention, Short Duration Discussion, Adjournment Motion, Private Member Bill; only "Debate" available when only CA is selected

All active filters are ANDed together and with the search query.

#### Acceptance Criteria

- All five filter dimensions available on results page
- Active filters visibly indicated; "clear filters" resets all; individual filter values removable
- Filter state persists across query refinements
- Date range From > To shows validation; filter not applied
- Proceeding type options disable correctly when only CA selected
- Session filter excludes CA records from result set
- Result count reflects filtered set

#### Edge Cases

- All proceeding types deselected: validation message; search not executed
- All bodies deselected: validation message; search not executed
- Speaker filter no match: no-results state; no error
- Session filter partially matches multiple sessions: all matching included
- Date range spanning the CA/LS-RS gap: union of CA and LS/RS records within range; no error

#### Dependencies

- Feature 01: canonical `speaker_name` and `session_name` fields
- Feature 02: search query execution accepting filter constraints

#### Test Requirements (F03)

- Session filter active: CA records absent from result set even if CA is selected in body filter and query matches CA records
- Date range 1948-01-01 to 2015-12-31: returns CA records 1948–1950 and LS/RS records 2014–2015; no records from 1951–2013; no error
- Only CA selected + non-Debate proceeding type: zero results, not an error
- Speaker filter "Singh" must match all canonicalized names containing "Singh"
- Speaker filter with only whitespace: treated as empty filter
- After RS body filter + query refinement: result set contains only RS records; filter indicator still shows RS active
- Deselecting all bodies and submitting: validation message; search not executed; previous result set visible
- Deselecting all proceeding types and submitting: validation message; search not executed
- From > To: inline validation error; displayed result set unchanged
- Body=LS + type=Starred Question + speaker="Jairam Ramesh": only records satisfying all three constraints returned

---

### F04: Query Expansion

#### Description

Query expansion augments user queries with synonyms and spell corrections before search execution, improving recall for users who search with different terminology than what appears in the indexed records. The expansion dictionary is seeded with parliamentary domain-specific terms and maintained as a static file in the codebase; updates require a re-deployment.

#### Synonym Dictionary

Bidirectional synonyms covering: legislative bodies, constitutional terminology, parliamentary procedure, common abbreviations, and well-known legislation short titles. Full list defined in the feature spec source file.

Phrase synonyms apply only when the full phrase appears in the query. Single-term synonyms apply to individual query terms. Multi-word synonyms are not broken into individual terms.

The dictionary is a static structured file (JSON or YAML) maintained in the codebase. No runtime editing in v1.

#### Spell Correction

Applies to individual query terms; suppressed inside phrase queries (quoted). Edit-distance based; phonetic matching for proper nouns. Corrected term added as OR alternative at lower weight than synonym expansions. Terms < 4 characters exempt from spell correction.

#### Acceptance Criteria

- "PM" query returns "Prime Minister" records at lower weight than "PM" records
- "fundamental rights" query returns "basic rights" records at lower weight
- "Parliment" query returns "Parliament" records at reduced weight
- Quoted phrase query applies phrase synonyms only; individual term synonyms not applied inside quotes
- Terms < 4 characters not spell-corrected
- Synonyms apply to LS, RS, and CA records equally
- Dictionary file is the only source of synonym definitions; no hardcoded synonyms elsewhere

#### Dependencies

- Feature 02: search execution model consuming expansion output

#### Test Requirements (F04)

- Bidirectionality must hold for all synonym pairs in the dictionary
- "fundamental rights" multi-term query must not additionally expand individual terms via single-term synonyms
- "rights" alone must not expand to "fundamental rights" via the phrase synonym
- Quoted phrase with misspelled term must not apply spell correction; searched verbatim
- Terms of 1, 2, or 3 characters must not trigger spell correction; term of exactly 4 characters is eligible
- For same record, synonym match contribution > spell-correction match contribution to relevance score
- "SC" query must generate all known expansions from the dictionary; absence of any defined expansion is a bug
- Synonym only in application logic (not dictionary file) must cause a test to fail
- "PM" expansion must not apply because "PM" appears as substring of "MGNREGA"

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
| Proceeding type | `proceeding_type` | Human-readable label (see label map below) |
| Date | `date` | Formatted as DD Month YYYY |
| Time of day | `time_of_day` | Shown as HH:MM near the date field when not null; omitted silently when null |
| Session | `session_name` | Shown if available; omitted for CA records |
| Subject / agenda item | `subject` | The debate title or agenda item this speech belongs to |
| Text snippet | derived from `full_text_en` | 2–3 sentences of context around the highest-relevance match; query terms highlighted |
| Language badge | `lang_original` | `hi`→"Hindi original"; `mixed`→"Mixed language"; `en`→no badge shown |
| Source link | `source_url` | "View source" link; opens in a new tab |

#### Result Card: Q+A Exchange Record

| Field | Source | Notes |
|-------|--------|-------|
| Question number | `question_number` | Displayed as "Q. [number]" |
| Subject | `subject` | Question subject/title |
| Proceeding type | `proceeding_type` | "Starred Question" or "Unstarred Question" or other Q+A type label |
| Legislative body | `source` | "Lok Sabha" or "Rajya Sabha" |
| Date | `date` | Formatted as DD Month YYYY |
| Time of day | `time_of_day` | Shown as HH:MM near the date field when not null; omitted silently when null |
| Session | `session_name` | Shown if available |
| Questioner | `questioner_names` (primary) | First named questioner; "+N others" if co-signatories present |
| Questioner party | `questioner_party` | Shown if available |
| Minister and ministry | `minister_name`, `ministry` | "Answered by [Minister Name], [Ministry]" |
| Text snippet | derived from `full_text_en` | 2–3 sentences of context around the highest-relevance match; query terms highlighted |
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

- 2–3 sentences extracted from `full_text_en`, from the passage with the highest density of query term matches
- Query terms highlighted in snippet
- If near start or end of `full_text_en`, snippet may be shorter than 3 sentences
- If `full_text_en: null`: snippet area shows "This speech was delivered in Hindi. No English text is available."
- For Q+A records, if match is in a supplementary exchange, snippet drawn from there with "From supplementary exchange" label

#### Pagination

- 20 results per page
- Exact count up to 9,999; "10,000+ results" for ≥ 10,000
- Pagination controls: previous, next, current page, total page count (when ≤ 500 pages)
- URL reflects current page number

#### Acceptance Criteria

- Every result card displays: body, proceeding type, date, subject, snippet with highlighted terms, working source link
- "View source" opens original document in new tab
- Snippet highlights all matched query terms
- Records with `full_text_en: null` display the untranslated-speech message; no empty snippet area
- Records with `lang_original: hi` show "Hindi original" badge; `lang_original: mixed` show "Mixed language" badge; `lang_original: en` show no badge
- Records with `time_of_day` not null display the time as HH:MM near the date; null time_of_day shows no time field and no placeholder
- Result count shown at top of result list
- Paginated result sets: direct URL loads correct page

#### Edge Cases

- Missing `speaker_party` or `speaker_constituency_or_state`: omitted; no placeholder
- `speaker_name: null`: show "Speaker unknown"
- Snippet contains HTML or special characters: escaped/sanitised; must not render as HTML
- Source URL missing or broken: "View source" link not shown; no broken link displayed

#### Dependencies

- Feature 01: indexed records with all metadata fields
- Feature 02: ranked results and match position data for snippet extraction

#### Test Requirements (F05)

- When highest-relevance match for starred Q+A is in supplementary exchange, snippet must be drawn from supplementary and "From supplementary exchange" label must be present
- A result set of exactly 9,999 must display "9,999 results" (exact), not "10,000+ results"
- A result set of exactly 10,000 must display "10,000+ results", not an exact count
- A result set of exactly 0 must display "0 results" and the no-results message simultaneously
- `full_text_en: null` record: snippet area must not be empty, blank, or absent — the placeholder message is required
- `full_text_en` containing HTML tags must render as plain text; tags must not be interpreted; script tags must not execute
- Navigating to page 3 via URL in a new browser session must load page 3 of the same results; URL must encode query and page number
- A starred question with exactly 1 questioner must not show the "+N others" label
- A starred question with 3 co-signatories must show "+3 others"
- `speaker_name_unresolved: true` record must display the raw `speaker_name` identically in format to a resolved name
- `lang_original: hi` card must display "Hindi original" badge; no other language label on that card
- `lang_original: mixed` card must display "Mixed language" badge
- `lang_original: en` card must show no language badge; badge element must be absent from DOM, not merely hidden
- `time_of_day: "14:35"` must display "14:35" near the date field; value must not be reformatted
- `time_of_day: null` must not render any time-of-day element — no placeholder, no empty field, no "—"

---

### F06: Sorting

#### Description

Users can sort search results by relevance, chronological order, or reverse chronological order. The default sort is relevance. Sort state persists across query refinements.

#### Sort Options

| Option | Order | Description |
|--------|-------|-------------|
| Relevance (default) | Descending relevance score | Ranked by combined relevance score from F02 |
| Chronological | Ascending date | Oldest first; secondary sort by `sequence_within_sitting` ascending for same date |
| Reverse chronological | Descending date | Newest first; secondary sort by `sequence_within_sitting` descending for same date |

#### Acceptance Criteria

- Three sort options available; default is Relevance on every new search
- Changing sort re-orders results without changing count or clearing filters
- Sort persists across query refinements
- Chronological/reverse-chronological use date as primary key and `sequence_within_sitting` as secondary key

#### Dependencies

- Feature 02: relevance scores
- Feature 01: `date` and `sequence_within_sitting` fields

#### Test Requirements (F06)

- Two records with the same date must be ordered by `sequence_within_sitting` ascending (chronological) or descending (reverse-chronological)
- Switching from chronological to relevance must reorder by relevance score; date order must not be preserved as tiebreaker
- Sort persists after query refinement; new results are in the same sort order
- Changing sort order must not change the result count
- Every new search defaults to Relevance sort regardless of the previous sort selection

---

### F07: Indexing Status Panel

#### Description

A read-only panel displaying total records indexed, per-source breakdown with date coverage, and last ingestion run date. In v1 it reads a pre-computed summary written by the ingestion pipeline; it does not query the search index directly.

#### Displayed Information

- Total records indexed; per-source record counts; per-source date coverage; last ingestion run date
- Homepage status strip: condensed summary (per-source counts + last updated date; no per-source date coverage)
- Full panel: accessible from footer link "Index status"; full format including date coverage and "0 records – not yet indexed" row for unindexed sources

#### Acceptance Criteria

- Homepage strip displays per-source counts and last updated date; zero-indexed sources shown as "0 [Body] records", not omitted
- Full panel displays total count, per-source counts, per-source date coverage, and last updated date
- Counts and dates reflect actual index state; not hardcoded
- Last updated date reflects most recent ingestion run completion timestamp
- Both surfaces are read-only

#### Dependencies

- Feature 01: ingestion pipeline writes the summary record

#### Test Requirements (F07)

- Panel must not query the search index at page load; disabling the search index must still show last known status data
- On fresh deployment, "Last updated" must display "Never", not null, blank, or a default date
- In full panel: source with zero records shows "0 records – not yet indexed" with no date range; empty date string or placeholder date is a bug
- In homepage strip: source with zero records appears as "0 [Body] records"; must not be omitted
- Total records count must equal the sum of the three per-source counts
- "Last updated" date must not update on page load, search execution, or any event other than an ingestion pipeline run

---

### F08: Search History

#### Description

Cookie-based recent searches and saved searches. No sign-in required. All data stored client-side. Recent searches recorded automatically; saved searches explicitly bookmarked by the user.

#### Recent Searches

- Auto-recorded on every query submission; max 10 entries; oldest removed at limit
- Duplicate query updates timestamp and position; only one entry per unique query string
- Cookie lifetime: 30 days from most recent submission
- Per entry: query text and submission timestamp; filter state not stored
- Actions: re-run (with default filters), delete individual, clear all

#### Saved Searches

- Explicitly saved from results page; max 20 entries; save disabled at limit with message
- No expiry; persistent cookie
- Per entry: name (defaults to query text, editable to 60 chars), query text, active filter state, save timestamp
- Actions: save current search, re-run with stored filters, rename, delete

#### Cookie Storage Constraints

- Recent and saved searches in separate cookies; total ≤ 4KB; recent searches trimmed first if near limit
- Cookies disabled: features silently unavailable; rest of application functions normally; no error shown

#### Acceptance Criteria

- Every submitted query added to recent searches automatically
- Recent list shows at most 10 entries, most recent first
- Duplicate query updates existing entry; does not create second entry
- Saved searches restore query + filter state exactly
- Save disabled with message when 20 saved searches exist
- Deleting removes entry immediately without page reload
- All history features work without authentication; no data sent to server

#### Dependencies

- Feature 02: search execution accepting a query string
- Feature 03: filter state model that saved searches restore

#### Test Requirements (F08)

- Same query submitted three times: exactly one entry with timestamp of third submission
- With 10 stored, submitting 11th distinct query removes oldest and adds new; list stays at exactly 10
- Re-running a recent search executes with default filters, not filters active at original submission
- Saved search with body=RS, type=Starred Question, from=2020-01-01 must restore exactly those selections on re-run
- With exactly 20 saved searches, save action visibly disabled with message; cannot create 21st entry
- Saving same query text twice creates two separate entries; does not overwrite first
- Cookies blocked: recent/saved search features not shown; no cookie error message; search and results function normally
- Name of exactly 60 characters accepted; 61 characters rejected
- Re-running a saved search with an unrecognised proceeding type value: search executes ignoring that value; no error

---

### F09: Detail Page

#### Description

A full-record detail page displaying the complete text and all metadata for a single indexed record. Accessible via a stable URL. Provides adjacent navigation within the same sitting and back navigation to the results page.

#### Route and API

- **Frontend route:** `/record/:id`
- **API endpoint:** `GET /api/record/{id}` — fetches a single document from Meilisearch by document `id`; returns 404 if not found

#### User Flows

**Arriving from search results:**
1. User clicks a result card
2. Browser navigates to `/record/:id`
3. Detail page loads: full text rendered as paragraphs, all metadata shown, adjacent navigation controls shown
4. "Back to results" link is present; clicking returns to the search results page preserving query and pagination state

**Direct access:**
1. User opens `/record/:id` directly
2. Detail page loads as above
3. "Search" link to homepage shown in place of "Back to results"

**Adjacent navigation:**
1. User clicks "Next" or "Prev"
2. Page navigates to the adjacent record by `sequence_within_sitting` within the same sitting
3. URL updates to `/record/:id` for the new record
4. "Same sitting" = same `source` + same `date` + same `sitting_number`; Q+A and speech records share the sequence space
5. At sequence boundaries, the boundary control is disabled (not hidden)

#### Full Text Display

- `full_text_en` rendered as paragraphs
- If `full_text_en: null`: display "This record was delivered in Hindi. No English text is available." in the text area

#### Metadata Fields Displayed

All fields shown explicitly. Null or not-applicable fields omitted silently (no placeholder), except where noted.

| Field | Display label | Notes |
|-------|--------------|-------|
| `source` | Legislative body | "Constituent Assembly", "Lok Sabha", or "Rajya Sabha" |
| `proceeding_type` | Proceeding type | Human-readable label per F05 label map |
| `date` | Date | DD Month YYYY |
| `time_of_day` | Time | HH:MM; omitted when null |
| `session_name` | Session | Omitted when null |
| `session_number` | Session number | Omitted when null |
| `sitting_number` | Sitting number | |
| `volume` | Volume | CA only; omitted for LS/RS |
| `subject` | Subject | |
| `speaker_name` | Speaker | Speech records only |
| `speaker_role` | Role | Speech records only; human-readable label |
| `speaker_party` | Party | Omitted when null |
| `speaker_constituency_or_state` | Constituency / State | Omitted when null; omitted for CA records |
| `speaker_name_unresolved` | — | When true, show "(name unresolved)" next to `speaker_name`; not shown when false |
| `question_number` | Question number | Q+A records only; "Q. [number]" |
| `questioner_names` | Questioner(s) | Q+A records only |
| `questioner_party` | Questioner party | Q+A records only; omitted when null |
| `minister_name` | Minister | Q+A records only |
| `ministry` | Ministry | Q+A records only |
| `lang_original` | Language | "English", "Hindi", or "Bilingual" — always shown |
| `is_translated` | Translation | "Includes official English translation" — shown only when true |
| `has_untranslated_content` | Untranslated content | "Some content unavailable in English" — shown only when true |
| `page_reference` | PDF page | "PDF page [N]" when not null; omitted when null |
| `word_count` | Word count | "[N] words" when not null; omitted when null |
| `sequence_within_sitting` | Position in sitting | "[N] of [total]" where total = count of records in the same sitting |
| `source_url` | Source | "View source" link in new tab; omitted when null |

#### Adjacent Navigation

- Neighbour records: query index for records with same `source`, `date`, `sitting_number`, sorted by `sequence_within_sitting`
- Prev = current − 1; Next = current + 1
- "Prev" disabled at lowest sequence in sitting; "Next" disabled at highest
- Disabled controls remain visible

#### Back Navigation

- Arrived via in-app link from search results: "Back to results" link
- Direct URL access (bookmark, external link): "Search" link to homepage

#### Acceptance Criteria

- `/record/:id` loads correct record for valid `id`; 404 page for unknown `id`
- Full `full_text_en` displayed as paragraphs; null shows defined message
- All non-null metadata fields displayed; null fields omitted with no placeholder
- `page_reference` shown as "PDF page [N]" when present; omitted when null
- `source_url` renders as "View source" link when present; omitted when null
- Adjacent navigation moves to correct record and updates URL
- Prev/Next disabled (not hidden) at sequence boundaries
- "Back to results" shown when arriving from search; "Search" link when accessed directly
- URL updates on adjacent navigation

#### Edge Cases

- `full_text_en: null`: text area shows defined message; all metadata still displays
- Record at sequence boundary: boundary-side control disabled; other behaves normally
- Only one record in sitting: both Prev and Next disabled
- `source_url: null`: "View source" not shown; no broken link
- Direct URL access with no referrer: "Search" link shown; no "Back to results"
- `id` not found: 404 response; frontend renders "Record not found" page

#### Architect Flags

- **New API endpoint:** `GET /api/record/{id}` — single-document fetch by Meilisearch document `id`; 404 for unknown id
- **Adjacent navigation query pattern:** filter by `source` + `date` + `sitting_number`, sort by `sequence_within_sitting`, fetch the two neighbours; assess query cost
- **New frontend route:** `/record/:id` — routing integration and referrer detection for back navigation
- **Re-ingestion requirement:** `id`, `lang_original`, `time_of_day`, `word_count`, and `sequence_within_sitting` (for Q+A) not derivable from stored data without re-parsing; full re-ingestion required for all existing records
- **sequence_within_sitting for Q+A records:** feasibility of assigning a shared sequence number across speech and Q+A record types within the same sitting for all three source providers

#### Dependencies

- Feature 01: indexed records with `id`, `sequence_within_sitting`, and all metadata fields
- Feature 02: search index accessible by document `id`

#### NFR Implications

- **Performance:** detail page full load including neighbour fetch must meet PERF-2 target

#### Test Requirements (F09)

- `sequence_within_sitting: 1` record must have "Prev" disabled; clicking disabled control produces no navigation
- Record at maximum `sequence_within_sitting` in its sitting must have "Next" disabled
- Sitting with exactly one record: both Prev and Next disabled simultaneously
- Disabled controls must be present in DOM and visible — not `display:none`, not removed
- After clicking "Next", URL updates to the next record's `/record/:id`; clicking Prev from that URL returns to the original record
- Record opened via in-app navigation: shows "Back to results"; link returns to results without re-executing search
- Record opened by direct URL in new tab: shows "Search" to homepage; must not show "Back to results"
- `full_text_en: null`: text area renders the defined message; not empty, blank, or absent; all other non-null metadata still renders
- `page_reference: 42` must display "PDF page 42"; `page_reference: null` must show no page reference label or value
- `sequence_within_sitting` display must show actual count M of records sharing same `source` + `date` + `sitting_number`; M must not be hardcoded
- `/record/nonexistent-id`: renders "Record not found" page; no blank page, no JS error, no partial render

---

## Non-Functional Requirements

### Performance

**PERF-1: Search response time**
Search results must be returned within 2 seconds at p95, measured from query submission to full result list rendered in the browser, across the full indexed corpus. This target applies with query expansion active (synonyms + spell corrections). Architecture must account for the additional scoring computation introduced by query expansion.

**PERF-2: Detail page response time**
The detail page must complete full page load — including the record fetch and the adjacent-neighbour fetch — within 500ms at p95.

### Reliability

**INF-R1: Ingestion resumability**
The bulk ingestion pipeline must be resumable from a per-document checkpoint. An interrupted run re-run against the same corpus must produce an identical final record count with no duplicates. Safe re-runs are a hard requirement, not a best-effort goal.

### Security

*To be populated as features are specced.*

### Storage

**INF-S1: Corpus storage sizing**
The full-text corpus (CA full record + 12 years of LS/RS debates and questions) is large. Storage architecture must be sized accordingly before build begins. Exact sizing is an architecture-stage deliverable.

### Rate Limiting and Compliance

**INF-RL1: Government website rate limiting**
The ingestion pipeline must comply with robots.txt on constitutionofindia.net, eparlib.sansad.in, sansad.in, rsdebate.nic.in, and the Internet Archive. Minimum inter-request delay must be specified at architecture stage. HTTP 429 responses must trigger exponential backoff and retry, not a skip.

### Processing

**INF-P1: Bulk ingestion duration**
Bulk ingestion is a long-running operation. No maximum time constraint is specified for v1, but real-time progress logging is required. The operation must not require human supervision to complete.

### Scalability

**SCALE-1: Concurrent search load**
Search must remain within the PERF-1 response time target under concurrent user load. Exact concurrency targets are an architecture-stage deliverable.

### Privacy

**PRIV-1: No server-side storage of user search data**
Search queries, filter selections, and search history are not persisted server-side in v1. All search history (recent searches and saved searches) is stored client-side in browser cookies only. No user identifiers are created or stored.

---

## Future Features

### Data Scope Expansion

- **Full parliamentary history:** extend LS and RS coverage beyond 2014 to include all available records
- **Ongoing ingestion:** scheduled pipeline to ingest new sessions automatically

### Language Support

- **Hindi search:** index Hindi-language text; requires separate tokenisation, stop-word lists, synonym dictionary

### User Accounts and Personalisation

- **User authentication:** sign-in with persistent cross-device history and saved searches
- **Cross-device sync:** saved searches accessible from any device when signed in
- **Search alerts:** notify users when new records matching a saved search are indexed

### Search Experience

- **Autocomplete / search-as-you-type:** query suggestions and speaker name completions
- **Faceted result counts:** count of results per filter value in the filter panel
- **Related results / "More like this":** records thematically similar to a result being viewed
- **Member profile pages:** dedicated page per member showing all indexed speeches and questions

### Platform

- **Mobile UI:** responsive layout optimised for small screens
- **Public API:** REST or GraphQL API for third-party integrations

### Administration

- **Admin interface for synonym dictionary:** in-application UI for adding/editing synonyms without deployment
- **Ingestion monitoring dashboard:** real-time visibility into ingestion pipeline progress and error rates

---

*Generated: 2026-06-01 | PRD v2.0 | SansadSearch*
