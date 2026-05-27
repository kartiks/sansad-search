# Test Spec 08: Search History

Supplements the feature spec. Does not repeat acceptance criteria or edge cases already stated there.

## Duplicate Query Deduplication

- Submitting the same query string three times must result in exactly one entry in recent searches, with the timestamp of the third submission; not two or three entries

## FIFO Rotation at Limit

- With 10 recent searches already stored, submitting an 11th (distinct) query must remove the oldest entry and add the new one; the list must remain at exactly 10 entries; the oldest entry must not reappear after the new submission

## Recent Search Re-runs with Default Filters

- Re-running a recent search must execute with all filters at their defaults, regardless of what filters were active when that query was originally submitted; the recent search entry does not capture filter state

## Saved Search Filter Restoration

- A saved search created with body = Rajya Sabha, proceeding type = Starred Question, date from = 2020-01-01 must restore exactly those filter selections when re-run; the result set must be equivalent to manually setting those same filters for that query

## Save Disabled at Limit

- With exactly 20 saved searches stored, the save action must be visibly disabled and show an explanatory message; attempting to trigger the save action by any means must not create a 21st entry

## Same Query Saved Twice

- Saving the same query text twice must create two separate saved search entries; the second save must not overwrite or merge with the first

## Cookie-Disabled Behaviour

- When cookies are blocked, recent searches and saved searches must not be shown; no error message about cookies must be displayed to the user; the search box and results must function normally

## Saved Search Name Length

- A saved search name of exactly 60 characters must be accepted; a name of 61 characters must be rejected (input truncated or validation shown) without losing the save action

## Stale Filter Value in Saved Search

- Re-running a saved search that contains an unrecognised proceeding type value (e.g., from a future schema change) must execute the search ignoring that filter value; it must not throw an error or prevent the search from running
