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
| Lok Sabha debates and questions | Internet Archive eparlib mirror (to Aug 2018) · elibrary.sansad.in "Lok Sabha Debates (Text)" (2019 onward) |
| Rajya Sabha debates and questions | Internet Archive rsdebate mirror (1952 – Dec 2009) — later data not yet available |

## Setup and Run

See [`docs/DEPLOYMENT.md §5`](docs/DEPLOYMENT.md) for full local development setup (Python env, Node, PostgreSQL, Meilisearch, env vars, and running ingestion).

## Documentation

Product requirements, architecture, data models, deployment runbooks and the UI spec live in [`docs/`](docs/).
