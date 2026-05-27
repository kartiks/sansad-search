# Test Spec 07: Indexing Status Panel

Supplements the feature spec. Does not repeat acceptance criteria or edge cases already stated there.

## Pre-computed Summary — Not Live Query

- The panel must not issue a query to the search index at page load; it must read from the pre-computed summary record written by the ingestion pipeline; a test that disables the search index must still show the last known status data without error

## Never-Run State

- On a fresh deployment where ingestion has never been run, the "Last updated" field must display "Never", not a null value, blank, or a default date

## Zero-Source Row Format

- A source with zero indexed records must display "0 records – not yet indexed" with no date range; displaying an empty date range string or a placeholder date (e.g., "Jan 1970") is a bug

## Count Accuracy

- The total records count displayed must equal the sum of the three per-source counts; a discrepancy between the total and the sum is a bug

## Ingestion Timestamp

- The "Last updated" date must reflect the ingestion run completion timestamp; it must not update when the page is loaded, when a search is run, or at any other time other than after an ingestion pipeline run
