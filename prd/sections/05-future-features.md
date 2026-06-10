# Future Features

Features explicitly deferred from v1. Not in scope for any v1 build phase.

## Data Scope Expansion

- **Full parliamentary history:** extend LS coverage back to 1952 across all accessible sources; restore RS post-2018 coverage when an accessible source is identified; extend RS coverage to include all available historical records
- **Ongoing ingestion:** scheduled pipeline to ingest new parliamentary sessions automatically as they are published on sansad.in and rajyasabha.gov.in

## Language Support

- **Hindi search:** index Hindi-language text and support queries in Hindi (Devanagari); requires separate tokenisation, stop-word lists, and synonym dictionary

## User Accounts and Personalisation

- **User authentication:** sign-in with persistent cross-device search history and saved searches
- **Cross-device sync:** saved searches accessible from any device when signed in (replaces cookie-only storage)
- **Search alerts:** notify users (email or in-app) when new records matching a saved search are indexed

## Search Experience

- **Autocomplete / search-as-you-type:** show query suggestions and speaker name completions as the user types in the search box
- **Faceted result counts:** show the count of results per filter value (e.g., "Lok Sabha (1,234), Rajya Sabha (567)") in the filter panel
- **Related results / "More like this":** surface records thematically similar to a result the user is viewing
- **Member profile pages:** dedicated page per member showing all their indexed speeches and questions

## Platform

- **Mobile UI:** responsive layout optimised for small screens; the web application is currently desktop-only
- **Public API:** REST or GraphQL API exposing search and record retrieval for third-party integrations

## Administration

- **Admin interface for synonym dictionary:** in-application UI for adding and editing query expansion synonyms without requiring a code deployment
- **Ingestion monitoring dashboard:** real-time visibility into ingestion pipeline progress and error rates for operators
