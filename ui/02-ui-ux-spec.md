# SansadSearch — UI/UX Spec

**PRD version:** v3.1

---

## Design Philosophy

Editorial research tool with restrained personality. Warm off-white surfaces and strong typographic hierarchy give the product a newspaper-archive feel — authoritative without being institutional. Deep navy anchors the identity; muted saffron is reserved for active/selected states only. Legislative source is signaled by a consistent body color accent system (ochre for CA, green for LS, crimson for RS) applied to card borders and badges throughout the product. Medium density: readable at a glance, scannable under load. No decorative chrome — every visual element must earn its presence.

---

## Visual Identity

### Color Palette

| Role | Hex | Usage |
|------|-----|-------|
| Background | `#F7F4EF` | Page background |
| Surface | `#FFFFFF` | Cards, modal, inputs, dropdown panels |
| Primary accent | `#1C3461` | Logo, primary buttons, active nav, links, chip backgrounds |
| Secondary accent | `#C96A1E` | Active/selected chips, search submit hover, term highlights, debug indicator |
| Text primary | `#1A1A1A` | Body text, headings, result titles |
| Text secondary | `#6B6B6B` | Metadata labels, timestamps, muted notices |
| Border / divider | `#E2DDD6` | Card borders, input borders, section dividers |
| Chip inactive | background `#EDF0F7`, text `#1C3461` | Applied filter chips (default state) |
| Chip active | background `#1C3461`, text `#FFFFFF` | Applied filter chips (hover/focus) |
| Status strip | `#EDE8E0` | Homepage indexing status footer background |
| Code surface | `#F5F5F5` | Debug panel content background |

### Body Color Palette

Applied consistently wherever legislative source is indicated: card left borders, body badges, Legislative Body toggle chips in the Advanced Search Modal, and corpus pills on the homepage.

| Body | Accent | Badge background | Badge text |
|------|--------|------------------|------------|
| Constituent Assembly | `#8B6914` | `#F9F3E3` | `#8B6914` |
| Lok Sabha | `#1E6B35` | `#EAF4EE` | `#1E6B35` |
| Rajya Sabha | `#9B1D20` | `#F9ECEC` | `#9B1D20` |

Card left border: 3px solid body accent color. Body badge: pill, body badge-bg + body badge-text, padding 3px 10px, border-radius 20px, Inter 12px Medium.

### Typography

| Role | Font | Size / Weight |
|------|------|---------------|
| Wordmark | Merriweather | 28px, Bold |
| Page headings (H1) | Merriweather | 22px, Bold |
| Section headings (H2) | Merriweather | 16px, SemiBold |
| Record detail subject | Merriweather | 16px, SemiBold |
| Body text | Inter | 15px, Regular |
| Result speaker name | Inter | 15px, SemiBold |
| Result snippet | Inter | 14px, Regular |
| Detail page full text | Inter | 15px, Regular, line-height 1.7 |
| Metadata (date, session, body) | Inter | 12px, Regular, color: Text secondary |
| UI labels, button text | Inter | 14px, Medium |
| Query expansion notice | Inter | 12px, Regular, color: Text secondary |
| Chip text | Inter | 13px, Medium |
| Debug panel content | SFMono, Consolas, monospace | 12px, Regular |

Both web fonts available on Google Fonts. Fallback stack: `Merriweather, Georgia, serif` and `Inter, system-ui, sans-serif`.

### Spacing and Density

- Base unit: 8px
- Card padding: 16px (result cards); 20px (detail page cards)
- Section vertical gap: 24px
- Search bar height: 48px
- Modal padding: 24px
- Chip padding: 6px 12px, border-radius 20px (pill shape)
- Card border-radius: 8px
- Modal border-radius: 12px

---

## Screen Layouts

### 1. Homepage

**Mockup:** `mockups/homepage.png`

**Layout:** Single centered column, max-width 680px, vertically centered in the viewport. Page background `#F7F4EF`. Indexing status strip pinned to bottom.

**Elements (top to bottom):**

1. **Wordmark:** "SansadSearch" in Merriweather Bold 28px, color `#1C3461`, centered.

2. **Tagline:** TAGLINE. Inter 14px Text secondary, centered, 6px below wordmark.

3. **Corpus pills row:** Three non-interactive pills in a horizontal row, centered, 8px below tagline. Use body badge styling per Body Color Palette. Inter 12px Medium, padding 4px 12px, border-radius 20px, 8px gap between pills.
   - "Constituent Assembly 1946–1950" — bg `#F9F3E3`, text `#8B6914`
   - "Lok Sabha" — bg `#EAF4EE`, text `#1E6B35`
   - "Rajya Sabha" — bg `#F9ECEC`, text `#9B1D20`

4. **Search bar:** Full width of the 680px column, 16px below corpus pills. Height 48px. White surface, 1px border `#E2DDD6`, border-radius 8px, box-shadow `0 2px 8px rgba(0,0,0,0.06)`. Placeholder: SEARCH_PLACEHOLDER. Submit button (magnifying glass icon) on right edge, bg `#1C3461`, white icon. On hover: submit button bg shifts to `#C96A1E`.

5. **Below search bar row:** Two items on the same line, 8px below search bar. Left-aligned: "Advanced Search" Inter 13px `#1C3461`, underline on hover. Right-aligned: Saved searches icon (bookmark, 18px, `#6B6B6B`; tooltip: "Saved searches").

6. **Suggested queries row:** 16px below the below-search-bar row. Shown only when the search bar is empty; hidden as soon as the user begins typing.
   - Label "Try:" Inter 12px Text secondary, inline left of chips.
   - Four chips in an inline wrapping row, 8px gap. One chip drawn randomly from each category pool on each page load (client-side, on component mount).
   - Chip style: bg `#EDF0F7`, text `#1C3461`, Inter 13px Medium, pill (6px 12px padding, border-radius 20px), cursor pointer. Hover: bg `#E0E5F2`.
   - On click: populates the search bar with the chip's query text and auto-submits.
   - **Query pools** (one chip selected randomly from each per page load):
     - *Constituent Assembly:* "fundamental rights constituent assembly" · "partition of Bengal" · "language of the union" · "directive principles of state policy" · "minorities constituent assembly"
     - *Speaker:* "Ambedkar" · "Nehru" · "Sardar Patel" · "Vajpayee" · "Manmohan Singh" · "Sushma Swaraj"
     - *Policy topic:* "MGNREGA" · "demonetisation" · "farm laws 2020" · "right to education" · "women reservation bill"
     - *LS/RS proceeding:* "no confidence motion" · "emergency powers" · "budget health allocation" · "electoral reform" · "climate change"

7. **Indexing status strip:** Full-width strip pinned to page bottom. Background `#EDE8E0`. Single centered line: "Indexed: [X] Constituent Assembly records · [Y] Lok Sabha records · [Z] Rajya Sabha records · Last updated: [date]" Inter 12px Text secondary. Left and right padding 24px. Height 36px.

**Responsive:**
- Desktop (≥1024px): centered 680px column as described
- Tablet (768–1023px): column width 90vw; corpus pills may wrap
- Mobile (<768px): column width 92vw; wordmark 22px; search bar height 44px; corpus pills stack vertically; suggested query chips wrap; status strip wraps to two lines if needed

---

### 2. Results Page

**Mockup:** `mockups/results-page-with-filters.png`

**Layout:** Full-width page. Sticky header at top. Content column max-width 860px, horizontally centered. Page background `#F7F4EF`.

**Sticky header (height 64px, white surface, bottom border `#E2DDD6`, box-shadow `0 2px 4px rgba(0,0,0,0.04)`):**
- Left: "SansadSearch" wordmark, Merriweather 20px Bold `#1C3461`, links to homepage
- Center: Search bar, width ~540px, height 40px, same styling as homepage bar but smaller
- Right of search bar: "Advanced Search" link (Inter 13px `#1C3461`) and saved searches bookmark icon (18px `#6B6B6B`)
- Far right (debug mode only): DEBUG_BADGE pill — bg `rgba(201,106,30,0.1)`, text `#C96A1E`, Inter 11px Medium, border-radius 4px, padding 2px 6px. Non-interactive. Visible only when `?debug=1` is active.

**Below header — filter chips row (conditional):**
- Shown only when one or more filters are active
- Chips in a horizontal row, 12px below the header, scrollable horizontally on overflow
- Each chip: pill, bg `#EDF0F7`, text `#1C3461`, 13px Medium, with `×` dismiss icon on right
- Subject filter chip label: "Subject: [value]"
- "Clear all" text link (Inter 13px `#6B6B6B`, underline on hover) at end of chip row

**Below chips row — query expansion notice (conditional):**
- Shown when F04 has expanded the query
- Single line, Inter 12px `#6B6B6B`: "Also searching for: [term1], [term2], …" — truncated with "…" if list exceeds line width
- 6px vertical gap above next element

**Global search debug panel (conditional — debug mode only):**
Appears between the query expansion notice (or filter chips row) and the results header row. Only shown when `?debug=1` is active.
- White surface card, 1px border `#E2DDD6`, border-radius 8px, 3px left border `#C96A1E`, margin-bottom 16px
- Panel header: "Search debug" Inter 13px SemiBold `#6B6B6B`, padding 12px 16px
- Five collapsible sections. Each section:
  - Header row: chevron icon (right-aligned) + label, Inter 13px Medium `#1A1A1A`, padding 10px 16px, hover bg `#F7F4EF`, cursor pointer
  - Content area (shown when expanded): bg `#F5F5F5`, SFMono/Consolas/monospace 12px `#1A1A1A`, padding 12px 16px, overflow-x auto, max-height 400px scrollable, 1px top border `#E2DDD6`
  - All collapsed by default
  - Sections in order: "Processed query" · "API request" · "API response" · "Meilisearch request" · "Meilisearch response"

**Results header row:**
- Left: "[N] results for "[query]"" Inter 13px Text secondary
- Right: sort dropdown — "Sort: Relevance ▾", Inter 14px, border `#E2DDD6`, border-radius 6px, bg white. Options: Relevance (default), Newest first, Oldest first. Selecting re-sorts immediately; label updates.

**Result cards:**
- White surface, 1px border `#E2DDD6`, border-radius 8px, padding 16px, vertical gap 12px between cards
- **3px left border in body accent color** (CA: `#8B6914`, LS: `#1E6B35`, RS: `#9B1D20`)
- Hover: box-shadow `0 4px 12px rgba(0,0,0,0.08)`, cursor pointer
- **Entire card is clickable** and navigates to `/record/:id`. "View source ↗" is an independent link; clicking it does not navigate to the detail page.

**Speech record card (top to bottom):**
1. **Metadata row:** Inline sequence, Inter 12px Text secondary:
   - Proceeding type badge: pill, bg `#EDF0F7`, text `#1C3461`, 1px border `#C5CADC`, 12px Medium, padding 3px 10px, border-radius 20px
   - " · " separator
   - Body badge: pill using body colors per Body Color Palette, 12px Medium, padding 3px 10px
   - " · " + Date formatted DD Month YYYY
   - " · " + Session name (if not null)
2. **Speaker row:** Inter 15px SemiBold `#1A1A1A`, 6px below metadata row. Append party and constituency/state in Inter 12px Text secondary separated by " · " if available. If `speaker_name` null: "Speaker unknown" in Text secondary.
3. **Subject line:** `subject` field, Inter 13px Regular `#6B6B6B`, 4px below speaker row, one-line truncation with ellipsis.
4. **Snippet:** Inter 14px Regular `#1A1A1A`, 6px below subject line. ≥200 words of context around the highest-relevance match. Matched terms (original and expanded) highlighted: bg `rgba(201,106,30,0.15)`, text `#C96A1E`. If `full_text_en` null: NO_ENGLISH_TEXT_SPEECH in Inter 14px Text secondary.
5. **Language badge (conditional):** If `lang_original` is `hi`: "Hindi original" pill; if `mixed`: "Mixed language" pill. Pill: bg `#EDF0F7`, Inter 11px Text secondary, padding 2px 8px, immediately below snippet. Not shown when `lang_original` is `en`.
6. **Translation indicator (conditional):** "Translated from Hindi" Inter 11px Text secondary, italic, below language badge (or snippet if no badge), when `is_translated` true.
7. **Source link:** "View source ↗" Inter 13px `#1C3461`, underline on hover, right-aligned, 8px below snippet area. Opens in new tab. Omitted if `source_url` null.
8. **Debug toggle (debug mode only):** "Debug ▾" / "Debug ▲", Inter 12px `#6B6B6B`, right-aligned, below source link. Toggles per-card debug panel.

**Q+A exchange record card (top to bottom):**
1. **Metadata row:** Same as speech card.
2. **Subject line:** `subject` field, Inter 15px SemiBold `#1A1A1A`, 6px below metadata row, two-line truncation with ellipsis.
3. **Question number:** "Q. [number]" Inter 12px Text secondary, 2px below subject.
4. **Questioner row:** Inter 13px `#1A1A1A`: questioner name + party in Text secondary if available. If co-signatories: "+N others". 4px below question number.
5. **Minister/ministry row:** Inter 13px Text secondary: "Answered by [Minister Name], [Ministry]". 2px below questioner row.
6. **Snippet:** Same as speech card. Prepend "From supplementary exchange — " in Inter 12px Text secondary if match is from supplementary. If `full_text_en` null: NO_ENGLISH_TEXT_SPEECH.
7. **Language badge (conditional):** Same as speech card.
8. **Translation indicator (conditional):** Same as speech card.
9. **Source link:** Same as speech card.
10. **Debug toggle (debug mode only):** Same as speech card.

**Per-card debug panel (debug mode only):**
Expands within the card below the debug toggle, separated by a 1px divider `#E2DDD6`, top margin 12px.
Four collapsible sections (same section styling as global debug panel, without the 3px left border accent):
- "Scoring details" — `_rankingScore` and `_rankingScoreDetails` from search response; renders whatever score fields Meilisearch returned for this hit
- "Document in index" — full Meilisearch document from search response
- "Processed record" — fetched lazily from `GET /api/debug/processed/{id}` on first expand; spinner while loading; error message if request fails; subsequent expands use cached data; 404 from API shows RAW_DOC_NOT_AVAILABLE message
- "Raw document" — fetched lazily from `GET /api/debug/raw/{id}` on first expand; same lazy/cached/error behavior; 404 shows RAW_DOC_NOT_AVAILABLE message
All four sections collapsed by default when panel opens.

**Loading state:** 5 skeleton cards — gray animated shimmer for metadata row, speaker name, and snippet lines.

**Empty state:** Centered, 48px top padding. EMPTY_RESULTS. No illustration.

**Inline validation:** Query empty or under 2 non-whitespace characters: VALIDATION_SHORT in Inter 13px `#C96A1E` below search bar. No search executes. Dismisses on typing.

**Error state:** Centered. ERROR_STATE. "Retry" primary button below.

**Pagination:** Centered below last card, 24px gap. Previous / page numbers / Next. Current page: bg `#1C3461`, white text, border-radius 6px. Adjacent pages: text `#1C3461`, border `#E2DDD6`. 20 results per page.

**Responsive:**
- Desktop (≥1024px): 860px centered column
- Tablet (768–1023px): 90vw; header search bar 60vw
- Mobile (<768px): 92vw; sort dropdown moves below chips row; header collapses to wordmark + icon row; search bar full-width below header

---

### 3. Advanced Search Modal

**Mockup:** `mockups/advanced-search-modal-ca-only.png` *(shows CA-only selected state with Proceeding Type chips conditionally disabled)*

**Trigger:** "Advanced Search" link in header or homepage.

**Layout:** Centered modal overlay. Background overlay: `rgba(0,0,0,0.4)`. Modal: white surface, border-radius 12px, padding 24px, max-width 560px, max-height 90vh, scrollable if needed.

**Header:** "Advanced Search" Merriweather 18px Bold `#1A1A1A`. Close icon (×) top-right, 20px, `#6B6B6B`, hover `#1A1A1A`.

**Fields (vertical stack, 16px gap between fields):**

**1. Legislative Body**
Label "Legislative Body" Inter 13px Medium `#1A1A1A`.
Three toggle chips in a horizontal row, 8px gap between chips. Chip height 36px, padding 8px 16px, border-radius 20px.
- "Constituent Assembly" — selected: bg `#8B6914`, white text; unselected: bg `#F9F3E3`, text `#8B6914`
- "Lok Sabha" — selected: bg `#1E6B35`, white text; unselected: bg `#EAF4EE`, text `#1E6B35`
- "Rajya Sabha" — selected: bg `#9B1D20`, white text; unselected: bg `#F9ECEC`, text `#9B1D20`
All three selected by default (no body restriction).
Validation: if all deselected, show "Select at least one source" Inter 12px `#C96A1E` below the chip row; Apply button disabled.

**2. Date Range**
Label "Date Range" Inter 13px Medium. Two date inputs side by side: "From" and "To". Labels in Inter 12px Text secondary above each input. Input height 36px, border `#E2DDD6`, border-radius 6px, Inter 14px. Both optional.
Validation: From later than To → "From date must be before To date" Inter 12px `#C96A1E` below the inputs; Apply disabled.

**3. Speaker**
Label "Speaker" Inter 13px Medium. Single text input, height 36px, full modal width. Placeholder: "e.g. Ambedkar".
Helper text Inter 11px Text secondary: "Use last name only for reliable results (names are canonicalized in the index)."

**4. Session**
Label "Session" Inter 13px Medium. Single text input, height 36px, full modal width. Placeholder: "e.g. Budget Session 2023".
Helper text Inter 11px Text secondary: "Constituent Assembly records have no session name and will not match a session filter."

**5. Subject**
Label "Subject" Inter 13px Medium. Single text input, height 36px, full modal width. Placeholder: "e.g. MGNREGA".
Helper text Inter 11px Text secondary: "Matches records whose subject contains this text (case-insensitive)."

**6. Proceeding Type**
Label "Proceeding Type" Inter 13px Medium.
"Select all" / "Clear" text action pair, Inter 12px `#6B6B6B`, right-aligned above the chip group, 4px below label. "Select all" selects all non-disabled chips; "Clear" deselects all selectable chips.
Nine toggle chips in a wrapping row, 8px gap: Debate · Starred Question · Unstarred Question · Zero Hour · Short Notice Question · Calling Attention · Short Duration Discussion · Adjournment Motion · Private Member Bill.
Chip size: height 32px, padding 6px 12px, border-radius 20px. Selected: bg `#1C3461`, white text. Unselected: bg `#EDF0F7`, text `#1C3461`.
When only CA is selected in Legislative Body: all chips except "Debate" are grayed (opacity 0.4, pointer-events none, not clickable).
All chips selected by default.
Validation: if all deselected, show "Select at least one proceeding type" Inter 12px `#C96A1E` below the chips; Apply disabled.

**Modal footer (sticky at bottom of modal):**
- Left: "Clear all" Inter 14px `#6B6B6B`, underline on hover. Resets all fields to defaults (all body chips selected, all proceeding type chips selected, date/speaker/session/subject inputs empty).
- Right: "Apply" button — bg `#1C3461`, white text, Inter 14px Medium, height 40px, border-radius 6px, min-width 96px. Disabled (opacity 0.4) when any field-level validation is failing.

**Pre-population:** Modal opens with current active filters pre-populated (chips toggled, inputs filled).

**Responsive:** Mobile (<768px): full-width modal with 16px side margins; body chips wrap if needed; date inputs stack vertically; proceeding type chips wrap.

---

### 4. Recent Searches Dropdown

**Trigger:** User focuses the search bar when it is empty.

**Layout:** Dropdown anchored below the search bar, full width of the search bar. White surface, 1px border `#E2DDD6`, border-radius 0 0 8px 8px, box-shadow `0 4px 12px rgba(0,0,0,0.08)`.

**Content:**
- Section label "Recent searches" Inter 12px Text secondary, padding 10px 16px 4px.
- Up to 10 items. Each: magnifying glass icon (14px `#6B6B6B`) + query text (Inter 14px `#1A1A1A`), padding 10px 16px, hover bg `#F7F4EF`. Click: populates search bar and submits.
- Divider line above footer.
- Footer: "Clear history" text link, Inter 13px `#6B6B6B`, right-aligned, padding 8px 16px.

**Empty state:** NO_RECENT, Inter 14px Text secondary, padding 12px 16px.

**Dismiss:** Click outside or Escape.

---

### 5. Saved Searches Panel

**Trigger:** Bookmark icon (right of search bar, in header or homepage).

**Layout:** Dropdown anchored below bookmark icon, width 320px. White surface, 1px border `#E2DDD6`, border-radius 8px, box-shadow `0 4px 12px rgba(0,0,0,0.08)`. Max-height 400px, scrollable.

**Header:** "Saved searches" Inter 14px SemiBold `#1A1A1A`, padding 12px 16px 8px.

**Content:**
Up to 20 items. Each item: two lines. Item padding 10px 16px. Hover bg `#F7F4EF`.
- Line 1: saved search name, Inter 14px `#1A1A1A`, one-line truncation with ellipsis.
- Line 2: filter summary, Inter 12px Text secondary. Format: show only non-default active filters as a " · " separated sequence. Components in order: body restriction (if not all three) · date range · subject ("Subject: [value]") · proceeding type restriction (if not all types). "No filters" if saved with default filter state. Example: "Lok Sabha · 2019–2024 · Subject: MGNREGA · Starred Question".
- Right side: pencil icon (rename, 14px `#6B6B6B`) and trash icon (delete, 14px `#6B6B6B`, hover `#C96A1E`). Delete: item removed, REMOVE_TOAST shown.
- Rename: Line 1 becomes inline text input (max 60 characters) with checkmark to confirm and × to cancel. On confirm: name updated in place, no toast.
- Clicking item text (not icons): restores query + full filter state (including subject), panel closes, search executes.

**Save button (results page only):** Below item list, full-width "Save current search" — border `1px solid #1C3461`, text `#1C3461`, bg white, Inter 14px, height 36px. On click: saves current query + all active filters (including subject if set). Button text changes briefly to "Saved ✓". SAVE_TOAST shown. At 20-entry limit: disabled (opacity 0.4), SAVE_LIMIT shown in Inter 12px Text secondary below it. Hidden on homepage.

**Empty state:** NO_SAVED, Inter 14px Text secondary, padding 16px.

**Dismiss:** Click outside or Escape.

---

### 6. Record Detail Page

**Mockup:** `mockups/record-detail-page.png` *(shows Lok Sabha speech record with metadata panel, disabled load-previous at sitting boundary, focal record full text, enabled load-next with appended adjacent record)*

**Route:** `/record/:id`

**Layout:** Full-width page. Sticky header: same as results page (wordmark + search bar + Advanced Search link + bookmark icon; debug badge if `?debug=1` present). Content column: max-width 860px, centered, page bg `#F7F4EF`.

**Content column structure (top to bottom):**

**Back navigation:**
Padding-top 24px, margin-bottom 16px. Inter 13px `#1C3461`, no underline by default, underline on hover.
- Arrived from search results (in-app navigation): BACK_TO_RESULTS
- Accessed directly (direct URL, bookmark, external link): BACK_TO_SEARCH — links to homepage

**Metadata panel:**
White surface card, padding 20px, border-radius 8px, 1px border `#E2DDD6`, **3px left border in body accent color**. Margin-bottom 16px.

- **Badge row:** Proceeding type badge + body badge on the same line, 12px below top of panel.
  - Proceeding type badge: bg `#EDF0F7`, text `#1C3461`, 1px border `#C5CADC`, Inter 12px Medium, padding 3px 10px, border-radius 20px
  - Body badge: body color pill per Body Color Palette, Inter 12px Medium, 8px left of proceeding type badge
- **Subject:** Merriweather 16px SemiBold `#1A1A1A`, 12px below badge row. Full width, wraps to multiple lines.
- **Metadata fields:** Two-column labeled grid, 24px below subject. Label: Inter 12px Text secondary. Value: Inter 14px `#1A1A1A`. Row gap 12px. Null fields omitted silently — no placeholder row rendered.

  | Label | Value format | Condition |
  |-------|-------------|-----------|
  | Date | DD Month YYYY | Always |
  | Time | HH:MM | `time_of_day` not null |
  | Session | `session_name` | Not null |
  | Session number | `session_number` | Not null |
  | Sitting number | `sitting_number` | Always |
  | Lok Sabha term | "[N]th/st/nd/rd Lok Sabha" (correct ordinal suffix) | LS records only |
  | Volume | `volume` | CA records only |
  | Speaker | `speaker_name` + "(name unresolved)" if `speaker_name_unresolved` | Speech records |
  | Role | `speaker_role` | Speech records, not null |
  | Party | `speaker_party` | Not null |
  | Constituency / State | `speaker_constituency_or_state` | Not null; omitted for CA records |
  | Question number | "Q. [number]" | Q+A records |
  | Questioner(s) | `questioner_names` | Q+A records |
  | Questioner party | `questioner_party` | Q+A records, not null |
  | Minister | `minister_name` | Q+A records |
  | Ministry | `ministry` | Q+A records |
  | Language | "English" / "Hindi" / "Bilingual" | Always |
  | Translation | "Includes official English translation" | `is_translated` true |
  | Untranslated content | "Some content unavailable in English" | `has_untranslated_content` true |
  | PDF page | "PDF page [N]" | `page_reference` not null |
  | Word count | "[N] words" | `word_count` not null |
  | Position in sitting | "[N] of [total]" | Always |

- **Source link:** "View source ↗" Inter 13px `#1C3461`, underline on hover, 16px top margin, bottom of panel. Opens in new tab. Omitted if `source_url` null.

**Load previous control:**
Centered, 12px below metadata panel. Label: LOAD_PREVIOUS. Style: height 36px, border `1px solid #E2DDD6`, text `#1C3461`, bg white, Inter 14px, border-radius 6px, min-width 160px.
- Disabled state: opacity 0.4, cursor default. Shown (not hidden) when focal record is at the lowest `sequence_within_sitting` in the sitting, or when the sitting contains only one record.
- Loading state: spinner replaces label; non-interactive.

**Adjacent records — prepended (above focal record):**
Inserted between the load-previous control and the focal record after each "Load 5 previous" action. Each record is a compact card: white surface, 1px border `#E2DDD6`, border-radius 8px, padding 16px, 12px gap below it, **3px left border in body accent color**.
- Header: speaker name for speech records; "Q. [number]" + questioner name for Q+A records. Inter 14px SemiBold `#1A1A1A`.
- Sub-header: proceeding type badge + date + subject, Inter 12px Text secondary, 4px below header.
- Body: `full_text_en` as paragraphs, Inter 14px Regular `#1A1A1A`, line-height 1.7, 12px top margin. If null: NO_ENGLISH_TEXT_RECORD in Inter 13px Text secondary.

**Focal record card:**
White surface, 1px border `#E2DDD6`, border-radius 8px, padding 20px, **3px left border in body accent color**. 12px below load-previous control (or below the last prepended adjacent card).
- Header: speaker name (Inter 15px SemiBold `#1A1A1A`) for speech; "Q. [number]" + questioner name (Inter 15px SemiBold) for Q+A.
- Body: `full_text_en` rendered as paragraphs, Inter 15px Regular `#1A1A1A`, line-height 1.7, 16px top margin. If null: NO_ENGLISH_TEXT_RECORD centered in Inter 14px Text secondary.

**Adjacent records — appended (below focal record):**
Same compact card style as prepended adjacent records. 12px gap below the focal record (or below the last appended adjacent card).

**Load next control:**
Same style and behavior as load-previous. Label: LOAD_NEXT. 12px below the last visible card (focal or appended adjacent).
Disabled when focal record is at the highest `sequence_within_sitting` in the sitting, or when sitting contains only one record.

**Adjacent load error:**
When an adjacent batch request fails: ADJACENT_ERROR in Inter 13px `#C96A1E`, displayed where the loaded cards would appear. Load control returns to enabled state. Existing loaded records are not affected.

**Adjacent load skeleton:** While fetching, show 1–5 shimmer skeleton cards matching the compact adjacent card dimensions.

**Initial page load skeleton:** Shimmer placeholder for the full metadata panel + focal record card while `GET /api/record/{id}` is in flight.

**404 state:** Content column shows RECORD_NOT_FOUND in Merriweather 18px Bold `#1A1A1A`, then RECORD_NOT_FOUND_DETAIL in Inter 14px Text secondary below, then BACK_TO_SEARCH link.

**Responsive:**
- Desktop (≥1024px): 860px centered column; 2-column metadata field grid
- Tablet (768–1023px): 90vw column; 2-column metadata grid
- Mobile (<768px): 92vw column; 1-column metadata grid; load control buttons full-width

---

## Interaction Patterns

### Navigation Model

Three primary views:
1. **Homepage** — search entry point
2. **Results page** — paginated search results with filter, sort, and debug overlay
3. **Record detail page** (`/record/:id`) — full record with adjacent sitting navigation; stable, shareable URL

All modals and panels (Advanced Search, Recent Searches, Saved Searches) are overlays and do not change the URL.

Debug mode is not a separate view — it is activated via `?debug=1` on the results page URL; removing the parameter deactivates it.

Navigating to the homepage clears active search state. Navigating from a result card to the detail page preserves results page state (query, filters, pagination) for the BACK_TO_RESULTS link. Direct URL access to a detail page shows BACK_TO_SEARCH instead.

### Input Methods

- Search submission: Enter key or click submit icon in search bar
- Suggested query: click chip on homepage; auto-submits
- Filter application: Advanced Search modal only; toggle chips for body and proceeding type; text inputs for date range, speaker, session, subject
- Filter removal: chip × dismiss, "Clear all", or re-open modal and modify
- Sort change: dropdown; immediate effect
- Saved/recent search restore: click on item
- Adjacent record loading: click LOAD_PREVIOUS or LOAD_NEXT controls
- Debug mode activation: manually append `?debug=1` to results page URL; remove to deactivate

### Feedback Patterns

| Event | Feedback |
|-------|----------|
| Search executing | Skeleton cards appear; results replace them |
| No results | EMPTY_RESULTS empty state |
| Search error | ERROR_STATE + "Retry" button |
| Filter applied | Modal closes; chips appear; results reload |
| Filter removed (chip ×) | Chip disappears; results reload |
| Search saved | SAVE_TOAST — 3s auto-dismiss, Inter 13px, white text, `#1C3461` bg, border-radius 6px |
| Search removed | REMOVE_TOAST — same styling |
| Query expanded | Compact notice below chips; no toast |
| Record detail loading | Shimmer placeholder for metadata panel + focal card |
| Adjacent records loading | Shimmer skeleton cards; replaced when loaded |
| Adjacent load error | ADJACENT_ERROR message; load control re-enabled |
| Debug section loading (Processed record / Raw document) | Spinner in section content area |
| Debug section fetch error | Error message in section; RAW_DOC_NOT_AVAILABLE for raw doc 404 |

Toasts appear bottom-center, 16px from bottom edge. One at a time. No toasts for search execution or adjacent loading events.

### Action Button Placement and Labeling

- Primary actions (Apply, Retry): right-aligned, filled `#1C3461` background
- Destructive or neutral actions (Clear all, Clear history): left-aligned or text-only, never filled
- Save current search: full-width outline button in saved searches panel footer
- Load controls (LOAD_PREVIOUS, LOAD_NEXT): centered, outlined
- All button labels are imperative verbs: "Apply", "Retry", "Save current search", "Clear all", LOAD_PREVIOUS, LOAD_NEXT

---

## Canonical Text

| Name | String | Used in |
|------|--------|---------|
| SEARCH_PLACEHOLDER | "Search parliamentary debates, questions, and speeches…" | Both search bars |
| TAGLINE | "Search the complete record of Indian parliamentary debates." | Homepage below wordmark |
| EMPTY_RESULTS | "No results found for "[query]". Try adjusting your search terms or removing filters." | Results page empty state |
| ERROR_STATE | "Search is temporarily unavailable. Please try again." | Results page error state |
| VALIDATION_SHORT | "Enter at least 2 characters to search." | Inline below search bar |
| SAVE_LIMIT | "Saved searches full — delete one to save" | Below disabled Save button |
| SAVE_TOAST | "Search saved" | Toast on save |
| REMOVE_TOAST | "Search removed" | Toast on remove |
| NO_RECENT | "No recent searches" | Recent searches dropdown empty state |
| NO_SAVED | "No saved searches yet." | Saved searches panel empty state |
| NO_ENGLISH_TEXT_SPEECH | "This speech was delivered in Hindi. No English text is available." | Result card snippet fallback |
| NO_ENGLISH_TEXT_RECORD | "This record was delivered in Hindi. No English text is available." | Record detail page; adjacent record cards |
| RECORD_NOT_FOUND | "Record not found" | Detail page 404 heading |
| RECORD_NOT_FOUND_DETAIL | "The record you're looking for does not exist or has been removed." | Detail page 404 body |
| BACK_TO_RESULTS | "← Back to results" | Detail page back nav (arrived from search) |
| BACK_TO_SEARCH | "← Search" | Detail page back nav (direct access); 404 state link |
| LOAD_PREVIOUS | "↑ Load 5 previous" | Adjacent load control above focal record |
| LOAD_NEXT | "↓ Load 5 next" | Adjacent load control below focal record |
| ADJACENT_ERROR | "Could not load records. Try again." | Adjacent batch load failure |
| RAW_DOC_NOT_AVAILABLE | "Raw document not available" | Debug panel raw document 404 |
| DEBUG_BADGE | "Debug" | Header badge when `?debug=1` is active |
