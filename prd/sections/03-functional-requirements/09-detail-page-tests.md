# Test Spec 09: Detail Page

Supplements the feature spec. Does not repeat acceptance criteria or edge cases already stated there.

## Lok Sabha Term Display

- A record with `lok_sabha_number: 17` must display "17th Lok Sabha"; a record with `lok_sabha_number: 21` must display "21st Lok Sabha"; a record with `lok_sabha_number: 22` must display "22nd Lok Sabha"; a record with `lok_sabha_number: 23` must display "23rd Lok Sabha" — the ordinal suffix must be correct for each value
- An RS record must not render any element with the text "Lok Sabha" in the metadata area; the `lok_sabha_number` field must be entirely absent from the DOM

## Inline Adjacent Loading

- Clicking "Load 5 next" must not trigger a page navigation; the URL must remain `/record/:id` of the focal record after the click
- After "Load 5 next" loads 5 records and 3 more remain, the "Load 5 next" control must be enabled; after a subsequent click that loads those 3, the control must be disabled
- Clicking "Load 5 previous" must prepend records above the focal record, not replace it; the focal record must remain in the DOM after any number of adjacent loads
- When the focal record is the only record in its sitting, both load controls must be disabled simultaneously; neither must be hidden or absent from the DOM

## Back Navigation Detection

- A record opened via in-app navigation from the results page must show "Back to results"; the link must navigate back to the results page without re-executing the search
- A record opened by pasting its URL directly into a new tab must show "Search" (to homepage) and must not show "Back to results"

## Null Full Text Area

- A record with `full_text_en: null` must render the defined message in the text area; the text area must not be empty, blank, or absent
- The same record must still render all non-null metadata fields; the null `full_text_en` must not suppress other field rendering

## page_reference Formatting

- A record with `page_reference: 42` must display "PDF page 42"; arbitrary integer values must be formatted as "PDF page [N]" with no additional text
- A record with `page_reference: null` must show no page reference label or value — not "PDF page —" or "PDF page null"

## sequence_within_sitting Display

- The "position in sitting" display must show "[N] of [M]" where M is the actual count of records sharing the same `source` + `date` + `sitting_number`; M must not be hardcoded or estimated

## 404 Handling

- A request to `/record/nonexistent-id` must render a "Record not found" page; it must not render a blank page, a JS error, or a partially loaded detail page
