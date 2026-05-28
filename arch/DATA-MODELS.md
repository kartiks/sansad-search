# Data Models — SansadSearch

**PRD version:** v1.0
**Generated:** 2026-05-28

---

## 1. Core Entities

### 1.1 `speeches` (PostgreSQL)

Primary canonical store for all speech-type records (debates, zero hour, calling attention, etc.).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | Primary key; used as Meilisearch document ID |
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
| `is_translated` | BOOLEAN | NOT NULL DEFAULT FALSE | True if any portion is official English translation of Hindi |
| `has_untranslated_content` | BOOLEAN | NOT NULL DEFAULT FALSE | True if Hindi portions could not be indexed |
| `speaker_name_unresolved` | BOOLEAN | NOT NULL DEFAULT FALSE | True if speaker_name could not be matched to names_dict |
| `source_url` | TEXT | NULL | URL of original HTML page or PDF |
| `page_reference` | INTEGER | NULL | Page number in source PDF; NULL for HTML |
| `volume` | INTEGER | NULL | CA volume number (1–12); NULL for LS/RS |
| `ocr_low_confidence` | BOOLEAN | NOT NULL DEFAULT FALSE | True if text was OCR-extracted with low confidence |
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
```

---

### 1.2 `qa_exchanges` (PostgreSQL)

Primary canonical store for starred and unstarred question records.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | Primary key; used as Meilisearch document ID |
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
| `minister_name` | VARCHAR(300) | NULL | Minister answering |
| `ministry` | VARCHAR(300) | NULL | Ministry responsible |
| `full_text_en` | TEXT | NULL | Full exchange text (main Q + answer + supplementaries for starred; Q + written answer for unstarred) |
| `is_translated` | BOOLEAN | NOT NULL DEFAULT FALSE | True if any portion is translated from Hindi |
| `has_untranslated_content` | BOOLEAN | NOT NULL DEFAULT FALSE | True if any portion could not be indexed |
| `source_url` | TEXT | NULL | URL of original document |
| `page_reference` | INTEGER | NULL | Page number in source PDF; NULL for HTML |
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

### 1.4 Deduplication Keys

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

---

## 2. Meilisearch Index

### 2.1 Index Name

`parliamentary_records`

### 2.2 Document Schema

Denormalized merge of `speeches` and `qa_exchanges` fields. `record_type` discriminates between the two. Fields not applicable to a record type are omitted (not sent as null) to minimize document size.

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

Q+A exchange documents include `question_number`, `questioner_names` (array), `questioner_party`, `minister_name`, `ministry` in place of speech-specific fields.

Fields excluded from Meilisearch (stored in PostgreSQL only): `page_reference`, `ocr_low_confidence`, `has_untranslated_content`, `session_number`, `created_at`, `dedup_key`.

### 2.3 Index Configuration

**searchableAttributes** (order determines field-level ranking weight in Meilisearch):
```json
["speaker_name", "minister_name", "ministry", "questioner_names", "subject", "full_text_en"]
```

**filterableAttributes:**
```json
["source", "proceeding_type", "date", "speaker_name", "session_name",
 "minister_name", "record_type"]
```

**sortableAttributes:**
```json
["date", "sequence_within_sitting"]
```

**rankingRules** (default order; no custom overrides):
```json
["words", "typos", "proximity", "attribute", "sort", "exactness"]
```

`words` — records matching more original query terms rank higher.
`typos` — fewer typo corrections needed = higher rank (handles spell-correction weight).
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

## 4. Storage

### 4.1 PostgreSQL (Railway managed)

**Purpose:** Primary canonical record store.

**Estimated corpus size:**
- ~300K–400K total records (250K+ unstarred Q+A, ~15K starred Q+A, ~35K debate speeches, ~20K other proceeding types, ~8K CA speeches)
- Average record size: 3–5 KB (text + metadata)
- Estimated data size: 1–2 GB
- With indexes: 2–3 GB total

Railway Starter plan (512 MB) is insufficient. Pro plan (scalable) required.

**Tables:** `speeches`, `qa_exchanges`, `index_status`

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
- `processed_urls (url TEXT PRIMARY KEY, processed_at TIMESTAMP)` — tracks source document URLs fully processed in a prior run
- `inserted_dedup_keys (dedup_key TEXT PRIMARY KEY)` — tracks dedup keys already written to PostgreSQL; prevents duplicate inserts on resume

**Purpose:** Fast local lookups during ingestion for resumability and deduplication. Eliminated after a clean full run completes; can be deleted and rebuilt from scratch if a full re-run is needed.

### 4.4 Browser Cookies (client-side only)

**Purpose:** F08 recent searches and saved searches.

Two separate cookies:
- `ss_recent`: JSON array of `{ query: string, timestamp: ISO8601 }`, max 10 entries, 30-day expiry
- `ss_saved`: JSON array of `{ name: string, query: string, filters: FilterState, saved_at: ISO8601 }`, max 20 entries, no expiry

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
