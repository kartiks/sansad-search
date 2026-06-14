# SansadSearch

Full-text search over Indian parliamentary and constituent assembly debates.

## Description

SansadSearch indexes the complete proceedings of the Constituent Assembly of India, Lok Sabha, and Rajya Sabha, enabling users to search the Indian legislative record by keyword, speaker, date range, legislative body, and session type. Results display in context with links back to the original source documents.

## Primary Users

- Researchers and academics studying Indian legislative history and constitutional development
- Journalists and analysts covering Indian politics and governance
- Lawyers and legal professionals researching legislative intent
- Students and educators
- Engaged citizens tracking parliamentary debates and questions

## Key Features

- Full-text search over Constituent Assembly, Lok Sabha, and Rajya Sabha records
- Advanced filters: date range, legislative body, speaker, session type (debates, starred questions, unstarred questions, zero hour, etc.)
- Query expansion with synonym support and spell correction for broader, well-ranked results
- Contextual result display with source snippets and links to original documents
- Sort by relevance, chronological, or reverse chronological order
- Indexing status panel showing total records indexed and latest date covered

## Data Sources

| Source | URL |
|--------|-----|
| Constituent Assembly debates | constitutionofindia.net (HTML) |
| Lok Sabha debates and questions | Internet Archive (archive.org) · eparlib.sansad.in (DSpace 7 fallback, 2019+) |
| Rajya Sabha debates and questions | Internet Archive (archive.org) — post-2018 data not available |

## Setup and Run

See [`arch/DEPLOYMENT.md §5`](arch/DEPLOYMENT.md) for full local development setup (Python env, Node, PostgreSQL, Meilisearch, env vars, and running ingestion).

## Development

This project is built using the PhaseCraft agentic development framework. See `TRACKER.md` for current lifecycle status and `PHASES.md` (added after `/plan`) for the implementation roadmap.
