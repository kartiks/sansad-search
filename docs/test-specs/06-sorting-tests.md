# Test Spec 06: Sorting

Supplements the feature spec. Does not repeat acceptance criteria or edge cases already stated there.

## Secondary Sort Key

- Two records with the same date must be ordered by `sequence_within_sitting` ascending in chronological mode and descending in reverse-chronological mode; date alone is insufficient as a sort key when records share a date

## Relevance Sort Isolation

- Switching from chronological to relevance sort must reorder results by relevance score; the previous date-based order must not be preserved as a tiebreaker within equal-relevance groups (tiebreaking within relevance sort is undefined and must not silently default to date order)

## Sort Persistence Across Refinement

- User sets sort to "Chronological", then edits the query and resubmits; the sort control must still show "Chronological" as active; new results must be in chronological order

## Result Count Invariance

- Changing sort order must not change the result count displayed; the count before and after a sort change must be identical for the same query and filter state

## Default Sort on New Search

- Every new search (fresh query submission from homepage or results page with a cleared query) must default to Relevance sort, regardless of the sort option that was active in the previous search session
