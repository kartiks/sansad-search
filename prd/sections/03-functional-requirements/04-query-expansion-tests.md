# Test Spec 04: Query Expansion

Supplements the feature spec. Does not repeat acceptance criteria or edge cases already stated there.

## Bidirectionality

- A query for "House of the People" must expand to include "Lok Sabha" at synonym weight; a query for "Lok Sabha" must expand to include "House of the People" at synonym weight
- Bidirectionality must hold for all synonym pairs in the dictionary; a synonym that expands A→B must also expand B→A

## Phrase Synonym Isolation

- A query for "fundamental rights" (unquoted multi-term) must expand using the phrase synonym "basic rights"; it must NOT additionally expand "fundamental" as a standalone term or "rights" as a standalone term via any single-term synonym entries
- A query for "rights" alone must not expand to "fundamental rights" via the phrase synonym; phrase synonyms must only apply when the full phrase is present in the query

## Spell Correction Suppression in Phrases

- A quoted phrase query containing a misspelled term (e.g., `"Parliment debate"`) must not apply spell correction; the phrase must be searched verbatim and return results only for that exact sequence

## Short Term Exemption

- A query term of 1, 2, or 3 characters must not trigger spell correction; the term must be searched as-is with no corrected alternatives added
- A query term of exactly 4 characters must be eligible for spell correction

## Correction Weight Below Synonym Weight

- For a query where both a synonym expansion and a spell correction match the same record, the synonym match contribution to the relevance score must be higher than the spell correction match contribution; they must not produce equal scores

## Ambiguous Abbreviation Expansion

- A query for "SC" must generate expansions for both "Scheduled Castes" and any other known expansions in the dictionary; all expansions must appear in results at reduced weight; the absence of any defined expansion for "SC" is a bug

## Dictionary as Sole Source

- Introducing a synonym relationship that is only hardcoded in application logic (not present in the dictionary file) must cause a test to fail; all synonym relationships must be derivable solely from the dictionary file

## Substring Non-Expansion

- A query term "MGNREGA" must not trigger the "PM" → "Prime Minister" synonym expansion because "PM" appears as a substring; expansion must only apply to exact full-term matches
