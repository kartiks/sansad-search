# Feature 08: Search History

## Description

Cookie-based recent searches and saved searches. No sign-in is required. All data is stored client-side in cookies; nothing is sent to the server. Recent searches are recorded automatically when a query is submitted. Saved searches are explicitly bookmarked by the user and persist until deleted. Both are accessible from the homepage and the results page.

## Recent Searches

### Storage and limits
- Automatically recorded each time a search query is submitted (regardless of whether any results were returned)
- Maximum 10 entries stored; when the limit is exceeded, the oldest entry is removed
- Duplicate queries: if the same query string is submitted again, the existing entry is updated to the most recent timestamp; only one entry per unique query string is maintained
- Cookie lifetime: 30 days from the most recent submission; entries older than 30 days are not displayed
- What is stored per entry: query text and submission timestamp; filter state is not stored with recent searches

### Actions
- Click a recent search entry to re-run that query (with default filters and default sort — not with any previously active filter state)
- Delete an individual recent search entry
- Clear all recent searches at once

## Saved Searches

### Storage and limits
- Explicitly saved by the user from the results page
- Maximum 20 saved searches stored
- When the 20-entry limit is reached, the user must delete an existing saved search before a new one can be saved; the save action is disabled with an explanatory message when at the limit
- No expiry; saved searches persist until the user deletes them
- Cookie lifetime: persistent (no expiry date set on the cookie); persists until cookie is cleared by the browser

### What is stored per saved search
- Name: defaults to the query text; user can rename to a custom label (max 60 characters)
- Query text
- Active filter state at the time of saving (legislative body, date range, speaker, session, proceeding type selections)
- Save timestamp

### Actions
- Save the current search (query + active filters) from the results page
- Re-run a saved search: re-executes the stored query with the stored filter state and default sort
- Rename a saved search (edit the name label)
- Delete a saved search

## Cookie Storage Constraints

- Recent searches and saved searches are stored in separate cookies
- Total cookie data for both combined must not exceed 4KB; if stored data approaches this limit, recent searches are trimmed first (oldest removed) before saved searches are affected
- If cookies are disabled in the browser, recent and saved search features are silently unavailable; the rest of the application functions normally with no error shown

## Acceptance Criteria

- Every submitted search query is added to recent searches automatically
- Recent searches list shows at most 10 entries, ordered by most recent first
- Submitting a duplicate query updates the timestamp and position of the existing entry; it does not create a second entry
- Saved searches store and restore query text and filter state exactly; re-running a saved search produces the same filter-active result set as if the user had manually set those filters
- Saved search name defaults to the query text and is editable up to 60 characters
- Saving is disabled (with message) when 20 saved searches exist
- Deleting a recent or saved search removes it immediately without page reload
- All history features work without user authentication; no data is sent to the server

## Edge Cases

- Cookie storage near capacity: oldest recent searches are removed silently to free space; saved searches are not removed automatically
- User clears browser cookies: all recent and saved search data is lost; application continues to function; no error shown
- Saved search references filter values that are no longer valid (e.g., a proceeding type that was renamed): the saved search still executes with the stored filter state; invalid filter values are silently ignored (treated as "not set") rather than causing an error
- Same query saved twice: allowed; user may give them different names; they appear as two separate entries
- Very long query text (up to 500 characters, the search truncation limit): stored and displayed as-is in the saved/recent list; display is truncated visually if the label is too long, but the full query is preserved for re-execution

## Dependencies

- Feature 02: search execution that accepts a query string
- Feature 03: filter state model that saved searches restore

## NFR Implications

- **Privacy:** all search history data is stored client-side in cookies only; no search queries or filter selections are persisted server-side in v1 → note in NFR
