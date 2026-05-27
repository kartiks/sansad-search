# Test Spec 02: Full-text Search

Supplements the feature spec. Does not repeat acceptance criteria or edge cases already stated there.

## Phrase Query Non-Adjacency

- A record containing "fundamental" and "rights" separated by other words must NOT match a phrase query for `"fundamental rights"`; only records where those words appear consecutively and in that order must match

## Field Boost vs. Term Frequency

- Given two records where record A contains the query term once in `speaker_name` and record B contains the query term ten times in `full_text_en` only, record A must rank higher than record B

## Expansion Weight Ordering

- For the same query and the same record, a match on the original term must produce a higher relevance score than a match on a synonym; a synonym match must produce a higher relevance score than a spell-correction match
- This ordering must hold even when term frequency in `full_text_en` is higher for the lower-ranked expansion variant

## AND Logic With Partial Expansion Coverage

- A record matching original term 1 and only a synonym expansion of term 2 must rank lower than a record matching both original terms
- A record matching only synonym expansions for all query terms must rank lower than a record matching at least one original term

## Case Insensitivity

- Queries "article 370", "Article 370", "ARTICLE 370", and "Article 370" must return identical result sets in identical rank order
- Speaker names in mixed case in the index must be matched regardless of the case used in the query

## Stop Word Boundary

- A query of "the right to speech" must execute as a search for "right speech" (stop words stripped); the result set must not differ from a direct query for "right speech"
- A query consisting entirely of stop words (e.g., "the and or") must show the validation message, not an empty result list

## Query Truncation

- A query of exactly 501 characters must be truncated to 500 characters before execution; the truncated query must execute without error
- The truncated query must not expose the truncation to the user (no error message, no truncation indicator)

## Special Character Handling

- A query containing parentheses, brackets, quotation marks, or boolean operators as literal characters (not as phrase delimiters) must not cause a search error; results must be returned or a no-results state shown
- A query of only special characters must be treated as an empty query and show the validation message

## Refinement Filter Persistence

- When the user modifies the query on the results page and resubmits, any active filter selections from Feature 03 must persist; the new result set must reflect the new query AND the previously active filters
- Only an explicit "clear filters" action (Feature 03) resets filters to defaults
