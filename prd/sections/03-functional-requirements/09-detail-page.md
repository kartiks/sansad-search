# Feature 09: Detail Page

## Description

A full-record detail page displaying the complete text and all metadata for a single indexed record. Accessible via a stable URL. Provides inline adjacent speech loading within the same sitting and back navigation to the results page.

## Route and API

- **Frontend route:** `/record/:id`
- **API endpoint:** `GET /api/record/{id}` — fetches a single document by record `id`; returns 404 if not found

## User Flows

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

## Full Text Display

- `full_text_en` is rendered as paragraphs (not a truncated snippet)
- If `full_text_en` is null: display the message "This record was delivered in Hindi. No English text is available." in the text area; no blank or empty area

## Metadata Fields Displayed

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

## Adjacent Speech Loading

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

## Back Navigation

- When the user arrived from a search results page (navigated via in-app link): show "Back to results" link that returns to the referring results page
- When the page is accessed directly (direct URL, bookmark, or external link): show "Search" link pointing to the homepage

## Acceptance Criteria

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

## Edge Cases

- Record with `full_text_en: null`: text area shows the defined message; all metadata fields still display normally
- Record at sequence boundary: the boundary-side load control is disabled; the opposite-direction control behaves normally
- Only one record in the sitting: both "Load 5 previous" and "Load 5 next" are disabled
- `source_url` is null: "View source" link is not shown; no broken link rendered
- Direct URL access with no referrer: "Search" link shown; no "Back to results" link
- `id` not found: 404 response; frontend renders a "Record not found" page
- Fewer than 5 records remain in a direction: load control loads however many are available (1–4) and then becomes disabled
- Adjacent load API call fails (network error or server error): an error message is shown in place of the loaded records; the load control returns to its pre-click enabled state (re-clickable); existing loaded records are not affected

## Architect Flags

The following items require architect input before build:

- **New API endpoint:** `GET /api/record/{id}` — single-document fetch by record `id`; error handling for unknown id (404)
- **Inline sitting load pattern:** adjacent loading requires fetching N records from a sitting starting at a given `sequence_within_sitting` offset, in either direction; the architect must determine whether this is a new endpoint (e.g., `GET /api/sitting/{source}/{date}/{sitting_number}?from_seq=N&limit=5&direction=prev|next`) or an extension to the existing record API
- **New frontend route:** `/record/:id` — routing integration and referrer detection for back navigation
- **Re-ingestion requirement:** `lok_sabha_number` and `segments` are new fields not present in existing records; full re-ingestion is required for all existing records
- **sequence_within_sitting for Q+A records:** feasibility of assigning a shared sequence number across speech and Q+A record types within the same sitting for all three source providers (CA, LS, RS)

## Dependencies

- Feature 01: indexed records with `id`, `sequence_within_sitting`, `lok_sabha_number`, and all metadata fields
- Feature 02: search index accessible by document `id`

## NFR Implications

- **Performance:** detail page full load including the initial record fetch must meet the PERF-2 target; adjacent batch loads after the initial page load are not subject to PERF-2 → see `04-non-functional-requirements.md`
