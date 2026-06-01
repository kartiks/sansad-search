# PRD Diff: v1.3 → v2.0

**Generated:** 2026-06-01
**Changes:** F01 new fields + CA parsing rules; F05 card updates; F09 new feature; NFR PERF-2 added

---

## Summary of Changes

| Change type | Location | Description |
|-------------|----------|-------------|
| Modified | F01 speech unit | 4 new indexed fields: `id`, `lang_original`, `time_of_day`, `word_count` |
| Modified | F01 Q+A unit (starred) | Same 4 new fields + `sequence_within_sitting` |
| Modified | F01 Q+A unit (unstarred) | Inherits same additions via "same fields as starred" |
| Modified | F01 | New section: CA Field-Level Parsing Rules (date + subject) |
| Modified | F01 | Updated acceptance criteria to require `id`, `lang_original`, `word_count`, `time_of_day` |
| Modified | F01 test spec | 3 new test cases for CA date and subject parsing |
| Modified | F05 speech card | Replace `is_translated` "Translated from Hindi" label with `lang_original` badge; add `time_of_day` row |
| Modified | F05 Q+A card | Same badge replacement and `time_of_day` row |
| Modified | F05 | Updated acceptance criteria to specify badge values by `lang_original` value |
| Modified | F05 test spec | 5 new test cases (badge per value, time_of_day present, time_of_day null) |
| Modified | NFR | New: PERF-2 — detail page full load ≤500ms p95 |
| **New** | F09 | Detail page feature spec |
| **New** | F09 test spec | 11 test cases |

---

## F01: Data Ingestion — Field Additions

### Speech unit — new fields (inserted before `is_translated`)

**Before:** First field was `source`.

**After:** New field `id` inserted as first field; `lang_original`, `time_of_day`, `word_count` inserted before `is_translated`.

```
ADDED to speech unit:

id           — Stable UUID assigned at ingest; preserved across re-runs via ON CONFLICT DO NOTHING on the deduplication key

lang_original — Language of the original speech before translation: en (English), hi (Hindi), or mixed (genuinely bilingual — alternates between Hindi and English in both directions; predominantly Hindi speeches with only translation fragments are classified hi); derived from Language Handling cases: case 1→en; cases 2 and 4→hi; case 3→mixed if genuinely alternating, hi if predominantly Hindi with translation fragments

time_of_day  — Time the speech began, as HH:MM (24-hour); extracted from HTML sources only; null for Internet Archive pre-OCR text and PDF sources

word_count   — Integer word count of full_text_en computed at ingest; null if full_text_en is null
```

### Q+A exchange unit (starred) — new fields

Same `id`, `lang_original`, `time_of_day`, `word_count` added.

Additionally:

```
ADDED to starred Q+A unit:

sequence_within_sitting — Integer position of this Q+A exchange within the sitting's proceedings, derived from document order (1-based); shared sequence space with speech units within the same sitting
```

Note: `sequence_within_sitting` is **not** added to the deduplication key for Q+A units. Q+A dedup key remains: source + date + sitting_number + proceeding_type + question_number.

### Q+A exchange unit (unstarred)

Inherits all additions from starred Q+A via "same fields as starred question" definition.

---

## F01: Data Ingestion — CA Field-Level Parsing Rules (new section)

**Before:** No CA-specific parsing rules existed.

**After:** New section "CA Field-Level Parsing Rules" added between Language Handling and Records Not Indexed as Standalone Units.

### Date field (CA only)

```
RULE: URL slug is the authoritative date source for CA records.
- URL format: DD-MMM-YYYY (e.g. 09-dec-1946)
- Parser parses slug directly → date as YYYY-MM-DD
- HTML-based date extraction MUST be skipped entirely for CA records
- Even when parse_html returns a date value, it must be discarded
- SUPERSEDES current ca.py behaviour (URL used as fallback only when parse_html returns None)
- For CA: URL date is ALWAYS applied regardless of parse_html output
```

### Subject field (CA only)

```
RULE: Each CA speech record's subject = nearest preceding standalone bold section header in the sitting page body.

Section header: standalone bold topic label between speech entries in debate body.
NOT section header: speaker names in bold/strong inside speech grid rows.

Assignment: Walk parsed DOM in document order. On standalone bold section header → set as current topic. Assign to all subsequent speech records until next section header.

Fallback: If no section header precedes first speech of sitting → subject = first item in page TOC.
TOC format: <ul> above debate body containing <li><a href="#ID">Topic</a></li> items.
Implementation must verify at build time: do anchor IDs correspond to id= attributes on body elements? Use that mapping if available.
```

---

## F01: Acceptance Criteria — Updates

**Before:**
```
- Every indexed record has: source, proceeding_type, date, subject, full_text_en (or null with has_untranslated_content flag), source_url
```

**After:**
```
- Every indexed record has: id, source, proceeding_type, date, subject, full_text_en (or null with has_untranslated_content flag), source_url, lang_original
- id is a stable UUID that does not change across re-runs for the same record
- word_count is present and non-null for all records where full_text_en is not null; null where full_text_en is null
- time_of_day is present (HH:MM) for HTML-sourced records where the sitting page includes time; null for all IA pre-OCR and PDF-sourced records
```

---

## F01: Test Spec — New Test Cases

**ADDED:**

```
CA Date Parsing:
- A CA record whose URL slug parses to a different date than what parse_html would return must store the URL-derived date, not the HTML-derived date; the HTML date must never appear in the indexed record
- A CA record must never have a null date caused by HTML parse failure when the URL slug is present and parseable; URL slug parse failure is the only condition under which a CA record's date may be missing

CA Subject Assignment:
- Two speech records from the same sitting that fall under the same bold section header must have identical subject values
- A speech record that follows a new section header in document order must not retain the subject value from the previous section header
- The first speech record in a sitting where no bold section header precedes it must have subject set to the text of the first item in the sitting page's TOC <ul>; it must not be null, empty, or set to a section header from later in the page
```

---

## F05: Result Display — Card Updates

### Speech card: is_translated label → lang_original badge

**Before:**
```
| Translation indicator | is_translated | If true, a "Translated from Hindi" label is shown near the snippet |
```

**After:**
```
| Language badge | lang_original | hi→"Hindi original"; mixed→"Mixed language"; en→no badge shown |
```

### Speech card: time_of_day added

**Added row (after Date row):**
```
| Time of day | time_of_day | Shown as HH:MM near the date field when not null; omitted silently when null |
```

### Q+A card: identical changes

Same replacement of `is_translated` label with `lang_original` badge and addition of `time_of_day` row.

### Acceptance Criteria updates

**Before:**
```
- Translated records show the "Translated from Hindi" label
```

**After:**
```
- Records with lang_original: hi show the "Hindi original" badge; records with lang_original: mixed show the "Mixed language" badge; records with lang_original: en show no badge
- Records with time_of_day not null display the time as HH:MM near the date; records with time_of_day: null display no time field and no placeholder
```

---

## F05: Test Spec — New Test Cases

**ADDED:**

```
Language Badge:
- lang_original: hi → "Hindi original" badge shown; no other language label
- lang_original: mixed → "Mixed language" badge shown
- lang_original: en → no language badge; badge element absent from DOM (not merely hidden)

Time of Day Display:
- time_of_day: "14:35" → display "14:35" near date field; must not reformat (not "2:35 PM")
- time_of_day: null → no time-of-day element rendered; no placeholder, no empty field, no "—"
```

---

## NFR — New Entry

**ADDED:**

```
PERF-2: Detail page response time
The detail page must complete full page load — including the record fetch and the adjacent-neighbour fetch — within 500ms at p95.
```

---

## F09: Detail Page — New Feature

**This feature did not exist in v1.3. Full specification:**

### Route and API
- Frontend route: `/record/:id`
- API endpoint: `GET /api/record/{id}` — single document fetch by Meilisearch document `id`; 404 if not found

### Full text display
- `full_text_en` rendered as paragraphs (not truncated snippet)
- `full_text_en: null` → "This record was delivered in Hindi. No English text is available."

### Metadata displayed
All fields shown explicitly; null/not-applicable fields omitted silently. Fields shown:
source, proceeding_type, date, time_of_day, session_name, session_number, sitting_number, volume (CA only), subject, speaker_name, speaker_role, speaker_party, speaker_constituency_or_state, speaker_name_unresolved (shown as "(name unresolved)" note when true), question_number (Q+A only), questioner_names (Q+A only), questioner_party (Q+A only), minister_name (Q+A only), ministry (Q+A only), lang_original (always shown as "English"/"Hindi"/"Bilingual"), is_translated (shown as "Includes official English translation" when true), has_untranslated_content (shown as "Some content unavailable in English" when true), page_reference (shown as "PDF page [N]" when not null), word_count (shown as "[N] words" when not null), sequence_within_sitting (shown as "[N] of [total]"), source_url (shown as "View source" link when not null).

### Adjacent navigation
- Same sitting = same source + date + sitting_number
- Q+A and speech records share the sequence space
- Prev = sequence − 1; Next = sequence + 1
- At boundaries: boundary control disabled (not hidden, not removed from DOM)
- URL updates to `/record/:id` of the new record on navigation

### Back navigation
- Arrived from search results: "Back to results" link (returns to results page preserving state)
- Direct URL access: "Search" link to homepage

### Architect flags (must be resolved before build)
1. New API endpoint: `GET /api/record/{id}`
2. Adjacent navigation query pattern: filter source+date+sitting_number, sort by sequence_within_sitting, fetch two neighbours
3. New frontend route: `/record/:id` — routing + referrer detection
4. Re-ingestion required: `id`, `lang_original`, `time_of_day`, `word_count`, `sequence_within_sitting` (Q+A) not derivable without re-parsing all source documents
5. sequence_within_sitting for Q+A: feasibility of shared sequence across speech and Q+A types for all three providers

### New test cases (F09)
- sequence 1 → Prev disabled; clicking disabled control produces no navigation
- maximum sequence → Next disabled
- single record in sitting → both Prev and Next disabled; controls visible in DOM
- After clicking Next → URL updates; clicking Prev returns to original record URL
- In-app arrival → "Back to results" shown; returns without re-executing search
- Direct URL → "Search" shown; "Back to results" absent
- full_text_en: null → defined message rendered; not empty; other metadata unaffected
- page_reference: 42 → "PDF page 42"; page_reference: null → no label or value
- sequence_within_sitting display shows actual M count for that sitting (not hardcoded)
- `/record/nonexistent-id` → "Record not found" page; no blank page, no JS error

---

*Diff generated: 2026-06-01 | v1.3 → v2.0*
