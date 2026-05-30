# PRD Diff: v1.1 → v1.2

Generated: 2026-05-30
Reason: Ingestion source redesign — CA PDF URLs on sansad.in were dead (HTTP 500); architecture changed to HTML-based sources. PRD data source references corrected to match actual ingestion architecture.

---

## Modified Content

### 1. Overview — Data Scope table (01-overview.md)

**Before:**
| Source | Coverage | Base URL |
|--------|----------|----------|
| Constituent Assembly debates | All 12 volumes, 1946–1950 | sansad.in (Lok Sabha archives) |
| Lok Sabha debates and questions | 2014–2026 (16th–18th Lok Sabha) | sansad.in |
| Rajya Sabha debates and questions | 2014–2026 | rajyasabha.gov.in |

**After:**
| Source | Coverage | Base URL |
|--------|----------|----------|
| Constituent Assembly debates | All 12 volumes, 1946–1950 | constitutionofindia.net |
| Lok Sabha debates and questions | 2014–2026 (16th–18th Lok Sabha) | eparlib.sansad.in (primary); Internet Archive (fallback) |
| Rajya Sabha debates and questions | 2014–2026 | sansad.in/rs (primary); Internet Archive; rsdebate.nic.in (fallback) |

---

### 2. Objectives — Objective 5 (02-objectives.md)

**Before:**
> 5. Provide verifiable citations: every result links directly to the original source document on sansad.in or rajyasabha.gov.in.

**After:**
> 5. Provide verifiable citations: every result links directly to the authoritative source document for that record.

---

### 3. F01 — Description paragraph (01-data-ingestion.md)

**Before:**
> The ingestion pipeline fetches, parses, segments, and indexes parliamentary records from three sources: Constituent Assembly debates (sansad.in archives), Lok Sabha records (sansad.in), and Rajya Sabha records (rajyasabha.gov.in).

**After:**
> The ingestion pipeline fetches, parses, segments, and indexes parliamentary records from three sources: Constituent Assembly debates, Lok Sabha records, and Rajya Sabha records.

---

### 4. F01 — Data Sources and Scope table (01-data-ingestion.md)

**Before:**
| Source | Content | Date scope | Format | Base URL |
|--------|---------|------------|--------|----------|
| Constituent Assembly | Plenary debates | All 12 volumes, 1946–1950 | PDF (some scanned) | sansad.in (Lok Sabha archives) |
| Lok Sabha | Debates and questions | 2014-01-01 to present | HTML and PDF | sansad.in |
| Rajya Sabha | Debates and questions | 2014-01-01 to present | HTML and PDF | rajyasabha.gov.in |

**After:**
| Source | Content | Date scope | Format | Base URL |
|--------|---------|------------|--------|----------|
| Constituent Assembly | Plenary debates | All 12 volumes, 1946–1950 | HTML | constitutionofindia.net |
| Lok Sabha | Debates and questions | 2014-01-01 to present | HTML and PDF | eparlib.sansad.in (primary); Internet Archive _djvu.txt pre-OCR text (fallback) |
| Rajya Sabha | Debates and questions | 2014-01-01 to present | HTML and PDF | sansad.in/rs HTML (primary); Internet Archive; rsdebate.nic.in DSpace (fallback) |

---

### 5. F01 — `source_url` field (Speech unit, starred Q+A, unstarred Q+A) (01-data-ingestion.md)

**Before (Speech unit):**
> `source_url` — URL of the original HTML page or PDF

**After (Speech unit):**
> `source_url` — URL of the original HTML page or PDF; for LS records fetched from Internet Archive, always set to the corresponding eparlib.sansad.in document URL

**Before (starred Q+A):**
> `source_url` — URL of the original document

**After (starred Q+A):**
> `source_url` — URL of the original document; for LS records fetched from Internet Archive, always set to the corresponding eparlib.sansad.in document URL

Same change applied to unstarred Q+A `source_url` field.

---

### 6. F01 — Edge Cases: CA OCR bullet removed (01-data-ingestion.md)

**Removed:**
> - Scanned CA PDFs: text extracted via OCR; records with OCR confidence below threshold are flagged (`ocr_low_confidence: true`) but still indexed

Reason: CA ingestion now uses constitutionofindia.net HTML only; no PDFs, no OCR.

---

### 7. F01 — NFR Implications: OCR bullet removed (01-data-ingestion.md)

**Removed:**
> - **OCR dependency:** scanned CA PDFs require OCR processing capability → flag in NFR

---

### 8. Test Spec F01 — OCR-Flagged Records section removed (01-data-ingestion-tests.md)

**Removed section:**
> ## OCR-Flagged Records
> - Records flagged with `ocr_low_confidence: true` must appear in the search index; they must not be silently dropped
> - `ocr_low_confidence` must be false for records sourced from digital (non-scanned) PDFs and HTML

---

### 9. NFR — INF-RL1 host list updated (04-non-functional-requirements.md)

**Before:**
> The ingestion pipeline must comply with robots.txt on sansad.in and rajyasabha.gov.in.

**After:**
> The ingestion pipeline must comply with robots.txt on constitutionofindia.net, eparlib.sansad.in, sansad.in, rsdebate.nic.in, and the Internet Archive.

---

### 10. NFR — INF-P2 removed (04-non-functional-requirements.md)

**Removed:**
> **INF-P2: OCR capability**
> Some Constituent Assembly volumes are scanned PDFs requiring OCR. The ingestion pipeline must include an OCR component. OCR accuracy is best-effort for scanned documents; low-confidence records must be flagged, not dropped.

Reason: CA is now HTML-only from constitutionofindia.net; OCR is no longer required.

---

## No New Features or Sections

No new feature files added. No features removed. F02–F08, all test specs (except F01), and all NFR items except INF-P2 are unchanged.

---

## Actionable Summary for Downstream Agents

1. **F01 ingestion implementation:** CA source is constitutionofindia.net HTML (167 sittings, 12 vols); no OCR component needed for CA. LS primary is eparlib.sansad.in DSpace; fallback is Internet Archive `_djvu.txt` pre-OCR text files. RS primary is sansad.in/rs HTML; fallbacks are Internet Archive and rsdebate.nic.in DSpace.
2. **`source_url` for LS/IA records:** when content is fetched from Internet Archive for LS, the stored `source_url` must be the corresponding eparlib.sansad.in document URL, not the archive.org URL.
3. **`ocr_low_confidence` field:** no longer exists; remove from any implementation or test that references it.
4. **INF-P2 removed:** no OCR component is required in the ingestion pipeline.
5. **INF-RL1 updated:** rate limiting and robots.txt compliance applies to all five source hosts listed.
