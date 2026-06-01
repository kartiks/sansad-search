# Feature 09: Detail Page

## Description

A full-record detail page displaying the complete text and all metadata for a single indexed record. Accessible via a stable URL. Provides adjacent navigation within the same sitting and back navigation to the results page.

## Route and API

- **Frontend route:** `/record/:id`
- **API endpoint:** `GET /api/record/{id}` — fetches a single document from Meilisearch by document `id`; returns 404 if not found

## User Flows

**Arriving from search results:**
1. User clicks a result card
2. Browser navigates to `/record/:id`
3. Detail page loads: full text rendered as paragraphs, all metadata fields shown, adjacent navigation controls shown
4. "Back to results" link is present; clicking it returns to the search results page (preserving query and pagination state)

**Direct access (bookmarked or shared URL):**
1. User opens `/record/:id` directly
2. Detail page loads as above
3. "Search" link to homepage is shown in place of "Back to results"

**Adjacent navigation:**
1. User clicks "Next" or "Prev" control
2. Page navigates to the adjacent record by `sequence_within_sitting` within the same sitting
3. URL updates to `/record/:id` for the new record
4. "Same sitting" is defined as: same `source` + same `date` + same `sitting_number`; Q+A exchange records and speech records share the sequence space
5. At sequence boundaries, the boundary control is disabled (not hidden or absent)

## Full Text Display

- `full_text_en` is rendered as paragraphs (not a truncated snippet)
- If `full_text_en` is null: display the message "This record was delivered in Hindi. No English text is available." in the text area; no blank or empty area

## Metadata Fields Displayed

All fields are shown explicitly. Fields that are null or not applicable for the record type are omitted silently (no placeholder label shown for null fields), except where noted below.

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

## Adjacent Navigation

- Neighbour records are determined by querying the index for records with the same `source`, `date`, and `sitting_number`, sorted by `sequence_within_sitting`
- The previous record is the one with `sequence_within_sitting` = current − 1; the next record is current + 1
- "Prev" is disabled when the current record has the lowest `sequence_within_sitting` in the sitting
- "Next" is disabled when the current record has the highest `sequence_within_sitting` in the sitting
- Disabled controls remain visible in the UI

## Back Navigation

- When the user arrived from a search results page (navigated via in-app link): show "Back to results" link that returns to the referring results page
- When the page is accessed directly (direct URL, bookmark, or external link): show "Search" link pointing to the homepage

## Acceptance Criteria

- `/record/:id` loads the correct record for any valid `id`; returns a 404 page for an unknown `id`
- Full `full_text_en` is displayed as paragraphs; null `full_text_en` shows the defined message
- All non-null metadata fields are displayed; null fields are omitted with no placeholder
- `page_reference` is shown as "PDF page [N]" when present; omitted when null
- `source_url` renders as a "View source" link when present; omitted when null
- Adjacent navigation moves to the correct record and updates the URL
- Prev/Next controls are disabled (not hidden) at sequence boundaries
- "Back to results" is shown when arriving from search; "Search" link when accessed directly
- URL updates on adjacent navigation so the new URL is bookmarkable

## Edge Cases

- Record with `full_text_en: null`: text area shows the defined message; all metadata fields still display normally
- Record at sequence boundary: the boundary-side nav control is disabled; the other control behaves normally
- Only one record in the sitting: both Prev and Next are disabled
- `source_url` is null: "View source" link is not shown; no broken link rendered
- Direct URL access with no referrer: "Search" link shown; no "Back to results" link
- `id` not found in index: 404 response; frontend renders a "Record not found" page

## Architect Flags

The following items require architect input before build:

- **New API endpoint:** `GET /api/record/{id}` — single-document fetch by Meilisearch document `id`; error handling for unknown id (404)
- **Adjacent navigation query pattern:** filter by `source` + `date` + `sitting_number`, sort by `sequence_within_sitting`, fetch the two neighbours; assess query cost and whether a single sorted fetch or two targeted fetches is preferable
- **New frontend route:** `/record/:id` — routing integration and referrer detection for back navigation
- **Re-ingestion requirement:** `id`, `lang_original`, `time_of_day`, `word_count`, and `sequence_within_sitting` (for Q+A) are not derivable from stored data without re-parsing source documents; full re-ingestion is required for all existing records
- **sequence_within_sitting for Q+A records:** feasibility of assigning a shared sequence number across speech and Q+A record types within the same sitting for all three source providers (CA, LS, RS)

## Dependencies

- Feature 01: indexed records with `id`, `sequence_within_sitting`, and all metadata fields
- Feature 02: search index accessible by document `id`

## NFR Implications

- **Performance:** detail page full load including the neighbour fetch must meet the PERF-2 target → see `04-non-functional-requirements.md`
