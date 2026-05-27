# Feature 02: Full-text Search

## Description

The core search interface. Users enter keyword queries; the system executes full-text search across the indexed corpus and returns a ranked result list. Query expansion — synonyms and spell corrections — is integrated into the search execution model, with expanded terms carrying reduced relevance weights. Feature 04 defines the synonym dictionary and correction rules that feed this feature.

## User Flows

**Standard search:**
1. User arrives at homepage; a prominent search box is visible
2. User types a query (minimum 2 characters) and presses Enter or clicks Search
3. System executes search with query expansion and returns a ranked result list
4. User can apply filters (Feature 03), change sort order (Feature 06), and inspect individual results (Feature 05)

**Refinement:**
1. User on results page modifies the query in the persistent search box and resubmits
2. New search executes; results page updates; active filter selections persist across query refinements
3. Filters are only reset by an explicit "clear filters" action (Feature 03)

**No results:**
1. Search executes; no records match
2. System shows explicit no-results state with suggestion to try fewer terms, different terms, or remove filters if any are active

**Invalid query:**
1. User submits query shorter than 2 characters, or submits with an empty box
2. System shows inline validation message; no search is executed

## Search Execution Model

### Fields searched

Queries execute across all of the following fields:

| Field | Description |
|-------|-------------|
| `full_text_en` | Full text of the speech or Q+A exchange |
| `subject` | Debate title or question subject |
| `speaker_name` | Name of the member or minister |
| `minister_name` | Name of the answering minister (Q+A records) |
| `ministry` | Ministry responsible (Q+A records) |

### Term matching and query expansion

- **Single-term query:** the term is expanded with synonyms and spell corrections (see Feature 04); the expanded set is evaluated as OR across all variants; original term scores at full weight; synonyms at reduced weight; spell corrections at lower weight still
- **Multi-term query:** AND logic applies across original term groups; all original terms must be present in a matching record (or covered by expansions); within each term group, OR logic applies across the original term and its expanded variants
- **Phrase query (double-quoted):** the exact phrase is matched first at full weight; phrase-level synonyms from Feature 04 are added as OR alternatives at reduced weight; individual term expansions within the phrase are not applied separately
- A record matching all original terms outranks a record matching only synonym expansions; a synonym match outranks a spell-correction match

### Relevance ranking factors

Applied in combined scoring (not strict hierarchy — all factors contribute to a single relevance score):

1. **Original term coverage:** fraction of original query terms matched in the record (vs. covered only by expansions)
2. **Field match location:** match in `speaker_name`, `subject`, `minister_name`, or `ministry` contributes more to the score than a match only in `full_text_en`
3. **Expansion match type:** synonym match contributes more than spell-correction match
4. **Term frequency and passage relevance:** within `full_text_en`, higher term frequency and denser co-occurrence of query terms contribute positively

### Default search scope

All sources (CA + LS + RS) are included by default. Users narrow scope via filters (Feature 03).

## Acceptance Criteria

- Search box is visible and accessible on the homepage
- A persistent search box pre-populated with the current query appears at the top of the results page
- Queries of 2 or more non-whitespace characters execute and return results
- Queries shorter than 2 non-whitespace characters display an inline validation message; no search is executed
- Empty submission displays an inline validation message; no search is executed
- A record matching all original query terms ranks above a record matching only synonym expansions for the same query
- A phrase query (double-quoted) returns only records where that exact word sequence is present; records containing the individual words non-adjacently do not match the phrase query
- Search is case-insensitive: "Fundamental Rights" and "fundamental rights" return identical result sets
- No-results state shows a clear message and suggestions; it is not an error page
- Search response time: ≤2 seconds at p95 across the full indexed corpus

## UI Behavior

- Homepage: full-width search box with a Search button; no autocomplete in v1
- Results page: compact search box at top pre-filled with current query; results list below
- Inline validation messages appear below the search box; no modal or page redirect
- No-results state: shown in the results area with message and suggestions

## Edge Cases

- Query consisting only of stop words (e.g., "the and or in"): strip stop words; if nothing remains after stripping, show the same validation message as an empty query
- Query exceeding 500 characters: truncate to 500 characters and execute; no error shown to the user
- Special characters (punctuation, brackets, symbols) in query: strip or escape before execution; must not cause a search error or empty result due to parsing failure
- Identical query resubmission: execute again; do not serve a cached stale result set
- Search backend error (infrastructure failure): display an explicit error state ("Search is temporarily unavailable") in the results area with a retry option; do not show an empty results list or a blank page

## Dependencies

- Feature 01: indexed corpus must exist
- Feature 04: synonym dictionary and spell-correction rules (search degrades gracefully to exact-match if Feature 04 is not yet available, but full expansion behaviour requires Feature 04)

## NFR Implications

- **Response time:** ≤2 seconds at p95; query expansion increases scoring computation — architecture must account for this → update NFR
- **Scalability:** search must remain within response time target under concurrent user load → flag for architecture sizing
