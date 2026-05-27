# Feature 05: Result Display

## Description

Each search result is displayed as a card showing the record's metadata, a contextual text snippet with matched terms highlighted, and a link to the original source document. Results are displayed in a paginated list. The display gives users enough context to assess relevance without opening the source document.

## Result Card: Speech Record

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

## Result Card: Q+A Exchange Record

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

## Proceeding Type Labels

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

## Snippet Generation

- Snippet is 2–3 sentences extracted from `full_text_en`, chosen from the passage with the highest density of query term matches
- Query terms (original and expanded matches) are highlighted in the snippet
- If the matched passage is near the start or end of `full_text_en`, the snippet may be shorter than 3 sentences
- If the record has `full_text_en: null` (untranslated Hindi speech): snippet area shows the message "This speech was delivered in Hindi. No English text is available." in place of a snippet; `has_untranslated_content` is the trigger
- For Q+A records, if the match is in a supplementary exchange rather than the main question/answer, the snippet is drawn from the supplementary exchange; a label "From supplementary exchange" is shown

## Pagination

- 20 results per page
- Result count displayed at the top of the list:
  - Exact count for up to 9,999 results (e.g., "47 results", "3,241 results")
  - Approximate count for 10,000 or more (e.g., "10,000+ results")
- Pagination controls show: previous page, next page, current page number, and total page count (if ≤ 500 pages); for result sets exceeding 500 pages, total page count is not shown
- URL reflects current page number so that results pages are shareable and bookmarkable

## Acceptance Criteria

- Every result card displays: body, proceeding type, date, subject, snippet with highlighted terms, and a working source link
- "View source" opens the original document in a new browser tab
- Snippet highlights all matched query terms (original terms and expanded matches)
- Records with `full_text_en: null` display the untranslated-speech message in place of a snippet; they do not display an empty or blank snippet area
- Translated records show the "Translated from Hindi" label
- Result count is shown at the top of the result list
- Paginated result sets: navigating to a specific page via URL (direct link or bookmarked URL) loads the correct page of results
- `speaker_name_unresolved: true` records display the raw name as stored; no error or blank in the speaker name field

## Edge Cases

- Record with missing `speaker_party` or `speaker_constituency_or_state`: those fields are simply omitted from the card; no placeholder text shown
- Record with `speaker_name: null` (unresolved attribution): speaker name area shows "Speaker unknown"
- Snippet contains HTML or special characters from source document: characters are escaped/sanitised before display; must not render as HTML
- Source URL is missing or broken: "View source" link is not shown; no broken link is displayed
- Query term appears in highlighted metadata field (e.g., speaker name) and also in snippet: both instances are highlighted independently

## Dependencies

- Feature 01: indexed records with all metadata fields
- Feature 02: search execution providing ranked results and match position data for snippet extraction

## NFR Implications

None beyond Feature 02's response time target, which covers end-to-end time to result list rendered.
