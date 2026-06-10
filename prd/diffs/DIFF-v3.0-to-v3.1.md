# PRD Diff: v3.0 → v3.1

**Generated:** 2026-06-09  
**Scope:** Post-phase-15 implemented changes incorporated into PRD  
**Nature:** All changes are modifications to existing features (F01, F03, F04, F05, F08) and supporting sections; no new feature numbers added.

---

## F01: Data Ingestion — MODIFIED

### 1. LS date scope expanded

**Before:** `2014-01-01 to present`  
**After:** `1947-08-15 to present`

Applies to: Data Sources table, acceptance criteria ("All LS and RS records dated 2014-01-01 or later" replaced with separate LS and RS criteria), and the date range boundary test spec (was `2014-01-01`; now `1947-08-15`).

### 2. LS provider chain updated

**Before:**  
Format: `Pre-OCR plain text (_djvu.txt); PDF`  
Base URL: `eparlib.sansad.in (primary); Internet Archive _djvu.txt pre-OCR text (fallback)`

**After:**  
Format: `Pre-OCR plain text (_djvu.txt); Tika-extracted PDF text`  
Base URL: `Internet Archive _djvu.txt pre-OCR text; elibrary.sansad.in DSpace 7 Text of Debates English (2019-01-01 to present)`

`eparlib.sansad.in` removed (confirmed unresponsive). `elibrary.sansad.in DSpace 7` added as new LS provider covering 2019-01-01 to present with Tika-extracted PDF text.

### 3. RS provider chain updated

**Before:**  
Date scope: `2014-01-01 to present`  
Format: `HTML and PDF`  
Base URL: `sansad.in/rs HTML (primary); Internet Archive; rsdebate.nic.in DSpace (fallback)`

**After:**  
Date scope: `1947-08-15 to present`  
Format: `Pre-OCR plain text (_djvu.txt)`  
Base URL: `Internet Archive (see RS coverage note)`

`sansad.in/rs` removed (JavaScript-rendered, not crawlable). `rsdebate.nic.in` removed (unresponsive). RS chain now contains Internet Archive only. Post-2018 RS records currently unavailable.

**RS coverage note added** (new paragraph after Data Sources table):

> The Rajya Sabha provider chain currently contains Internet Archive only. `sansad.in/rs` was removed because it is JavaScript-rendered and not crawlable; `rsdebate.nic.in` was removed because it is unresponsive. RS coverage therefore reflects what Internet Archive holds, which does not currently extend to post-2018 records. The provider chain is designed to be extended — adding a new RS provider restores coverage for the periods it serves without requiring changes to this spec.

### 4. source_url field description simplified

**Before (speech and Q+A):**  
"For LS records: always the Internet Archive URL (eparlib.sansad.in is not reliably accessible and must not be used). For RS records fetched via Internet Archive or rsdebate.nic.in: the Internet Archive URL. For RS records fetched from sansad.in HTML: the sansad.in URL."

**After:**  
"For LS records: the Internet Archive URL. For RS records: the Internet Archive URL (current chain contains Internet Archive only)."

### 5. Acceptance criteria updated

**Before:**  
"All LS and RS records dated 2014-01-01 or later are ingested across all proceeding types listed above"  
"For LS records, source_url is the Internet Archive URL; for RS records fetched via IA or rsdebate.nic.in, source_url is the Internet Archive URL; for RS records from sansad.in HTML, source_url is the sansad.in URL; for CA records, source_url is the constitutionofindia.net URL"

**After:**  
"All LS records dated 1947-08-15 or later available in the LS provider chain are ingested across all proceeding types listed above"  
"RS records are ingested from all providers in the RS provider chain; coverage reflects what those providers make accessible"  
"For LS records, source_url is the Internet Archive URL; for RS records, source_url is the Internet Archive URL; for CA records, source_url is the constitutionofindia.net URL"

### 6. Edge case removed

**Removed:** "RS record fetched from Internet Archive with no derivable DSpace handle: set `source_url` to null; log a warning; do not use the archive.org URL as a fallback to this rule"

This edge case was specific to the rsdebate.nic.in → IA URL derivation path. Since rsdebate.nic.in is removed, the edge case is moot.

### 7. Test spec: Date Range Boundary updated

**Before:**  
"Records dated exactly 2014-01-01 are included in scope; records dated 2013-12-31 are excluded"  
"Scope is fixed at 2014-01-01, not a rolling window recalculated at run time"

**After:**  
"LS records dated exactly 1947-08-15 are included in scope; LS records dated 1947-08-14 are excluded"  
"RS records dated exactly 1947-08-15 are included in scope; RS records dated 1947-08-14 are excluded"  
"Scope boundaries are fixed constants, not rolling windows recalculated at run time"

### 8. Test spec: Source URL Rules simplified

**Before:**  
"An LS record must have source_url set to an Internet Archive URL; it must not contain 'eparlib.sansad.in'"  
"An RS record fetched via Internet Archive or rsdebate.nic.in must have source_url set to an Internet Archive URL; it must not contain 'rsdebate.nic.in'"  
"An RS record fetched from sansad.in HTML must have source_url containing 'sansad.in'"

**After:**  
"An LS record (regardless of which provider fetched it) must have source_url set to an Internet Archive URL (archive.org domain)"  
"An RS record must have source_url set to an Internet Archive URL (archive.org domain); the current RS chain contains Internet Archive only"

---

## F03: Search Filters — MODIFIED

### 1. New filter dimension: Subject (§5)

**Added** as filter dimension §5 (Proceeding type renumbered from §5 to §6):

> **5. Subject**
> - Free text input; case-insensitive substring match against the `subject` field
> - Matches records whose subject contains the entered string anywhere
> - Empty field: no subject filter applied
> - No autocomplete in v1

### 2. Acceptance criteria updated

**Before:** "All five filter dimensions are available on the results page"  
**After:** "All six filter dimensions are available on the results page"  
**Added:** "Subject filter applies a case-insensitive substring match against the `subject` field; empty value applies no subject restriction"

### 3. Date range minimum for LS/RS updated

**Before:** "When only LS and/or RS is selected: minimum selectable date is 2014-01-01"  
**After:** "When only LS and/or RS is selected: minimum selectable date is 1947-08-15"

### 4. Gap edge case rephrased

**Before:** "Date range spans the gap between CA (1946–1950) and LS/RS (2014–present): no records exist in the gap years; result set is the union of CA records within range and LS/RS records within range; no error"

**After:** "Date range spans years with no indexed records (e.g., between the end of CA proceedings and the first LS/RS sittings, or RS years not covered by the current provider chain): result set is the union of records that exist within the range from each indexed source; no error is shown for the gaps"

### 5. Test spec: Date Range Gap updated

**Before:** "A date range of 1948-01-01 to 2015-12-31 must return CA records dated 1948-01-01 to 1950-12-31 and LS/RS records dated 2014-01-01 to 2015-12-31; no records from 1951–2013 must appear; no error must be shown for the gap years"

**After:**  
"A date range spanning the gap between CA proceedings and LS/RS sittings (e.g., 1951-01-01 to 1951-12-31, after CA ended and before Parliament was constituted) must return zero results without error"  
"A date range that spans records from multiple sources with a gap between them must return the union of records from each source within the range; no error must be shown for the gap years"

### 6. Test spec: Subject Filter Substring Matching — new section added

New test section:  
"A subject filter value that is a substring of a longer subject (e.g., 'Water' matching a record with subject 'Water Resources Management') must produce a match; an exact-only match implementation is a bug"  
"A subject filter value containing only whitespace must be treated as an empty filter; the result set must be identical to the unfiltered result set"

---

## F04: Query Expansion — MODIFIED

### 1. New section: Query Preprocessing

**Added** before the Synonym Dictionary section:

> **Query Preprocessing**
>
> Before synonym expansion and spell correction, the query string is normalized:
> - U+201C (") and U+201D (") curly double quotes are converted to ASCII straight double quotes (`"`)
>
> This ensures that phrase queries typed on macOS and iOS — which auto-substitute typographic curly quotes for `"` — are correctly interpreted as phrase search syntax by Meilisearch, which uses ASCII straight double quotes to delimit phrase queries.

### 2. Acceptance criteria: new criterion added

**Added:** "A query string containing U+201C or U+201D curly quotes around a phrase is treated as a phrase query equivalent to the same phrase enclosed in ASCII straight double quotes"

### 3. Test spec: Curly Quote Normalization — new section added

New test section:  
"A query string containing U+201C (") and U+201D (") curly double quotes around a phrase must result in those characters being converted to ASCII straight double quotes before the query is transmitted to Meilisearch; U+201C and U+201D must not appear in the query string sent to the search engine"

---

## F05: Result Display — MINOR FIX

### Snippet size reduced and result card table descriptions corrected

**Snippet Generation section:**  
Before: "at least 400 words" (v3.0)  
After: "at least 200 words"

Applies to: Snippet Generation min size, both result card table "Text snippet" rows, and the Snippet Minimum Size test spec.

**Result card table alignment fix:**  
Before: "2–3 sentences of context" (v3.0 carry-over inconsistency)  
After: "≥200 words of context" (now consistent with Snippet Generation section)

---

## F08: Search History — MODIFIED

### "What is stored per saved search" updated

**Before:** "Active filter state at the time of saving (legislative body, date range, speaker, session, proceeding type selections)"  
**After:** "Active filter state at the time of saving (legislative body, date range, speaker, session, subject, proceeding type selections)"

Added `subject` to the filter state captured in saved searches, consistent with F03 adding subject as a filter dimension.

---

## Supporting Sections — MODIFIED

### 01-overview.md

- Product description updated to reflect expanded scope and subject filter capability
- Data Scope table: LS and RS rows updated (scope, providers)
- v1 Constraints: "last 12 years of LS/RS" replaced with specific LS/RS scope statements

### 02-objectives.md

- Objective 3: "legislative body, speaker, and proceeding type" → "legislative body, speaker, session, subject, and proceeding type"

### 04-non-functional-requirements.md

- INF-RL1: Removed `eparlib.sansad.in`, `sansad.in`, `rsdebate.nic.in` from compliance list; now: `constitutionofindia.net, elibrary.sansad.in, and the Internet Archive`

### 05-future-features.md

- "Full parliamentary history" item updated: "extend LS and RS coverage beyond 2014" → "extend LS coverage back to 1952 across all accessible sources; restore RS post-2018 coverage when an accessible source is identified; extend RS coverage to include all available historical records"

---

## Downstream Impact

All changes are modifications to existing features. No new feature numbers were added.

**ARCH stage:** ARCH docs (ARCHITECTURE.md, DATA-MODELS.md, DEPLOYMENT.md) were already aligned to these changes at the time of implementation. No re-run of /arch is required.

**PLAN stage:** No new phases required; all changes are already implemented and tested.

**BUILD/REVIEW:** All 15 phases are complete and CLEAR. No re-runs required.
