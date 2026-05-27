# Test Spec 03: Search Filters

Supplements the feature spec. Does not repeat acceptance criteria or edge cases already stated there.

## Session Filter Excludes CA Records

- When a session filter is active (any non-empty value), CA records must be absent from the result set even if CA is selected in the body filter and the query would otherwise match CA records

## Date Range Gap

- A date range of 1948-01-01 to 2015-12-31 must return CA records dated 1948-01-01 to 1950-12-31 and LS/RS records dated 2014-01-01 to 2015-12-31; no records from 1951–2013 must appear; no error must be shown for the gap years

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

## Combined Filter AND Logic

- A query with body = LS, proceeding type = Starred Question, speaker = "Jairam Ramesh" must return only records satisfying all three constraints simultaneously; a LS debate speech by "Jairam Ramesh" must not appear; a RS starred question by "Jairam Ramesh" must not appear
