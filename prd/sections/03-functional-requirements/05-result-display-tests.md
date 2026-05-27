# Test Spec 05: Result Display

Supplements the feature spec. Does not repeat acceptance criteria or edge cases already stated there.

## Snippet from Supplementary Exchange

- When the highest-relevance match for a starred Q+A record is in a supplementary exchange (not the main Q+A), the displayed snippet must be drawn from the supplementary exchange and the "From supplementary exchange" label must be present; a snippet from the main Q+A must not be shown instead

## Result Count Threshold

- A result set of exactly 9,999 records must display an exact count ("9,999 results"), not the approximate form
- A result set of exactly 10,000 records must display the approximate form ("10,000+ results"), not an exact count
- A result set of exactly 0 records must display "0 results", not the no-results state message (the no-results state message is for when no records match the query; "0 results" appears when the count is computed but is zero — these are the same situation, but the count display and the no-results message must both be present)

## Untranslated Speech Snippet Placeholder

- A record with `full_text_en: null` must display the "This speech was delivered in Hindi. No English text is available." message in the snippet area
- The snippet area for such records must not be empty, blank, or absent — the placeholder message is required
- A record with `full_text_en: null` must still display all other metadata fields normally (body, date, speaker, subject, source link)

## HTML Sanitisation in Snippet

- A `full_text_en` value containing HTML tags (e.g., `<b>`, `<script>`, `&amp;`) must render as plain text in the snippet; tags must not be interpreted as HTML; script tags must not execute

## Page URL Persistence

- Navigating to page 3 of results, copying the URL, and opening it in a new browser session must load page 3 of the same search results without requiring re-entry of the query
- The URL must encode both the query and the page number; a URL missing either parameter must default to page 1 of the query results

## Co-Signatory Display

- A starred question with exactly 1 questioner must not show the "+N others" label
- A starred question with 3 co-signatories (4 total including primary) must show "+3 others" next to the primary questioner's name

## Speaker Name Unresolved Display

- A record with `speaker_name_unresolved: true` must display the raw name stored in `speaker_name` without any error indicator or blank; the display must be identical in format to a resolved name
