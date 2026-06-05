"""
Provider contract, DocumentRef dataclass, and shared pipeline helpers.

Each corpus is served by an ordered chain of providers. The corpus orchestrator
(ca.py, ls.py, rs.py) tries providers in order and uses the first that yields
parseable content for each document.

DocumentRef is the standard handoff between discovery and fetching. It carries
all information needed by the parsers and indexer without coupling them to any
specific provider.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class DocumentRef:
    """Provider-agnostic descriptor for a single source document.

    canonical_doc_id
        Provider-agnostic identity key used by the checkpoint store for
        document-level deduplication:
          - LS/RS: the DSpace handle number N (so IA eparlib.nic.in.{N} and
            DSpace 123456789/{N} collapse to one entry)
          - CA: the constitutionofindia.net day-URL (single provider)

    citation_url
        The canonical URL that appears as source_url in indexed records.
        Must NOT be an archive.org URL (ARCHITECTURE.md Non-Negotiable #9).
        None when no derivable canonical URL exists (e.g. RS-via-IA with no
        DSpace handle — PRD v1.3 edge case).

    metadata
        Discovered metadata from the provider (date, session number, title,
        etc.). Keys vary by provider and corpus; parsers read what they need.
    """

    corpus: str                          # "CA", "LS", or "RS"
    provider: str                        # e.g. "coi_html", "internet_archive"
    format: str                          # "html", "pdf", or "ia_text"
    fetch_url: str                       # URL to retrieve document content
    canonical_doc_id: str                # checkpoint/dedup key
    citation_url: str | None             # source_url in records; never archive.org
    metadata: dict[str, Any] = field(default_factory=dict)


class Provider(ABC):
    """Abstract base for all ingestion providers.

    Subclasses implement discovery (listing/browse crawl to produce a set of
    DocumentRefs) and fetching (HTTP retrieval of one document).

    The corpus orchestrator calls discover() once per run to get the full set
    of DocumentRefs, then calls fetch() for each DocumentRef whose
    canonical_doc_id is absent from the checkpoint store.
    """

    @abstractmethod
    async def discover(self) -> list[DocumentRef]:
        """Enumerate all documents available from this provider.

        Returns a list of DocumentRef objects. May be empty if the provider
        has no documents in scope (e.g. after the date filter is applied).
        """

    @abstractmethod
    async def fetch(self, doc_ref: DocumentRef) -> bytes | str | None:
        """Fetch the content of a single document.

        Returns:
            bytes for PDF documents (format="pdf")
            str for HTML documents (format="html") and IA text (format="ia_text")
            None if the fetch fails and the document should be skipped
        """


def extract_stage1_fields(raw_record: dict) -> tuple[Optional[str], dict]:
    """Split a parser-output raw_record into (extracted_text, metadata_json).

    extracted_text is the raw_text field consumed by segmenters in Stage 2.
    metadata_json contains all other fields needed to reconstruct the raw_record,
    minus raw_html (large, not used by segmenters).
    """
    extracted_text = raw_record.get("raw_text")
    metadata = {k: v for k, v in raw_record.items() if k not in ("raw_text", "raw_html")}
    return extracted_text, metadata
