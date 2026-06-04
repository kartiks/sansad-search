# PRD Diff — v2.0 to v2.1

**Generated:** 2026-06-04
**Change type:** Minor (existing feature update — F01)
**Reason:** Phase 12 QA run-3 gap: implementation passes `--date-from`/`--date-to` to Stage 1 (`run_stage1()`), contradicting PHASES.md spec ("Stage 1 ignores them"). Product Agent ratified the implementation as the correct behavior (both-stage scope). F01 updated to reflect the ratified design.

---

## Modified: F01 — Data Ingestion

### Description (modified)

**Added (after existing first paragraph):**
> The pipeline is implemented as a two-stage process. Stage 1 (fetch) downloads source documents and writes raw content to a `raw_documents` store. Stage 2 (process) reads from that store and produces indexed `speeches`/`qa_exchanges` records. The two stages can be run together or independently via the `--stage` flag.

### New section: Two-Stage Pipeline (added)

Complete new section covering:

**Stage control table:**
| `--stage` value | Behavior |
|-----------------|----------|
| `fetch` | Stage 1 only: discover and download source documents; write to `raw_documents` |
| `process` | Stage 2 only: read from `raw_documents`; parse, segment, and index |
| `all` | Stage 1 then Stage 2 sequentially for each source (default) |

**Stage 1 (fetch) flow:**
1. Discover documents for the selected corpus(es)
2. Check `raw_documents` PK for each `canonical_doc_id`; skip if already present
3. Fetch new documents from source with rate limiting
4. Extract text and metadata
5. Apply date-window gate when `--date-from`/`--date-to` are provided: write to `raw_documents` only if the document's date falls within the window; skip out-of-window documents
6. Write raw content (extracted text + metadata JSON) to `raw_documents`

Stage 1 does not write to `speeches`, `qa_exchanges`, or the SQLite checkpoint store. It does not update `index_status`.

**Stage 2 (process) flow:**
1. Read `raw_documents` rows for the selected corpus; apply `--date-from`/`--date-to` window if provided
2. Skip documents already checkpointed as processed in the SQLite `processed_documents` store
3. Segment each document into speech and Q+A exchange units
4. Canonicalize speaker names and session names
5. Index each unit into `speeches`/`qa_exchanges`
6. Checkpoint the document in `processed_documents` after all its records are successfully indexed

`index_status` is updated only at the end of Stage 2, not at the end of Stage 1.

**Date filtering (key behavioral change):**
> `--date-from YYYY-MM-DD` and `--date-to YYYY-MM-DD` scope **both stages**:
> - **Stage 1:** only documents whose parsed date falls within the window are written to `raw_documents`; out-of-window documents are skipped after parsing
> - **Stage 2:** only `raw_documents` rows with dates within the window are read and processed
>
> When neither flag is provided, both stages operate on the full corpus without date restriction.

### User Flows — step 1 (modified)

**Before:**
> Operator runs ingestion with a source selector (CA | LS | RS | all) and optional date override

**After:**
> Operator runs ingestion with a source selector (CA | LS | RS | all), `--stage fetch|process|all` (default `all`), and optional `--date-from`/`--date-to` to restrict the date window applied to both stages

### Acceptance Criteria (added items)

The following criteria were added (existing criteria unchanged):

- `--stage fetch` writes raw content to `raw_documents` without producing any `speeches` or `qa_exchanges` records
- `--stage process` reads from `raw_documents` and produces indexed records without fetching from source
- Re-running Stage 1 against an already-fetched corpus writes zero new `raw_documents` rows (PK dedup skips all)
- `--stage fetch --date-from X --date-to Y` writes only documents with dates within that range to `raw_documents`; documents outside the window are skipped after parsing
- `--stage all --date-from X --date-to Y` produces `speeches`/`qa_exchanges` records only for dates within the specified range

### Test Spec — new section: Stage 1 Date Window Gate (added)

- A document dated exactly on `date_from` must be written to `raw_documents`; a document dated one day before `date_from` must not be written
- A document dated exactly on `date_to` must be written to `raw_documents`; a document dated one day after `date_to` must not be written
- When neither `--date-from` nor `--date-to` is specified, Stage 1 must write all discovered documents to `raw_documents` regardless of date

---

## Modified: PHASES.md — Phase 12

### main.py bullet (modified)

**Before:**
> add `--date-from YYYY-MM-DD` and `--date-to YYYY-MM-DD` for Stage 2 scope (scope which `raw_documents` rows are read; **Stage 1 ignores them**); routing: `--stage fetch` → call each orchestrator's `run_stage1()` only; `--stage process` → call each orchestrator's `run_stage2()` only, passing `date_from`/`date_to`; `--stage all` → `run_stage1()` then `run_stage2()` for each source sequentially

**After:**
> add `--date-from YYYY-MM-DD` and `--date-to YYYY-MM-DD` to **scope both stages**: Stage 1 applies a post-parse date-window gate, writing only documents within the window to `raw_documents`; Stage 2 reads only `raw_documents` rows within the window; routing: `--stage fetch` → call each orchestrator's `run_stage1(date_from, date_to)` only; `--stage process` → call each orchestrator's `run_stage2()` only, passing `date_from`/`date_to`; `--stage all` → `run_stage1(date_from, date_to)` then `run_stage2(date_from, date_to)` for each source sequentially

### Stop condition (added items)

The following stop conditions were added:
- `--stage fetch --date-from 2024-01-01 --date-to 2024-12-31` writes only documents with dates within that range to `raw_documents` and skips all out-of-range documents
- `--stage fetch` without a date filter writes all discovered documents regardless of date

---

## No Changes

F02, F03, F04, F05, F06, F07, F08, F09, all NFR items, Future Features — unchanged.
