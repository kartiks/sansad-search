# Test Spec 10: Debug Mode

Supplements the feature spec. Does not repeat acceptance criteria or edge cases already stated there.

## Activation Isolation

- A page load without `?debug=1` must produce zero calls to `/api/debug/processed/*` or `/api/debug/raw/*` endpoints — not even prefetched or background calls
- A page load with `?debug=1` must not activate debug mode on other open tabs or sessions that do not have the parameter in their URL

## Lazy Fetch Caching

- Expanding the Processed record section, collapsing it, and expanding it again must result in exactly one total call to `/api/debug/processed/{id}`, not two
- Expanding the Raw document section for result A and then expanding the Raw document section for result B must result in two separate calls (one per result id), not one shared call
- Expanding Processed record for a result must not trigger a call to `/api/debug/raw/{id}` for that result, and vice versa

## Normal Mode Regression

- In normal mode (no `?debug=1`), the DOM must contain no debug toggle elements, no debug panel containers, and no global debug panel element — not merely hidden with CSS
- Meilisearch search requests made in normal mode must not include `_rankingScore` or `_rankingScoreDetails` in the attributes to retrieve — confirmed by inspecting the request body or the API response for the absence of these fields

## 404 Handling in Debug Sections

- When `GET /api/debug/processed/{id}` returns 404, the Processed record section must display an error message; the rest of the debug panel (Scoring details, Document in index, Raw document) must continue to function normally
- When `GET /api/debug/raw/{id}` returns 404, the Raw document section must display an error message; other sections must be unaffected

## Section Independence

- Collapsing the global debug panel must not collapse any per-result debug panel, and vice versa
- Each of the five global sections must be independently togglable; expanding one must not collapse another
- Each of the four per-result sections must be independently togglable
