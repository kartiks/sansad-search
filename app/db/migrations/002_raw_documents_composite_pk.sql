-- Migration 002: fix raw_documents PK to (canonical_doc_id, corpus) composite.
--
-- The original single-column PK on canonical_doc_id caused LS ingestion to
-- pre-populate handle numbers that RS ingestion then silently skipped, because
-- both InternetArchiveProvider instances share the eparlib.nic.in.{N} namespace.
--
-- Apply to existing databases only. Fresh databases should use schema.sql directly.

ALTER TABLE raw_documents DROP CONSTRAINT raw_documents_pkey;
ALTER TABLE raw_documents ADD PRIMARY KEY (canonical_doc_id, corpus);
