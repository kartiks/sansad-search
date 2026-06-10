# Feature 04: Query Expansion

## Description

Query expansion augments user queries with synonyms and spell corrections before search execution, improving recall for users who search with different terminology than what appears in the indexed records. Expanded terms are OR alternatives carrying reduced relevance weights — see Feature 02 for how weights are integrated into result ranking. The expansion dictionary is seeded with parliamentary domain-specific terms and maintained as a static file in the codebase; updates require a re-deployment.

## Query Preprocessing

Before synonym expansion and spell correction, the query string is normalized:

- U+201C (") and U+201D (") curly double quotes are converted to ASCII straight double quotes (`"`)

This ensures that phrase queries typed on macOS and iOS — which auto-substitute typographic curly quotes for `"` — are correctly interpreted as phrase search syntax by Meilisearch, which uses ASCII straight double quotes to delimit phrase queries.

## Synonym Dictionary

### Coverage

The dictionary covers the following categories of parliamentary domain synonyms. Synonyms are bidirectional: if A expands to B, B also expands to A.

**Legislative bodies**
- "Lok Sabha" ↔ "House of the People" ↔ "Lower House"
- "Rajya Sabha" ↔ "Council of States" ↔ "Upper House"
- "Parliament" ↔ "both Houses" (phrase-level synonym for contexts referencing joint sessions)
- "Constituent Assembly" ↔ "CA" (abbreviation only; not expanded to other phrases)

**Constitutional terminology**
- "fundamental rights" ↔ "basic rights" ↔ "Part III rights"
- "Directive Principles" ↔ "DPSP" ↔ "Directive Principles of State Policy"
- "amendment" ↔ "constitutional amendment" (phrase-level, for queries about constitutional changes)
- "Preamble" ↔ "preamble to the Constitution"

**Parliamentary procedure**
- "starred question" ↔ "oral question"
- "unstarred question" ↔ "written question"
- "zero hour" ↔ "zero-hour"
- "private member bill" ↔ "private member's bill"
- "calling attention" ↔ "calling attention motion"
- "adjournment motion" ↔ "adjournment"
- "Question Hour" ↔ "question period"
- "division" ↔ "vote" (in parliamentary voting context)

**Common abbreviations expanded to full forms**
- "PM" ↔ "Prime Minister"
- "CM" ↔ "Chief Minister"
- "SC" ↔ "Scheduled Castes" (single-term; not expanded when "SC/ST" is used together)
- "ST" ↔ "Scheduled Tribes" (single-term)
- "SC/ST" ↔ "Scheduled Castes and Scheduled Tribes" (phrase-level)
- "OBC" ↔ "Other Backward Classes" ↔ "Other Backward Communities"
- "EWS" ↔ "Economically Weaker Sections"
- "GST" ↔ "Goods and Services Tax"
- "CAG" ↔ "Comptroller and Auditor General"
- "CBI" ↔ "Central Bureau of Investigation"
- "ED" ↔ "Enforcement Directorate"
- "FIR" ↔ "First Information Report"
- "PIL" ↔ "Public Interest Litigation"
- "Art." ↔ "Article" (for constitutional article references)
- "Sec." ↔ "Section"
- "Cl." ↔ "Clause"

**Well-known legislation (short title ↔ full title)**
- "RTI" ↔ "Right to Information" ↔ "Right to Information Act"
- "RTE" ↔ "Right to Education" ↔ "Right to Education Act"
- "MGNREGA" ↔ "NREGA" ↔ "Mahatma Gandhi National Rural Employment Guarantee Act"
- "POCSO" ↔ "Protection of Children from Sexual Offences"
- "IPC" ↔ "Indian Penal Code"
- "CrPC" ↔ "Code of Criminal Procedure"
- "BNS" ↔ "Bharatiya Nyaya Sanhita"
- "BNSS" ↔ "Bharatiya Nagarik Suraksha Sanhita"

### Phrase synonyms vs. single-term synonyms

Phrase synonyms (e.g., "fundamental rights" ↔ "basic rights") apply only when the user's query contains the full phrase or when the user submits a phrase query (quoted or unquoted multi-word sequence matching the phrase). Single-term synonyms (e.g., "PM" ↔ "Prime Minister") apply to individual query terms.

Multi-word synonyms are not broken into individual terms for expansion. "Fundamental rights" as a phrase synonym does not cause "fundamental" alone to expand to anything, nor "rights" alone.

### Dictionary maintenance

The dictionary is a static structured file (e.g., JSON or YAML) maintained in the codebase. Adding or modifying synonyms requires updating the file and redeploying. The dictionary file is the single source of truth; no runtime editing in v1.

## Spell Correction

### Scope

Spell correction applies to individual query terms. It does not apply within phrase queries (quoted terms are matched verbatim; spell correction is suppressed inside quotes).

### Correction method

Edit-distance based correction: terms within a configurable edit distance from indexed vocabulary are offered as corrections. Phonetic matching is applied additionally for proper nouns (member names, place names) where character-level edit distance is insufficient.

### Correction behaviour

- A corrected term is added as an OR alternative at a lower weight than synonym expansions
- The original (possibly misspelled) term is still included in the query at full weight; if the original term happens to match records exactly, those matches are returned
- Correction is applied silently — no "did you mean?" prompt is shown in v1; corrections appear in results without user notification
- Over-correction risk: very short terms (fewer than 4 characters) are exempt from spell correction to avoid spurious matches

## Acceptance Criteria

- A query for "PM" returns records containing "Prime Minister" at a lower relevance weight than records containing "PM"
- A query for "fundamental rights" returns records containing "basic rights" at a lower relevance weight than records containing "fundamental rights"
- A query for "Parliment" (misspelled) returns records containing "Parliament" at a reduced weight
- A quoted phrase query ("fundamental rights") applies phrase-level synonyms only; individual term synonyms are not applied to terms inside the quotes
- A query string containing U+201C or U+201D curly quotes around a phrase is treated as a phrase query equivalent to the same phrase enclosed in ASCII straight double quotes
- Terms shorter than 4 characters are not spell-corrected
- Synonyms and spell corrections apply to LS, RS, and CA records equally
- The synonym dictionary file is the only source of synonym definitions; no synonyms are hardcoded elsewhere in the application

## Edge Cases

- Ambiguous abbreviation ("SC" in a legal context vs. "SC" as Supreme Court): expand to all known expansions; ranking determines which is more relevant to the query context
- User queries a term that is itself a synonym expansion of another term (e.g., user searches "House of the People"): expands bidirectionally to include "Lok Sabha" at reduced weight
- Dictionary term that is a substring of a longer query term: expansion applies only to exact term matches, not substring matches (e.g., "PM" does not expand within "MGNREPM")
- Spell correction produces a correction that is also in the synonym dictionary: apply both — the correction is an OR alternative at correction weight; the correction's synonym is a further OR alternative at synonym weight

## Dependencies

- Feature 02: the search execution model that consumes expansion output and applies relevance weights

## NFR Implications

None beyond what is captured in Feature 02 (response time target must account for expansion computation).
