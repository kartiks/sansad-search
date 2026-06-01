# Test Spec 09: Detail Page

Supplements the feature spec. Does not repeat acceptance criteria or edge cases already stated there.

## Adjacent Navigation Boundaries

- A record with `sequence_within_sitting: 1` must have the "Prev" control in a disabled state; clicking a disabled control must produce no navigation
- A record with the maximum `sequence_within_sitting` in its sitting must have the "Next" control disabled
- A sitting containing exactly one record must have both "Prev" and "Next" disabled simultaneously
- Disabled controls must be present in the DOM and visible — not `display:none`, not removed from the DOM

## URL Update on Adjacent Navigation

- After clicking "Next", the browser URL must update to `/record/:id` of the next record before any subsequent "Prev" click; navigating Prev from that updated URL must return to the original record

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
