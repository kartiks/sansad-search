# Non-Functional Requirements

## Performance

**PERF-1: Search response time**
Search results must be returned within 2 seconds at p95, measured from query submission to full result list rendered in the browser, across the full indexed corpus. This target applies with query expansion active (synonyms + spell corrections). Architecture must account for the additional scoring computation introduced by query expansion.

**PERF-2: Detail page response time**
The detail page must complete full page load — including the record fetch and the adjacent-neighbour fetch — within 500ms at p95.

**PERF-4: Snippet size bound**
The search API `snippet_size` parameter is bounded to 20–1000 words; numeric values outside this range are clamped to the nearest bound, and missing/non-integer/non-numeric values fall back to the default. The default is 100 words and is operator-configurable as a deployment setting. The maximum bound exists to keep search response payloads within the PERF-1 ≤2s p95 target; PERF-1 must hold at `snippet_size=1000` across the full indexed corpus.

## Reliability

**INF-R1: Ingestion resumability**
The bulk ingestion pipeline must be resumable from a per-document checkpoint. An interrupted run re-run against the same corpus must produce an identical final record count with no duplicates. Safe re-runs are a hard requirement, not a best-effort goal.

## Security

**SEC-1: Debug mode data exposure**
Debug mode (`?debug=1`) exposes full database records (speeches, qa_exchanges, raw_documents rows), internal query details, and Meilisearch request/response payloads via unauthenticated endpoints (`GET /api/debug/processed/{id}` and `GET /api/debug/raw/{id}`). This is a deliberate choice for v1. Any deployment handling sensitive or access-controlled parliamentary data must review whether unauthenticated debug access is acceptable before enabling this feature in production.

## Storage

**INF-S1: Corpus storage sizing**
The full-text corpus (CA full record + 12 years of LS/RS debates and questions) is large. Storage architecture must be sized accordingly before build begins. Exact sizing is an architecture-stage deliverable.

## Rate Limiting and Compliance

**INF-RL1: Government website rate limiting**
The ingestion pipeline must comply with robots.txt on constitutionofindia.net, elibrary.sansad.in, and the Internet Archive. Minimum inter-request delay must be specified at architecture stage. HTTP 429 responses must trigger exponential backoff and retry, not a skip.

## Processing

**INF-P1: Bulk ingestion duration**
Bulk ingestion is a long-running operation. No maximum time constraint is specified for v1, but real-time progress logging is required. The operation must not require human supervision to complete.

## Scalability

**SCALE-1: Concurrent search load**
Search must remain within the PERF-1 response time target under concurrent user load. Exact concurrency targets are an architecture-stage deliverable.

## Debug Mode Performance

**PERF-3: Debug mode SLA exemption**
PERF-1 and PERF-2 response time targets do not apply when debug mode is active (`?debug=1`). Debug mode responses include large additional payloads — full Meilisearch documents, full database rows, and complete raw source documents — and are exempt from all response time SLAs.

## Privacy

**PRIV-1: No server-side storage of user search data**
Search queries, filter selections, and search history are not persisted server-side in v1. All search history (recent searches and saved searches) is stored client-side in browser cookies only. No user identifiers are created or stored.
