# Non-Functional Requirements

## Performance

**PERF-1: Search response time**
Search results must be returned within 2 seconds at p95, measured from query submission to full result list rendered in the browser, across the full indexed corpus. This target applies with query expansion active (synonyms + spell corrections). Architecture must account for the additional scoring computation introduced by query expansion.

## Reliability

**INF-R1: Ingestion resumability**
The bulk ingestion pipeline must be resumable from a per-document checkpoint. An interrupted run re-run against the same corpus must produce an identical final record count with no duplicates. Safe re-runs are a hard requirement, not a best-effort goal.

## Security

*To be populated as features are specced.*

## Storage

**INF-S1: Corpus storage sizing**
The full-text corpus (CA full record + 12 years of LS/RS debates and questions) is large. Storage architecture must be sized accordingly before build begins. Exact sizing is an architecture-stage deliverable.

## Rate Limiting and Compliance

**INF-RL1: Government website rate limiting**
The ingestion pipeline must comply with robots.txt on constitutionofindia.net, eparlib.sansad.in, sansad.in, rsdebate.nic.in, and the Internet Archive. Minimum inter-request delay must be specified at architecture stage. HTTP 429 responses must trigger exponential backoff and retry, not a skip.

## Processing

**INF-P1: Bulk ingestion duration**
Bulk ingestion is a long-running operation. No maximum time constraint is specified for v1, but real-time progress logging is required. The operation must not require human supervision to complete.

## Scalability

**SCALE-1: Concurrent search load**
Search must remain within the PERF-1 response time target under concurrent user load. Exact concurrency targets are an architecture-stage deliverable.

## Privacy

**PRIV-1: No server-side storage of user search data**
Search queries, filter selections, and search history are not persisted server-side in v1. All search history (recent searches and saved searches) is stored client-side in browser cookies only. No user identifiers are created or stored.
