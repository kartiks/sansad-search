# Feature 07: Indexing Status Panel

## Description

A read-only panel displaying the current state of the search index: total records indexed, a per-source breakdown with date coverage, and the date of the last ingestion run. Gives users transparency about what data is available before or after a search. In v1, the index is populated by a one-time bulk load (Feature 01); the status panel reflects the actual state of the index at any given time, including partial loads.

## Displayed Information

| Item | Description |
|------|-------------|
| Total records indexed | Count of all indexed records across all sources |
| Per-source record count | Separate count for CA, Lok Sabha, and Rajya Sabha |
| Per-source date coverage | Earliest and latest indexed date for each source |
| Last ingestion run | Date the ingestion pipeline last completed or was last run |

### Display format

```
Search Index Status

Total records indexed: [N]

Constituent Assembly      [N] records    1946–1950
Lok Sabha                 [N] records    Jan 2014 – [Month Year]
Rajya Sabha               [N] records    Jan 2014 – [Month Year]

Last updated: [DD Month YYYY]
```

Counts use thousands separators (e.g., "1,234,567"). If a source has not yet been indexed, its row shows "0 records – not yet indexed" rather than a date range.

## Data Source

The status panel reads from a summary record written by the ingestion pipeline (Feature 01) at the end of each run. The summary record stores: per-source record counts, per-source earliest and latest indexed dates, and the ingestion run timestamp. The panel does not query the search index directly at page load; it reads the pre-computed summary.

## Display Surfaces

### Homepage Status Strip

A condensed summary shown on the homepage, below the search box, giving users a quick overview of index scope before searching. Shows per-source record counts and the last ingestion date. Does not show per-source date coverage. Sources with zero indexed records are still shown in the strip; their count displays as "0 [Body] records".

Format: `[N] Constituent Assembly records · [N] Lok Sabha records · [N] Rajya Sabha records · Last updated: [DD Month YYYY]`

### Full Indexing Status Panel

The detailed view of index state, accessible from the results page via a persistent footer link labelled "Index status". Displays the full format described in the Displayed Information section above, including per-source date coverage and the "0 records – not yet indexed" row format for sources with zero records.

## Acceptance Criteria

- The homepage strip displays per-source record counts and the last updated date
- The full indexing status panel displays total record count, per-source counts, per-source date coverage, and last updated date
- Counts and dates reflect the actual state of the index; they are not hardcoded
- Homepage strip: a source with zero indexed records is shown as "0 [Body] records" in the strip; it is not omitted
- Full panel: a source with zero indexed records shows "0 records – not yet indexed" without a date range
- Last updated date reflects the most recent ingestion run completion timestamp, not the current date
- Both surfaces are read-only; no user interaction is required or available beyond viewing

## Edge Cases

- Ingestion pipeline has never been run (fresh deployment): panel shows all sources as "0 records – not yet indexed" and last updated as "Never"
- Ingestion ran but encountered errors and indexed fewer records than expected: panel shows the actual indexed count, not an expected count; no error or warning is displayed in the panel
- Per-source date coverage spans a gap (e.g., some months missing from the middle of the date range): the displayed range is the earliest and latest indexed date; the panel does not indicate internal gaps
- Summary record is malformed or unreadable: the panel displays a "Status unavailable" message in place of the counts and dates; it does not crash or show partial/corrupted data

## Dependencies

- Feature 01: ingestion pipeline that writes the summary record the panel reads from

## NFR Implications

None. The panel reads a pre-computed summary; no real-time index query is performed.
