# SansadSearch — Product Requirements Document

**Version:** v1.0  
**Date:** 2026-05-28  
**Git tag:** — (tag after committing)  

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
4. [Non-Functional Requirements](#4-non-functional-requirements)
5. [Future Features](#5-future-features)

---

## 1. Overview

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

## 2. Objectives

1. Make Indian parliamentary records discoverable through full-text keyword search across all three source corpora.
2. Serve both domain experts (who search using precise parliamentary terminology) and general users (who search in plain language) without requiring expertise.
3. Enable filtering by date range, legislative body, speaker, and proceeding type so users can narrow large result sets to relevant records.
4. Display results with enough context — speaker identity, session, subject, and a passage snippet — that users can assess relevance without opening the source document.
5. Provide verifiable citations: every result links directly to the original source document on sansad.in or rajyasabha.gov.in.
6. Index the Constituent Assembly debates in full, giving researchers access to the complete constitutional drafting record in searchable form.

---

## 3. Functional Requirements

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
| `speaker_name` | Member's full canonical name (honorifics stripped) |
| `speaker_party` | Party or group affiliation |
| `speaker_constituency_or_state` | Constituency (LS), state (RS), or null (CA) |
| `speaker_role` | member \| minister \| presiding_officer |
| `sequence_within_sitting` | Integer position of this speech within the sitting's proceedings, derived from document order (1-based) |
| `full_text_en` | Full English text of the speech; see Language Handling |
| `is_translated` | true if `full_text_en` contains or includes official English translation of Hindi portions |
| `has_untranslated_content` | true if any portion of the speech could not be indexed due to absent translation |
| `speaker_name_unresolved` | true if `speaker_name` could not be matched to a canonical form in the names dictionary |
| `source_url` | URL of the original HTML page or PDF |
| `page_reference` | Page number in source PDF; null for HTML sources |
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

**Q+A exchange unit (unstarred question):** same as starred question except `proceeding_type: unstarred_question`, `full_text_en` contains question text and written answer only (no supplementaries), and uses a single `questioner_name` field rather than an array.

#### Language Handling

Official parliamentary records include English translations of speeches delivered in Hindi. The pipeline applies the following rules in order:

1. **Speech in English:** store verbatim in `full_text_en`; `is_translated: false`
2. **Speech in Hindi with official English translation present:** store the translation in `full_text_en`; `is_translated: true`
3. **Bilingual speech:** store all English text — both original English portions and translated Hindi portions — in `full_text_en`; `is_translated: true`
4. **Hindi speech with no translation available:** `full_text_en: null`; `has_untranslated_content: true`; record is still indexed

#### Canonicalization

**Speaker names:** Strip honorific prefixes (Shri, Smt., Dr., Prof., Adv., Kumari) and resolve abbreviation/ordering variants using a canonical names dictionary seeded from official LS, RS, and CA member lists. Unresolved names are stored as found with `speaker_name_unresolved: true`.

**Session names:** Canonicalize to "[Session Type] Session [Year]" format, with multi-part sessions as "(Part [N])". CA records have `session_name: null`.

#### Records Not Indexed as Standalone Units

- Unattributed speech: "SEVERAL HON. MEMBERS", "AN HON. MEMBER", "SOME HON. MEMBERS"
- Presiding officer interventions in their presiding capacity
- Procedural interruptions: points of order, rulings, division votes

#### Deduplication

HTML source preferred over PDF when both are available for the same proceeding. Duplicate detection key: source + date + sitting_number + proceeding_type + speaker_name + sequence_within_sitting (or question_number for Q+A units).

#### Acceptance Criteria

- All 12 volumes of CA debates are ingested; speeches indexed per individual member contribution
- All LS and RS records dated 2014-01-01 or later are ingested across all proceeding types listed
- Every indexed record has: source, proceeding_type, date, subject, full_text_en (or null with has_untranslated_content flag), source_url
- Starred Q+A records include the complete exchange: main question + answer + all supplementary questions and responses
- Re-running ingestion on a fully indexed corpus produces zero new records and zero duplicate records
- Progress log is written in real time; a completion summary is printed at the end

#### Edge Cases

- Scanned CA PDFs: OCR-extracted; low-confidence records flagged (`ocr_low_confidence: true`) but still indexed
- Missing speaker attribution: index with `speaker_name: null`; do not skip
- Missing date: log as error and skip the record; date is required
- HTTP 4xx (excluding 429): log and skip; no retry
- HTTP 5xx: retry up to 3 times with exponential backoff; log and skip if all fail
- HTTP 429: exponential backoff and retry; do not skip
- Malformed HTML/PDF: log parsing error with URL; skip
- Records outside date scope within an in-scope document: skip individual records; continue processing

#### Dependencies

None. This is the foundational feature.

#### NFR Implications

Rate limiting compliance, corpus storage sizing, bulk processing time, resumability, OCR capability — all flagged in NFR section.

---

#### F01 Test Requirements

- Date range: records dated exactly 2014-01-01 are in scope; records dated 2013-12-31 are excluded; scope is fixed, not a rolling window
- Deduplication: HTML preferred over PDF; compound key (source + date + sitting_number + proceeding_type + speaker_name + sequence_within_sitting); a member speaking twice in the same sitting produces two records with distinct sequence_within_sitting values
- Resumability: checkpoint is per source document; partially-processed documents produce no duplicates on resume; record count after clean run equals count after interrupted-then-resumed run
- Starred question completeness: all supplementaries included, including those paginated across multiple source pages
- Language handling: Hindi speech with translation → `full_text_en` contains translation text, not Devanagari; no translation → `full_text_en` is null (not empty string); `is_translated: true` whenever any translated content is present; bilingual speech concatenates original English and translated Hindi portions in order
- Unattributed speech: "SEVERAL HON. MEMBERS", "AN HON. MEMBER", "SOME HON. MEMBERS" must never appear as `speaker_name`; presiding officer speeches must not be standalone indexed records
- OCR-flagged records: `ocr_low_confidence: true` records appear in the index; silent omission is a bug; `ocr_low_confidence: false` for digital/HTML sources
- Zero hour attribution: individual member name in `speaker_name`; "ZERO HOUR" must not appear as `speaker_name`
- Missing date: zero records indexed from that document; one logged error; ingestion continues for subsequent documents
- Progress log: completion summary count matches actual index count; every skipped document has a URL in the error log
- Speaker name canonicalization: same member appearing as "Shri Narendra Modi", "Narendra Modi", "N. Modi" produces identical `speaker_name` values; honorifics stripped; unresolved names stored as found with `speaker_name_unresolved: true`
- Session name canonicalization: variant formats for the same session produce identical `session_name`; CA records have `session_name: null`

---

### F02: Full-text Search

#### Description

The core search interface. Users enter keyword queries; the system executes full-text search across the indexed corpus and returns a ranked result list. Query expansion (synonyms and spell corrections) is integrated into the search execution model, with expanded terms carrying reduced relevance weights. Feature 04 defines the synonym dictionary and correction rules.

#### User Flows

**Standard search:**
1. User arrives at homepage; a prominent search box is visible
2. User types a query (minimum 2 characters) and presses Enter or clicks Search
3. System executes search with query expansion and returns a ranked result list
4. User can apply filters (F03), change sort order (F06), and inspect results (F05)

**Refinement:**
1. User on results page modifies the query and resubmits
2. New search executes; active filter selections persist; filters reset only by explicit clear action

**No results:**
1. Search executes; no records match
2. System shows explicit no-results state with suggestion to try fewer terms, different terms, or remove filters

**Invalid query:**
1. User submits query shorter than 2 characters or empty box
2. System shows inline validation message; no search executed

#### Search Execution Model

**Fields searched:** `full_text_en`, `subject`, `speaker_name`, `minister_name`, `ministry`

**Term matching and query expansion:**
- Single-term: expanded with synonyms and spell corrections (F04); OR across all variants; original term at full weight; synonyms at reduced weight; corrections at lower weight still
- Multi-term: AND across original term groups; OR within each term group across original term and its expansions
- Phrase query (double-quoted): exact phrase at full weight; phrase-level synonyms as OR alternatives at reduced weight; individual term expansions within the phrase are not applied separately
- A record matching all original terms outranks one matching only synonym expansions; synonym match outranks spell-correction match

**Relevance ranking factors** (combined scoring):
1. Original term coverage: fraction of original query terms matched vs. covered only by expansions
2. Field match location: `speaker_name`, `subject`, `minister_name`, `ministry` match > `full_text_en` match
3. Expansion match type: synonym match > spell-correction match
4. Term frequency and passage relevance within `full_text_en`

**Default scope:** all sources (CA + LS + RS); users narrow via F03.

#### Acceptance Criteria

- Search box visible and accessible on homepage; persistent pre-populated search box on results page
- Queries ≥ 2 non-whitespace characters execute and return results
- Queries < 2 non-whitespace characters: inline validation message; no search executed
- Empty submission: inline validation message; no search executed
- Record matching all original query terms ranks above record matching only synonym expansions
- Phrase query returns only records with exact word sequence; non-adjacent matches excluded
- Case-insensitive: "Fundamental Rights" and "fundamental rights" return identical result sets
- No-results state: explicit message and suggestions; not an error page
- Backend error: explicit "Search is temporarily unavailable" message with retry option; not a blank page
- Search response time: ≤2 seconds at p95 across full indexed corpus

#### Edge Cases

- Stop-words-only query: strip stop words; if nothing remains, show validation message
- Query > 500 characters: truncate to 500 and execute; no error shown
- Special characters: strip or escape; must not cause search error
- Identical resubmission: execute again; no stale cached result

#### Dependencies

- F01: indexed corpus
- F04: synonym dictionary and spell-correction rules (degrades to exact-match without F04)

---

#### F02 Test Requirements

- Phrase query non-adjacency: "fundamental rights" phrase query must NOT match records where "fundamental" and "rights" appear non-consecutively
- Field boost vs. term frequency: record with query term once in `speaker_name` ranks higher than record with query term ten times in `full_text_en` only
- Expansion weight ordering: original term > synonym > spell correction in relevance score; holds even when term frequency in `full_text_en` favours the lower-ranked variant
- AND logic with partial expansion: record matching original term 1 + only synonym of term 2 ranks lower than record matching both original terms; record matching only synonym expansions for all terms ranks lower than one matching at least one original term
- Case insensitivity: "article 370", "Article 370", "ARTICLE 370" return identical result sets in identical rank order
- Stop word boundary: "the right to speech" executes as "right speech"; a query of only stop words shows validation message, not an empty result list
- Query truncation: 501-character query truncated to 500 and executed without error; truncation not shown to user
- Special character handling: query containing parentheses, brackets, or boolean operators as literals does not cause an error
- Filter persistence: active F03 filter selections persist when query is refined; only explicit clear resets filters

---

### F03: Search Filters

#### Description

Filters allow users to narrow search results by legislative body, date range, speaker, session, and proceeding type. All filters combine with AND and with the search query. Filter state persists across query refinements and resets only by explicit clear action.

#### Filter Dimensions

**1. Legislative body** — multi-select: CA, Lok Sabha, Rajya Sabha; default all selected

**2. Date range** — From/To date pickers; both optional; constrained to indexed scope:
- Only CA selected: 1946-01-01 – 1950-12-31
- Only LS/RS: minimum 2014-01-01
- CA + LS/RS: full range 1946-01-01 to present
- From > To: inline validation; filter not applied

**3. Speaker** — free text; case-insensitive substring match against canonical `speaker_name`; no autocomplete in v1; note shown to search without honorifics

**4. Session** — free text; case-insensitive substring match against `session_name`; CA records have null `session_name` and are excluded when session filter is active

**5. Proceeding type** — multi-select: Debate, Starred Question, Unstarred Question, Zero Hour, Short Notice Question, Calling Attention, Short Duration Discussion, Adjournment Motion, Private Member Bill; default all selected; when only CA selected, only "Debate" is available

#### Filter Combination Logic

All active filters AND together and AND with the search query.

#### Acceptance Criteria

- All five filter dimensions available on results page
- Active filters visibly indicated; "clear filters" resets all to defaults; individual filter values removable
- Filter state persists across query refinements; only explicit clear resets
- From > To: validation message; filter not applied
- Proceeding type options disable correctly when only CA selected in body filter
- Session filter active: CA records excluded from result set
- Result count reflects filtered set

#### Edge Cases

- All proceeding types deselected: validation message; no search executed
- All bodies deselected: validation message; no search executed
- Date range spanning gap years (1951–2013): no error; union of CA and LS/RS records within range
- Session filter value partially matches multiple sessions: all matching sessions included

#### Dependencies

- F01: canonical `speaker_name` and `session_name` fields
- F02: search execution accepting filter constraints

---

#### F03 Test Requirements

- Session filter excludes CA: when session filter is active, CA records absent even if CA is selected in body filter
- Date range gap: range 1948-01-01 to 2015-12-31 returns CA records through 1950 and LS/RS records from 2014; no records from 1951–2013; no error
- Proceeding type constraint with only CA: selecting non-Debate types when only CA selected produces zero results, not an error
- Speaker substring: "Singh" matches all canonical names containing "Singh"; whitespace-only speaker input treated as empty filter
- Filter persistence: after applying RS body filter and refining query, body filter still shows RS active; results contain only RS records
- Zero-selection validation: deselecting all bodies or all proceeding types shows validation; previous result set remains visible
- Date validation: From = 2022-06-01, To = 2021-01-01 shows inline error; result set not modified
- Combined AND: body=LS + proceeding=Starred Question + speaker="Jairam Ramesh" returns only LS starred questions by that speaker; LS debates and RS starred questions by same speaker excluded

---

### F04: Query Expansion

#### Description

Query expansion augments user queries with synonyms and spell corrections before search execution, improving recall for users searching with different terminology than what appears in indexed records. Expanded terms are OR alternatives carrying reduced relevance weights (see F02 for ranking integration). The expansion dictionary is a static file in the codebase; updates require re-deployment.

#### Synonym Dictionary

Synonyms are bidirectional. The dictionary covers:

**Legislative bodies:** "Lok Sabha" ↔ "House of the People" ↔ "Lower House"; "Rajya Sabha" ↔ "Council of States" ↔ "Upper House"; "Constituent Assembly" ↔ "CA"

**Constitutional terminology:** "fundamental rights" ↔ "basic rights" ↔ "Part III rights"; "Directive Principles" ↔ "DPSP" ↔ "Directive Principles of State Policy"; "Preamble" ↔ "preamble to the Constitution"

**Parliamentary procedure:** "starred question" ↔ "oral question"; "unstarred question" ↔ "written question"; "zero hour" ↔ "zero-hour"; "private member bill" ↔ "private member's bill"; "calling attention" ↔ "calling attention motion"; "adjournment motion" ↔ "adjournment"; "division" ↔ "vote"

**Abbreviations:** PM ↔ Prime Minister; CM ↔ Chief Minister; SC ↔ Scheduled Castes; ST ↔ Scheduled Tribes; SC/ST ↔ Scheduled Castes and Scheduled Tribes; OBC ↔ Other Backward Classes ↔ Other Backward Communities; EWS ↔ Economically Weaker Sections; GST ↔ Goods and Services Tax; CAG ↔ Comptroller and Auditor General; CBI ↔ Central Bureau of Investigation; ED ↔ Enforcement Directorate; FIR ↔ First Information Report; PIL ↔ Public Interest Litigation; Art. ↔ Article; Sec. ↔ Section; Cl. ↔ Clause

**Well-known legislation:** RTI ↔ Right to Information ↔ Right to Information Act; RTE ↔ Right to Education ↔ Right to Education Act; MGNREGA ↔ NREGA ↔ Mahatma Gandhi National Rural Employment Guarantee Act; POCSO ↔ Protection of Children from Sexual Offences; IPC ↔ Indian Penal Code; CrPC ↔ Code of Criminal Procedure; BNS ↔ Bharatiya Nyaya Sanhita; BNSS ↔ Bharatiya Nagarik Suraksha Sanhita

Phrase synonyms apply only when the full phrase is present in the query. Multi-word synonyms are not broken into individual terms for expansion.

#### Spell Correction

- Edit-distance based correction for individual query terms; phonetic matching additionally for proper nouns
- Corrections added as OR alternatives at lower weight than synonyms
- Spell correction suppressed inside quoted phrases
- Terms fewer than 4 characters are exempt from spell correction

#### Acceptance Criteria

- "PM" query returns "Prime Minister" records at lower weight than "PM" records
- "fundamental rights" returns "basic rights" records at lower weight
- "Parliment" (misspelled) returns "Parliament" records at reduced weight
- Quoted phrase query applies phrase-level synonyms only; individual term synonyms not applied inside quotes
- Terms < 4 characters not spell-corrected
- Dictionary file is the only source of synonym definitions

#### Edge Cases

- Ambiguous abbreviation: expand to all known expansions; ranking determines relevance
- Bidirectional: user searching "House of the People" expands to "Lok Sabha" at synonym weight
- Substring non-expansion: "PM" inside "MGNREGA" does not trigger PM expansion
- Correction that is also a dictionary synonym: correction is OR alternative at correction weight; correction's synonym is further OR at synonym weight

#### Dependencies

- F02: search execution model consuming expansion output

---

#### F04 Test Requirements

- Bidirectionality: "House of the People" expands to "Lok Sabha"; "Lok Sabha" expands to "House of the People"; must hold for all synonym pairs
- Phrase synonym isolation: "fundamental rights" expands using phrase synonym "basic rights" but does NOT expand "fundamental" or "rights" individually; "rights" alone does not expand via the phrase synonym
- Spell correction suppression: quoted phrase with misspelled term searched verbatim; no correction applied
- Short term exemption: 1, 2, 3-character terms not spell-corrected; 4-character terms eligible
- Correction weight below synonym weight: same record matched by both synonym and correction; synonym contribution higher
- Ambiguous abbreviation: "SC" generates all defined expansions; absence of any defined expansion is a bug
- Dictionary as sole source: synonym hardcoded only in application logic (not in dictionary file) must fail a test
- Substring non-expansion: "MGNREGA" does not trigger "PM" → "Prime Minister" expansion

---

### F05: Result Display

#### Description

Each search result is displayed as a card showing metadata, a contextual text snippet with matched terms highlighted, and a link to the original source document. Results are paginated. The display gives users enough context to assess relevance without opening the source.

#### Result Card: Speech Record

Speaker name (canonical) • Party • Constituency/state (if available) | Body | Proceeding type | Date (DD Month YYYY) | Session (if available)  
Subject: [debate title or agenda item]  
Snippet: 2–3 sentences with highlighted query terms  
[Translation indicator if `is_translated: true`]  
[View source → new tab]

#### Result Card: Q+A Exchange Record

Q. [number]: [subject] | Proceeding type | Body | Date | Session  
Questioner: [primary name] ([party]) +N others if co-signatories | Answered by: [minister], [ministry]  
Snippet: 2–3 sentences with highlighted query terms; "From supplementary exchange" label if match is from a supplementary  
[Translation indicator if `is_translated: true`]  
[View source → new tab]

#### Proceeding Type Labels

debate → Debate | starred_question → Starred Question | unstarred_question → Unstarred Question | zero_hour → Zero Hour | short_notice_question → Short Notice Question | calling_attention → Calling Attention | short_duration_discussion → Short Duration Discussion | adjournment_motion → Adjournment Motion | private_member_bill → Private Member Bill

#### Snippet Generation

- 2–3 sentences from `full_text_en` chosen from the passage with highest query term density; matched terms highlighted
- `full_text_en: null`: shows "This speech was delivered in Hindi. No English text is available." in place of snippet
- Q+A match in supplementary exchange: snippet drawn from supplementary with "From supplementary exchange" label

#### Pagination

- 20 results per page
- Result count: exact for ≤9,999; "10,000+" for ≥10,000
- Pagination controls: previous/next, current page, total page count (if ≤500 pages)
- URL reflects current page number (shareable/bookmarkable)

#### Acceptance Criteria

- Every card displays: body, proceeding type, date, subject, snippet with highlighted terms, working source link
- "View source" opens original document in new tab
- `full_text_en: null` records show placeholder message, not blank snippet
- Translated records show "Translated from Hindi" label
- Result count shown at top of result list
- Direct URL to a specific page loads the correct page

#### Edge Cases

- Missing party/constituency: fields omitted; no placeholder
- `speaker_name: null`: shows "Speaker unknown"
- HTML/special chars in snippet: escaped; not rendered as HTML
- Missing source URL: "View source" link not shown; no broken link
- `speaker_name_unresolved: true`: raw name displayed normally

#### Dependencies

- F01: indexed records with all metadata fields
- F02: search execution providing ranked results and match position data

---

#### F05 Test Requirements

- Snippet from supplementary: when highest-relevance match is in supplementary exchange, snippet drawn from supplementary; "From supplementary exchange" label present; main Q+A snippet must not be shown instead
- Result count threshold: 9,999 results → exact count; 10,000 results → "10,000+"; 0 results → "0 results" with no-results message also present
- Untranslated speech placeholder: `full_text_en: null` shows placeholder message; snippet area not empty/blank/absent; all other metadata fields display normally
- HTML sanitisation: `full_text_en` containing HTML tags renders as plain text; script tags do not execute
- Page URL persistence: direct URL to page 3 of results loads page 3 without re-entry of query; URL must encode both query and page number
- Co-signatory display: 1 questioner → no "+N others" label; 4 total questioners → "+3 others"
- Speaker name unresolved: `speaker_name_unresolved: true` displays raw name without error indicator; format identical to resolved name display

---

### F06: Sorting

#### Description

Users can sort search results by relevance (default), chronological order (oldest first), or reverse chronological order (newest first). Sort state persists across query refinements and resets only by explicit change.

#### Sort Options

| Option | Primary key | Secondary key |
|--------|-------------|---------------|
| Relevance (default) | Relevance score descending | — |
| Chronological | Date ascending | `sequence_within_sitting` ascending |
| Reverse chronological | Date descending | `sequence_within_sitting` descending |

#### Acceptance Criteria

- Three sort options available on results page
- Default sort on every new search: Relevance
- Changing sort re-orders results without changing count or clearing filters
- Sort selection persists across query refinements
- Chronological and reverse-chronological use date as primary key, `sequence_within_sitting` as secondary

#### Edge Cases

- All results share same date: `sequence_within_sitting` is the effective sort key
- Relevance sort: records not additionally sorted by date; tiebreaking within equal-relevance groups is undefined

#### Dependencies

- F02: relevance scores for relevance sort
- F01: `date` and `sequence_within_sitting` for date-based sorts

---

#### F06 Test Requirements

- Secondary sort key: two records with same date ordered by `sequence_within_sitting` in both chronological and reverse-chronological modes
- Relevance sort isolation: switching from chronological to relevance does not preserve date order as tiebreaker
- Sort persistence: user sets chronological, refines query; sort control still shows "Chronological"; results in chronological order
- Result count invariance: changing sort does not change result count for same query and filter state
- Default sort on new search: every new search defaults to Relevance regardless of prior sort selection

---

### F07: Indexing Status Panel

#### Description

A read-only panel displaying: total records indexed, per-source counts and date coverage, and the date of the last ingestion run. Reads from a pre-computed summary record written by the ingestion pipeline; does not query the search index at page load.

#### Display Format

```
Search Index Status

Total records indexed: [N]

Constituent Assembly      [N] records    1946–1950
Lok Sabha                 [N] records    Jan 2014 – [Month Year]
Rajya Sabha               [N] records    Jan 2014 – [Month Year]

Last updated: [DD Month YYYY]
```

Counts use thousands separators. Unindexed source shows "0 records – not yet indexed" without a date range.

#### Placement

- Homepage, below the search box
- Accessible from the results page via a persistent footer link ("Index status")

#### Acceptance Criteria

- Panel displays total count, per-source counts, per-source date coverage, last updated date
- Counts and dates reflect actual index state; not hardcoded
- Zero-records source: "0 records – not yet indexed"; no date range
- Last updated: reflects ingestion run completion timestamp, not current date
- Read-only; no user interaction

#### Edge Cases

- Ingestion never run: all sources show "0 records – not yet indexed"; last updated shows "Never"
- Summary record malformed or unreadable: panel shows "Status unavailable"; no crash or partial data
- Internal coverage gaps: panel shows earliest and latest indexed date; gaps not indicated

#### Dependencies

- F01: ingestion pipeline writes the summary record

---

#### F07 Test Requirements

- Pre-computed summary: panel reads from summary record; disabling search index must not prevent status panel from loading
- Never-run state: last updated displays "Never"; not null, blank, or a default date
- Zero-source row: "0 records – not yet indexed" with no date range; placeholder date is a bug
- Count accuracy: total = sum of three per-source counts; discrepancy is a bug
- Ingestion timestamp: "Last updated" only changes after an ingestion pipeline run completes; not at page load or search execution

---

### F08: Search History

#### Description

Cookie-based recent searches and saved searches. No sign-in required. All data stored client-side in cookies; nothing sent to server. Recent searches recorded automatically; saved searches explicitly bookmarked by the user.

#### Recent Searches

- Auto-recorded on every submitted query; max 10 entries; FIFO rotation
- Duplicate queries: update timestamp and position; one entry per unique query string
- Cookie lifetime: 30 days from most recent submission
- Stores: query text and timestamp only (no filter state)
- Actions: click to re-run (with default filters), delete individual entry, clear all

#### Saved Searches

- Explicitly saved from results page; max 20 entries
- Save disabled (with message) when at 20-entry limit
- No expiry; persistent until user deletes
- Stores: name (default = query text, editable up to 60 chars), query text, active filter state, save timestamp
- Actions: save, re-run (restores query + filter state, default sort), rename, delete

#### Cookie Storage Constraints

- Recent searches and saved searches in separate cookies; combined total must not exceed 4KB
- Near capacity: oldest recent searches trimmed first; saved searches not auto-removed
- Cookies disabled: feature silently unavailable; application functions normally; no error shown

#### Acceptance Criteria

- Every submitted query added to recent searches automatically
- Recent list shows ≤10 entries, most recent first; duplicate query updates position/timestamp
- Saved searches restore query text and filter state exactly
- Saved search name defaults to query text; editable to 60 characters
- Save disabled at 20-entry limit with explanatory message
- All features work without authentication; no server-side data storage

#### Edge Cases

- Browser cookies cleared: all history lost; application continues normally
- Saved search with stale filter values: invalid values silently ignored; search executes
- Same query saved twice: two separate entries allowed
- Query up to 500 characters: stored and preserved for re-execution; visually truncated in display if needed

#### Dependencies

- F02: search execution accepting query string
- F03: filter state model for saved search restore

---

#### F08 Test Requirements

- Duplicate deduplication: same query submitted 3 times → exactly 1 recent entry with timestamp of third submission
- FIFO rotation: 10 entries stored; 11th distinct query removes oldest; list remains at 10
- Recent search re-runs with default filters: re-running a recent search executes with all filters at defaults regardless of original filter state
- Saved search filter restoration: saved search with body=RS, proceeding=Starred Question, from=2020-01-01 restores exactly those filter values on re-run; result set equivalent to manual filter setting
- Save disabled at limit: exactly 20 saved searches stored; save action visibly disabled; no 21st entry creatable by any means
- Same query saved twice: produces two separate entries; second does not overwrite first
- Cookie-disabled behaviour: no cookie-related error shown; search box and results function normally
- Saved search name length: 60 characters accepted; 61 characters rejected without losing the save action
- Stale filter value: unrecognised proceeding type in saved search does not cause error; search runs with that filter value ignored

---

## 4. Non-Functional Requirements

### Performance

**PERF-1: Search response time**
Search results must be returned within 2 seconds at p95, measured from query submission to full result list rendered in the browser, across the full indexed corpus. This target applies with query expansion active (synonyms + spell corrections). Architecture must account for the additional scoring computation introduced by query expansion.

### Reliability

**INF-R1: Ingestion resumability**
The bulk ingestion pipeline must be resumable from a per-document checkpoint. An interrupted run re-run against the same corpus must produce an identical final record count with no duplicates. Safe re-runs are a hard requirement.

### Security

*No authentication or user data storage in v1. No specific security NFRs beyond standard web application hardening (XSS prevention in result display, no server-side user data storage).*

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
Some Constituent Assembly volumes are scanned PDFs requiring OCR. The ingestion pipeline must include an OCR component. OCR accuracy is best-effort; low-confidence records must be flagged, not dropped.

### Scalability

**SCALE-1: Concurrent search load**
Search must remain within the PERF-1 response time target under concurrent user load. Exact concurrency targets are an architecture-stage deliverable.

### Privacy

**PRIV-1: No server-side storage of user search data**
Search queries, filter selections, and search history are not persisted server-side in v1. All search history (recent searches and saved searches) is stored client-side in browser cookies only. No user identifiers are created or stored.

---

## 5. Future Features

### Data Scope Expansion

- **Full parliamentary history:** extend LS and RS coverage beyond 2014 to all available records
- **Ongoing ingestion:** scheduled pipeline to ingest new sessions automatically as published

### Language Support

- **Hindi search:** index Hindi-language text and support queries in Devanagari; requires separate tokenisation, stop-word lists, and synonym dictionary

### User Accounts and Personalisation

- **User authentication:** persistent cross-device search history and saved searches
- **Cross-device sync:** saved searches accessible from any device when signed in
- **Search alerts:** notify users when new records matching a saved search are indexed

### Search Experience

- **Autocomplete / search-as-you-type:** query suggestions and speaker name completions as the user types
- **Faceted result counts:** count of results per filter value shown in the filter panel
- **Related results / "More like this":** thematically similar records to a viewed result
- **Member profile pages:** dedicated page per member showing all indexed speeches and questions

### Platform

- **Mobile UI:** responsive layout optimised for small screens
- **Public API:** REST or GraphQL API for third-party integrations

### Administration

- **Admin interface for synonym dictionary:** in-application UI for editing synonyms without re-deployment
- **Ingestion monitoring dashboard:** real-time visibility into ingestion pipeline progress for operators

---

## Footer

Generated: 2026-05-28  
PRD version: v1.0  
Sections compiled from: `prd/sections/01-overview.md`, `02-objectives.md`, `03-functional-requirements/01–08`, `04-non-functional-requirements.md`, `05-future-features.md`  
Next version will include a diff file in `prd/diffs/`.
