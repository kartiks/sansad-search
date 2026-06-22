# PRD Diff: v3.2 → v3.3

**From:** PRD-v3.2.md (2026-06-12)  
**To:** PRD-v3.3.md (2026-06-22)  
**Bump type:** Minor (modifications to existing features F02 + F05; one new NFR item)

This diff is actionable without reading the full PRD. Downstream agents (`/build`, `/arch`, `/plan`) should treat every item below as a required change.

---

## Summary

The result-snippet size becomes configurable. Previously it was a fixed minimum of ≥200 words. Now:
- An optional per-request API parameter `snippet_size` (integer, words) sets the target snippet length.
- The default is **operator-configurable**, defaulting to **100 words** (lowered from the previous fixed 200).
- Accepted range **20–1000 words**; out-of-range numeric values are **clamped**; non-integer/non-numeric/missing values fall back to the default.
- The web UI exposes **no** control for this — it relies on the default. The parameter is for programmatic API consumers.

This affects F02 (API/search behavior), F05 (snippet rendering), and adds NFR PERF-4. No new feature files; no changes to F01, F03, F04, F06–F10, or any other NFR item.

---

## F02: Full-text Search — MODIFIED

### New section: "Snippet Size Parameter" (added after "Default search scope")

```
The search API accepts an optional `snippet_size` parameter (integer, words) that
sets the target length of result snippets. Snippet rendering is defined in F05.

- Omitted, non-integer, or non-numeric value → operator-configurable default
  (default 100 words); no error surfaced; search executes
- Accepted range: 20–1000 words
- Out-of-range numeric value clamped to nearest bound (below 20 → 20; above 1000 → 1000);
  no error surfaced; search executes
- Default is operator-configurable as a deployment setting (see NFR PERF-4)
- Web UI exposes no control; relies on the default. Parameter is for programmatic API consumers.
- Exact API field name / wire format is an architecture-stage decision; `snippet_size`
  is the conceptual name.
```

### Acceptance Criteria — ADDED

```
- A search with no `snippet_size` returns snippets at the configured default size (default 100 words)
- A search with `snippet_size=300` returns snippets targeting 300 words
- A search with `snippet_size=5` is clamped to 20; a search with `snippet_size=5000` is clamped to 1000
- A search with a non-integer or non-numeric `snippet_size` falls back to the default and still returns results
```

### NFR Implications — ADDED bullet

```
- Snippet size payload: the `snippet_size` parameter increases response payload at larger
  values; a maximum bound is required so the response time target still holds at the largest
  permitted size → see NFR PERF-4
```

### Test Spec F02 — ADDED section "Snippet Size Clamp Boundaries"

```
- `snippet_size=20` and `snippet_size=1000` accepted as-is (bounds inclusive; not clamped)
- `snippet_size=19` clamps to 20; `snippet_size=1001` clamps to 1000
- `snippet_size=0` and negative clamp to 20 — NOT treated as invalid/default
- non-integer numeric (e.g. 100.5) falls back to default (100); not truncated/rounded
- present-but-empty value falls back to default
```

---

## F05: Result Display — MODIFIED

### Result Card tables (Speech + Q+A) — Text snippet row CHANGED

**Before:**
```
| Text snippet | derived from `full_text_en` | ≥200 words; query terms highlighted |
```

**After:**
```
| Text snippet | derived from `full_text_en` | Sized to the effective snippet size (default 100 words); query terms highlighted |
```

### Snippet Generation — CHANGED

**Before:**
```
- ≥200 words from the highest-density passage; query terms highlighted
- Full text shown when `full_text_en` < 200 words
- Null `full_text_en`: "This speech was delivered in Hindi. No English text is available."
- Q+A supplementary match: "From supplementary exchange" label shown
```

**After:**
```
- Passage from the highest-density match region, targeting the effective snippet size — the
  per-request `snippet_size` from F02 if supplied (clamped to 20–1000 words), else the
  operator-configurable default (default 100 words); the search engine's crop length is
  driven by the effective snippet size; query terms highlighted
- Full text shown (no padding) when `full_text_en` has fewer words than the effective snippet size
- Snippet may be shorter than the effective snippet size when the matched passage is near the
  start or end of `full_text_en`
- Null `full_text_en`: "This speech was delivered in Hindi. No English text is available."
- Q+A supplementary match: "From supplementary exchange" label shown
```

Note: a prior mechanism reference to "the Meilisearch crop length must be configured to produce this minimum" is generalized to engine-neutral "the search engine's crop length is driven by the effective snippet size."

### Test Spec F05 — section RENAMED + CHANGED

**Before — "Snippet Minimum Size":**
```
- >200 words in `full_text_en` → snippet ≥200 words (unless passage is near start/end); <200 words → full text shown
```

**After — "Snippet Size":**
```
- No `snippet_size` supplied → default-sized snippet of 100 words (not the legacy 200)
- `full_text_en` longer than the effective snippet size → snippet cropped to approximately that
  size (unless passage is near start/end); shorter than the effective snippet size → full text
  shown, no words omitted, no padding
```

---

## NFR — NEW ITEM

### PERF-4: Snippet size bound — ADDED (under Performance, after PERF-3)

```
The search API `snippet_size` parameter is bounded to 20–1000 words; out-of-range numeric
values are clamped to the nearest bound; missing/non-integer/non-numeric values fall back to
the default. Default is 100 words and is operator-configurable as a deployment setting. The
maximum bound exists so PERF-1 (≤2s p95) holds at `snippet_size=1000` across the full corpus.
```

---

## Downstream Impact Notes (for /plan, /arch, /build)

- **Behavior change, not purely additive:** the default snippet drops from 200 → 100 words. Already-built F05 rendering and the default crop length must change; existing tests asserting 200 must be updated to 100.
- **New API surface:** `snippet_size` request parameter on the search endpoint, with clamp/fallback validation. Exact field name, type coercion, and crop-length wiring are an `/arch` decision (DATA-MODELS search request/config).
- **NFR:** PERF-4 must be verified at `snippet_size=1000`.
- This change spans already-completed phases → fix is forward-only via a new phase. Run `/plan` to add a phase, then `/build`.
