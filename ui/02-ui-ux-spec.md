# SansadSearch — UI/UX Spec

**PRD version:** v1.0

---

## Design Philosophy

Editorial research tool with restrained personality. Warm off-white surfaces and strong typographic hierarchy give the product a newspaper-archive feel — authoritative without being institutional. Deep navy anchors the identity in the subject matter; muted saffron is reserved for active/selected states only. Medium density: readable at a glance, scannable under load. No decorative chrome — every visual element must earn its presence.

---

## Visual Identity

### Color Palette

| Role | Hex | Usage |
|------|-----|-------|
| Background | `#F7F4EF` | Page background |
| Surface | `#FFFFFF` | Cards, modal, inputs, dropdown panels |
| Primary accent | `#1C3461` | Logo, primary buttons, active nav, links, chip backgrounds |
| Secondary accent | `#C96A1E` | Active/selected chips, search submit button hover, term highlights in snippets |
| Text primary | `#1A1A1A` | Body text, headings, result titles |
| Text secondary | `#6B6B6B` | Metadata labels, timestamps, muted notices |
| Border / divider | `#E2DDD6` | Card borders, input borders, section dividers |
| Chip inactive | background `#EDF0F7`, text `#1C3461` | Applied filter chips (default state) |
| Chip active | background `#1C3461`, text `#FFFFFF` | Applied filter chips (hover/focus) |
| Status strip | `#EDE8E0` | Homepage indexing status footer background |

### Typography

| Role | Font | Size / Weight |
|------|------|---------------|
| Wordmark | Merriweather | 28px, Bold |
| Page headings (H1) | Merriweather | 22px, Bold |
| Section headings (H2) | Merriweather | 16px, SemiBold |
| Body text | Inter | 15px, Regular |
| Result speaker name | Inter | 15px, SemiBold |
| Result snippet | Inter | 14px, Regular |
| Metadata (date, session, body) | Inter | 12px, Regular, color: Text secondary |
| UI labels, button text | Inter | 14px, Medium |
| Query expansion notice | Inter | 12px, Regular, color: Text secondary |
| Chip text | Inter | 13px, Medium |

Both fonts available on Google Fonts. Fallback stack: `Merriweather, Georgia, serif` and `Inter, system-ui, sans-serif`.

### Spacing and Density

- Base unit: 8px
- Card padding: 16px
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

**Layout:** Single centered column, max-width 680px, vertically centered in the viewport. Page background `#F7F4EF`. Indexing status strip pinned to bottom of page.

**Elements (top to bottom):**
1. **Wordmark:** "SansadSearch" in Merriweather Bold 28px, color `#1C3461`, centered. One-line tagline below in Inter 14px Text secondary: "Search the complete record of Indian parliamentary debates."
2. **Search bar:** Full width of the 680px column. Height 48px. White surface, 1px border `#E2DDD6`, border-radius 8px, box-shadow `0 2px 8px rgba(0,0,0,0.06)`. Placeholder text: "Search parliamentary debates, questions, and speeches…". Submit button (magnifying glass icon) on right edge, background `#1C3461`, white icon. On hover: submit button background shifts to `#C96A1E`.
3. **Below search bar row:** Two items on the same line, 8px below the search bar. Left-aligned: "Advanced Search" — Inter 13px, `#1C3461`, underline on hover. Right-aligned: Saved searches icon (bookmark icon, 18px, `#6B6B6B`; tooltip: "Saved searches").
4. **Indexing status strip:** Full-width strip pinned to page bottom. Background `#EDE8E0`. Single line of text centered: "Indexed: [X] Constituent Assembly records · [Y] Lok Sabha records · [Z] Rajya Sabha records · Last updated: [date]" in Inter 12px, Text secondary. Left and right padding 24px. Height 36px.

**Empty state (no interaction):** No additional elements. The homepage contains only the wordmark, tagline, search bar, below-bar row, and status strip.

**Responsive:**
- Desktop (≥1024px): centered 680px column as described
- Tablet (768–1023px): column width = 90vw
- Mobile (<768px): column width = 92vw; wordmark 22px; search bar height 44px; status strip wraps to two lines if needed

---

### 2. Results Page

**Mockup:** `mockups/results-page-with-filters.png`

**Layout:** Full-width page. Sticky header at top. Content column max-width 860px, horizontally centered. Page background `#F7F4EF`.

**Sticky header (height 64px, white surface, bottom border `#E2DDD6`, box-shadow `0 2px 4px rgba(0,0,0,0.04)`):**
- Left: "SansadSearch" wordmark, Merriweather 20px Bold `#1C3461`, links to homepage
- Center: Search bar, width ~540px, height 40px, same styling as homepage bar but smaller
- Right of search bar: "Advanced Search" link (Inter 13px `#1C3461`) and saved searches bookmark icon (18px `#6B6B6B`)

**Below header — filter chips row (conditional):**
- Shown only when one or more filters are active
- Chips in a horizontal row, 12px below the header, scrollable horizontally on overflow
- Each chip: pill shape, background `#EDF0F7`, text `#1C3461`, 13px Medium, with `×` dismiss icon on right
- "Clear all" text link (Inter 13px `#6B6B6B`, underline on hover) at the end of the chip row

**Below chips row — query expansion notice (conditional):**
- Shown only when F04 has expanded the query
- Single line, Inter 12px, color `#6B6B6B`: "Also searching for: [term1], [term2], …" — truncated with "…" if list exceeds available line width
- 6px vertical gap above first result

**Results header row:**
- Left: result count — Inter 13px Text secondary: "[N] results for "[query]""
- Right: sort dropdown — label "Sort: Relevance ▾", Inter 14px, border `#E2DDD6`, border-radius 6px, background white. Options: Relevance (default), Newest first, Oldest first. Selecting an option re-sorts immediately; label updates to reflect selection.

**Result cards:**
- White surface, border `1px solid #E2DDD6`, border-radius 8px, padding 16px, vertical gap 12px between cards
- Two card types share base card styling (hover, border, shadow).
- Hover state: box-shadow deepens to `0 4px 12px rgba(0,0,0,0.08)`, no background change.

**Speech record card (top to bottom):**
  1. **Metadata row:** Left-aligned inline sequence — [Proceeding type badge] · [Legislative body full label] · [Date formatted as DD Month YYYY] · [Session name if available]. Inter 12px Text secondary. Proceeding type badge: pill with `#EDF0F7` background, `#1C3461` text, 11px Medium. Legislative body shown in full: "Constituent Assembly", "Lok Sabha", or "Rajya Sabha".
  2. **Speaker row:** Inter 15px SemiBold `#1A1A1A`, 6px below metadata row. If `speaker_party` or `speaker_constituency_or_state` available, append in same line in Inter 12px Text secondary separated by " · ". If both absent, omit — no placeholder. If `speaker_name` null, show "Speaker unknown" in Text secondary.
  3. **Subject line:** `subject` field (debate title / agenda item), Inter 13px Regular `#6B6B6B`, 4px below speaker row, truncated at one line with ellipsis.
  4. **Snippet:** Inter 14px Regular `#1A1A1A`, 6px below subject line. 2–3 sentences. Matched terms (original and expanded) highlighted with background `rgba(201, 106, 30, 0.15)` and text `#C96A1E`. If `full_text_en` is null, show "This speech was delivered in Hindi. No English text is available." in Inter 14px Text secondary.
  5. **Translation indicator (conditional):** If `is_translated` true, show "Translated from Hindi" in Inter 11px Text secondary, italic, immediately below snippet.
  6. **Source link:** "View source ↗" — Inter 13px `#1C3461`, underline on hover, right-aligned, 8px below snippet/indicator. Opens in new tab. Omitted if `source_url` null.

**Q+A exchange record card (top to bottom):**
  1. **Metadata row:** Same styling as speech card.
  2. **Subject line:** `subject` field (question title), Inter 15px SemiBold `#1A1A1A`, 6px below metadata row, truncated at two lines.
  3. **Question number:** "Q. [number]" in Inter 12px Text secondary, 2px below subject.
  4. **Questioner row:** Inter 13px Regular `#1A1A1A`: "[Questioner name]" + party in Text secondary if available. If co-signatories: "[Primary name] +N others". 4px below question number.
  5. **Minister/ministry row:** Inter 13px Text secondary: "Answered by [Minister Name], [Ministry]". 2px below questioner row.
  6. **Snippet:** Same styling as speech card. If match is from a supplementary exchange, prepend "From supplementary exchange — " in Inter 12px Text secondary before snippet text.
  7. **Translation indicator (conditional):** Same as speech card.
  8. **Source link:** Same as speech card.

**Loading state:** Skeleton cards matching result card dimensions — gray animated shimmer blocks for metadata row, speaker name, and snippet lines. Show 5 skeleton cards while results load.

**Empty state:** Centered in results column, 48px top padding. Inter 15px Text primary: "No results found for "[query]"." One line below in Inter 14px Text secondary: "Try adjusting your search terms or removing filters." No illustration.

**Inline validation (search bar):** If query is empty or under 2 non-whitespace characters, show validation message directly below the search bar: Inter 13px `#C96A1E`: "Enter at least 2 characters to search." No search executes. Message dismisses when the user begins typing again.

**Error state:** Centered. Inter 15px Text primary: "Search is temporarily unavailable." Inter 14px Text secondary: "Please try again." Primary button "Retry" below.

**Pagination:** Centered below last result card, 24px gap. Previous / page numbers / Next. Current page: background `#1C3461`, white text, border-radius 6px. Adjacent pages: text `#1C3461`, border `#E2DDD6`. 20 results per page.

**Responsive:**
- Desktop (≥1024px): 860px centered column
- Tablet (768–1023px): 90vw column; header search bar width 60vw
- Mobile (<768px): 92vw column; sort dropdown moves below chips row; header collapses to wordmark + icon row only; search bar full-width below header

---

### 3. Advanced Search Modal

**Mockup:** `mockups/advanced-search-modal-ca-only.png` *(shows CA-only selected state with proceeding types conditionally disabled)*

**Trigger:** "Advanced Search" link in header or homepage below-bar row.

**Layout:** Centered modal overlay. Background overlay: `rgba(0,0,0,0.4)`. Modal: white surface, border-radius 12px, padding 24px, max-width 560px, max-height 90vh, scrollable if needed.

**Header:** "Advanced Search" in Merriweather 18px Bold `#1A1A1A`. Close icon (×) top-right, 20px, `#6B6B6B`, hover `#1A1A1A`.

**Fields (vertical stack, 16px gap between fields):**

1. **Legislative Body** — label "Legislative Body" Inter 13px Medium `#1A1A1A`. Multi-select checkbox group (any combination valid): Constituent Assembly / Lok Sabha / Rajya Sabha. All three checked by default (no body restriction). Horizontal layout if space allows; vertical stack on mobile. Validation: if the user unchecks all three, show inline message "Select at least one source" in Inter 12px `#C96A1E` below the group; Apply button is disabled.

2. **Date Range** — label "Date Range" Inter 13px Medium. Two date inputs side by side: "From" and "To". Input style: height 36px, border `#E2DDD6`, border-radius 6px, Inter 14px. "From" and "To" labels in Inter 12px Text secondary above each input. Both inputs optional. Validation: if From is later than To, show inline message "From date must be before To date" in Inter 12px `#C96A1E` below the inputs; Apply button is disabled.

3. **Speaker** — label "Speaker" Inter 13px Medium. Single text input, height 36px. Placeholder: "e.g. Ambedkar". Full modal width. Helper text below in Inter 11px Text secondary: "Use last name only for reliable results (names are canonicalized in the index)."

4. **Session** — label "Session" Inter 13px Medium. Single text input, height 36px. Placeholder: "e.g. Budget Session 2023". Full modal width. Helper text below in Inter 11px Text secondary: "Constituent Assembly records have no session name and will not match a session filter."

5. **Proceeding Type** — label "Proceeding Type" Inter 13px Medium. Multi-select checkbox list (two columns if space allows): Starred Question / Unstarred Question / Short Notice Question / Zero Hour / Adjournment Motion / Calling Attention / Short Duration Discussion / Adjournment Motion / Private Member Bill / Debate. All checked by default (no type restriction). When only CA is selected in Legislative Body: all options except Debate are visually disabled (grayed out, non-interactive). Validation: if the user unchecks all options, show inline message "Select at least one proceeding type" in Inter 12px `#C96A1E` below the list; Apply button is disabled.

**Modal footer (sticky at bottom of modal):**
- Left: "Clear all" — Inter 14px `#6B6B6B`, underline on hover. Resets all fields to defaults (all bodies checked, all types checked, date/speaker/session inputs empty).
- Right: "Apply" primary button — background `#1C3461`, white text, Inter 14px Medium, height 40px, border-radius 6px, min-width 96px. Disabled (opacity 0.4, not clickable) when any field-level validation is failing. On click when valid: modal closes; active filters appear as chips below search bar; search re-executes with filters applied.

**Pre-population:** If filters are already active (chips visible), modal opens with those fields pre-populated.

**Responsive:** On mobile (<768px), modal is full-width with 16px side margins; all checkboxes stack vertically.

---

### 4. Recent Searches Dropdown

**Trigger:** User focuses the search bar when it is empty.

**Layout:** Dropdown panel anchored below the search bar, full width of the search bar. White surface, border `1px solid #E2DDD6`, border-radius 0 0 8px 8px, box-shadow `0 4px 12px rgba(0,0,0,0.08)`.

**Content:**
- Section label "Recent searches" Inter 12px Text secondary, padding 10px 16px 4px.
- Up to 10 items. Each item: magnifying glass icon (14px `#6B6B6B`) + query text (Inter 14px `#1A1A1A`), padding 10px 16px, hover background `#F7F4EF`. Click: populates search bar and submits.
- Divider line above footer.
- Footer: "Clear history" text link, Inter 13px `#6B6B6B`, right-aligned, padding 8px 16px.

**Empty state:** Single line "No recent searches" Inter 14px Text secondary, padding 12px 16px.

**Dismiss:** Clicking outside the dropdown or pressing Escape closes it without action.

---

### 5. Saved Searches Panel

**Trigger:** Bookmark icon (right of search bar, in header or homepage).

**Layout:** Dropdown panel anchored below the bookmark icon, width 320px. White surface, border `1px solid #E2DDD6`, border-radius 8px, box-shadow `0 4px 12px rgba(0,0,0,0.08)`. Max-height 400px, scrollable.

**Header:** "Saved searches" Inter 14px SemiBold `#1A1A1A`, padding 12px 16px 8px.

**Content:**
- Up to 20 items. Each item: two lines.
  - Line 1: saved search name (defaults to query text, user-editable), Inter 14px `#1A1A1A`, truncated at one line with ellipsis.
  - Line 2: filter summary in Inter 12px Text secondary (e.g., "Lok Sabha · 2019–2024 · Starred Question"). "No filters" if saved without filter state.
  - Right side: two icon buttons — pencil icon (rename, 14px `#6B6B6B`) and trash icon (delete, 14px `#6B6B6B`, hover `#C96A1E`). On delete: item removed, toast shown ("Search removed").
- Rename interaction: clicking pencil icon on an item converts Line 1 to an inline text input (max 60 characters) with a checkmark button to confirm and × to cancel. On confirm: name updated in place, no toast.
- Item padding: 10px 16px. Hover background: `#F7F4EF`. Clicking the item text (not icons) restores query + filter state, panel closes, search executes.

**Save button (results page only):** Below the item list, a full-width "Save current search" button — border `1px solid #1C3461`, text `#1C3461`, background white, Inter 14px, height 36px. On click: current query + filter state saved, button text changes briefly to "Saved ✓", toast shown ("Search saved"). When 20 saved searches already exist: button is disabled (opacity 0.4) and shows label "Saved searches full — delete one to save" in Inter 12px Text secondary below it. Button hidden on homepage (no active search to save).

**Empty state:** "No saved searches yet." Inter 14px Text secondary, padding 16px.

**Dismiss:** Clicking outside or pressing Escape closes the panel.

---

## Interaction Patterns

### Navigation Model

- Two primary views: Homepage and Results page. No in-app routing beyond these two.
- Indexing status information lives in the homepage footer strip — no separate page.
- All modals and panels are overlays; they do not change the URL.
- Navigating back to the homepage from a results page clears the active search state.

### Input Methods

- Search submission: Enter key or click on submit icon in search bar.
- Filter application: via Advanced Search modal only; no inline filter controls on the results page.
- Filter removal: click `×` on a chip, or "Clear all" link, or re-open Advanced Search modal and modify.
- Sort change: dropdown selection; takes effect immediately.
- Saved/recent search restore: click on item in respective panel.

### Feedback Patterns

| Event | Feedback |
|-------|----------|
| Search executing | Skeleton cards appear immediately; results replace them |
| No results | Empty state message in results column |
| Search error | Error state with Retry button |
| Filter applied | Modal closes; chip appears; results reload |
| Filter removed (chip ×) | Chip disappears; results reload |
| Search saved | Toast bottom-center: "Search saved" — 3s auto-dismiss, Inter 13px, white text, `#1C3461` background, border-radius 6px |
| Search removed | Toast bottom-center: "Search removed" — same styling |
| Query expanded | Compact single-line notice below chips: "Also searching for: [terms]" — no toast, no modal |

Toasts appear bottom-center, 16px from bottom edge. One toast at a time. No toasts for search execution events (loading states handle those).

### Action Button Placement and Labeling

- Primary actions (Apply, Retry): right-aligned, filled `#1C3461` background
- Destructive or neutral actions (Clear all, Clear history): left-aligned or text-only, never filled
- Save current search: full-width outline button in saved searches panel footer
- All button labels are imperative verbs: "Apply", "Retry", "Save current search", "Clear all"

---

## Canonical Text

| Name | String | Used in |
|------|--------|---------|
| SEARCH_PLACEHOLDER | "Search parliamentary debates, questions, and speeches…" | Homepage search bar, results page search bar |
| TAGLINE | "Search the complete record of Indian parliamentary debates." | Homepage below wordmark |
| EMPTY_RESULTS | "No results found for "[query]". Try adjusting your search terms or removing filters." | Results page empty state |
| ERROR_STATE | "Search is temporarily unavailable. Please try again." | Results page error state |
| VALIDATION_SHORT | "Enter at least 2 characters to search." | Inline below search bar on empty/short submit |
| SAVE_LIMIT | "Saved searches full — delete one to save" | Below disabled Save button when at 20-entry limit |
| SAVE_TOAST | "Search saved" | Toast on save |
| REMOVE_TOAST | "Search removed" | Toast on remove |
| NO_RECENT | "No recent searches" | Recent searches dropdown empty state |
| NO_SAVED | "No saved searches yet." | Saved searches panel empty state |
