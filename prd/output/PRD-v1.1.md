# SansadSearch — Product Requirements Document

**Version:** 1.1
**Date:** 2026-05-29
**Previous version:** 1.0

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
4. [Non-Functional Requirements](#non-functional-requirements)
5. [Future Features](#future-features)

---

## Overview

### Product

SansadSearch is a web-based full-text search application over Indian parliamentary records. It enables users to search the proceedings of the Constituent Assembly of India (1946–1950) and the last 12 years of Lok Sabha and Rajya Sabha debates and questions by keyword, speaker, date range, legislative body, and proceeding type.

### Data Scope (v1)

| Source | Coverage | Base URL |
|--------|----------|----------|
| Constituent Assembly debates | All 12 volumes, 1946–1950 | sansad.in (Lok Sabha archives) |
| Lok Sabha debates and questions | 2014–2026 (16th–18th Lok Sabha) | sansad.in |
| Rajya Sabha debates and questions | 2014–2026 | rajyasabha.gov.in |

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
5. Provide verifiable citations: every result links directly to the original source document on sansad.in or rajyasabha.gov.in.
6. Index the Constituent Assembly debates in full, giving researchers access to the complete constitutional drafting record in searchable form.

---

## Functional Requirements

---

### F01: Data Ingestion

#### Description

The ingestion pipeline fetches, parses, segments, and indexes parliamentary records from three sources: Constituent Assembly debates (sansad.in archives), Lok Sabha records (sansad.in), and Rajya Sabha records (rajyasabha.gov.in). In v1 it is a one-time bulk operation. It must be resumable: an interrupted run continues from the last successful document checkpoint without reprocessing already-indexed records or creating duplicates.

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
| Constituent Assembly | Plenary debates | All 12 volumes, 1946–1950 | PDF (some scanned) | sansad.in (Lok Sabha archives) |
| Lok Sabha | Debates and questions | 2014-01-01 to present | HTML and PDF | sansad.in |
| Rajya Sabha | Debates and questions | 2014-01-01 to present | HTML and PDF | rajyasabha.gov.in |

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

**Speech unit**

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
| `source_url` | URL of the original HTML page or PDF |
| `page_reference` | Page number in source PDF; null for HTML sources |
| `sequence_within_sitting` | Integer position of this speech within the sitting's proceedings, derived from document order (1-based) |
| `volume` | CA volume number (1–12); null for LS/RS |

**Q+A exchange unit (starred question)**

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
| `source_url` | URL of the original document |
| `page_reference` | Page number in source PDF; null for HTML sources |

**Q+A exchange unit (unstarred question)**

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

#### Records Not Indexed as Standalone Units

The following are not indexed as standalone searchable records:
- Unattributed speech: "SEVERAL HON. MEMBERS", "AN HON. MEMBER", "SOME HON. MEMBERS", and similar
- Presiding officer interventions: speeches by the Speaker (Lok Sabha) or Chairman/Vice-Chairman (Rajya Sabha) made in their presiding capacity
- Procedural interruptions: points of order, rulings, and division votes

These may appear as part of the `full_text_en` of a surrounding Q+A exchange unit (e.g., presiding officer directing the house during a starred question) but are not separately indexed.

#### Canonicalization

**Speaker names**

Speaker names in source records appear in multiple variants across sittings and sessions (honorific prefixes, abbreviated forms, ordering variants, transliteration differences). All speaker names must be canonicalized to a consistent form at ingestion time.

Canonicalization rules:
- Strip honorific prefixes: Shri, Smt., Dr., Prof., Adv., Kumari, and any other titles present in the source records
- Resolve abbreviation variants and ordering variants (e.g., "Modi, Narendra" → "Narendra Modi") using a canonical names dictionary
- The canonical names dictionary maps known name variants to a single canonical full name; it must be seeded from official Lok Sabha and Rajya Sabha member lists and the CA member list
- If a speaker name is not found in the canonical names dictionary, store the raw name as found in the source record and set `speaker_name_unresolved: true`
- Unresolved names are indexed and searchable; they are flagged for manual dictionary updates

**Session names**

Session names in source records may appear in inconsistent formats across sources (e.g., "Budget Session, 2023" vs "Budget Session 2023" vs "Budget Session (Second Part) 2023"). Canonicalize to a consistent format: "[Session Type] Session [Year]" with multi-part sessions appended as "(Part [N])" where applicable. Example canonical forms: "Budget Session 2023", "Monsoon Session 2022", "Budget Session 2023 (Part 2)".

CA records have no session name; `session_name` is null for all CA records.

#### Deduplication

When the same proceeding is available as both HTML and PDF from the source site, the HTML version is preferred. Only one record is created per unique speech or Q+A exchange. Duplicate detection key: source + date + sitting_number + proceeding_type + speaker_name + sequence_within_sitting (or question_number for Q+A units). The sequence_within_sitting field is required because a member may speak multiple times in the same sitting on the same agenda item.

#### Acceptance Criteria

- All 12 volumes of CA debates are ingested; speeches indexed per individual member contribution
- All LS and RS records dated 2014-01-01 or later are ingested across all proceeding types listed above
- Every indexed record has: source, proceeding_type, date, subject, full_text_en (or null with has_untranslated_content flag), source_url
- Starred Q+A records include the complete exchange: main question + answer + all supplementary questions and responses
- Re-running ingestion on a fully indexed corpus produces zero new records and zero duplicate records
- Progress log is written in real time; a completion summary is printed at the end
- Ingestion can be scoped to a single source (CA only, LS only, RS only) for targeted re-runs

#### Edge Cases

- Scanned CA PDFs: text extracted via OCR; records with OCR confidence below threshold are flagged (`ocr_low_confidence: true`) but still indexed
- Speeches entirely in Hindi with no available translation: indexed with metadata only; `full_text_en: null`
- Missing speaker attribution in source record: index with `speaker_name: null`; do not skip the record
- Missing date: log as an error and skip the record (date is required for filtering)
- HTTP 4xx errors (excluding 429): log and skip; do not retry
- HTTP 5xx errors: retry up to 3 times with exponential backoff; log and skip if all retries fail
- HTTP 429 (rate limited): back off with exponential delay and retry; do not skip
- Malformed or unparseable HTML/PDF: log parsing error with document URL; skip
- Records outside the date scope appearing within an in-scope document: skip those records; continue processing in-scope records in the same document

#### Dependencies

None. This is the foundational feature.

#### NFR Implications

- **Rate limiting:** ingestion must comply with robots.txt on sansad.in and rajyasabha.gov.in; minimum inter-request delay to be specified at architecture stage → flag in NFR
- **Storage:** full-text corpus of 12+ years of parliamentary proceedings is substantial → flag in NFR for architecture sizing
- **Processing time:** bulk ingestion is a long-running operation expected to take hours; exact time budget not specified for v1 but progress logging is required → flag in NFR
- **Resumability:** ingestion must checkpoint per source document and support safe re-runs → flag in NFR as a reliability requirement
- **OCR dependency:** scanned CA PDFs require OCR processing capability → flag in NFR

#### Test Requirements (F01)

- Records dated exactly 2014-01-01 are included in scope; records dated 2013-12-31 are excluded; scope is fixed, not a rolling window
- When the same proceeding is available as both HTML and PDF, exactly one record is created; the HTML-sourced record is retained
- Duplicate detection uses the full compound key; a member speaking twice in the same sitting produces two separate records with distinct `sequence_within_sitting` values
- Checkpoint granularity is per source document; a partially-processed document is fully reprocessed on resume with no duplicates
- A starred Q+A unit must include every supplementary question and response, including across paginated source pages
- `full_text_en` must contain the official translation (not Devanagari text) when a Hindi speech has a translation; `full_text_en` must be null (not empty string) when no translation is available
- `is_translated` must be true whenever `full_text_en` contains any translated content
- "SEVERAL HON. MEMBERS", "AN HON. MEMBER", "SOME HON. MEMBERS" must never appear as `speaker_name` values; presiding officer speeches in presiding capacity must not appear as standalone indexed records
- `ocr_low_confidence: true` records must appear in the search index; they must not be dropped
- Zero hour speeches must carry the individual member's name; "ZERO HOUR" must not appear as `speaker_name`
- Speaker appearing as "Shri Narendra Modi", "Narendra Modi", and "N. Modi" must produce identical `speaker_name` values; honorifics must be stripped; names not in the dictionary produce `speaker_name_unresolved: true` with raw name stored (not null)
- Session name variants for the same session must produce identical `session_name` values; CA records must have `session_name: null`
- A source document with no parseable date must produce zero indexed records and one logged error; ingestion must not halt for subsequent documents
- Completion summary record count must match actual records retrievable from the search index; error log must include source URL for every skipped document

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

**Fields searched**

Queries execute across all of the following fields:

| Field | Description |
|-------|-------------|
| `full_text_en` | Full text of the speech or Q+A exchange |
| `subject` | Debate title or question subject |
| `speaker_name` | Name of the member or minister |
| `minister_name` | Name of the answering minister (Q+A records) |
| `ministry` | Ministry responsible (Q+A records) |

**Term matching and query expansion**

- **Single-term query:** the term is expanded with synonyms and spell corrections (see Feature 04); the expanded set is evaluated as OR across all variants; original term scores at full weight; synonyms at reduced weight; spell corrections at lower weight still
- **Multi-term query:** AND logic applies across original term groups; all original terms must be present in a matching record (or covered by expansions); within each term group, OR logic applies across the original term and its expanded variants
- **Phrase query (double-quoted):** the exact phrase is matched first at full weight; phrase-level synonyms from Feature 04 are added as OR alternatives at reduced weight; individual term expansions within the phrase are not applied separately
- A record matching all original terms outranks a record matching only synonym expansions; a synonym match outranks a spell-correction match

**Relevance ranking factors**

Applied in combined scoring (not strict hierarchy — all factors contribute to a single relevance score):

1. **Original term coverage:** fraction of original query terms matched in the record (vs. covered only by expansions)
2. **Field match location:** match in `speaker_name`, `subject`, `minister_name`, or `ministry` contributes more to the score than a match only in `full_text_en`
3. **Expansion match type:** synonym match contributes more than spell-correction match
4. **Term frequency and passage relevance:** within `full_text_en`, higher term frequency and denser co-occurrence of query terms contribute positively

**Default search scope**

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

#### Test Requirements (F02)

- A record containing "fundamental" and "rights" separated by other words must NOT match a phrase query for `"fundamental rights"`; only records where those words appear consecutively and in that order must match
- Given record A with query term once in `speaker_name` and record B with query term ten times in `full_text_en` only, record A must rank higher
- A match on the original term must produce a higher relevance score than a synonym match; a synonym match must produce a higher relevance score than a spell-correction match — even when term frequency in `full_text_en` is higher for the lower-ranked variant
- A record matching original term 1 and only a synonym expansion of term 2 must rank lower than a record matching both original terms
- "article 370", "Article 370", "ARTICLE 370", and "Article 370" must return identical result sets in identical rank order
- "the right to speech" must execute as a search for "right speech"; a query of entirely stop words must show the validation message
- A query of exactly 501 characters must be truncated to 500 characters before execution; truncation must not be exposed to the user
- A query containing parentheses, brackets, or boolean operators as literal characters must not cause a search error; a query of only special characters must show the validation message
- Active filter selections from Feature 03 must persist when the user modifies the query and resubmits; only an explicit "clear filters" action resets filters

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
  - When only LS and/or RS is selected: minimum selectable date is 2014-01-01
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

**5. Proceeding type**
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

- All five filter dimensions are available on the results page
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
- Date range spans the gap between CA (1946–1950) and LS/RS (2014–present): no records exist in the gap years; result set is the union of CA records within range and LS/RS records within range; no error

#### Dependencies

- Feature 01: canonical `speaker_name` and `session_name` fields in the index
- Feature 02: search query execution that accepts filter constraints

#### NFR Implications

None beyond what is already captured for Feature 02 (search response time target applies to filtered queries as well).

#### Test Requirements (F03)

- When a session filter is active, CA records must be absent from the result set even if CA is selected in the body filter and the query would otherwise match CA records
- A date range of 1948-01-01 to 2015-12-31 must return CA records dated 1948-01-01 to 1950-12-31 and LS/RS records dated 2014-01-01 to 2015-12-31; no records from 1951–2013; no error for the gap years
- When CA is the only selected body, selecting any proceeding type other than "Debate" must produce zero results, not an error
- Speaker filter "Singh" must match any canonicalized speaker name containing "Singh"; a filter value of only whitespace must be treated as empty (no speaker restriction)
- After applying a body filter and refining the query, the body filter must not silently reset; the active filter indicator must still show the filter as active
- Deselecting all bodies or all proceeding types and submitting must show a validation message and not execute a search; the previous result set must remain visible
- From = 2022-06-01 and To = 2021-01-01 must show an inline validation error and must not modify the displayed result set
- A query with body = LS, proceeding type = Starred Question, speaker = "Jairam Ramesh" must return only records satisfying all three constraints simultaneously

---

### F04: Query Expansion

#### Description

Query expansion augments user queries with synonyms and spell corrections before search execution, improving recall for users who search with different terminology than what appears in the indexed records. Expanded terms are OR alternatives carrying reduced relevance weights — see Feature 02 for how weights are integrated into result ranking. The expansion dictionary is seeded with parliamentary domain-specific terms and maintained as a static file in the codebase; updates require a re-deployment.

#### Synonym Dictionary

**Coverage**

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

**Phrase synonyms vs. single-term synonyms**

Phrase synonyms (e.g., "fundamental rights" ↔ "basic rights") apply only when the user's query contains the full phrase or when the user submits a phrase query (quoted or unquoted multi-word sequence matching the phrase). Single-term synonyms (e.g., "PM" ↔ "Prime Minister") apply to individual query terms.

Multi-word synonyms are not broken into individual terms for expansion. "Fundamental rights" as a phrase synonym does not cause "fundamental" alone to expand to anything, nor "rights" alone.

**Dictionary maintenance**

The dictionary is a static structured file (e.g., JSON or YAML) maintained in the codebase. Adding or modifying synonyms requires updating the file and redeploying. The dictionary file is the single source of truth; no runtime editing in v1.

#### Spell Correction

**Scope**

Spell correction applies to individual query terms. It does not apply within phrase queries (quoted terms are matched verbatim; spell correction is suppressed inside quotes).

**Correction method**

Edit-distance based correction: terms within a configurable edit distance from indexed vocabulary are offered as corrections. Phonetic matching is applied additionally for proper nouns (member names, place names) where character-level edit distance is insufficient.

**Correction behaviour**

- A corrected term is added as an OR alternative at a lower weight than synonym expansions
- The original (possibly misspelled) term is still included in the query at full weight; if the original term happens to match records exactly, those matches are returned
- Correction is applied silently — no "did you mean?" prompt is shown in v1; corrections appear in results without user notification
- Over-correction risk: very short terms (fewer than 4 characters) are exempt from spell correction to avoid spurious matches

#### Acceptance Criteria

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

#### Test Requirements (F04)

- A query for "House of the People" must expand to include "Lok Sabha" at synonym weight; bidirectionality must hold for all synonym pairs
- A query for "fundamental rights" must expand using the phrase synonym "basic rights"; it must NOT additionally expand "fundamental" or "rights" as standalone terms; "rights" alone must not expand to "fundamental rights"
- A quoted phrase query containing a misspelled term must not apply spell correction; it must be searched verbatim
- Query terms of 1, 2, or 3 characters must not trigger spell correction; a term of exactly 4 characters must be eligible
- Where both a synonym expansion and a spell correction match the same record, the synonym match contribution must be higher than the spell correction match contribution
- A query for "SC" must generate expansions for all known expansions in the dictionary; the absence of any defined expansion is a bug
- A synonym relationship only hardcoded in application logic (not in the dictionary file) must cause a test to fail
- "MGNREGA" must not trigger the "PM" → "Prime Minister" expansion because "PM" appears as a substring

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
| Session | `session_name` | Shown if available; omitted for CA records |
| Subject / agenda item | `subject` | The debate title or agenda item this speech belongs to |
| Text snippet | derived from `full_text_en` | 2–3 sentences of context around the highest-relevance match; query terms highlighted |
| Translation indicator | `is_translated` | If true, a "Translated from Hindi" label is shown near the snippet |
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
| Session | `session_name` | Shown if available |
| Questioner | `questioner_names` (primary) | First named questioner; additional questioners shown as "+N others" if co-signatories present |
| Questioner party | `questioner_party` | Shown if available |
| Minister and ministry | `minister_name`, `ministry` | "Answered by [Minister Name], [Ministry]" |
| Text snippet | derived from `full_text_en` | 2–3 sentences of context around the highest-relevance match; query terms highlighted |
| Translation indicator | `is_translated` | Shown if true |
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

- Snippet is 2–3 sentences extracted from `full_text_en`, chosen from the passage with the highest density of query term matches
- Query terms (original and expanded matches) are highlighted in the snippet
- If the matched passage is near the start or end of `full_text_en`, the snippet may be shorter than 3 sentences
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
- Translated records show the "Translated from Hindi" label
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

#### Test Requirements (F05)

- When the highest-relevance match for a starred Q+A record is in a supplementary exchange, the displayed snippet must be drawn from the supplementary exchange and the "From supplementary exchange" label must be present; a snippet from the main Q+A must not be shown instead
- A result set of exactly 9,999 records must display an exact count ("9,999 results"), not the approximate form; a result set of exactly 10,000 records must display "10,000+ results"
- A result set of 0 records must display "0 results" and the no-results state message must both be present
- A record with `full_text_en: null` must display "This speech was delivered in Hindi. No English text is available." in the snippet area; all other metadata fields must still display normally
- A `full_text_en` value containing HTML tags (e.g., `<b>`, `<script>`, `&amp;`) must render as plain text in the snippet; tags must not be interpreted as HTML; script tags must not execute
- A URL missing the page parameter must default to page 1 of the query results; a URL with page=3 must load page 3
- A starred question with exactly 1 questioner must not show the "+N others" label; with 3 co-signatories (4 total) must show "+3 others"
- A record with `speaker_name_unresolved: true` must display the raw name in `speaker_name` without any error indicator or blank; display must be identical in format to a resolved name

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

#### Test Requirements (F06)

- Two records with the same date must be ordered by `sequence_within_sitting` ascending in chronological mode and descending in reverse-chronological mode
- Switching from chronological to relevance sort must reorder results by relevance score; the previous date-based order must not be preserved as a tiebreaker within equal-relevance groups
- After setting sort to "Chronological" and refining the query, the sort control must still show "Chronological" as active; new results must be in chronological order
- Changing sort order must not change the result count displayed
- Every new search (fresh query submission) must default to Relevance sort, regardless of the sort option active in the previous search session

---

### F07: Indexing Status Panel

#### Description

A read-only display of the current state of the search index: total records indexed, a per-source breakdown with date coverage, and the date of the last ingestion run. Gives users transparency about what data is available before or after a search. In v1, the index is populated by a one-time bulk load (Feature 01); the status display reflects the actual state of the index at any given time, including partial loads.

#### Displayed Information

| Item | Description |
|------|-------------|
| Total records indexed | Count of all indexed records across all sources |
| Per-source record count | Separate count for CA, Lok Sabha, and Rajya Sabha |
| Per-source date coverage | Earliest and latest indexed date for each source |
| Last ingestion run | Date the ingestion pipeline last completed or was last run |

**Full panel display format:**

```
Search Index Status

Total records indexed: [N]

Constituent Assembly      [N] records    1946–1950
Lok Sabha                 [N] records    Jan 2014 – [Month Year]
Rajya Sabha               [N] records    Jan 2014 – [Month Year]

Last updated: [DD Month YYYY]
```

Counts use thousands separators (e.g., "1,234,567"). If a source has not yet been indexed, its row in the full panel shows "0 records – not yet indexed" rather than a date range.

#### Data Source

The status display reads from a summary record written by the ingestion pipeline (Feature 01) at the end of each run. The summary record stores: per-source record counts, per-source earliest and latest indexed dates, and the ingestion run timestamp. The display does not query the search index directly at page load; it reads the pre-computed summary.

#### Display Surfaces

**Homepage Status Strip**

A condensed summary shown on the homepage, below the search box, giving users a quick overview of index scope before searching. Shows per-source record counts and the last ingestion date. Does not show per-source date coverage. Sources with zero indexed records are still shown in the strip; their count displays as "0 [Body] records".

Format: `[N] Constituent Assembly records · [N] Lok Sabha records · [N] Rajya Sabha records · Last updated: [DD Month YYYY]`

**Full Indexing Status Panel**

The detailed view of index state, accessible from the results page via a persistent footer link labelled "Index status". Displays the full format described in Displayed Information above, including per-source date coverage and the "0 records – not yet indexed" row format for sources with zero records.

#### Acceptance Criteria

- The homepage strip displays per-source record counts and the last updated date
- The full indexing status panel displays total record count, per-source counts, per-source date coverage, and last updated date
- Counts and dates reflect the actual state of the index; they are not hardcoded
- Homepage strip: a source with zero indexed records is shown as "0 [Body] records" in the strip; it is not omitted
- Full panel: a source with zero indexed records shows "0 records – not yet indexed" without a date range
- Last updated date reflects the most recent ingestion run completion timestamp, not the current date
- Both surfaces are read-only; no user interaction is required or available beyond viewing

#### Edge Cases

- Ingestion pipeline has never been run (fresh deployment): all sources shown as "0 [Body] records" in the strip and "0 records – not yet indexed" in the full panel; last updated shown as "Never"
- Ingestion ran but encountered errors and indexed fewer records than expected: the actual indexed count is shown; no error or warning is displayed
- Per-source date coverage spans a gap (e.g., some months missing from the middle of the date range): the displayed range is the earliest and latest indexed date; the panel does not indicate internal gaps
- Summary record is malformed or unreadable: the display shows a "Status unavailable" message in place of the counts and dates; it does not crash or show partial/corrupted data

#### Dependencies

- Feature 01: ingestion pipeline that writes the summary record the display reads from

#### NFR Implications

None. The display reads a pre-computed summary; no real-time index query is performed.

#### Test Requirements (F07)

- The display must not issue a query to the search index at page load; it must read from the pre-computed summary record; disabling the search index must not prevent the last known status data from showing
- On a fresh deployment where ingestion has never been run, the "Last updated" field must display "Never", not a null value, blank, or a default date
- **Full panel only:** a source with zero indexed records must display "0 records – not yet indexed" with no date range; an empty date range string or a placeholder date is a bug
- **Homepage strip:** a source with zero indexed records must still appear in the strip as "0 [Body] records"; it must not be omitted
- The total records count displayed in the full panel must equal the sum of the three per-source counts; a discrepancy is a bug
- The "Last updated" date must reflect the ingestion run completion timestamp; it must not update when the page is loaded, when a search is run, or at any other time other than after an ingestion pipeline run

---

### F08: Search History

#### Description

Cookie-based recent searches and saved searches. No sign-in is required. All data is stored client-side in cookies; nothing is sent to the server. Recent searches are recorded automatically when a query is submitted. Saved searches are explicitly bookmarked by the user and persist until deleted. Both are accessible from the homepage and the results page.

#### Recent Searches

**Storage and limits**
- Automatically recorded each time a search query is submitted (regardless of whether any results were returned)
- Maximum 10 entries stored; when the limit is exceeded, the oldest entry is removed
- Duplicate queries: if the same query string is submitted again, the existing entry is updated to the most recent timestamp; only one entry per unique query string is maintained
- Cookie lifetime: 30 days from the most recent submission; entries older than 30 days are not displayed
- What is stored per entry: query text and submission timestamp; filter state is not stored with recent searches

**Actions**
- Click a recent search entry to re-run that query (with default filters and default sort — not with any previously active filter state)
- Delete an individual recent search entry
- Clear all recent searches at once

#### Saved Searches

**Storage and limits**
- Explicitly saved by the user from the results page
- Maximum 20 saved searches stored
- When the 20-entry limit is reached, the user must delete an existing saved search before a new one can be saved; the save action is disabled with an explanatory message when at the limit
- No expiry; saved searches persist until the user deletes them
- Cookie lifetime: persistent (no expiry date set on the cookie); persists until cookie is cleared by the browser

**What is stored per saved search**
- Name: defaults to the query text; user can rename to a custom label (max 60 characters)
- Query text
- Active filter state at the time of saving (legislative body, date range, speaker, session, proceeding type selections)
- Save timestamp

**Actions**
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

#### Test Requirements (F08)

- Submitting the same query string three times must result in exactly one entry in recent searches, with the timestamp of the third submission
- With 10 recent searches already stored, submitting an 11th (distinct) query must remove the oldest entry and add the new one; the list must remain at exactly 10 entries
- Re-running a recent search must execute with all filters at their defaults, regardless of what filters were active when originally submitted
- A saved search created with body = Rajya Sabha, proceeding type = Starred Question, date from = 2020-01-01 must restore exactly those filter selections when re-run
- With exactly 20 saved searches stored, the save action must be visibly disabled and show an explanatory message; it must not create a 21st entry
- Saving the same query text twice must create two separate saved search entries; the second save must not overwrite the first
- When cookies are blocked, recent and saved searches must not be shown; no error message about cookies must be displayed; search and results must function normally
- A saved search name of exactly 60 characters must be accepted; 61 characters must be rejected without losing the save action
- Re-running a saved search with an unrecognised proceeding type value must execute the search ignoring that filter value; it must not throw an error

---

## Non-Functional Requirements

### Performance

**PERF-1: Search response time**
Search results must be returned within 2 seconds at p95, measured from query submission to full result list rendered in the browser, across the full indexed corpus. This target applies with query expansion active (synonyms + spell corrections). Architecture must account for the additional scoring computation introduced by query expansion.

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
The ingestion pipeline must comply with robots.txt on sansad.in and rajyasabha.gov.in. Minimum inter-request delay must be specified at architecture stage. HTTP 429 responses must trigger exponential backoff and retry, not a skip.

### Processing

**INF-P1: Bulk ingestion duration**
Bulk ingestion is a long-running operation. No maximum time constraint is specified for v1, but real-time progress logging is required. The operation must not require human supervision to complete.

**INF-P2: OCR capability**
Some Constituent Assembly volumes are scanned PDFs requiring OCR. The ingestion pipeline must include an OCR component. OCR accuracy is best-effort for scanned documents; low-confidence records must be flagged, not dropped.

### Scalability

**SCALE-1: Concurrent search load**
Search must remain within the PERF-1 response time target under concurrent user load. Exact concurrency targets are an architecture-stage deliverable.

### Privacy

**PRIV-1: No server-side storage of user search data**
Search queries, filter selections, and search history are not persisted server-side in v1. All search history (recent searches and saved searches) is stored client-side in browser cookies only. No user identifiers are created or stored.

---

## Future Features

Features explicitly deferred from v1. Not in scope for any v1 build phase.

### Data Scope Expansion

- **Full parliamentary history:** extend LS and RS coverage beyond 2014 to include all available records (potentially back to 1952 for Lok Sabha)
- **Ongoing ingestion:** scheduled pipeline to ingest new parliamentary sessions automatically as they are published on sansad.in and rajyasabha.gov.in

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

*Generated: 2026-05-29 | PRD v1.1 | Changes from v1.0: F05 edge case removed (metadata-field highlighting); F07 updated to distinguish homepage status strip from full indexing status panel.*
