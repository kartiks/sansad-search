# Feature 03: Search Filters

## Description

Filters allow users to narrow search results by legislative body, date range, speaker, session, and proceeding type. All filters are combinable with each other and with the search query. Filter state persists across query refinements on the results page and is only reset by an explicit clear action.

## User Flows

**Applying filters:**
1. User is on the results page with an active search query
2. User selects one or more filter values (body, date range, speaker, session, proceeding type)
3. System re-executes the search with the filter constraints applied; result list updates
4. Active filters are visually indicated; result count reflects the filtered set

**Clearing filters:**
1. User clicks "Clear filters" (clears all filters at once) or removes an individual filter value
2. System re-executes the search without the cleared constraint(s); result list updates

**Filter persistence:**
1. User refines the search query while filters are active
2. Active filter selections persist; new results reflect the updated query AND the existing filters
3. Filters are only reset by an explicit clear action — not by query refinement

**No results with active filters:**
1. Active filters eliminate all results for the current query
2. System shows the no-results state (Feature 02) with an additional "clear filters" suggestion

## Filter Dimensions

### 1. Legislative body
- Multi-select: CA, Lok Sabha, Rajya Sabha
- Default: all three selected (no body restriction)
- Any combination of one, two, or all three is valid

### 2. Date range
- Two inputs: From date and To date
- Both are optional; leaving one or both empty applies no date bound on that side
- Date range is constrained to the indexed scope:
  - When only CA is selected in the body filter: picker restricts to 1946-01-01 – 1950-12-31
  - When only LS and/or RS is selected: minimum selectable date is 1947-08-15
  - When CA and LS/RS are both selected: full range 1946-01-01 to present is selectable; records from each body are included within their respective indexed scope
- From date must not be later than To date; if it is, an inline validation message is shown and the filter is not applied

### 3. Speaker
- Free text input; case-insensitive substring match against the canonical `speaker_name` field
- Matches speaker names containing the entered string anywhere in the name
- Empty field: no speaker filter applied
- Note: speaker names in the index are canonicalized (honorifics stripped, variants resolved); users searching "Dr. Ambedkar" should enter "Ambedkar" for reliable results; a note to this effect is shown near the field
- No autocomplete in v1

### 4. Session
- Free text input; case-insensitive substring match against `session_name`
- Matches sessions whose name contains the entered string (e.g., "Budget" matches "Budget Session 2023")
- Empty field: no session filter applied
- CA records have null `session_name` and will not match any session filter query; when a session filter is active, CA records are excluded from results
- No autocomplete in v1

### 5. Subject
- Free text input; case-insensitive substring match against the `subject` field
- Matches records whose subject contains the entered string anywhere
- Empty field: no subject filter applied
- No autocomplete in v1

### 6. Proceeding type
- Multi-select: Debate, Starred Question, Unstarred Question, Zero Hour, Short Notice Question, Calling Attention, Short Duration Discussion, Adjournment Motion, Private Member Bill
- Default: all types selected (no type restriction)
- Available options are constrained by the legislative body selection:
  - When only CA is selected: only "Debate" is available; all other options are disabled
  - When LS and/or RS is selected (alone or with CA): all options are available
- A user selecting types that do not exist for a selected body will simply receive no results from that body for those types; no error is shown

## Filter Combination Logic

All active filters are ANDed together and ANDed with the search query. A record must satisfy all active filter constraints to appear in results.

Examples:
- Body = Rajya Sabha AND Date = 2020–2022 AND Proceeding type = Starred Question: returns only RS starred questions from that date range
- Speaker = "Ambedkar": returns all record types from all bodies where `speaker_name` contains "Ambedkar" (primarily CA records)
- Session = "Monsoon": returns all records from any session whose name contains "Monsoon" (LS/RS only; CA excluded)

## Acceptance Criteria

- All six filter dimensions are available on the results page
- Subject filter applies a case-insensitive substring match against the `subject` field; empty value applies no subject restriction
- Each filter can be set independently or in any combination
- Active filters are visibly indicated on the results page (e.g., filter chips or highlighted state)
- A "clear filters" control resets all filters to their defaults in a single action
- Individual filter values can be removed without clearing all filters
- Filter state persists when the user refines the query; only an explicit clear resets filters
- Date range From > To shows a validation message; filter is not applied
- Proceeding type options disable correctly when only CA is selected in the body filter
- Session filter active: CA records are excluded from the result set
- Result count displayed on the results page reflects the filtered set, not the total unfiltered count

## Edge Cases

- All proceeding types deselected: show validation message ("Select at least one proceeding type"); do not execute search with zero types selected
- All legislative bodies deselected: show validation message ("Select at least one source"); do not execute search with zero bodies selected
- Speaker filter with no matching canonical name in the index: show no-results state; do not error
- Session filter value that partially matches multiple sessions (e.g., "Session 2022" matches Monsoon Session 2022, Budget Session 2022, Winter Session 2022): all matching sessions are included in results
- Date range spans years with no indexed records (e.g., between the end of CA proceedings and the first LS/RS sittings, or RS years not covered by the current provider chain): result set is the union of records that exist within the range from each indexed source; no error is shown for the gaps

## Dependencies

- Feature 01: canonical `speaker_name` and `session_name` fields in the index
- Feature 02: search query execution that accepts filter constraints

## NFR Implications

None beyond what is already captured for Feature 02 (search response time target applies to filtered queries as well).
