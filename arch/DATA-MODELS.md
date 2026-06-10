# Data Models — SansadSearch

**PRD version:** v3.1
**Generated:** 2026-05-28 (v1.0); updated 2026-05-29 (v1.1); updated 2026-05-30 (ingestion source redesign — checkpoint store keyed on canonical document id; citation provenance annotations; reconciled to PRD v1.2: `ocr_low_confidence` dropped from `speeches` — OCR removed pipeline-wide. `qa_exchanges`/`index_status`/Meilisearch document schema otherwise unchanged.); updated 2026-05-31 (reconciled to PRD v1.3: `source_url` descriptions distinguish LS vs RS for the IA path — RS-via-IA cites rsdebate.nic.in derived from handle N, null when no handle derivable); updated 2026-06-01 (PRD v2.0: F01 — `lang_original`/`time_of_day`/`word_count` added to both tables, `sequence_within_sitting` added to `qa_exchanges`, sitting composite indexes for F09 adjacent nav; F05 — `lang_original`/`time_of_day` added to Meilisearch doc + search results; F09 — new `GET /api/record/{id}` contract; `id` stability rule documented); updated 2026-06-03 (raw document store: new `raw_documents` PostgreSQL table as Stage 1 intermediate store; SQLite `processed_documents` semantics updated to Stage 2 complete signal); updated 2026-06-04 (PRD v2.1: §1.4 `raw_documents` composite PK `(canonical_doc_id, corpus)` — fixes sole-PK error; per-corpus dedup semantics documented); updated 2026-06-06 (PRD v3.0: F01 — `lok_sabha_number` + `segments` added to `speeches`, `lok_sabha_number` added to `qa_exchanges`, `canonical_doc_id` link column added to both tables (F10 debug-raw lookup), `source_url` rules reversed (IA URL is now the citation for LS and RS-via-IA/rsdebate); F05 — Meilisearch `cropLength` ≥400 words; F09 — `GET /api/record/{id}` returns `has_prev`/`has_next` (not `adjacent` ids) + new `GET /api/record/{id}/adjacent` range-fetch contract; F10 — debug envelope on `POST /api/search`, new `GET /api/debug/processed/{id}` and `GET /api/debug/raw/{id}` endpoints, debug-mode Meilisearch retrieval config); updated 2026-06-09 (PRD v3.1: F03 — `subject` added to `filterableAttributes` + §2.4 subject filter expression; F05 — `cropLength` reduced from 400 to 200 words)

---

## 1. Core Entities

### 1.1 `speeches` (PostgreSQL)

Primary canonical store for all speech-type records (debates, zero hour, calling attention, etc.).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | Primary key; used as Meilisearch document ID and as the F09 detail-page route param. **Stable across incremental re-runs** (inserts use `ON CONFLICT (dedup_key) DO NOTHING`, so an existing row keeps its `id`); reassigned only by a full clean reindex that truncates the table (see §1.4) |
| `source` | VARCHAR(2) | NOT NULL, CHECK IN ('CA','LS','RS') | Source corpus |
| `proceeding_type` | VARCHAR(50) | NOT NULL | See proceeding type enum below |
| `date` | DATE | NOT NULL | Date of sitting (YYYY-MM-DD) |
| `session_name` | VARCHAR(200) | NULL | Canonicalized session name; NULL for CA |
| `session_number` | INTEGER | NULL | Official session number; NULL for CA |
| `sitting_number` | INTEGER | NULL | Sitting number within session |
| `subject` | TEXT | NULL | Debate title or agenda item |
| `speaker_name` | VARCHAR(300) | NULL | Canonical name (honorifics stripped); NULL if unattributed |
| `speaker_party` | VARCHAR(200) | NULL | Party/group affiliation |
| `speaker_constituency_or_state` | VARCHAR(200) | NULL | Constituency (LS), state (RS), NULL for CA |
| `speaker_role` | VARCHAR(30) | CHECK IN ('member','minister','presiding_officer') | Role in this speech |
| `sequence_within_sitting` | INTEGER | NULL | 1-based position within sitting proceedings |
| `full_text_en` | TEXT | NULL | Full English text; NULL if no translation available |
| `lang_original` | VARCHAR(5) | NOT NULL, CHECK IN ('en','hi','mixed') | Language of the original speech before translation. Derived from F01 Language Handling: case 1→`en`; cases 2 & 4→`hi`; case 3→`mixed` if genuinely alternating, `hi` if predominantly Hindi with only translation fragments |
| `time_of_day` | VARCHAR(5) | NULL | Speech start time as `HH:MM` (24-hour), stored verbatim (no reformatting). Extracted from HTML sources only; NULL for Internet Archive pre-OCR text and PDF sources |
| `word_count` | INTEGER | NULL | Word count of `full_text_en`, computed at ingest; NULL when `full_text_en` is NULL |
| `is_translated` | BOOLEAN | NOT NULL DEFAULT FALSE | True if any portion is official English translation of Hindi |
| `has_untranslated_content` | BOOLEAN | NOT NULL DEFAULT FALSE | True if Hindi portions could not be indexed |
| `speaker_name_unresolved` | BOOLEAN | NOT NULL DEFAULT FALSE | True if speaker_name could not be matched to names_dict |
| `source_url` | TEXT | NULL | Source-document citation URL (PRD v3.0 rules, ARCHITECTURE.md Non-Negotiable #9): **CA** → constitutionofindia.net day page; **LS** → Internet Archive item URL (`https://archive.org/details/{ia_identifier}`); eparlib.sansad.in is **not** used; **RS via Internet Archive or rsdebate.nic.in** → Internet Archive item URL; **RS via sansad.in HTML** → sansad.in page URL. **NULL** when no accessible URL can be derived (e.g. an LS/RS item fetched via DSpace fallback that is genuinely absent from the IA mirror, so no IA URL exists). The archive.org URL **is now the citation** for LS and RS-via-IA/rsdebate (reversal of the pre-v3.0 rule) |
| `lok_sabha_number` | INTEGER | NULL | Lok Sabha term number (e.g. 17 for the 17th Lok Sabha); extracted from source metadata at ingest. **LS only** — NULL for RS and CA records |
| `page_reference` | INTEGER | NULL | Page number in source PDF; NULL for HTML and for IA pre-OCR text records |
| `volume` | INTEGER | NULL | CA volume number (1–12); NULL for LS/RS |
| `segments` | JSONB | NULL | Speech-text segments from Adjacent Speech Merging (F01, PRD v3.0). JSONB array; each element `{"text": "...", "segment_index": N}` (0-based). Single-element array for an unmerged speech; multi-element when consecutive same-speaker speeches were merged. `full_text_en` = segment texts joined with `\n\n`; `word_count` = combined total; `sequence_within_sitting` = position of the first segment in the merge group. PostgreSQL-only — excluded from the Meilisearch document (§2.2) |
| `canonical_doc_id` | TEXT | NULL | Identity of the `raw_documents` row this record was segmented from (the document-level `canonical_doc_id`; the record's `source` is the matching `corpus`). Written by the Stage 2 indexer. Powers the F10 `GET /api/debug/raw/{id}` lookup (`raw_documents WHERE canonical_doc_id = $1 AND corpus = source`). NULL only for rows written before the v3.0 re-ingestion. PostgreSQL-only — excluded from the Meilisearch document |
| `dedup_key` | VARCHAR(500) | UNIQUE NOT NULL | Compound deduplication key (see Deduplication section) |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Ingestion timestamp |

**Proceeding type enum values (speeches):** `debate`, `zero_hour`, `short_duration_discussion`, `calling_attention`, `adjournment_motion`, `private_member_bill`, `short_notice_question`

**Indexes:**
```sql
CREATE INDEX idx_speeches_source ON speeches(source);
CREATE INDEX idx_speeches_date ON speeches(date);
CREATE INDEX idx_speeches_proceeding_type ON speeches(proceeding_type);
CREATE INDEX idx_speeches_speaker_name ON speeches(speaker_name);
CREATE INDEX idx_speeches_session_name ON speeches(session_name);
CREATE INDEX idx_speeches_dedup_key ON speeches(dedup_key);
-- F09 adjacent-navigation: same-sitting neighbour lookup by sequence
CREATE INDEX idx_speeches_sitting ON speeches(source, date, sitting_number, sequence_within_sitting);
```

---

### 1.2 `qa_exchanges` (PostgreSQL)

Primary canonical store for starred and unstarred question records.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | Primary key; used as Meilisearch document ID and as the F09 detail-page route param. Stability identical to `speeches.id` (stable across incremental re-runs; reassigned only by a full clean reindex) |
| `source` | VARCHAR(2) | NOT NULL, CHECK IN ('LS','RS') | Source corpus (CA has no question hour) |
| `proceeding_type` | VARCHAR(30) | NOT NULL, CHECK IN ('starred_question','unstarred_question') | |
| `date` | DATE | NOT NULL | Date of sitting |
| `session_name` | VARCHAR(200) | NULL | Canonicalized session name |
| `session_number` | INTEGER | NULL | Official session number |
| `sitting_number` | INTEGER | NULL | Sitting number within session |
| `question_number` | INTEGER | NULL | Official question number |
| `subject` | TEXT | NULL | Question subject/title |
| `questioner_names` | TEXT[] | NOT NULL | Primary questioner + co-signatories; always an array; unstarred has exactly 1 element |
| `questioner_party` | VARCHAR(200) | NULL | Party affiliation of primary questioner |
| `minister_name` | VARCHAR(300) | NULL | Name of the minister who answered the question, extracted from the minister's response section (PRD v3.0 rule). **Never** set to question-preamble text (e.g. "Will the minister of [Ministry] be pleased to state…"). When the name is not identifiable from the response section, set to `"Minister of [Ministry]"` using the `ministry` value |
| `ministry` | VARCHAR(300) | NULL | Ministry responsible |
| `lok_sabha_number` | INTEGER | NULL | Lok Sabha term number (e.g. 17); extracted from source metadata at ingest. **LS only** — NULL for RS records |
| `sequence_within_sitting` | INTEGER | NULL | 1-based position within the sitting's proceedings, in document order. **Shared sequence space with `speeches`** for the same sitting (a Q+A exchange and a speech never share a number); powers F09 inline adjacent loading. **Not** part of the dedup key (see §1.4) |
| `full_text_en` | TEXT | NULL | Full exchange text (main Q + answer + supplementaries for starred; Q + written answer for unstarred) |
| `lang_original` | VARCHAR(5) | NOT NULL, CHECK IN ('en','hi','mixed') | Language of the original exchange before translation; same derivation as `speeches.lang_original` |
| `time_of_day` | VARCHAR(5) | NULL | Exchange start time as `HH:MM` (24-hour), stored verbatim; HTML sources only; NULL for IA pre-OCR text and PDF sources |
| `word_count` | INTEGER | NULL | Word count of `full_text_en`, computed at ingest; NULL when `full_text_en` is NULL |
| `is_translated` | BOOLEAN | NOT NULL DEFAULT FALSE | True if any portion is translated from Hindi |
| `has_untranslated_content` | BOOLEAN | NOT NULL DEFAULT FALSE | True if any portion could not be indexed |
| `source_url` | TEXT | NULL | Source-document citation URL (PRD v3.0 rules, ARCHITECTURE.md Non-Negotiable #9): **LS** → Internet Archive item URL (eparlib.sansad.in **not** used); **RS via Internet Archive or rsdebate.nic.in** → Internet Archive item URL; **RS via sansad.in HTML** → sansad.in page URL. **NULL** when no accessible URL can be derived (e.g. an item fetched via DSpace fallback that is absent from the IA mirror). The archive.org URL **is now the citation** for LS and RS-via-IA/rsdebate (reversal of the pre-v3.0 rule) |
| `page_reference` | INTEGER | NULL | Page number in source PDF; NULL for HTML and for IA pre-OCR text records |
| `canonical_doc_id` | TEXT | NULL | Identity of the `raw_documents` row this record was segmented from (the record's `source` is the matching `corpus`). Written by the Stage 2 indexer. Powers the F10 `GET /api/debug/raw/{id}` lookup. NULL only for rows written before the v3.0 re-ingestion. PostgreSQL-only — excluded from the Meilisearch document |
| `dedup_key` | VARCHAR(500) | UNIQUE NOT NULL | Compound deduplication key |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Ingestion timestamp |

**Indexes:**
```sql
CREATE INDEX idx_qa_source ON qa_exchanges(source);
CREATE INDEX idx_qa_date ON qa_exchanges(date);
CREATE INDEX idx_qa_proceeding_type ON qa_exchanges(proceeding_type);
CREATE INDEX idx_qa_questioner_names ON qa_exchanges USING GIN(questioner_names);
CREATE INDEX idx_qa_minister_name ON qa_exchanges(minister_name);
CREATE INDEX idx_qa_session_name ON qa_exchanges(session_name);
CREATE INDEX idx_qa_dedup_key ON qa_exchanges(dedup_key);
-- F09 adjacent-navigation: same-sitting neighbour lookup by sequence
CREATE INDEX idx_qa_sitting ON qa_exchanges(source, date, sitting_number, sequence_within_sitting);
```

---

### 1.3 `index_status` (PostgreSQL)

One row per completed ingestion run. The API reads the most recent row for the F07 status panel.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PK | Auto-increment |
| `run_completed_at` | TIMESTAMPTZ | NOT NULL | Ingestion run completion timestamp |
| `total_records` | INTEGER | NOT NULL | Sum of all three source counts |
| `ca_count` | INTEGER | NOT NULL DEFAULT 0 | Indexed CA records |
| `ca_date_from` | DATE | NULL | Earliest CA record date (NULL if ca_count = 0) |
| `ca_date_to` | DATE | NULL | Latest CA record date (NULL if ca_count = 0) |
| `ls_count` | INTEGER | NOT NULL DEFAULT 0 | Indexed LS records |
| `ls_date_from` | DATE | NULL | Earliest LS record date (NULL if ls_count = 0) |
| `ls_date_to` | DATE | NULL | Latest LS record date (NULL if ls_count = 0) |
| `rs_count` | INTEGER | NOT NULL DEFAULT 0 | Indexed RS records |
| `rs_date_from` | DATE | NULL | Earliest RS record date (NULL if rs_count = 0) |
| `rs_date_to` | DATE | NULL | Latest RS record date (NULL if rs_count = 0) |

**Query pattern (API):**
```sql
SELECT * FROM index_status ORDER BY run_completed_at DESC LIMIT 1;
```

---

### 1.4 `raw_documents` (PostgreSQL)

Intermediate raw document store. One row per source document per corpus (keyed on the composite `(canonical_doc_id, corpus)`). Written by Stage 1 (fetch + parse); read by Stage 2 (segment + index). Persists extracted text and document-level metadata, decoupling the scraping cost from segmentation and indexing.

**Primary key:** `PRIMARY KEY (canonical_doc_id, corpus)` — composite. The same `canonical_doc_id` value (e.g. a DSpace handle number shared by LS and RS IA providers) may appear as two independent rows, one per corpus. Dedup is scoped per corpus; a row fetched for LS does not suppress fetching the same id for RS.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `canonical_doc_id` | TEXT | NOT NULL (part of composite PK) | Provider-agnostic document identity. LS/RS: DSpace handle number `N` — Internet Archive `eparlib.nic.in.{N}` and DSpace `123456789/{N}` collapse to one row per corpus. CA: constitutionofindia.net day-page URL. Same key used by the SQLite checkpoint store and the cross-provider dedup logic |
| `corpus` | VARCHAR(2) | NOT NULL, CHECK IN ('CA','LS','RS') (part of composite PK) | Source corpus. Together with `canonical_doc_id`, forms the table primary key |
| `date` | DATE | NULL | Sitting date derived from document metadata or URL slug. NULL if unparseable at Stage 1 |
| `provider` | VARCHAR(50) | NOT NULL | Provider that satisfied the fetch (e.g. `coi_html`, `internet_archive`, `eparlib_dspace`, `rsdebate_dspace`, `sansad_rs_html`) |
| `format` | VARCHAR(20) | NOT NULL, CHECK IN ('html','ia_text','pdf','elibrary_text') | Source format: `html` (CA coi + recent RS sansad.in/rs), `ia_text` (IA pre-OCR `_djvu.txt`), `pdf` (direct DSpace embedded-text), `elibrary_text` (elibrary.sansad.in Tika-extracted PDF text) |
| `extracted_text` | TEXT | NULL | Post-parse, pre-segment raw text. NULL if the parser yielded no text (e.g. a text-less PDF — row is written to record the fetch; Stage 2 will produce zero records for it) |
| `metadata_json` | JSONB | NOT NULL DEFAULT '{}' | Document-level metadata at fetch time. Keys vary by provider: IA custom fields (`eparlib_title`, `eparlib_date`, `eparlib_lok_sabha_number`, etc.), DSpace item fields, HTML page metadata |
| `fetch_url` | TEXT | NULL | Actual URL from which content was downloaded (provider's download URL). Informational; not a citation |
| `citation_url` | TEXT | NULL | Canonical citation URL. Same value propagated to `source_url` on the derived `speeches`/`qa_exchanges` rows (PRD v3.0 rules): constitutionofindia.net day-page for CA; Internet Archive item URL for LS (any path) and for RS via IA/rsdebate; sansad.in page URL for RS via sansad.in HTML; NULL when no accessible URL can be derived |
| `fetched_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | Timestamp of Stage 1 write |

**Indexes:**
```sql
CREATE INDEX idx_raw_documents_corpus_date ON raw_documents(corpus, date);
```

Supports Stage 2 selective re-processing queries: `WHERE corpus = $1 AND date BETWEEN $2 AND $3`.

---

### 1.5 Deduplication Keys

Compound key format for each record type. Keys are stored in the `dedup_key` column and also in the local SQLite checkpoint store during ingestion.

**Speech:**
```
{source}_{date}_{sitting_number}_{proceeding_type}_{speaker_name_normalized}_{sequence_within_sitting}
```

**Q+A exchange:**
```
{source}_{date}_{sitting_number}_{proceeding_type}_{question_number}
```

`speaker_name_normalized`: lowercase, spaces replaced with `_`, special characters stripped. Applied before canonicalization to ensure consistency even when canonical name lookup fails.

**`sequence_within_sitting` is excluded from the Q+A dedup key** (PRD v2.0). The Q+A key stays `{source}_{date}_{sitting_number}_{proceeding_type}_{question_number}`. The speech key already includes `sequence_within_sitting`. Keeping `sequence_within_sitting` out of the Q+A key ensures a re-parse that shifts the shared sequence numbering does not create duplicate Q+A rows.

**`id` stability.** Because inserts use `ON CONFLICT (dedup_key) DO NOTHING`, a record's `id` is preserved across incremental re-runs (the existing row is left untouched). A **full clean reindex** truncates the tables (DEPLOYMENT §6.1) and therefore reassigns all `id`s — externally shared/bookmarked `/record/:id` URLs are stable only within the same canonical dataset, not across a full reingest.

**Two dedup layers.** The `dedup_key` above is the **record-level** guard (one row per unique speech / Q+A exchange), enforced by the PostgreSQL `UNIQUE` constraint and the SQLite `inserted_dedup_keys` mirror. It is distinct from **document-level** identity (`canonical_doc_id`, see §4.3), which prevents the same source document — available from more than one provider (e.g. Internet Archive `eparlib.nic.in.{N}` and DSpace `123456789/{N}`) — from being fetched and parsed twice. Document-level identity is a fetch-time optimisation in the checkpoint store; record-level `dedup_key` is the authoritative guarantee that no duplicate record is written.

---

## 2. Meilisearch Index

### 2.1 Index Name

`parliamentary_records`

### 2.2 Document Schema

Denormalized merge of `speeches` and `qa_exchanges` fields. `record_type` discriminates between the two. Fields not applicable to a record type are omitted (not sent as null) to minimize document size.

**`record_type` values:** `"speech"` for speech records (from `speeches` table); `"qa"` for Q+A exchange records (from `qa_exchanges` table). Set by `indexer.py` at push time.

**Speech document:**
```json
{
  "id": "uuid-from-postgresql",
  "record_type": "speech",

  "source": "CA | LS | RS",
  "proceeding_type": "debate | zero_hour | starred_question | ...",
  "date": "YYYY-MM-DD",
  "session_name": "Budget Session 2023",
  "sitting_number": 42,
  "subject": "Discussion on the Constitution (Amendment) Bill",
  "full_text_en": "Mr. President, I rise to speak on...",
  "lang_original": "en",
  "time_of_day": "14:35",
  "is_translated": false,
  "source_url": "https://sansad.in/...",

  "speaker_name": "Ambedkar, B.R.",
  "speaker_party": "Independent",
  "speaker_constituency_or_state": null,
  "speaker_role": "member",
  "sequence_within_sitting": 7,
  "speaker_name_unresolved": false,
  "volume": 3
}
```

Both record types carry `lang_original` and `time_of_day` (for the F05 result-card badge and time row).

**Q+A exchange document:** uses `"record_type": "qa"` and includes `question_number`, `questioner_names` (array), `questioner_party`, `minister_name`, `ministry`, **and `sequence_within_sitting`** (new in v2.0 — Q+A now carries it for correct chronological sort within the shared sitting sequence) in place of speech-specific fields (`speaker_name`, `speaker_party`, `speaker_constituency_or_state`, `speaker_role`, `speaker_name_unresolved`, `volume`). Like the speech doc, it also carries `lang_original` and `time_of_day`.

Fields excluded from Meilisearch (stored in PostgreSQL only, served by the F09 detail endpoint and the F10 debug endpoints): `word_count`, `page_reference`, `has_untranslated_content`, `session_number`, `created_at`, `dedup_key`, **`lok_sabha_number`**, **`segments`**, **`canonical_doc_id`**.

**v3.0 exclusion rationale:** `lok_sabha_number` is a detail-page-only display field (F09, LS records) — search result cards (F05) do not use it, no F03 filter targets it, and the detail page is served from PostgreSQL — so it is kept out of the Meilisearch document and is **not** a filterable attribute (§2.3). `segments` and `canonical_doc_id` are likewise PostgreSQL-only: `full_text_en` already carries the merged text for search, and `canonical_doc_id` only serves the debug-raw lookup. (If a future feature adds a Lok-Sabha-term filter or facet, `lok_sabha_number` would need to be added to the document and to `filterableAttributes`.)

### 2.3 Index Configuration

**searchableAttributes** (order determines field-level ranking weight in Meilisearch):
```json
["speaker_name", "minister_name", "ministry", "questioner_names", "subject", "full_text_en"]
```

**filterableAttributes:**
```json
["source", "proceeding_type", "date", "speaker_name", "session_name",
 "minister_name", "record_type", "subject"]
```

**sortableAttributes:**
```json
["date", "sequence_within_sitting"]
```

**rankingRules** (default order; no custom overrides):
```json
["sort", "words", "typo", "proximity", "attribute", "exactness"]
```

`sort` — first position so that chronological/reverse_chronological sort takes full effect; skipped entirely when no sort parameter is provided (relevance mode), so relevance ordering is unaffected.
`words` — records matching more original query terms rank higher.
`typo` — fewer typo corrections needed = higher rank (handles spell-correction weight).
`attribute` — matches in earlier searchableAttributes (speaker, minister, subject) rank above full_text matches.
`exactness` — exact-token matches rank above synonym-expanded matches.

**typoTolerance:**
```json
{
  "enabled": true,
  "minWordSizeForTypos": { "oneTypo": 5, "twoTypos": 9 },
  "disableOnAttributes": ["date", "source", "proceeding_type", "source_url"]
}
```

Meilisearch's built-in typo tolerance covers the PRD's spell-correction requirement (edit-distance and phonetic matching for proper nouns is approximated by typo tolerance; terms < 4 characters are covered by `minWordSizeForTypos.oneTypo: 5`).

**synonyms:** Loaded from `data/synonyms.json` via `ingest/setup_meilisearch.py`. Bidirectional entries in the JSON file map to bidirectional synonym pairs in Meilisearch. Phrase synonyms (multi-word entries) are supported by Meilisearch's synonyms API.

**pagination:**
```json
{ "maxTotalHits": 10000 }
```
Maps to the PRD's "10,000+" display threshold for result counts ≥ 10,000.

**Snippet / crop configuration (F05 — PRD v3.1):** Snippets are produced at search time by `api/services/search.py` via Meilisearch query-time parameters (not index settings). To satisfy the F05 ≥200-word snippet requirement:
```json
{
  "attributesToCrop": ["full_text_en"],
  "cropLength": 200,
  "cropMarker": "…",
  "attributesToHighlight": ["full_text_en", "subject", "speaker_name",
                            "minister_name", "questioner_names"],
  "highlightPreTag": "<mark>",
  "highlightPostTag": "</mark>"
}
```
- `cropLength` is measured in **words**; `200` yields a crop window of at least 200 words centred on the densest match passage (the `_formatted.full_text_en` field of each hit is the snippet source).
- When `full_text_en` contains fewer than `cropLength` words, Meilisearch returns the full text uncropped — satisfying the F05 "no truncation of content shorter than the minimum" rule.
- A match near the start/end of `full_text_en` yields a shorter crop window (still anchored on the match) — acceptable per F05.
- `search.py` strips all HTML except the `<mark>` highlight tags before returning `snippet` (DATA-MODELS §3.1).

**Debug-mode retrieval (F10 — PRD v3.0):** When `debug=1` is present on `POST /api/search`, `search.py` augments the Meilisearch query with score and full-document retrieval parameters so each hit carries its ranking score and complete index document:
```json
{
  "showRankingScore": true,
  "showRankingScoreDetails": true,
  "attributesToRetrieve": ["*"]
}
```
- `showRankingScore: true` surfaces `_rankingScore` on each hit; `showRankingScoreDetails: true` surfaces the per-rule `_rankingScoreDetails` breakdown — these are the Meilisearch mechanism that places `_rankingScore` / `_rankingScoreDetails` into each returned hit (they are search-request parameters, not index `filterableAttributes` or persistent settings).
- `attributesToRetrieve: ["*"]` disables any field masking so the "Document in index" debug section can show every field of the Meilisearch document.
- In normal (non-debug) mode none of these three parameters is sent, so scores are omitted and the standard document fields are returned. The index settings above are unchanged by debug mode.

### 2.4 Filter Expression Patterns

Built by `api/services/search.py` based on incoming filter state:

| Filter | Meilisearch filter expression |
|--------|------------------------------|
| Legislative body | `source IN ["LS", "RS"]` |
| Proceeding type | `proceeding_type IN ["debate", "starred_question"]` |
| Date from | `date >= "2020-01-01"` |
| Date to | `date <= "2022-12-31"` |
| Speaker substring | `speaker_name CONTAINS "Singh"` |
| Session substring | `session_name CONTAINS "Budget Session"` |
| Subject substring | `subject CONTAINS "Water"` |

Multiple active filters are joined with `AND`.

Session filter excludes CA records implicitly: CA records have `session_name` omitted from the document (not indexed), so `session_name CONTAINS "..."` will never match CA records.

### 2.5 Sort Parameters

| UI sort option | Meilisearch sort param |
|---------------|----------------------|
| Relevance (default) | `[]` (no explicit sort; ranking rules apply) |
| Chronological | `["date:asc", "sequence_within_sitting:asc"]` |
| Reverse chronological | `["date:desc", "sequence_within_sitting:desc"]` |

---

## 3. API Contracts

### 3.1 POST /api/search

**Request body:**
```json
{
  "query": "string",
  "filters": {
    "sources": ["CA", "LS", "RS"],
    "proceeding_types": ["debate", "starred_question", "unstarred_question",
                         "zero_hour", "short_notice_question", "calling_attention",
                         "short_duration_discussion", "adjournment_motion",
                         "private_member_bill"],
    "date_from": "YYYY-MM-DD",
    "date_to": "YYYY-MM-DD",
    "speaker": "string",
    "session": "string"
  },
  "sort": "relevance",
  "page": 1
}
```

Field rules:
- `query`: required; server truncates to 500 characters; after stop-word stripping if only stop words remain, return empty results with `validation_error: "query_only_stopwords"`
- `filters`: optional; omitting a field means no restriction on that dimension
- `sources`: omit = all three; empty array = validation error `sources_empty`
- `proceeding_types`: omit = all; empty array = validation error `proceeding_types_empty`
- `date_from`/`date_to`: both optional; if both present and `date_from > date_to` = validation error `date_range_invalid`
- `sort`: default `"relevance"`; enum: `"relevance"`, `"chronological"`, `"reverse_chronological"`
- `page`: integer ≥ 1; default 1

**Debug query parameter (F10):** `POST /api/search?debug=1` (also accepts `debug=true`). When present, the endpoint (a) adds the debug retrieval parameters to the Meilisearch query (§2.3 "Debug-mode retrieval"), so each result carries `_rankingScore`, `_rankingScoreDetails`, and the full index document; and (b) adds a top-level `debug` envelope to the response (below). When absent, the response is exactly as documented for normal mode (no `debug` key, no score fields). Debug mode is exempt from PERF-1 (NFR PERF-3) — the payload is large and unbounded by design.

**Response body (200 OK):**
```json
{
  "total": 1234,
  "total_display": "1,234",
  "page": 1,
  "total_pages": 62,
  "per_page": 20,
  "expansion_notice": ["Prime Minister", "Chief Minister"],
  "results": [
    {
      "id": "3f2a1b...",
      "record_type": "speech",
      "source": "LS",
      "proceeding_type": "debate",
      "proceeding_type_label": "Debate",
      "date": "2023-03-15",
      "date_display": "15 March 2023",
      "session_name": "Budget Session 2023",
      "subject": "General Discussion on the Union Budget",
      "snippet": "The Finance Minister stated that <mark>PM</mark> infrastructure...",
      "snippet_from_supplementary": false,
      "lang_original": "en",
      "time_of_day": "14:35",
      "is_translated": false,
      "source_url": "https://sansad.in/...",
      "speaker_name": "Jairam Ramesh",
      "speaker_party": "INC",
      "speaker_constituency_or_state": null,
      "speaker_name_unresolved": false,
      "question_number": null,
      "questioner_names": null,
      "questioner_party": null,
      "minister_name": null,
      "ministry": null
    }
  ]
}
```

`total_display`: `"10,000+"` when `total >= 10000`; otherwise comma-formatted integer string.
`expansion_notice`: array of expanded term strings for the "Also searching for:" UI notice. Empty array if no expansion occurred.
`snippet`: HTML-safe string; matched terms wrapped in `<mark>` tags. All other HTML stripped.
`snippet_from_supplementary`: `true` only for Q+A records where the best-match passage is from a supplementary exchange.
`lang_original`: `"en" | "hi" | "mixed"` — drives the F05 card badge (`hi`→"Hindi original", `mixed`→"Mixed language", `en`→no badge).
`time_of_day`: `"HH:MM"` or `null` — F05 cards render it verbatim near the date; omit silently when null.

**Debug envelope (200 OK, only when `?debug=1`):** two additions to the response —

1. **Per-result score fields.** Each object in `results` additionally carries `_rankingScore` (float 0.0–1.0) and `_rankingScoreDetails` (per-rule object: `words`, `typo`, `proximity`, `attribute`, `exactness`, plus any configured rule), passed through verbatim from the Meilisearch hit. The full Meilisearch index document for the hit is also returned unmasked (drives the per-result "Document in index" debug section). When Meilisearch returns no `_rankingScoreDetails` (unsupported), the field is absent and the UI shows whatever score fields are present (F10 edge case).

2. **Top-level `debug` envelope** (siblings of `total`, `results`, …):
```json
{
  "debug": {
    "processed_query": "prime minister OR PM OR chief minister",
    "meilisearch_request": {
      "method": "POST",
      "url": "https://xxx.meilisearch.io/indexes/parliamentary_records/search",
      "body": { "q": "...", "filter": "...", "sort": [], "offset": 0, "limit": 20,
                "attributesToCrop": ["full_text_en"], "cropLength": 200,
                "showRankingScore": true, "showRankingScoreDetails": true,
                "attributesToRetrieve": ["*"] }
    },
    "meilisearch_response": { "...full Meilisearch response body as received by the backend..." }
  }
}
```
- `processed_query`: the query string after synonym expansion, stop-word stripping, and phrase detection — exactly as submitted to Meilisearch (powers the global "Processed query" panel section).
- `meilisearch_request`: the HTTP request the backend issued to Meilisearch — `method`, `url`, and `body` (the global "Meilisearch request" section).
- `meilisearch_response`: the complete, unmodified Meilisearch response body the backend received (the global "Meilisearch response" section).
- The global panel's "API request" and "API response" sections are **not** in this envelope — the frontend constructs them from its own `fetch` to `/api/search` (the "API response" section displays this entire response body, debug envelope included).
- The `debug` key is absent entirely in normal mode.

**Validation error response (400):**
```json
{
  "error": "validation_error",
  "code": "sources_empty | proceeding_types_empty | date_range_invalid | query_too_short | query_only_stopwords",
  "message": "human-readable description"
}
```

**Backend error response (503):**
```json
{
  "error": "search_unavailable",
  "message": "Search is temporarily unavailable."
}
```

---

### 3.2 GET /api/status

No request parameters.

Single endpoint serving both F07 surfaces (per PRD v1.1). The **homepage status strip** (condensed) renders per-source `count` and `last_updated` only. The **full indexing status panel** (`IndexingStatusPage.jsx`, reached via the Results page footer link) renders `total_records`, per-source `count`, per-source `date_from`/`date_to`, and `last_updated`. No additional fields or endpoint are required to support the full panel — it consumes the same response below.

**Response body (200 OK — index populated):**
```json
{
  "status": "ok",
  "total_records": 350000,
  "sources": {
    "ca": { "count": 8200, "date_from": "1946-12-09", "date_to": "1950-11-26" },
    "ls": { "count": 198000, "date_from": "2014-06-04", "date_to": "2026-05-15" },
    "rs": { "count": 143800, "date_from": "2014-06-11", "date_to": "2026-04-20" }
  },
  "last_updated": "2026-05-15T14:30:00Z"
}
```

**Response body (200 OK — ingestion never run):**
```json
{
  "status": "ok",
  "total_records": 0,
  "sources": {
    "ca": { "count": 0, "date_from": null, "date_to": null },
    "ls": { "count": 0, "date_from": null, "date_to": null },
    "rs": { "count": 0, "date_from": null, "date_to": null }
  },
  "last_updated": null
}
```

**Response body (200 OK — `index_status` table unreadable or malformed):**
```json
{ "status": "unavailable" }
```

---

### 3.3 GET /api/record/{id}

F09 detail page. Served from **PostgreSQL** (not Meilisearch). Single record fetched by `id` from `speeches` UNION ALL `qa_exchanges`; adjacent neighbours resolved over the same sitting.

**Path parameter:** `id` — the record UUID (the `id` column / Meilisearch document id).

**Response body (200 OK):**

All fields the F09 spec displays. Speech-only and Q+A-only fields are `null` (or omitted) for the other record type. `null`/not-applicable fields are rendered as silently omitted by the client.

```json
{
  "id": "3f2a1b...",
  "record_type": "speech | qa",
  "source": "LS",
  "lok_sabha_number": 17,
  "proceeding_type": "debate",
  "proceeding_type_label": "Debate",
  "date": "2023-03-15",
  "date_display": "15 March 2023",
  "time_of_day": "14:35",
  "session_name": "Budget Session 2023",
  "session_number": 7,
  "sitting_number": 42,
  "volume": null,
  "subject": "General Discussion on the Union Budget",
  "full_text_en": "Mr. Speaker, I rise to speak on...",
  "lang_original": "en",
  "is_translated": false,
  "has_untranslated_content": false,
  "page_reference": null,
  "word_count": 1820,
  "source_url": "https://eparlib.sansad.in/...",

  "speaker_name": "Jairam Ramesh",
  "speaker_role": "member",
  "speaker_party": "INC",
  "speaker_constituency_or_state": null,
  "speaker_name_unresolved": false,

  "question_number": null,
  "questioner_names": null,
  "questioner_party": null,
  "minister_name": null,
  "ministry": null,

  "sequence_within_sitting": 7,
  "sitting_total": 58,
  "has_prev": true,
  "has_next": true
}
```

Field rules:
- `record_type`: `"speech"` (from `speeches`) or `"qa"` (from `qa_exchanges`).
- `lok_sabha_number`: integer for **LS** records; `null` for RS and CA. F09 renders it as "[N]th/st/nd/rd Lok Sabha" (ordinal suffix computed client-side); omitted from display when null.
- `proceeding_type_label`, `date_display`: server-formatted display strings (same conventions as `/api/search`).
- Speech-type records populate the speaker block and `volume`; Q+A-type records populate `question_number`, `questioner_names`, `questioner_party`, `minister_name`, `ministry`. The non-applicable group is `null`.
- `sitting_total`: count of all records (speeches + Q+A) in the same sitting — supports the "[N] of [total]" display; `sequence_within_sitting` is `N`.
- `has_prev`: `true` when at least one record in the same sitting has a lower `sequence_within_sitting` than this record (a "Load 5 previous" batch is available); `false` at the lower boundary. Drives the **initial** enabled/disabled state of the "Load 5 previous" control (disabled, not hidden, when false).
- `has_next`: `true` when at least one record in the same sitting has a higher `sequence_within_sitting`; `false` at the upper boundary. Drives the initial state of the "Load 5 next" control.
- When both `has_prev` and `has_next` are `false`, the sitting contains only this record and both controls are disabled (F09 single-record edge case).
- Same sitting = same `source` + `date` + `sitting_number` (`IS NOT DISTINCT FROM`, so CA records with `NULL sitting_number` group by `source`+`date`). The shared sequence space spans **both** tables.
- **Replaces the pre-v3.0 `adjacent.{prev_id,next_id}` object** (single-record Prev/Next navigation, removed in F09 v3.0). Actual neighbour records are fetched by `GET /api/record/{id}/adjacent` (§3.4), not embedded here.

**Not-found response (404):**
```json
{ "error": "not_found", "message": "Record not found." }
```
Returned when no row in either table has the given `id`. The client renders a "Record not found" page (no blank page, no JS error).

---

### 3.4 GET /api/record/{id}/adjacent

F09 inline adjacent loading ("Load 5 previous" / "Load 5 next"). Returns up to `limit` records from the **focal record's sitting**, strictly beyond a given sequence position in one direction. Served from **PostgreSQL** (same store and sitting definition as §3.3). Not subject to PERF-2 (NFR PERF-2 clarification — adjacent batch loads are excluded from the detail-page SLA).

**Path parameter:** `id` — the focal record UUID. Used only to resolve the sitting identity (`source` + `date` + `sitting_number`); the focal record itself is never included in the response.

**Query parameters:**
| Param | Required | Description |
|-------|----------|-------------|
| `direction` | Required | `prev` or `next`. `prev` = records with **lower** `sequence_within_sitting`; `next` = records with **higher** |
| `from_seq` | Required | Integer, exclusive boundary. Records are returned strictly below (`prev`) or above (`next`) this sequence value. First click passes the focal record's own `sequence_within_sitting`; each subsequent click passes the lowest-loaded seq (`prev`) or highest-loaded seq (`next`) currently on screen |
| `limit` | Optional | Max records to return; default `5`, max `5` |

**Query semantics (PostgreSQL):**
- `prev`: `WHERE <same sitting> AND sequence_within_sitting < from_seq ORDER BY sequence_within_sitting DESC LIMIT limit` — the `limit` records immediately below `from_seq`.
- `next`: `WHERE <same sitting> AND sequence_within_sitting > from_seq ORDER BY sequence_within_sitting ASC LIMIT limit` — the `limit` records immediately above `from_seq`.
- Neighbours are drawn from **both** `speeches` and `qa_exchanges` (UNION ALL), ordered by the shared `sequence_within_sitting`. Same-sitting grouping uses `IS NOT DISTINCT FROM` on `sitting_number` (handles CA `NULL`).
- Served by `idx_speeches_sitting` / `idx_qa_sitting` (§1.1/§1.2).

**Response body (200 OK):**
```json
{
  "direction": "next",
  "records": [
    {
      "id": "a4e8...",
      "record_type": "speech | qa",
      "source": "LS",
      "lok_sabha_number": 17,
      "proceeding_type": "debate",
      "proceeding_type_label": "Debate",
      "date": "2023-03-15",
      "date_display": "15 March 2023",
      "time_of_day": "14:40",
      "session_name": "Budget Session 2023",
      "session_number": 7,
      "sitting_number": 42,
      "volume": null,
      "subject": "General Discussion on the Union Budget",
      "full_text_en": "Mr. Speaker, continuing on the point...",
      "lang_original": "en",
      "is_translated": false,
      "has_untranslated_content": false,
      "page_reference": null,
      "word_count": 540,
      "source_url": "https://archive.org/details/eparlib.nic.in.123456",
      "speaker_name": "Jairam Ramesh",
      "speaker_role": "member",
      "speaker_party": "INC",
      "speaker_constituency_or_state": null,
      "speaker_name_unresolved": false,
      "question_number": null,
      "questioner_names": null,
      "questioner_party": null,
      "minister_name": null,
      "ministry": null,
      "sequence_within_sitting": 8
    }
  ],
  "has_more": true
}
```

Field rules:
- `records`: **always returned in ascending `sequence_within_sitting` order**, regardless of `direction`, so the client renders them top-to-bottom in document order. For `prev`, the backend fetches `DESC` then reverses to ascending before returning. Each record carries the same fields as the §3.3 detail record **except** the sitting-context fields (`sitting_total`, `has_prev`, `has_next`) — F09 requires speaker/questioner/minister, date, subject, proceeding type, and full text per loaded record; the full field set is returned for rendering parity with the focal record.
- `records` is `[]` when no records exist beyond `from_seq` in `direction` (e.g. `from_seq` already at the boundary). With the `has_prev`/`has_next` gating from §3.3 this should not normally be reached, but an empty array is the defined response.
- `has_more`: `true` when at least one further record exists beyond the returned batch in `direction` (i.e. beyond `min`/`max` returned `sequence_within_sitting`); `false` when the batch reached the sitting boundary. The client uses it to keep the load control enabled (`true`) or disable it (`false`) after the batch. When fewer than `limit` records are returned, `has_more` is `false`.

**Not-found response (404):**
```json
{ "error": "not_found", "message": "Record not found." }
```
Returned when no record with the given focal `id` exists (cannot resolve a sitting). The client treats this the same as a failed adjacent load (F09 edge case: show an error in place of the loaded records; the control returns to its pre-click enabled state).

**Validation error (400):** `direction` not in `{prev,next}`, or `from_seq` not an integer → `{ "error": "validation_error", "message": "..." }`.

---

### 3.5 GET /api/debug/processed/{id}

F10 "Processed record" section (lazy fetch). Returns the **complete** PostgreSQL row from `speeches` or `qa_exchanges` for the given record `id` — every column, including `segments` (JSONB), `canonical_doc_id`, `dedup_key`, `word_count`, `has_untranslated_content`, `created_at`, and all other columns not exposed by `/api/search` or `/api/record/{id}`. No authentication (NFR SEC-1 — deliberate v1 choice, debug-only). Exempt from PERF-1/PERF-2 (PERF-3).

**Path parameter:** `id` — the record UUID.

**Response body (200 OK):**
```json
{
  "table": "speeches",
  "row": {
    "id": "3f2a1b...",
    "source": "LS",
    "proceeding_type": "debate",
    "...": "every column of the matched speeches / qa_exchanges row, verbatim",
    "segments": [
      { "text": "Mr. Speaker, I rise to speak on...", "segment_index": 0 },
      { "text": "Continuing on the point of order...", "segment_index": 1 }
    ],
    "canonical_doc_id": "123456",
    "created_at": "2026-05-15T14:30:00Z"
  }
}
```
- `table`: `"speeches"` or `"qa_exchanges"` — which table the row came from (the row is looked up as `speeches WHERE id` then `qa_exchanges WHERE id`).
- `row`: the full row as a JSON object; column names map 1:1 to §1.1 / §1.2. JSONB columns (`segments`) are returned as nested JSON; `DATE`/`TIMESTAMPTZ` as ISO strings; arrays (`questioner_names`) as JSON arrays.
- No field masking — this is the diagnostic surface (SEC-1).

**Not-found response (404):**
```json
{ "error": "not_found", "message": "Record not found." }
```
Returned when no row in either table has the given `id`. The UI shows an error message in the "Processed record" section (not blank, no crash) per F10 acceptance criteria.

---

### 3.6 GET /api/debug/raw/{id}

F10 "Raw document" section (lazy fetch). Returns the **complete** `raw_documents` row from which the record with the given `id` was processed — including the full `extracted_text` and `metadata_json`. No authentication (SEC-1). Exempt from PERF-1/PERF-2 (PERF-3).

**Path parameter:** `id` — the **processed** record UUID (from `speeches`/`qa_exchanges`), not a `raw_documents` key.

**Resolution:**
1. Look up the processed record by `id` (`speeches` then `qa_exchanges`) to obtain its `canonical_doc_id` and `source`.
2. Fetch `raw_documents WHERE canonical_doc_id = <record.canonical_doc_id> AND corpus = <record.source>` (the composite PK, §1.4).

**Response body (200 OK):**
```json
{
  "row": {
    "canonical_doc_id": "123456",
    "corpus": "LS",
    "date": "2023-03-15",
    "provider": "internet_archive",
    "format": "ia_text",
    "extracted_text": "...full pre-segment raw text of the entire sitting document...",
    "metadata_json": { "eparlib_title": "...", "eparlib_lok_sabha_number": "17", "...": "..." },
    "fetch_url": "https://archive.org/download/eparlib.nic.in.123456/...",
    "citation_url": "https://archive.org/details/eparlib.nic.in.123456",
    "fetched_at": "2026-05-10T09:12:00Z"
  }
}
```
- `row`: the full `raw_documents` row; columns map 1:1 to §1.4. `extracted_text` is returned in full with no truncation (F10 edge case: the UI scrolls within the section).

**Not-found response (404):**
```json
{ "error": "not_found", "message": "Raw document not available." }
```
Returned when **either** no processed record has the given `id`, **or** the processed record exists but has `canonical_doc_id = NULL` or no matching `raw_documents` row (e.g. the raw document was deleted after processing — F10 edge case). The UI shows "Raw document not available" in the section.

---

## 4. Storage

### 4.1 PostgreSQL (Railway managed)

**Purpose:** Primary canonical record store.

**Estimated corpus size:**
- ~300K–400K total records (250K+ unstarred Q+A, ~15K starred Q+A, ~35K debate speeches, ~20K other proceeding types, ~8K CA speeches)
- Average record size: 3–5 KB (text + metadata)
- Estimated data size: 1–2 GB
- With indexes: 2–3 GB total

Railway Starter plan (512 MB) is insufficient. Pro plan (scalable) required.

**Tables:** `speeches`, `qa_exchanges`, `raw_documents`, `index_status`

### 4.2 Meilisearch Cloud

**Purpose:** Derived search index. Derived from PostgreSQL; rebuilt from PostgreSQL on schema changes.

**Index:** `parliamentary_records` (single index, all record types)

**Estimated index size:**
- ~350K documents × ~5 KB average document = ~1.75 GB raw documents
- Meilisearch storage overhead (inverted index, position data): typically 3–5× raw document size
- Estimated total: 5–9 GB

Meilisearch Cloud Growth plan (supports up to 2M documents) is required.

### 4.3 Local SQLite (ingestion only, not deployed)

**File:** `data/ingestion_checkpoints.db` (`.gitignore`d)

**Tables:**
- `processed_documents (canonical_doc_id TEXT NOT NULL, corpus TEXT NOT NULL, provider TEXT, fetch_url TEXT, processed_at TIMESTAMP, PRIMARY KEY (canonical_doc_id, corpus))` — **Stage 2 complete signal.** Tracks source documents whose `raw_documents` row has been fully segmented, canonicalized, and written to `speeches`/`qa_exchanges`. Keyed on `(canonical_doc_id, corpus)` — composite key matching the `raw_documents` PK. Corpus scoping is required so that LS Stage 2 processing of handle N does not suppress RS Stage 2 processing of the same handle N when `--source all` runs sequentially. Written by Stage 2 after all records from a raw document are persisted. Guards Stage 2 resumability — if Stage 2 is interrupted, re-running it will skip documents already in this table. **Does not** guard against cross-provider double-fetch: Stage 1 dedup is handled by the `raw_documents` PK lookup in PostgreSQL.
- `inserted_dedup_keys (dedup_key TEXT PRIMARY KEY)` — tracks record-level dedup keys already written to PostgreSQL; prevents duplicate inserts on Stage 2 resume. Unchanged; mirrors the PostgreSQL `dedup_key` UNIQUE constraint for fast local lookup without a round-trip to PostgreSQL.

**Purpose:** Fast local lookups during Stage 2 for resumability and record-level deduplication. The `processed_documents` table must be partially cleared (for the re-processing scope) before a selective Stage 2 re-run (DEPLOYMENT §6.4). Eliminated along with `raw_documents` on a full clean reindex.

### 4.4 Browser Cookies (client-side only)

**Purpose:** F08 recent searches and saved searches.

Two separate cookies:
- `ss_recent`: JSON array of `{ query: string, timestamp: number }`, max 10 entries, 30-day expiry
- `ss_saved`: JSON array of `{ id: string, name: string, query: string, filters: FilterState, timestamp: number }`, max 20 entries, no expiry

`FilterState` shape:
```json
{
  "sources": ["CA", "LS", "RS"],
  "proceeding_types": ["debate", "starred_question", ...],
  "date_from": "YYYY-MM-DD | null",
  "date_to": "YYYY-MM-DD | null",
  "speaker": "string | null",
  "session": "string | null"
}
```

Combined cookie size must not exceed 4 KB. Near-capacity handling: trim oldest `ss_recent` entries first; never auto-remove `ss_saved` entries.
