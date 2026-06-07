-- SansadSearch PostgreSQL schema
-- Run this against a fresh database to create all tables and indexes.
-- PRD v2.0: added lang_original, time_of_day, word_count to both tables;
-- sequence_within_sitting added to qa_exchanges; sitting composite indexes added.
-- PRD v3.0: added lok_sabha_number + canonical_doc_id to both tables;
-- segments JSONB added to speeches (Adjacent Speech Merging). All three are
-- PostgreSQL-only (excluded from the Meilisearch document).

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── speeches ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS speeches (
    id                          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    source                      VARCHAR(2)  NOT NULL CHECK (source IN ('CA','LS','RS')),
    proceeding_type             VARCHAR(50) NOT NULL,
    date                        DATE        NOT NULL,
    session_name                VARCHAR(200),
    session_number              INTEGER,
    sitting_number              INTEGER,
    subject                     TEXT,
    speaker_name                VARCHAR(300),
    speaker_party               VARCHAR(200),
    speaker_constituency_or_state VARCHAR(200),
    speaker_role                VARCHAR(30) CHECK (speaker_role IN ('member','minister','presiding_officer')),
    sequence_within_sitting     INTEGER,
    full_text_en                TEXT,
    lang_original               VARCHAR(5)  NOT NULL CHECK (lang_original IN ('en','hi','mixed')),
    time_of_day                 VARCHAR(5),
    word_count                  INTEGER,
    is_translated               BOOLEAN     NOT NULL DEFAULT FALSE,
    has_untranslated_content    BOOLEAN     NOT NULL DEFAULT FALSE,
    speaker_name_unresolved     BOOLEAN     NOT NULL DEFAULT FALSE,
    source_url                  TEXT,
    page_reference              INTEGER,
    volume                      INTEGER,
    lok_sabha_number            INTEGER,
    segments                    JSONB,
    canonical_doc_id            TEXT,
    dedup_key                   VARCHAR(500) UNIQUE NOT NULL,
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

-- v3.0 columns, idempotent for existing databases.
ALTER TABLE speeches ADD COLUMN IF NOT EXISTS lok_sabha_number INTEGER;
ALTER TABLE speeches ADD COLUMN IF NOT EXISTS segments         JSONB;
ALTER TABLE speeches ADD COLUMN IF NOT EXISTS canonical_doc_id TEXT;

CREATE INDEX IF NOT EXISTS idx_speeches_source          ON speeches(source);
CREATE INDEX IF NOT EXISTS idx_speeches_date            ON speeches(date);
CREATE INDEX IF NOT EXISTS idx_speeches_proceeding_type ON speeches(proceeding_type);
CREATE INDEX IF NOT EXISTS idx_speeches_speaker_name   ON speeches(speaker_name);
CREATE INDEX IF NOT EXISTS idx_speeches_session_name   ON speeches(session_name);
CREATE INDEX IF NOT EXISTS idx_speeches_dedup_key      ON speeches(dedup_key);
-- F09 adjacent-navigation: same-sitting neighbour lookup by sequence
CREATE INDEX IF NOT EXISTS idx_speeches_sitting        ON speeches(source, date, sitting_number, sequence_within_sitting);

-- ── qa_exchanges ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS qa_exchanges (
    id                       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    source                   VARCHAR(2)  NOT NULL CHECK (source IN ('LS','RS')),
    proceeding_type          VARCHAR(30) NOT NULL CHECK (proceeding_type IN ('starred_question','unstarred_question')),
    date                     DATE        NOT NULL,
    session_name             VARCHAR(200),
    session_number           INTEGER,
    sitting_number           INTEGER,
    question_number          INTEGER,
    subject                  TEXT,
    questioner_names         TEXT[]      NOT NULL,
    questioner_party         VARCHAR(200),
    minister_name            VARCHAR(300),
    ministry                 VARCHAR(300),
    sequence_within_sitting  INTEGER,
    full_text_en             TEXT,
    lang_original            VARCHAR(5)  NOT NULL CHECK (lang_original IN ('en','hi','mixed')),
    time_of_day              VARCHAR(5),
    word_count               INTEGER,
    is_translated            BOOLEAN     NOT NULL DEFAULT FALSE,
    has_untranslated_content BOOLEAN     NOT NULL DEFAULT FALSE,
    source_url               TEXT,
    page_reference           INTEGER,
    lok_sabha_number         INTEGER,
    canonical_doc_id         TEXT,
    dedup_key                VARCHAR(500) UNIQUE NOT NULL,
    created_at               TIMESTAMPTZ DEFAULT NOW()
);

-- v3.0 columns, idempotent for existing databases.
ALTER TABLE qa_exchanges ADD COLUMN IF NOT EXISTS lok_sabha_number INTEGER;
ALTER TABLE qa_exchanges ADD COLUMN IF NOT EXISTS canonical_doc_id TEXT;

CREATE INDEX IF NOT EXISTS idx_qa_source           ON qa_exchanges(source);
CREATE INDEX IF NOT EXISTS idx_qa_date             ON qa_exchanges(date);
CREATE INDEX IF NOT EXISTS idx_qa_proceeding_type  ON qa_exchanges(proceeding_type);
CREATE INDEX IF NOT EXISTS idx_qa_questioner_names ON qa_exchanges USING GIN(questioner_names);
CREATE INDEX IF NOT EXISTS idx_qa_minister_name    ON qa_exchanges(minister_name);
CREATE INDEX IF NOT EXISTS idx_qa_session_name     ON qa_exchanges(session_name);
CREATE INDEX IF NOT EXISTS idx_qa_dedup_key        ON qa_exchanges(dedup_key);
-- F09 adjacent-navigation: same-sitting neighbour lookup by sequence
CREATE INDEX IF NOT EXISTS idx_qa_sitting          ON qa_exchanges(source, date, sitting_number, sequence_within_sitting);

-- ── raw_documents ────────────────────────────────────────────────────────────
-- Intermediate raw document store. Written by Stage 1 (fetch + parse).
-- Read by Stage 2 (segment + index). One row per source document.

CREATE TABLE IF NOT EXISTS raw_documents (
    canonical_doc_id TEXT         NOT NULL,
    corpus           VARCHAR(2)   NOT NULL CHECK (corpus IN ('CA','LS','RS')),
    date             DATE,
    provider         VARCHAR(50)  NOT NULL,
    format           VARCHAR(10)  NOT NULL CHECK (format IN ('html','ia_text','pdf')),
    extracted_text   TEXT,
    metadata_json    JSONB        NOT NULL DEFAULT '{}',
    fetch_url        TEXT,
    citation_url     TEXT,
    fetched_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (canonical_doc_id, corpus)
);

CREATE INDEX IF NOT EXISTS idx_raw_documents_corpus_date ON raw_documents(corpus, date);

-- ── index_status ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS index_status (
    id               SERIAL      PRIMARY KEY,
    run_completed_at TIMESTAMPTZ NOT NULL,
    total_records    INTEGER     NOT NULL,
    ca_count         INTEGER     NOT NULL DEFAULT 0,
    ca_date_from     DATE,
    ca_date_to       DATE,
    ls_count         INTEGER     NOT NULL DEFAULT 0,
    ls_date_from     DATE,
    ls_date_to       DATE,
    rs_count         INTEGER     NOT NULL DEFAULT 0,
    rs_date_from     DATE,
    rs_date_to       DATE
);
