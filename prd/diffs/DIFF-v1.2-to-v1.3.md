# PRD Diff: v1.2 → v1.3

**Generated:** 2026-05-30
**Scope:** F01 Data Ingestion — two corrections routed back from ARCH reconciliation + one new edge case

---

## Modified Content

### F01: Data Sources and Scope — LS format column

**Before:**
```
| Lok Sabha | Debates and questions | 2014-01-01 to present | HTML and PDF | eparlib.sansad.in (primary); Internet Archive _djvu.txt pre-OCR text (fallback) |
```

**After:**
```
| Lok Sabha | Debates and questions | 2014-01-01 to present | Pre-OCR plain text (_djvu.txt); PDF | eparlib.sansad.in (primary); Internet Archive _djvu.txt pre-OCR text (fallback) |
```

**Reason:** LS ingestion chain uses IA _djvu.txt pre-OCR plain text as primary and eparlib DSpace PDF as fallback. No HTML source exists in the LS chain. Previous "HTML and PDF" description was inaccurate.

---

### F01: Speech unit — `source_url` field

**Before:**
> URL of the original HTML page or PDF; for LS records fetched from Internet Archive, always set to the corresponding eparlib.sansad.in document URL

**After:**
> URL of the original HTML page or PDF; for LS records fetched from Internet Archive, always set to the corresponding eparlib.sansad.in document URL; for RS records fetched from Internet Archive, always set to the corresponding rsdebate.nic.in document URL (derived from the DSpace handle)

**Reason:** RS ingestion chain includes Internet Archive as a fallback source. The canonical-citation rule (never cite archive.org) must apply to RS-via-IA records as well as LS-via-IA records. The canonical RS URL is rsdebate.nic.in, derived from the DSpace handle present in the IA record.

---

### F01: Q+A exchange unit (starred and unstarred) — `source_url` field

**Before:**
> URL of the original document; for LS records fetched from Internet Archive, always set to the corresponding eparlib.sansad.in document URL

**After:**
> URL of the original document; for LS records fetched from Internet Archive, always set to the corresponding eparlib.sansad.in document URL; for RS records fetched from Internet Archive, always set to the corresponding rsdebate.nic.in document URL (derived from the DSpace handle)

**Reason:** Same as speech unit above. Applies to all record types, not just speech units.

---

### F01: Edge Cases — new entry

**Added:**
> RS record fetched from Internet Archive with no derivable DSpace handle: set `source_url` to null; log a warning; do not use the archive.org URL

**Reason:** Failure mode for the RS canonical-citation rule. If the DSpace handle cannot be extracted from the IA record metadata, the implementation must not fall back to the archive.org URL (which is prohibited as a citation URL). Setting source_url to null is handled gracefully by F05 ("Source URL is missing or broken: 'View source' link is not shown; no broken link is displayed").

---

## No Changes

- F02 through F08: unchanged
- Non-Functional Requirements: unchanged
- Test specs F01–F08: no test spec changes required (new behaviors are explicitly stated in the feature spec; Coding Agent derives tests directly)
