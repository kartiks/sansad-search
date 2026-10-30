# Test Spec 03: Search Filters

Supplements the feature spec. Does not repeat acceptance criteria or edge cases already stated there.

## Session Filter Excludes CA Records

- When a session filter is active (any non-empty value), CA records must be absent from the result set even if CA is selected in the body filter and the query would otherwise match CA records

## Date Range Gap

- A date range spanning the gap between CA proceedings and LS/RS sittings (e.g., 1951-01-01 to 1951-12-31, after CA ended and before Parliament was constituted) must return zero results without error
- A date range that spans records from multiple sources with a gap between them must return the union of records from each source within the range; no error must be shown for the gap years

## Proceeding Type Constraint When Only CA Is Selected

- When CA is the only selected body, selecting any proceeding type other than "Debate" must produce zero results, not an error; the disabled state of the non-Debate options is a UI concern but the filter must still be functionally correct (no results, no crash)

## Speaker Substring Matching

- A speaker filter value of "Singh" must match records attributed to any canonicalized speaker name containing "Singh" (e.g., "Manmohan Singh", "Rajnath Singh", "V.P. Singh")
- A speaker filter value containing only whitespace must be treated as an empty filter (no speaker restriction applied)

## Filter Persistence Across Query Refinements

- After applying a Rajya Sabha body filter and refining the search query, the result set must contain only RS records; the body filter must not silently reset to "all bodies"
- The active filter indicator on the results page must still show the RS filter as active after query refinement

## Zero-Selection Validation

- Deselecting all bodies and submitting must show a validation message and not execute a search; the previous result set must remain visible
- Deselecting all proceeding types and submitting must show a validation message and not execute a search; the previous result set must remain visible

## Date Validation Ordering

- Setting From = 2022-06-01 and To = 2021-01-01 (From after To) must show an inline validation error and must not modify the displayed result set

## Subject Filter Substring Matching

- A subject filter value that is a substring of a longer subject (e.g., "Water" matching a record with subject "Water Resources Management") must produce a match; an exact-only match implementation is a bug
- A subject filter value containing only whitespace must be treated as an empty filter; the result set must be identical to the unfiltered result set

## Combined Filter AND Logic

- A query with body = LS, proceeding type = Starred Question, speaker = "Jairam Ramesh" must return only records satisfying all three constraints simultaneously; a LS debate speech by "Jairam Ramesh" must not appear; a RS starred question by "Jairam Ramesh" must not appear
