# PRD Diff: v2.1 → v3.0

**Generated:** 2026-06-06  
**From:** PRD-v2.1.md  
**To:** PRD-v3.0.md  
**Nature:** Major version bump — new feature F10; significant changes to F01, F05, F09; bug fixes to F01 (minister_name, source_url)

---

## Summary of Changes

| Feature | Change type | Scope |
|---------|-------------|-------|
| F01 | Modified | Added `lok_sabha_number` field; added `segments` field; added Adjacent Speech Merging section; fixed `minister_name` extraction rule; fixed `source_url` rules for LS and RS |
| F05 | Modified | Snippet size increased from 2–3 sentences to ≥400 words |
| F09 | Modified | Added `lok_sabha_number` display; replaced single Prev/Next navigation with inline 5-at-a-time adjacent loading |
| F10 | New | Debug mode feature (full new feature spec and test spec) |
| NFR | Modified | Added SEC-1 (debug mode security), PERF-2 clarification (adjacent loads excluded), PERF-3 (debug mode SLA exemption) |

---

## F01: Data Ingestion

### New field: `lok_sabha_number` (speech unit and Q+A exchange units)

**Added to speech unit field table:**
```
lok_sabha_number | Lok Sabha term number (e.g., 17 for the 17th Lok Sabha); INTEGER; 
                   extracted from source data at ingestion time; null for RS and CA records
```

**Added to Q+A starred/unstarred field tables:**
```
lok_sabha_number | Lok Sabha term number (e.g., 17); INTEGER; null for RS records
```

**New acceptance criterion:**
> LS speech and Q+A records have `lok_sabha_number` populated with the correct Lok Sabha term number; RS and CA records have `lok_sabha_number: null`

---

### New field: `segments` (speech unit only)

**Added to speech unit field table:**
```
segments | JSONB array of speech text segments; each element: {"text": "...", "segment_index": N} 
           (0-based); single-element array for speeches that were not merged with any adjacent speech
```

**`full_text_en` field description updated:**
```
BEFORE: Full English text of the speech; see Language Handling below
AFTER:  Full English text of the speech; for merged speeches, the concatenation of all segment texts 
        joined with \n\n; see Language Handling below
```

**`sequence_within_sitting` field description updated:**
```
BEFORE: Integer position of this speech within the sitting's proceedings, derived from document order (1-based)
AFTER:  Integer position of this speech within the sitting's proceedings, derived from document order (1-based); 
        for merged speeches, the position of the first segment in the merge group
```

---

### New section: Adjacent Speech Merging

Entirely new section added between "Records Not Indexed as Standalone Units" and "Canonicalization":

> During Stage 2 processing, consecutive speeches by the same speaker within the same sitting are merged into a single `speeches` record. This applies to speech units only; Q+A exchange units are never merged.
>
> **Merge conditions (all must be true):** same `speaker_name`; same sitting; same `proceeding_type`; consecutive in document order with no break signal.
>
> **Break signals (any one prevents merging):** a speech or interjection by a different speaker; a section heading (H1/H2/H3 or equivalent); a procedural entry (new question number heading, block header such as "QUESTIONS" / "STARRED QUESTION NO. X", formal procedural marker such as "The House adjourned for lunch").
>
> **Merged record structure:** `segments` JSONB array, one element per original speech. `full_text_en` = segments joined with `\n\n`. `word_count` = total combined word count. `sequence_within_sitting` = position of first segment. Unmerged speeches have a single-element `segments` array.

**Stage 2 flow updated:**
> Step 4 added: "Apply adjacent speech merging to speech units (see Adjacent Speech Merging section)"

**Deduplication section updated:**
```
BEFORE: The sequence_within_sitting field is required because a member may speak multiple times 
        in the same sitting on the same agenda item.
AFTER:  For merged speech records, sequence_within_sitting in the dedup key is the position of 
        the first segment in the merge group. The sequence_within_sitting field is required because 
        a member may speak multiple times in the same sitting on the same agenda item with 
        intervening speakers.
```

**New acceptance criteria:**
> Adjacent speeches by the same speaker with no break signal between them are merged into a single record; the merged record's `segments` array contains one element per original speech; `full_text_en` is the concatenation of all segment texts separated by `\n\n`.
>
> Adjacent speeches by the same speaker separated by a different speaker's speech, a section heading, or a procedural entry are stored as separate records with distinct `sequence_within_sitting` values.

---

### Bug fix: `minister_name` extraction

**`minister_name` field description updated (Q+A starred and unstarred):**
```
BEFORE: Minister answering
AFTER:  Name of the minister who answered the question; extracted from the minister's response section 
        in the source document; must never be set to question preamble text (e.g., "Will the minister 
        of [Ministry] be pleased to state…"); if the minister's name is not identifiable from the 
        response section, set to "Minister of [Ministry]" using the value of the ministry field
```

**New acceptance criterion:**
> `minister_name` never contains question preamble text; Q+A records where the minister's name is not identifiable from the response section have `minister_name` set to "Minister of [Ministry]"

**New edge case:**
> Q+A record where the minister's name is not present in the response section: `minister_name` is set to "Minister of [Ministry]" using the value of the `ministry` field; must never be set to question preamble text such as "Will the minister of [Ministry] be pleased to state…"

---

### Bug fix: `source_url` rules for LS and RS

**`source_url` field description updated (speech unit and Q+A units):**
```
BEFORE: URL of the original HTML page or PDF; for LS records fetched from Internet Archive, 
        always set to the corresponding eparlib.sansad.in document URL; for RS records fetched 
        from Internet Archive, always set to the corresponding rsdebate.nic.in document URL 
        (derived from the DSpace handle)

AFTER:  URL of the original source document. For LS records: always the Internet Archive URL 
        (eparlib.sansad.in is not reliably accessible and must not be used). For RS records 
        fetched via Internet Archive or rsdebate.nic.in: the Internet Archive URL. For RS records 
        fetched from sansad.in HTML: the sansad.in URL. For CA records: the 
        constitutionofindia.net URL. Null if no accessible URL can be derived for the record.
```

**New acceptance criterion:**
> For LS records, `source_url` is the Internet Archive URL; for RS records fetched via IA or rsdebate.nic.in, `source_url` is the Internet Archive URL; for RS records from sansad.in HTML, `source_url` is the sansad.in URL; for CA records, `source_url` is the constitutionofindia.net URL

---

### F01 test spec changes

**Deduplication test updated:**
```
REMOVED: A member speaking twice in the same sitting must produce two separate indexed records 
         with distinct sequence_within_sitting values; they must not be merged.

ADDED:   Two speeches by the same speaker in the same sitting with a different speaker's speech 
         between them must produce two separate indexed records.
         
         Two consecutive speeches by the same speaker in the same sitting with no break signal 
         must produce a single merged record with two-element segments array; full_text_en 
         contains both texts separated by \n\n.
```

**New test sections added:** Minister Name Extraction (3 tests), Source URL Rules (4 tests), Adjacent Speech Merging (4 tests).

---

## F05: Result Display

### Snippet size increase

**Snippet Generation section updated:**
```
BEFORE: Snippet is 2–3 sentences extracted from full_text_en, chosen from the passage with the 
        highest density of query term matches
        If the matched passage is near the start or end of full_text_en, the snippet may be 
        shorter than 3 sentences

AFTER:  Snippet is a passage of at least 400 words extracted from full_text_en, chosen from the 
        passage with the highest density of query term matches; the Meilisearch crop length must 
        be configured to produce this minimum
        If full_text_en contains fewer than 400 words, the full text is shown as the snippet 
        (no truncation of content shorter than the minimum)
        If the matched passage is near the start or end of full_text_en, the snippet may be 
        shorter than 400 words
```

**F05 test spec: new section "Snippet Minimum Size" added** (2 tests: ≥400 words for long full_text_en; full text for short full_text_en).

---

## F09: Detail Page

### New metadata field: `lok_sabha_number`

**Added to metadata fields table:**
```
lok_sabha_number | Lok Sabha term | Displayed as "[N]th/st/nd/rd Lok Sabha" with the correct 
                                    ordinal suffix (e.g., "17th Lok Sabha", "21st Lok Sabha"); 
                                    shown only for LS records; omitted for RS and CA records
```

**New acceptance criterion:**
> `lok_sabha_number` displayed as "[N]th/st/nd/rd Lok Sabha" for LS records; omitted for RS and CA records

---

### Adjacent navigation replaced with inline adjacent loading

**Section renamed and replaced:**
```
BEFORE section "Adjacent Navigation":
  - Neighbour records determined by querying index for same source/date/sitting_number
  - Prev = sequence_within_sitting - 1; Next = current + 1
  - Prev disabled at lowest sequence; Next disabled at highest
  - Disabled controls remain visible

AFTER section "Adjacent Speech Loading":
  - "Load 5 previous" control above focal record; "Load 5 next" below
  - Controls disabled (not hidden) at sitting boundaries
  - Clicking loads up to 5 records in the appropriate direction; prepended or appended inline
  - URL does not change; remains at /record/:id of focal record
  - After batch: control stays enabled if more remain; disabled if none remain
  - Each loaded record shows: speaker name/questioner/minister, date, subject, proceeding type, full text
```

**User flows section updated:** "Adjacent navigation" flow replaced with "Adjacent loading" flow.

**Acceptance criteria changes:**
```
REMOVED: Adjacent navigation moves to the correct record and updates the URL
REMOVED: Prev/Next controls are disabled (not hidden) at sequence boundaries
REMOVED: URL updates on adjacent navigation so the new URL is bookmarkable

ADDED:   Clicking "Load 5 next" appends up to 5 next sitting records inline without page navigation; 
         URL remains at focal record's /record/:id
ADDED:   Clicking "Load 5 previous" prepends up to 5 previous sitting records inline without page navigation
ADDED:   Each loaded adjacent record displays speaker name (or questioner/minister for Q+A), date, 
         subject, proceeding type, and full text
ADDED:   After loading a batch, if more records remain in that direction, the load control stays enabled; 
         when none remain, the control is disabled
ADDED:   Load controls are disabled (not hidden) at sitting boundaries; both disabled when only 
         one record in sitting
```

**Architect flags updated:** "Adjacent navigation query pattern" flag replaced with "Inline sitting load pattern" flag describing the new range-fetch API requirement.

**F09 test spec: significant changes:**
- URL-update-on-adjacent-nav tests removed
- Adjacent boundary tests updated for new inline controls
- New tests: "Load 5 next" does not trigger page navigation; after loading batch with N remaining, control state correct; "Load 5 previous" prepends without removing focal record; single-record sitting: both controls disabled, not hidden

---

## F10: Debug Mode (NEW)

**Entire new feature.** See PRD-v3.0.md F10 for full spec.

**New files created:**
- `/prd/sections/03-functional-requirements/10-debug-mode.md`
- `/prd/sections/03-functional-requirements/10-debug-mode-tests.md`

**Summary:**
- `?debug=1` URL parameter activates debug mode
- Per-result: 4-section debug panel (scoring details, document in index, processed record, raw document); processed record and raw document fetched lazily on first expand
- Global: 5-section panel (processed query, API request, API response, Meilisearch request, Meilisearch response)
- New backend endpoints: `GET /api/debug/processed/{id}`, `GET /api/debug/raw/{id}`
- No authentication required

---

## NFR Changes

**PERF-2 clarification:**
```
BEFORE: The detail page must complete full page load — including the record fetch and the 
        adjacent-neighbour fetch — within 500ms at p95.
AFTER:  The detail page must complete full page load — including the initial record fetch — 
        within 500ms at p95. Adjacent batch loads after the initial page load are not subject 
        to this target.
```

**New PERF-3:**
> PERF-1 and PERF-2 response time targets do not apply when debug mode is active (`?debug=1`). Debug mode responses include large additional payloads and are exempt from all response time SLAs.

**New SEC-1:**
> Debug mode exposes full database records and internal query details via unauthenticated endpoints. Deliberate v1 choice. Must be reviewed before production use with sensitive data.

---

## Downstream Impact

These changes require a full re-ingestion of all existing records:
- `lok_sabha_number` is a new field not present in existing records
- `segments` is a new field; existing speech records are structurally changed by merging
- `source_url` values for LS and RS records must be corrected (eparlib/rsdebate URLs → IA URLs)
- `minister_name` values for affected Q+A records must be corrected

**Action required:** Run `/plan` to add new phases covering:
1. Schema migration (add `lok_sabha_number`, `segments` to speeches; add `lok_sabha_number` to qa_exchanges)
2. Re-ingestion of all LS records with corrected source_url and lok_sabha_number; adjacent speech merging applied
3. Re-ingestion of RS records with corrected source_url
4. Debug mode backend (new endpoints, search debug envelope)
5. Frontend: inline adjacent loading; lok_sabha_number display; larger snippets; debug UI
