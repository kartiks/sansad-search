# Feature 06: Sorting

## Description

Users can sort search results by relevance, chronological order (oldest first), or reverse chronological order (newest first). The default sort is relevance. Sort state persists across query refinements and is only reset when the user explicitly changes it.

## Sort Options

| Option | Order | Description |
|--------|-------|-------------|
| Relevance (default) | Descending relevance score | Records ranked by the combined relevance score from Feature 02; highest-scoring first |
| Chronological | Ascending date | Oldest records first; secondary sort by `sequence_within_sitting` ascending for records on the same date |
| Reverse chronological | Descending date | Newest records first; secondary sort by `sequence_within_sitting` descending for records on the same date |

## User Flows

**Changing sort order:**
1. User is on the results page with an active search and result list
2. User selects a sort option from the sort control
3. Result list re-orders; result count does not change; all active filters remain in place
4. The selected sort option is visually indicated as active

**Sort persistence:**
1. User changes sort to "Chronological" then refines the search query
2. Sort selection persists; new results are displayed in chronological order

## Acceptance Criteria

- Three sort options are available on the results page: Relevance, Chronological, Reverse chronological
- Default sort on every new search is Relevance
- Changing sort re-orders results without changing the result count or clearing filters
- Sort selection persists across query refinements
- Chronological and reverse-chronological sorts use date as the primary key and `sequence_within_sitting` as the secondary key
- Relevance sort uses the relevance score from Feature 02; records are not additionally sorted by date in relevance mode

## Edge Cases

- All results share the same date (e.g., single-sitting filter): chronological and reverse-chronological both use `sequence_within_sitting` as the effective sort key; results are ordered by their position within that sitting
- Relevance sort with query expansion: records matching only expanded terms appear lower in relevance order than those matching original terms; this is governed by the scoring model in Feature 02, not by the sort control

## Dependencies

- Feature 02: relevance scores used for the relevance sort option
- Feature 01: `date` and `sequence_within_sitting` fields used for date-based sort options

## NFR Implications

None beyond the response time target in Feature 02.
