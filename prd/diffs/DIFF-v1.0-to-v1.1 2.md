# PRD Diff: v1.0 → v1.1
Date: 2026-05-29
Reason: Phase 4 QA review run-1 routed two gaps to Product Agent; both resolved by clarifying existing specs.

---

## F05: Result Display — Edge Case Removed

**Change type:** Removal of one edge case from feature spec.

**Removed from Edge Cases section:**

> Query term appears in highlighted metadata field (e.g., speaker name) and also in snippet: both instances are highlighted independently

**Why:** This edge case contradicted the rest of F05. The displayed-fields tables, snippet-generation section, and all acceptance criteria specify highlighting only in the snippet. The backend (Phase 3) wraps `<mark>` in the snippet only; cards render `speaker_name`/`subject` as plain text. Metadata-field highlighting is not required in v1.

**Coding Agent impact:** None. The existing implementation is correct as-is. No code change required. The Phase 4 HTML-sanitisation tests should be updated (separately, per Coding Agent gaps) but are not affected by this removal.

---

## F07: Indexing Status Panel — Two Display Surfaces Distinguished

**Change type:** Clarification of existing feature; no new feature added.

### What changed

F07 previously described a single panel format placed on the homepage and accessible via a footer link ("the same information"). This was ambiguous: the Phase 4 build correctly implemented a condensed homepage strip (counts + last-updated only), but the spec's detailed format (per-source date coverage, "0 records – not yet indexed") was not matched by the build.

The spec now explicitly defines two surfaces:

**Homepage Status Strip (condensed)**
- Shows per-source record counts and last-updated date only
- Does NOT show per-source date coverage
- A source with zero indexed records is shown as "0 [Body] records" in the strip; it is NOT omitted
- Format: `[N] Constituent Assembly records · [N] Lok Sabha records · [N] Rajya Sabha records · Last updated: [DD Month YYYY]`

**Full Indexing Status Panel (detailed)**
- Accessible via the persistent footer link labelled "Index status" on the results page
- Shows total count, per-source counts, per-source date coverage, and last-updated date
- A source with zero indexed records shows "0 records – not yet indexed" without a date range (this format applies to the full panel only, not the homepage strip)

### Acceptance criteria changes

**Replaced:**
> Panel displays total record count, per-source counts, per-source date coverage, and last updated date

**With:**
> The homepage strip displays per-source record counts and the last updated date
> The full indexing status panel displays total record count, per-source counts, per-source date coverage, and last updated date

**Replaced:**
> If a source has zero indexed records, its row shows "0 records – not yet indexed" without a date range

**With:**
> Homepage strip: a source with zero indexed records is shown as "0 [Body] records" in the strip; it is not omitted
> Full panel: a source with zero indexed records shows "0 records – not yet indexed" without a date range

**Replaced:**
> Panel is read-only; no user interaction is required or available beyond viewing

**With:**
> Both surfaces are read-only; no user interaction is required or available beyond viewing

### Edge case change

**Replaced (fresh deployment):**
> panel shows all sources as "0 records – not yet indexed" and last updated as "Never"

**With:**
> all sources shown as "0 [Body] records" in the strip and "0 records – not yet indexed" in the full panel; last updated shown as "Never"

### Coding Agent impact

**Homepage strip (Phase 4):** The existing Phase 4 implementation (`Home.jsx`, `formatStatusStrip`) is correct as specified. No change required to the homepage strip code.

**Full indexing status panel (not yet built):** The footer link on the results page is rendered (Phase 4, `Results.jsx`) but the full panel it links to has not been implemented. The full panel — with per-source date coverage and "0 records – not yet indexed" row format — must be built before the footer link is functional. This is not yet assigned to a phase.

**Test spec change:** The "Zero-Source Row Format" test now scopes to the full panel only. A new test for the homepage strip zero-count behavior has been added (source with zero count must appear as "0 [Body] records", not be omitted).

---

## No Other Changes

F01, F02, F03, F04, F06, F08, NFR, and Future Features are unchanged from v1.0.
