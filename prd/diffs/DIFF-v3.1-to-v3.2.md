# PRD Diff: v3.1 → v3.2

**Generated:** 2026-06-12  
**Scope:** F01 wording — storage-agnostic checkpoint store references

---

## Summary

One feature affected: **F01 (Data Ingestion)**. Two wording-only changes. No functional behavior changed. No new features, no removed features, no schema changes, no API changes.

---

## Modified Content

### F01: Stage 1 (fetch) flow — final note

**Before (v3.1):**
> Stage 1 does not write to `speeches`, `qa_exchanges`, or the SQLite checkpoint store. It does not update `index_status`.

**After (v3.2):**
> Stage 1 does not write to `speeches`, `qa_exchanges`, or the checkpoint store. It does not update `index_status`.

---

### F01: Stage 2 (process) flow — step 2

**Before (v3.1):**
> 2. Skip documents already checkpointed as processed in the SQLite `processed_documents` store

**After (v3.2):**
> 2. Skip documents already checkpointed as processed in the checkpoint store (`processed_documents`)

---

## Unchanged

All other sections of the PRD are identical to v3.1. No test spec changes. No NFR changes. No new features or removed features.

---

## Reason

The checkpoint store was migrated from SQLite to PostgreSQL (ARCH session 2026-06-12). These two lines named the storage technology explicitly, which contradicts the architecture decision. The fix removes the SQLite qualifier so the spec describes behavior without prescribing storage medium — consistent with INF-R1 which is already storage-agnostic.
