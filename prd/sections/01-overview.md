# Overview

## Product

SansadSearch is a web-based full-text search application over Indian parliamentary records. It enables users to search the proceedings of the Constituent Assembly of India (1946–1950), historical Lok Sabha debates and questions, and available Rajya Sabha records, by keyword, speaker, date range, legislative body, subject, and proceeding type.

## Data Scope (v1)

| Source | Coverage | Base URL |
|--------|----------|----------|
| Constituent Assembly debates | All 12 volumes, 1946–1950 | constitutionofindia.net |
| Lok Sabha debates and questions | 1947-08-15 to present; elibrary.sansad.in covers 2019-01-01 to present | Internet Archive; elibrary.sansad.in DSpace 7 |
| Rajya Sabha debates and questions | 1947-08-15 to present; post-2018 records currently unavailable | Internet Archive only |

## Indexed Record Types

Two units are indexed:

**Speech** — one member's individual contribution to a debate or special proceeding. Stores: speaker identity, party, constituency/state, date, session, subject/agenda item, full English text, and a reference to the source document.

**Q+A exchange** — a complete question-and-answer unit:
- Starred question: main question, minister's formal answer, all supplementary questions (with member attribution), and minister's responses to supplementaries
- Unstarred question: question text and written answer (laid on the table)

## v1 Constraints

- Web application only; mobile version is future scope
- English-language text only; Hindi-language portions of proceedings are not indexed in v1
- Fully public, anonymous — no user authentication required
- Cookie-based search history and saved searches (no sign-in required)
- One-time bulk ingestion; no scheduled or ongoing updates in v1
- LS data scope: 1947-08-15 to present (elibrary.sansad.in provides 2019+ coverage; Internet Archive provides earlier records); RS data scope: 1947-08-15 to present, post-2018 records currently unavailable pending an accessible source

## Target Users

- Researchers and academics studying Indian legislative history and constitutional development
- Journalists and analysts covering Indian politics and governance
- Lawyers and legal professionals researching legislative intent
- Law students and educators
- Engaged citizens tracking parliamentary debates and questions
