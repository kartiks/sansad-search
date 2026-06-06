# SansadSearch — Product Requirements Document

**Version:** 3.0  
**Date:** 2026-06-06  
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

## 2. Objectives

1. Make Indian parliamentary records discoverable through full-text keyword search across all three source corpora.
2. Serve both domain experts (who search using precise parliamentary terminology) and general users (who search in plain language) without requiring expertise.
3. Enable filtering by date range, legislative body, speaker, and proceeding type so users can narrow large result sets to relevant records.
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

**Stage control**

| `--stage` value | Behavior |
|-----------------|----------|
| `fetch` | Stage 1 only: discover and download source documents; write to `raw_documents` |
| `process` | Stage 2 only: read from `raw_documents`; parse, segment, and index |
| `all` | Stage 1 then Stage 2 sequentially for each source (default) |

**Stage 1 (fetch) flow**

1. Discover documents for the selected corpus(es)
2. Check `raw_documents` PK for each `canonical_doc_id`; skip if already present
3. Fetch new documents from source with rate limiting
4. Extract text and metadata
5. Apply date-window gate when `--date-from`/`--date-to` are provided: write to `raw_documents` only if the document's date falls within the window; skip out-of-window documents
6. Write raw content (extracted text + metadata JSON) to `raw_documents`

Stage 1 does not write to `speeches`, `qa_exchanges`, or the SQLite checkpoint store. It does not update `index_status`.

**Stage 2 (process) flow**

1. Read `raw_documents` rows for the selected corpus; apply `--date-from`/`--date-to` window if provided
2. Skip documents already checkpointed as processed in the SQLite `processed_documents` store
3. Segment each document into speech and Q+A exchange units
4. Apply adjacent speech merging to speech units (see Adjacent Speech Merging section)
5. Canonicalize speaker names and session names
6. Index each unit into `speeches`/`qa_exchanges`
7. Checkpoint the document in `processed_documents` after all its records are successfully indexed

`index_status` is updated only at the end of Stage 2, not at the end of Stage 1.

**Date filtering**

`--date-from YYYY-MM-DD` and `--date-to YYYY-MM-DD` scope both stages:

- **Stage 1:** only documents whose parsed date falls within the window are written to `raw_documents`; out-of-window documents are skipped after parsing
- **Stage 2:** only `raw_documents` rows with dates within the window are read and processed

When neither flag is provided, both stages operate on the full corpus without date restriction.

#### User Flows

**Initial bulk ingestion:**
1. Operator runs ingestion with a source selector (CA | LS | RS | all), `--stage fetch|process|all` (default `all`), and optional `--date-from`/`--date-to`
2. System enumerates all records in scope for the specified source(s)
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
| Lok Sabha | Debates and questions | 2014-01-01 to present | Pre-OCR plain text (_djvu.txt); PDF | eparlib.sansad.in (primary); Internet Archive (fallback) |
| Rajya Sabha | Debates and questions | 2014-01-01 to present | HTML and PDF | sansad.in/rs HTML (primary); Internet Archive; rsdebate.nic.in DSpace (fallback) |

#### Proceeding Types Indexed

**Constituent Assembly:** plenary debate speeches only.

**Lok Sabha and Rajya Sabha:** debate speeches, starred questions, unstarred questions, zero hour speeches, short notice questions, calling attention motions, short duration discussions, adjournment motions, private member bills.

#### Indexed Record Fields

**Speech unit**

| Field | Description |
|-------|-------------|
| `id` | Stable UUID; preserved across re-runs via ON CONFLICT DO NOTHING on the dedup key |
| `source` | CA \| LS \| RS |
| `proceeding_type` | debate \| zero_hour \| short_duration_discussion \| calling_attention \| adjournment_motion \| private_member_bill |
| `date` | Date of sitting (YYYY-MM-DD) |
| `session_name` | E.g. "Budget Session 2023"; null for CA |
| `session_number` | Official session number; null for CA |
| `sitting_number` | Sitting number within session |
| `subject` | Agenda item or debate title |
| `speaker_name` | Member's full name |
| `speaker_party` | Party or group affiliation |
| `speaker_constituency_or_state` | Constituency (LS), state (RS), or null (CA) |
| `speaker_role` | member \| minister \| presiding_officer |
| `full_text_en` | Full English text; for merged speeches, concatenation of all segment texts joined with `\n\n` |
| `segments` | JSONB array of speech text segments; each element: `{"text": "...", "segment_index": N}` (0-based); single-element array for unmerged speeches |
| `lang_original` | `en`, `hi`, or `mixed` |
| `time_of_day` | HH:MM; HTML sources only; null for IA pre-OCR and PDF |
| `word_count` | Integer word count of `full_text_en`; null if `full_text_en` is null |
| `is_translated` | true if `full_text_en` contains official English translation of Hindi portions |
| `has_untranslated_content` | true if any portion could not be indexed due to absent translation |
| `speaker_name_unresolved` | true if `speaker_name` not found in canonical names dictionary |
| `source_url` | For LS: Internet Archive URL (eparlib.sansad.in must not be used). For RS via IA or rsdebate.nic.in: Internet Archive URL. For RS from sansad.in HTML: sansad.in URL. For CA: constitutionofindia.net URL. Null if no accessible URL derivable. |
| `page_reference` | Page number in source PDF; null for HTML |
| `sequence_within_sitting` | 1-based position in sitting; for merged speeches, position of the first segment |
| `volume` | CA volume number (1–12); null for LS/RS |
| `lok_sabha_number` | Lok Sabha term number (e.g., 17); INTEGER; null for RS and CA |

**Q+A exchange unit (starred question)**

| Field | Description |
|-------|-------------|
| `id` | Stable UUID |
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
| `minister_name` | Name of the minister who answered; extracted from the minister's response section; must never be set to question preamble text (e.g., "Will the minister of [Ministry] be pleased to state…"); falls back to "Minister of [Ministry]" when name not identifiable |
| `ministry` | Ministry responsible |
| `full_text_en` | Full text of the exchange: main question + answer + all supplementaries |
| `lang_original` | `en`, `hi`, or `mixed` |
| `time_of_day` | HH:MM; HTML sources only; null otherwise |
| `word_count` | Integer word count of `full_text_en`; null if null |
| `is_translated` | true if any portion was translated from Hindi |
| `has_untranslated_content` | true if any portion could not be indexed due to absent translation |
| `source_url` | Same rules as speech unit source_url |
| `page_reference` | Page number in source PDF; null for HTML |
| `sequence_within_sitting` | 1-based position; shared sequence space with speech units |
| `lok_sabha_number` | Lok Sabha term number; null for RS |

**Q+A exchange unit (unstarred question):** Same as starred except `proceeding_type: unstarred_question`, `full_text_en` contains question text and written answer only (no supplementaries), and uses single `questioner_name` field. All `source_url`, `minister_name`, and `lok_sabha_number` rules apply equally.

#### Language Handling

1. **Speech in English:** store verbatim; `is_translated: false`
2. **Speech in Hindi with official English translation:** store translation; `is_translated: true`
3. **Bilingual speech:** store all English text (original English + translated Hindi); `is_translated: true`
4. **Hindi speech with no translation:** `full_text_en: null`; `has_untranslated_content: true`; still indexed

#### Adjacent Speech Merging

During Stage 2, consecutive speeches by the same speaker within the same sitting are merged into a single `speeches` record. Applies to speech units only; Q+A exchange units are never merged.

**Merge conditions (all must be true):** same `speaker_name`; same sitting (same `source` + `date` + `sitting_number`); same `proceeding_type`; consecutive in document order with no break signal between them.

**Break signals (any one prevents merging):** a speech or interjection by a different speaker; a section heading (H1/H2/H3 tag or equivalent structural heading); a procedural entry (new question number heading, block header such as "QUESTIONS" / "STARRED QUESTION NO. X", formal procedural marker such as "The House adjourned for lunch").

**Merged record structure:** `segments` is a JSONB array with one element per original speech, ordered by document position. `full_text_en` = all segment texts joined with `\n\n`. `word_count` = total word count of combined text. `sequence_within_sitting` = position of the first segment. Unmerged speeches have a single-element `segments` array.

#### CA Field-Level Parsing Rules

**Date:** URL slug is authoritative (format `DD-MMM-YYYY`). HTML-derived date is always discarded for CA records.

**Subject:** Set to the nearest preceding standalone bold section header in the sitting page body. Fallback: first item in the sitting page's TOC `<ul>` if no section header precedes the first speech.

#### Records Not Indexed as Standalone Units

Unattributed speech ("SEVERAL HON. MEMBERS", "AN HON. MEMBER", etc.), presiding officer interventions in their presiding capacity, and procedural interruptions (points of order, rulings, division votes).

#### Canonicalization

**Speaker names:** strip honorific prefixes (Shri, Smt., Dr., Prof., Adv., Kumari); resolve variants using canonical names dictionary; store unresolved names with `speaker_name_unresolved: true`.

**Session names:** canonicalize to "[Session Type] Session [Year]"; multi-part sessions: "(Part [N])".

#### Deduplication

Duplicate detection key: source + date + sitting_number + proceeding_type + speaker_name + sequence_within_sitting (or question_number for Q+A). For merged speech records, `sequence_within_sitting` is the position of the first segment.

#### Acceptance Criteria

- All 12 CA volumes ingested; all LS/RS records from 2014-01-01 ingested across all proceeding types
- Every record has: id, source, proceeding_type, date, subject, full_text_en (or null with flag), source_url, lang_original
- `id` stable across re-runs; `word_count` non-null when `full_text_en` non-null
- `time_of_day` present (HH:MM) for HTML-sourced records; null for IA pre-OCR and PDF
- Starred Q+A includes complete exchange including all supplementaries
- Re-running on fully indexed corpus: zero new records, zero duplicates
- `--stage fetch/process` operate independently per spec; date window gate functions on both stages
- LS records have `lok_sabha_number` populated; RS and CA records have `lok_sabha_number: null`
- `minister_name` never contains question preamble text; falls back to "Minister of [Ministry]" when name not identifiable
- LS `source_url` is always Internet Archive URL; RS via IA/rsdebate has Internet Archive URL; RS from sansad.in has sansad.in URL; CA has constitutionofindia.net URL
- Adjacent same-speaker speeches with no break signal merged into one record; `segments` array contains one element per original speech; `full_text_en` = segments joined with `\n\n`
- Adjacent same-speaker speeches separated by different speaker / section heading / procedural entry are stored as separate records

#### Edge Cases

- Hindi speech with no translation: `full_text_en: null`; indexed with metadata only
- Missing speaker attribution: `speaker_name: null`; record still indexed
- Missing date: log error and skip; do not halt
- HTTP 4xx (non-429): log and skip; HTTP 5xx: retry 3x with backoff; HTTP 429: backoff and retry, never skip
- Malformed HTML/PDF: log and skip
- RS record from IA with no derivable DSpace handle: `source_url: null`; log warning
- Q+A minister name absent from response section: `minister_name` = "Minister of [Ministry]"; must never be set to preamble text

---

**Test Spec — F01**

- Records dated exactly 2014-01-01 are in scope; 2013-12-31 are excluded
- HTML-sourced record is retained when same proceeding available as HTML and PDF
- Two same-speaker speeches with intervening different speaker: two separate records
- Two consecutive same-speaker speeches with no break signal: one merged record with two-element `segments` array; `full_text_en` contains both texts separated by `\n\n`
- Three consecutive same-speaker speeches with no break: single merged record with three-element `segments` array
- Two same-speaker speeches with section heading (H-tag) between them: two separate records
- Two same-speaker speeches with procedural block header between them: two separate records
- Merged record `segments` elements ordered by document position (segment_index 0 = earliest)
- Checkpoint granularity per source document; interrupted document fully reprocessed on resume with no duplicates
- A starred Q+A unit must include every supplementary exchange, not just the first
- Hindi speech with official translation: `full_text_en` = translation text; `is_translated: true`; not null, not Devanagari
- Hindi speech no translation: `full_text_en: null` (not empty string, not Devanagari)
- "SEVERAL HON. MEMBERS" etc. must never appear as `speaker_name` value
- Presiding officer speeches must not appear as standalone indexed records
- Zero hour speeches: individual member's name in `speaker_name`; string "ZERO HOUR" must not appear as `speaker_name`
- Name appearing as "Shri Narendra Modi", "Narendra Modi", "N. Modi" must produce identical `speaker_name` in all records
- Session variants for the same session must produce identical `session_name`; CA records: `session_name: null`
- CA date: URL-slug date always stored; HTML-derived date never used
- Stage 1 date window: documents on `date_from` included; one day before excluded; same for `date_to`
- Q+A record with preamble-only text: `minister_name` = "Minister of [Ministry]", never preamble text
- LS `source_url`: archive.org domain; must not contain "eparlib.sansad.in"
- RS via IA: archive.org domain; RS from sansad.in HTML: sansad.in domain

---

### F02: Full-text Search

#### Description

Core search interface. Users enter keyword queries; the system executes full-text search across the indexed corpus and returns a ranked result list. Query expansion — synonyms and spell corrections — is integrated into the search execution model.

#### User Flows

**Standard search:** User types query (≥2 characters), submits; system returns ranked results with active filter support.  
**Refinement:** User modifies query on results page; active filter selections persist.  
**No results:** System shows no-results state with suggestions.  
**Invalid query:** Query <2 characters or empty shows inline validation; no search executed.

#### Search Execution Model

**Fields searched:** `full_text_en`, `subject`, `speaker_name`, `minister_name`, `ministry`.

**Term matching:**
- Single-term: expanded with synonyms (reduced weight) and spell corrections (lower weight); evaluated as OR across all variants
- Multi-term: AND across original term groups; OR across each term and its expansions
- Phrase query (double-quoted): exact phrase at full weight; phrase-level synonyms as OR alternatives at reduced weight; individual term expansions not applied separately
- Original term match > synonym match > spell correction match in ranking

**Relevance ranking factors:** original term coverage; field match location (speaker_name/subject/minister_name/ministry > full_text_en); expansion match type; term frequency and passage density in full_text_en.

**Default scope:** all sources (CA + LS + RS).

#### Acceptance Criteria

- Queries ≥2 non-whitespace characters execute; <2 show inline validation
- Original term match ranks above synonym match; phrase query matches only adjacent sequence
- Case-insensitive; stop words stripped; queries >500 chars truncated to 500
- No-results state shows message and suggestions; backend errors show explicit error state
- Search response ≤2 seconds at p95

#### Edge Cases

Stop words only → same validation as empty query; >500 char → truncate silently; special characters → strip/escape; backend error → "Search is temporarily unavailable" with retry.

---

**Test Spec — F02**

- Record containing "fundamental" and "rights" non-adjacently must NOT match phrase query `"fundamental rights"`
- Record A: query term once in `speaker_name`; Record B: same term 10× in `full_text_en` only — Record A ranks higher
- Original term match > synonym match > spell correction match in score, even when term frequency higher for lower-ranked variant
- Record matching original term 1 + synonym of term 2: ranks lower than record matching both original terms
- "article 370", "Article 370", "ARTICLE 370" return identical result sets in identical rank order
- Query "the right to speech" executes as "right speech" (stop words stripped); result set identical to direct query "right speech"
- Query of only stop words: shows validation message, not empty result list
- 501-character query: truncated to 500; no error shown to user
- Query with parentheses/brackets as literal chars: no search error; results or no-results shown
- Active filters persist when user refines query from results page

---

### F03: Search Filters

#### Description

Filters narrow results by legislative body, date range, speaker, session, and proceeding type. Combinable with each other and with the search query. Filter state persists across query refinements.

#### Filter Dimensions

1. **Legislative body:** multi-select CA/LS/RS; default all selected
2. **Date range:** From/To; optional; constrained to indexed scope per body selection; From > To shows validation
3. **Speaker:** free text; case-insensitive substring match on canonical `speaker_name`
4. **Session:** free text; case-insensitive substring match on `session_name`; CA records excluded when active
5. **Proceeding type:** multi-select all types; when only CA selected, only "Debate" available

All active filters ANDed together and ANDed with search query.

#### Acceptance Criteria

- All five filter dimensions available on results page; each independently settable
- Active filters visually indicated; "clear filters" resets all; individual values removable
- Filter state persists on query refinement; only explicit clear resets
- All-bodies-deselected and all-types-deselected: validation message, no search executed
- Date range From > To: inline validation message, filter not applied

---

**Test Spec — F03**

- Session filter active: CA records absent from result set even if CA selected in body filter and query matches CA records
- Date range 1948-01-01 to 2015-12-31: returns CA records 1948–1950 + LS/RS 2014–2015; no records from 1951–2013; no error
- When only CA body selected: non-Debate proceeding types produce zero results (no error, no crash)
- Speaker filter "Singh": matches any canonical speaker name containing "Singh"; whitespace-only value treated as empty (no filter)
- RS body filter persists after query refinement; active filter indicator still shows RS filter
- All bodies deselected + submit: validation message shown; previous result set remains visible
- All types deselected + submit: validation message shown; previous result set remains visible
- From=2022-06-01, To=2021-01-01: inline validation error; result set not modified
- LS + Starred Question + speaker="Jairam Ramesh": LS debate speeches by that speaker must not appear; RS starred questions by that speaker must not appear

---

### F04: Query Expansion

#### Description

Augments user queries with synonyms and spell corrections before search execution. Expanded terms are OR alternatives at reduced relevance weights. Dictionary is domain-specific, static, and seeded with parliamentary terminology.

#### Synonym Dictionary

Bidirectional synonyms covering: legislative body names, constitutional terminology, parliamentary procedure terms, common abbreviations, well-known legislation short titles. See `/prd/sections/03-functional-requirements/04-query-expansion.md` for the full dictionary.

#### Spell Correction

Edit-distance based; phonetic matching for proper nouns. Terms <4 characters exempt. Corrected terms are OR alternatives at weight below synonym expansions. Spell correction suppressed inside phrase queries.

#### Acceptance Criteria

- "PM" → returns records containing "Prime Minister" at lower weight
- "fundamental rights" → returns records containing "basic rights" at lower weight  
- "Parliment" (misspelled) → returns records containing "Parliament" at reduced weight
- Quoted phrase query: phrase-level synonyms only; individual term synonyms not applied inside quotes
- Terms <4 characters not spell-corrected
- Dictionary file is the sole source of synonym definitions

---

**Test Spec — F04**

- "House of the People" expands to "Lok Sabha" and vice versa; bidirectionality holds for all pairs
- Query "fundamental rights" (unquoted): phrase synonym "basic rights" applied; "fundamental" and "rights" not individually expanded
- Quoted phrase containing misspelled term: no spell correction applied; verbatim phrase matched
- Terms of 1, 2, 3 characters: no spell correction; terms of exactly 4 characters: eligible for spell correction
- Synonym match contribution > spell correction match contribution for same record and query
- Query "SC" must expand to all defined expansions; absence of any defined expansion is a bug
- Synonym in application logic not in dictionary file: test must fail (dictionary is sole source)
- Query "MGNREGA": "PM" → "Prime Minister" synonym must not trigger (substring non-expansion)

---

### F05: Result Display

#### Description

Each search result is displayed as a card showing the record's metadata, a contextual text snippet with matched terms highlighted, and a link to the original source document.

#### Result Card: Speech Record

Speaker name, party/group, constituency/state, legislative body, proceeding type, date (DD Month YYYY), time of day (HH:MM if not null), session, subject/agenda item, text snippet, language badge, source link.

#### Result Card: Q+A Exchange Record

Question number ("Q. [number]"), subject, proceeding type, legislative body, date, time of day, session, questioner (primary + "+N others" if co-signatories), questioner party, "Answered by [Minister Name], [Ministry]", text snippet, language badge, source link.

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

- Snippet is a passage of at least 400 words extracted from `full_text_en`, chosen from the passage with the highest density of query term matches; Meilisearch crop length must be configured to produce this minimum
- If `full_text_en` contains fewer than 400 words, the full text is shown (no truncation of content shorter than the minimum)
- If the matched passage is near the start or end of `full_text_en`, the snippet may be shorter than 400 words
- Query terms (original and expanded) highlighted in the snippet
- `full_text_en: null` records: snippet area shows "This speech was delivered in Hindi. No English text is available."
- Q+A records where match is in supplementary exchange: snippet drawn from supplementary; label "From supplementary exchange" shown

#### Pagination

20 results per page; exact count ≤9,999; "10,000+" for ≥10,000; pagination controls with current page and total pages (if ≤500 pages); URL reflects page number.

#### Acceptance Criteria

- Every card: body, proceeding type, date, subject, snippet with highlighted terms, working source link
- "View source" opens original document in new tab
- Records with `full_text_en: null` display untranslated-speech message; no empty snippet area
- `lang_original: hi` → "Hindi original" badge; `mixed` → "Mixed language" badge; `en` → no badge
- `time_of_day` not null: displayed as HH:MM near date; null: no time field shown
- Snippet ≥400 words for records with full_text_en >400 words; full text shown when full_text_en ≤400 words
- Result count shown at top; paginated links load correct page by URL

#### Edge Cases

- Missing party/constituency: omitted (no placeholder)
- `speaker_name: null`: shows "Speaker unknown"
- HTML/special characters in snippet: escaped; must not render as HTML
- Source URL null/missing: "View source" not shown; no broken link

---

**Test Spec — F05**

- Highest-relevance match in supplementary exchange: snippet drawn from supplementary + label shown; main Q+A snippet must not appear instead
- 9,999 results: exact count displayed; 10,000 results: "10,000+" displayed
- `full_text_en: null` record: untranslated-speech message shown; snippet area not empty/blank/absent; all other metadata fields display normally
- `full_text_en` containing HTML tags (e.g., `<b>`, `<script>`): rendered as plain text; tags not interpreted; scripts not executed
- Page 3 URL copied and opened in new session: loads page 3 without re-entering query; URL encodes both query and page number
- Starred question with 1 questioner: no "+N others" label; with 3 co-signatories (4 total): shows "+3 others"
- `lang_original: hi`: "Hindi original" badge; `mixed`: "Mixed language" badge; `en`: no badge element in DOM (not merely hidden)
- `time_of_day: "14:35"`: displays "14:35" near date; not reformatted as "2:35 PM"; `time_of_day: null`: no time element in DOM
- `speaker_name_unresolved: true`: raw name displayed; no error indicator; format identical to resolved name display
- `full_text_en` >400 words: snippet ≥400 words; `full_text_en` ≤400 words: full text shown with no words omitted

---

### F06: Sorting

#### Description

Users can sort search results by relevance (default), chronological, or reverse chronological. Sort persists across query refinements.

#### Sort Options

| Option | Order |
|--------|-------|
| Relevance (default) | Descending relevance score |
| Chronological | Ascending date; secondary: `sequence_within_sitting` ascending |
| Reverse chronological | Descending date; secondary: `sequence_within_sitting` descending |

#### Acceptance Criteria

- Three sort options on results page; default is Relevance on every new search
- Changing sort reorders results without changing count or clearing filters
- Sort persists across query refinements
- Date-based sorts: primary key date, secondary key `sequence_within_sitting`

---

**Test Spec — F06**

- Two records same date: ordered by `sequence_within_sitting` ascending (chronological) or descending (reverse-chronological)
- Switch from chronological to relevance: results reordered by relevance; date not used as tiebreaker
- Sort set to "Chronological", query refined: sort control still shows "Chronological"; new results in chronological order
- Changing sort: result count unchanged before and after
- Every new search from homepage or cleared query: defaults to Relevance sort

---

### F07: Indexing Status Panel

#### Description

Read-only panel showing total records indexed, per-source breakdown with date coverage, and last ingestion run date.

#### Displayed Information

```
Search Index Status

Total records indexed: [N]

Constituent Assembly      [N] records    1946–1950
Lok Sabha                 [N] records    Jan 2014 – [Month Year]
Rajya Sabha               [N] records    Jan 2014 – [Month Year]

Last updated: [DD Month YYYY]
```

Counts use thousands separators. Unindexed source: "0 records – not yet indexed".

#### Display Surfaces

**Homepage status strip:** condensed, shows per-source counts and last updated date; no date coverage.  
**Full panel:** accessible via footer link "Index status"; full detail including date coverage.

#### Acceptance Criteria

- Counts and dates reflect actual index state; not hardcoded
- Homepage strip: source with zero records shows "0 [Body] records"; not omitted
- Full panel: source with zero records shows "0 records – not yet indexed" without date range
- Last updated reflects ingestion run completion timestamp

#### Edge Cases

- Never run: all sources "0 records – not yet indexed"; last updated "Never"
- Summary record malformed: "Status unavailable" message; no crash

---

**Test Spec — F07**

- Panel reads from pre-computed summary (not live index query); disabling search index must still show last known status
- Fresh deployment: "Last updated" displays "Never" (not null, blank, or default date)
- Full panel zero-source: "0 records – not yet indexed" with no date range (not empty date string or placeholder date)
- Homepage strip zero-source: source still shown as "0 [Body] records"; not omitted
- Total records count = sum of three per-source counts; discrepancy is a bug
- "Last updated" does not update on page load, search, or any event other than ingestion run completion

---

### F08: Search History

#### Description

Cookie-based recent searches (auto-recorded) and saved searches (explicitly bookmarked). No sign-in required. All data stored client-side; nothing sent to server.

#### Recent Searches

- Auto-recorded per submission; max 10 entries; duplicate query updates timestamp (not duplicated); 30-day cookie lifetime
- Actions: re-run (with default filters), delete individual, clear all

#### Saved Searches

- Explicit save from results page; max 20; no expiry; persistent cookie
- Stores: name (defaults to query, max 60 chars), query text, active filter state, save timestamp
- Actions: save, re-run (restores stored query + filter state), rename, delete

#### Cookie Constraints

- Recent and saved in separate cookies; combined ≤4KB; if approaching limit, recent searches trimmed first
- Cookies disabled: features silently unavailable; no error shown

#### Acceptance Criteria

- Every submitted query auto-added to recent searches; max 10, most recent first
- Duplicate query: updates timestamp/position; no second entry created
- Saved search restores query + filter state exactly; defaults to query text as name
- Saving disabled with message at 20-entry limit
- All history works without authentication; no data sent to server

---

**Test Spec — F08**

- Same query submitted 3×: exactly 1 recent search entry with timestamp of 3rd submission
- 10 entries stored + 11th distinct query: oldest removed; list remains at exactly 10
- Re-running recent search: executes with default filters (not original submission filters)
- Saved search (body=RS, type=Starred, date from=2020-01-01): re-running restores exactly those filter selections
- Exactly 20 saved: save action visibly disabled with explanatory message; no 21st entry creatable
- Same query saved twice: two separate entries (second does not overwrite first)
- Cookies blocked: recent/saved searches not shown; no cookie error message; search functions normally
- Name of exactly 60 chars: accepted; 61 chars: rejected (truncated or validation)
- Saved search with unrecognised proceeding type: executes ignoring that value; no error

---

### F09: Detail Page

#### Description

A full-record detail page displaying the complete text and all metadata for a single indexed record. Accessible via a stable URL. Provides inline adjacent speech loading within the same sitting and back navigation to the results page.

#### Route and API

- **Frontend route:** `/record/:id`
- **API endpoint:** `GET /api/record/{id}` — returns 404 if not found

#### User Flows

**Arriving from search results:** Click result card → navigate to `/record/:id` → full text, all metadata, and adjacent loading controls shown → "Back to results" link returns to results page preserving state.

**Direct access:** Page loads as above; "Search" link to homepage shown in place of "Back to results".

**Adjacent loading:**
1. User clicks "Load 5 previous" or "Load 5 next"
2. Up to 5 adjacent records from the same sitting loaded inline (prepended above or appended below) without page navigation
3. URL remains at `/record/:id` of the focal record
4. Same sitting: same `source` + `date` + `sitting_number`; Q+A and speech records share sequence space
5. If more records remain after load: control stays enabled; if none remain: control disabled

#### Full Text Display

`full_text_en` rendered as paragraphs. If null: "This record was delivered in Hindi. No English text is available."

#### Metadata Fields Displayed

| Field | Display label | Notes |
|-------|--------------|-------|
| `source` | Legislative body | "Constituent Assembly", "Lok Sabha", or "Rajya Sabha" |
| `lok_sabha_number` | Lok Sabha term | "[N]th/st/nd/rd Lok Sabha" with correct ordinal suffix; LS only; omitted for RS/CA |
| `proceeding_type` | Proceeding type | Human-readable label per F05 label map |
| `date` | Date | DD Month YYYY |
| `time_of_day` | Time | HH:MM; omitted when null |
| `session_name` | Session | Omitted when null |
| `session_number` | Session number | Omitted when null |
| `sitting_number` | Sitting number | |
| `volume` | Volume | CA only |
| `subject` | Subject | |
| `speaker_name` | Speaker | Speech records only |
| `speaker_role` | Role | Speech records only |
| `speaker_party` | Party | Omitted when null |
| `speaker_constituency_or_state` | Constituency / State | Omitted when null; omitted for CA |
| `speaker_name_unresolved` | — | "(name unresolved)" next to speaker name when true |
| `question_number` | Question number | Q+A only; "Q. [number]" |
| `questioner_names` | Questioner(s) | Q+A only |
| `questioner_party` | Questioner party | Q+A only; omitted when null |
| `minister_name` | Minister | Q+A only |
| `ministry` | Ministry | Q+A only |
| `lang_original` | Language | "English", "Hindi", or "Bilingual" — always shown |
| `is_translated` | Translation | "Includes official English translation" when true |
| `has_untranslated_content` | Untranslated content | "Some content unavailable in English" when true |
| `page_reference` | PDF page | "PDF page [N]"; omitted when null |
| `word_count` | Word count | "[N] words"; omitted when null |
| `sequence_within_sitting` | Position in sitting | "[N] of [total]" |
| `source_url` | Source | "View source" link in new tab; omitted when null |

#### Adjacent Speech Loading

- Above focal record: "Load 5 previous" control; below: "Load 5 next" control
- "Load 5 previous" disabled when focal record has lowest `sequence_within_sitting` in sitting; "Load 5 next" disabled at highest
- Clicking loads up to 5 records in the appropriate direction; appended/prepended without page navigation
- After batch load: control stays enabled if more remain; disabled if none remain
- Each loaded adjacent record shows: speaker name (or questioner/minister for Q+A), date, subject, proceeding type, full text
- URL does not change on adjacent loads; remains at `/record/:id` of focal record

#### Acceptance Criteria

- `/record/:id` loads correct record; 404 for unknown id
- `full_text_en` shown as paragraphs; null shows defined message
- All non-null metadata fields shown; null fields omitted with no placeholder
- `lok_sabha_number` displayed as "[N]th/st/nd/rd Lok Sabha" for LS; omitted for RS/CA
- `page_reference` shown as "PDF page [N]" when present; omitted when null
- "Load 5 next" appends records inline without page navigation; URL unchanged
- "Load 5 previous" prepends records inline without page navigation
- Load controls disabled (not hidden) at sitting boundaries; both disabled when only one record in sitting
- "Back to results" from search navigation; "Search" link on direct access

#### Edge Cases

- `full_text_en: null`: defined message shown; all other metadata renders normally
- Record at sequence boundary: boundary-side control disabled; other behaves normally
- Only one record in sitting: both controls disabled
- `source_url: null`: no "View source" link; no broken link
- Direct URL access: "Search" link shown; no "Back to results"
- `id` not found: 404; "Record not found" page rendered
- Fewer than 5 records remain in direction: loads available count; control becomes disabled

---

**Test Spec — F09**

- `lok_sabha_number: 17` → "17th Lok Sabha"; `lok_sabha_number: 21` → "21st Lok Sabha"; `lok_sabha_number: 22` → "22nd Lok Sabha"; `lok_sabha_number: 23` → "23rd Lok Sabha" (ordinal suffix correct for each value)
- RS record: no element with text "Lok Sabha" in metadata area; `lok_sabha_number` entirely absent from DOM
- "Load 5 next": no page navigation; URL remains `/record/:id` of focal record
- After loading 5 with 3 more remaining: "Load 5 next" enabled; after loading those 3: control disabled
- "Load 5 previous": records prepended above focal record; focal record remains in DOM
- Focal record is only record in sitting: both load controls disabled simultaneously; neither hidden or absent from DOM
- Record opened via in-app nav: "Back to results" shown; returns to results without re-executing search
- Record opened by direct URL: "Search" to homepage shown; no "Back to results"
- `full_text_en: null`: defined message rendered; text area not empty/blank/absent; all non-null metadata fields still render
- `page_reference: 42` → "PDF page 42"; `page_reference: null` → no label or value (not "PDF page —" or "PDF page null")
- "Position in sitting" shows "[N] of [M]" where M = actual count of records with same source + date + sitting_number; M not hardcoded
- `/record/nonexistent-id` → "Record not found" page; not blank page, JS error, or partial load

---

### F10: Debug Mode

#### Description

A diagnostic facility exposing internal search scoring, index data, and database records for each search result. Activated via URL parameter. No authentication required.

#### Activation

Append `?debug=1` to any search results URL. Active for the duration of that page view.

#### User Flows

**Activating:** Add `?debug=1` to URL → global debug panel appears above results; each result card shows "Debug" toggle.

**Inspecting a result:** Click "Debug" toggle → 4 collapsible sections appear (all collapsed by default):
1. **Scoring details** — rendered from initial search response
2. **Document in index** — rendered from initial search response
3. **Processed record** — fetched lazily via `GET /api/debug/processed/{id}` on first expand
4. **Raw document** — fetched lazily via `GET /api/debug/raw/{id}` on first expand

Subsequent expands of Processed record or Raw document use previously fetched data (no re-fetch).

**Inspecting overall search:** Expand sections in the global debug panel (all data from search-time capture; no additional requests).

#### Per-Result Debug Panel Sections

1. **Scoring details:** `_rankingScore` (overall 0.0–1.0), `_rankingScoreDetails` (per-rule breakdown: words, typo, proximity, attribute, exactness, and any custom rules); all score fields returned by Meilisearch shown
2. **Document in index:** full Meilisearch document for this result; all fields present in index document
3. **Processed record:** full PostgreSQL row from `speeches` or `qa_exchanges`; fetched lazily; includes `segments` JSONB
4. **Raw document:** full PostgreSQL row from `raw_documents`; fetched lazily; includes full extracted text content

#### Global Search Debug Panel Sections

1. **Processed query:** query after synonym expansion, stopword filtering, and all service-layer transformations
2. **API request:** method, URL, query parameters, and request body sent from frontend to backend
3. **API response:** status code, response headers, and full response body (including debug envelope)
4. **Meilisearch request:** method, URL, and body sent from backend to Meilisearch
5. **Meilisearch response:** full response body received from Meilisearch by backend

#### Backend Requirements

When `debug=true/1` on search endpoint: include `_rankingScore`, `_rankingScoreDetails`, full document fields in each hit; include debug envelope in response (processed query, Meilisearch request/response).

New endpoints (no auth): `GET /api/debug/processed/{id}` (PostgreSQL speeches/qa_exchanges row; 404 if not found); `GET /api/debug/raw/{id}` (PostgreSQL raw_documents row linked to this record; 404 if not found or not linked).

#### Acceptance Criteria

- `?debug=1` activates debug mode; removing param deactivates
- Every result card shows "Debug" toggle in debug mode; no toggle in normal mode
- Global debug panel visible above results in debug mode; not rendered in normal mode
- Scoring details and Document in index render without additional requests (in initial search response)
- Processed record: exactly one request on first expand; zero on subsequent expands
- Raw document: exactly one request on first expand; zero on subsequent expands
- Processed record and Raw document fetch independently (expanding one does not fetch the other)
- All 4 per-result sections and all 5 global sections independently collapsible/expandable
- 404 from debug endpoints: UI shows error message in that section; other sections unaffected
- No calls to `/api/debug/*` endpoints in normal mode

#### Edge Cases

- No `_rankingScoreDetails` from Meilisearch: show available score fields; section not hidden
- Raw document deleted after processing: 404; "Raw document not available" shown in section
- Very large raw document: full content rendered; no truncation

---

**Test Spec — F10**

- Page load without `?debug=1`: zero calls to `/api/debug/processed/*` or `/api/debug/raw/*`; no debug toggle elements, panel containers, or global debug panel in DOM (not merely hidden)
- `?debug=1` on one tab must not activate debug mode on other tabs without the parameter
- Meilisearch requests in normal mode: must not include `_rankingScore` or `_rankingScoreDetails` in attributes to retrieve
- Expand Processed record → collapse → expand again: exactly 1 call to `/api/debug/processed/{id}` (not 2)
- Expand Raw document for result A + expand Raw document for result B: 2 separate calls (one per id)
- Expand Processed record for a result: must not trigger a call to `/api/debug/raw/{id}` for that result; vice versa
- `GET /api/debug/processed/{id}` returns 404: error message shown in that section; Scoring details, Document in index, Raw document sections continue to function
- `GET /api/debug/raw/{id}` returns 404: error message in Raw document section; other sections unaffected
- Collapsing global debug panel must not collapse any per-result debug panel
- Each of the 5 global sections independently togglable; expanding one must not collapse another
- Each of the 4 per-result sections independently togglable

---

## 4. Non-Functional Requirements

### Performance

**PERF-1: Search response time**
Search results must be returned within 2 seconds at p95, measured from query submission to full result list rendered in the browser, across the full indexed corpus. This target applies with query expansion active (synonyms + spell corrections).

**PERF-2: Detail page response time**
The detail page must complete full page load — including the initial record fetch — within 500ms at p95. Adjacent batch loads after initial page load are not subject to this target.

**PERF-3: Debug mode SLA exemption**
PERF-1 and PERF-2 response time targets do not apply when debug mode is active (`?debug=1`). Debug mode responses include large additional payloads and are exempt from all response time SLAs.

### Reliability

**INF-R1: Ingestion resumability**
The bulk ingestion pipeline must be resumable from a per-document checkpoint. An interrupted run re-run against the same corpus must produce an identical final record count with no duplicates.

### Security

**SEC-1: Debug mode data exposure**
Debug mode (`?debug=1`) exposes full database records (speeches, qa_exchanges, raw_documents rows), internal query details, and Meilisearch request/response payloads via unauthenticated endpoints. This is a deliberate choice for v1. Any deployment handling sensitive or access-controlled parliamentary data must review whether unauthenticated debug access is acceptable before enabling this feature in production.

### Storage

**INF-S1: Corpus storage sizing**
The full-text corpus (CA full record + 12 years of LS/RS debates and questions) is large. Storage architecture must be sized accordingly before build begins.

### Rate Limiting and Compliance

**INF-RL1: Government website rate limiting**
The ingestion pipeline must comply with robots.txt on constitutionofindia.net, eparlib.sansad.in, sansad.in, rsdebate.nic.in, and the Internet Archive. HTTP 429 responses must trigger exponential backoff and retry, not a skip.

### Processing

**INF-P1: Bulk ingestion duration**
Bulk ingestion is a long-running operation. No maximum time constraint for v1, but real-time progress logging is required.

### Scalability

**SCALE-1: Concurrent search load**
Search must remain within the PERF-1 response time target under concurrent user load. Exact concurrency targets are an architecture-stage deliverable.

### Debug Mode Performance

*(See PERF-3 above.)*

### Privacy

**PRIV-1: No server-side storage of user search data**
Search queries, filter selections, and search history are not persisted server-side in v1. All search history is stored client-side in browser cookies only. No user identifiers are created or stored.

---

## 5. Future Features

*(Features explicitly deferred from v1.)*

### Data Scope Expansion

- **Full parliamentary history:** extend LS/RS coverage beyond 2014 to all available records
- **Ongoing ingestion:** scheduled pipeline to ingest new sessions automatically

### Language Support

- **Hindi search:** index Hindi-language text and support queries in Hindi (Devanagari)

### User Accounts and Personalisation

- **User authentication:** sign-in with persistent cross-device history and saved searches
- **Cross-device sync:** saved searches accessible from any device when signed in
- **Search alerts:** notify users when new records matching a saved search are indexed

### Search Experience

- **Autocomplete / search-as-you-type**
- **Faceted result counts**
- **Related results / "More like this"**
- **Member profile pages**

### Platform

- **Mobile UI:** responsive layout optimised for small screens
- **Public API:** REST or GraphQL API for third-party integrations

### Administration

- **Admin interface for synonym dictionary**
- **Ingestion monitoring dashboard**

---

## Footer

Generated: 2026-06-06  
PRD version: 3.0  
Sections compiled from: /prd/sections/01-overview.md, 02-objectives.md, 03-functional-requirements/*, 04-non-functional-requirements.md, 05-future-features.md  
Features: F01–F10  
Previous version: 2.1  
