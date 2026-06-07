"""Tests for ingest.sources.providers.internet_archive — InternetArchiveProvider."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ingest.sources._provider import DocumentRef
from ingest.sources.providers.internet_archive import (
    InternetArchiveProvider,
    RSDEBATE_BASE,
    RSDEBATE_ITEM_PATTERN,
    _extract_handle_number,
    _get_meta,
)


# ── Helper: build fixture IA search and metadata responses ─────────────────────

def _ia_search_response(identifiers: list[str]) -> MagicMock:
    """Fake IA advancedsearch.php JSON response."""
    docs = [{"identifier": ident} for ident in identifiers]
    resp = MagicMock(status_code=200)
    resp.json.return_value = {
        "response": {
            "docs": docs,
            "numFound": len(docs),
        }
    }
    return resp


def _ia_metadata_response(identifier: str, document_url: str, date: str = "2023-03-15") -> MagicMock:
    """Fake IA metadata API JSON response for one identifier (includes DjVuTXT file entry)."""
    resp = MagicMock(status_code=200)
    resp.json.return_value = {
        "server": "ia801205.us.archive.org",
        "dir": f"/5/items/{identifier}",
        "files": [
            {"name": "LSD_17_09_08_djvu.txt", "format": "DjVuTXT"},
        ],
        "metadata": {
            "identifier": identifier,
            "eparlib_document_url": document_url,
            "eparlib_date": date,
            "eparlib_lok_sabha_number": "17",
            "eparlib_session_number": "8",
            "eparlib_title": "Lok Sabha Debates",
            "title": identifier,
        },
    }
    return resp


# ── _extract_handle_number ────────────────────────────────────────────────────

class TestExtractHandleNumber:
    def test_extracts_N_from_eparlib_identifier(self):
        assert _extract_handle_number("eparlib.nic.in.12345") == "12345"

    def test_extracts_N_case_insensitive(self):
        assert _extract_handle_number("EPARLIB.NIC.IN.99") == "99"

    def test_returns_none_for_non_matching(self):
        assert _extract_handle_number("something_else.12345") is None

    def test_returns_none_for_empty(self):
        assert _extract_handle_number("") is None

    def test_returns_none_for_partial_match(self):
        # Identifier must fully match the pattern
        assert _extract_handle_number("eparlib.nic.in.12345.extra") is None


class TestGetMeta:
    def test_returns_string_value(self):
        assert _get_meta({"key": "value"}, "key") == "value"

    def test_returns_first_element_of_list(self):
        assert _get_meta({"key": ["first", "second"]}, "key") == "first"

    def test_returns_none_for_missing_key(self):
        assert _get_meta({}, "missing") is None

    def test_returns_none_for_empty_list(self):
        assert _get_meta({"key": []}, "key") is None

    def test_converts_int_to_str(self):
        result = _get_meta({"key": 42}, "key")
        assert result == "42"


# ── InternetArchiveProvider.__init__ ─────────────────────────────────────────

class TestInternetArchiveProviderInit:
    def test_valid_ls_corpus(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        p = InternetArchiveProvider(client, corpus="LS")
        assert p._corpus == "LS"

    def test_valid_rs_corpus(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        p = InternetArchiveProvider(client, corpus="RS")
        assert p._corpus == "RS"

    def test_invalid_corpus_raises(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        with pytest.raises(ValueError, match="corpus must be 'LS' or 'RS'"):
            InternetArchiveProvider(client, corpus="CA")


# ── InternetArchiveProvider.discover() ───────────────────────────────────────

class TestInternetArchiveProviderDiscover:
    async def test_enumerates_fixture_ia_results_and_fetches_metadata(self):
        """
        Enumerate fixture IA search results, fetch fixture metadata JSON,
        and return DocumentRef with citation_url = archive.org item URL (Non-Neg #9 v3.0).
        """
        identifiers = ["eparlib.nic.in.12345", "eparlib.nic.in.67890"]
        doc_url_1 = "https://eparlib.sansad.in/handle/123456789/12345"
        doc_url_2 = "https://eparlib.sansad.in/handle/123456789/67890"

        search_resp_1 = _ia_search_response(identifiers)
        meta_resp_1 = _ia_metadata_response("eparlib.nic.in.12345", doc_url_1)
        meta_resp_2 = _ia_metadata_response("eparlib.nic.in.67890", doc_url_2)

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [search_resp_1, meta_resp_1, meta_resp_2]

        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            provider = InternetArchiveProvider(client, corpus="LS", rate_delay=0.0)
            doc_refs = await provider.discover()

        assert len(doc_refs) == 2

    async def test_citation_url_is_ia_item_url_for_ls(self):
        """PRD v3.0 (Non-Neg #9 reversal): LS citation_url is the archive.org item URL."""
        search_resp_1 = _ia_search_response(["eparlib.nic.in.12345"])
        meta_resp = _ia_metadata_response(
            "eparlib.nic.in.12345",
            "https://eparlib.sansad.in/handle/123456789/12345",
        )

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [search_resp_1, meta_resp]

        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            provider = InternetArchiveProvider(client, corpus="LS", rate_delay=0.0)
            doc_refs = await provider.discover()

        assert len(doc_refs) == 1
        ref = doc_refs[0]
        assert ref.citation_url == "https://archive.org/details/eparlib.nic.in.12345"
        assert "eparlib.sansad.in" not in (ref.citation_url or "")

    async def test_lok_sabha_number_on_ls_metadata(self):
        """PRD v3.0: lok_sabha_number is parsed to an int and surfaced on LS DocumentRefs."""
        search_resp_1 = _ia_search_response(["eparlib.nic.in.12345"])
        meta_resp = _ia_metadata_response(
            "eparlib.nic.in.12345",
            "https://eparlib.sansad.in/handle/123456789/12345",
        )

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [search_resp_1, meta_resp]

        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            provider = InternetArchiveProvider(client, corpus="LS", rate_delay=0.0)
            doc_refs = await provider.discover()

        assert doc_refs[0].metadata["lok_sabha_number"] == 17

    async def test_canonical_doc_id_is_handle_number_N(self):
        """canonical_doc_id must be the DSpace handle number N (not the full identifier)."""
        search_resp_1 = _ia_search_response(["eparlib.nic.in.12345"])
        meta_resp = _ia_metadata_response(
            "eparlib.nic.in.12345",
            "https://eparlib.sansad.in/handle/123456789/12345",
        )

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [search_resp_1, meta_resp]

        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            provider = InternetArchiveProvider(client, corpus="LS", rate_delay=0.0)
            doc_refs = await provider.discover()

        assert doc_refs[0].canonical_doc_id == "12345"

    async def test_fetch_url_is_djvu_txt(self):
        """fetch_url must be assembled from server+dir+name of the DjVuTXT file entry."""
        search_resp_1 = _ia_search_response(["eparlib.nic.in.12345"])
        meta_resp = _ia_metadata_response(
            "eparlib.nic.in.12345",
            "https://eparlib.sansad.in/handle/123456789/12345",
        )

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [search_resp_1, meta_resp]

        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            provider = InternetArchiveProvider(client, corpus="LS", rate_delay=0.0)
            doc_refs = await provider.discover()

        ref = doc_refs[0]
        assert ref.format == "ia_text"
        expected_url = (
            "https://ia801205.us.archive.org"
            "/5/items/eparlib.nic.in.12345"
            "/LSD_17_09_08_djvu.txt"
        )
        assert ref.fetch_url == expected_url
        assert "archive.org/download" not in ref.fetch_url

    async def test_no_djvu_txt_file_skips_document(self):
        """If IA metadata has no DjVuTXT entry in files, the item is skipped."""
        search_resp_1 = _ia_search_response(["eparlib.nic.in.12345"])
        meta_no_djvu = MagicMock(status_code=200)
        meta_no_djvu.json.return_value = {
            "server": "ia801205.us.archive.org",
            "dir": "/5/items/eparlib.nic.in.12345",
            "files": [
                {"name": "eparlib.nic.in.12345.pdf", "format": "Text PDF"},
            ],
            "metadata": {
                "identifier": "eparlib.nic.in.12345",
                "eparlib_document_url": "https://eparlib.sansad.in/handle/123456789/12345",
            },
        }

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [search_resp_1, meta_no_djvu]

        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            provider = InternetArchiveProvider(client, corpus="LS", rate_delay=0.0)
            doc_refs = await provider.discover()

        assert len(doc_refs) == 0

    async def test_doc_ref_metadata_contains_eparlib_fields(self):
        """doc_ref.metadata must carry all eparlib_* fields from the IA metadata JSON."""
        search_resp_1 = _ia_search_response(["eparlib.nic.in.12345"])
        meta_resp = _ia_metadata_response(
            "eparlib.nic.in.12345",
            "https://eparlib.sansad.in/handle/123456789/12345",
            date="2023-03-15",
        )

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [search_resp_1, meta_resp]

        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            provider = InternetArchiveProvider(client, corpus="LS", rate_delay=0.0)
            doc_refs = await provider.discover()

        meta = doc_refs[0].metadata
        assert meta["eparlib_document_url"] == "https://eparlib.sansad.in/handle/123456789/12345"
        assert meta["eparlib_date"] == "2023-03-15"
        assert meta["identifier"] == "eparlib.nic.in.12345"

    async def test_identifier_not_matching_pattern_skipped(self):
        """Identifiers that do not match eparlib.nic.in.{N} are skipped."""
        search_resp_1 = _ia_search_response(["eparlib.nic.in.12345", "unknown.item.99"])
        meta_resp = _ia_metadata_response(
            "eparlib.nic.in.12345",
            "https://eparlib.sansad.in/handle/123456789/12345",
        )

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [search_resp_1, meta_resp]

        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            provider = InternetArchiveProvider(client, corpus="LS", rate_delay=0.0)
            doc_refs = await provider.discover()

        # Only the valid eparlib identifier produces a DocumentRef
        assert len(doc_refs) == 1
        assert doc_refs[0].canonical_doc_id == "12345"

    async def test_corpus_set_on_doc_refs(self):
        search_resp_1 = _ia_search_response(["eparlib.nic.in.42"])
        meta_resp = _ia_metadata_response(
            "eparlib.nic.in.42",
            "https://eparlib.sansad.in/handle/123456789/42",
        )

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [search_resp_1, meta_resp]

        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            provider = InternetArchiveProvider(client, corpus="LS", rate_delay=0.0)
            doc_refs = await provider.discover()

        assert doc_refs[0].corpus == "LS"
        assert doc_refs[0].provider == "internet_archive"

    async def test_citation_url_independent_of_eparlib_document_url(self):
        """PRD v3.0: citation_url derives from the IA identifier, not eparlib_document_url.

        Even when eparlib_document_url is absent, the archive.org item URL is
        cited (it is null only when no IA identifier is derivable).
        """
        search_resp_1 = _ia_search_response(["eparlib.nic.in.12345"])
        meta_no_url = MagicMock(status_code=200)
        meta_no_url.json.return_value = {
            "server": "ia801205.us.archive.org",
            "dir": "/5/items/eparlib.nic.in.12345",
            "files": [{"name": "LSD_djvu.txt", "format": "DjVuTXT"}],
            "metadata": {
                "identifier": "eparlib.nic.in.12345",
                "eparlib_date": "2023-03-15",
            },
        }

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [search_resp_1, meta_no_url]

        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            provider = InternetArchiveProvider(client, corpus="LS", rate_delay=0.0)
            doc_refs = await provider.discover()

        assert len(doc_refs) == 1
        assert doc_refs[0].citation_url == "https://archive.org/details/eparlib.nic.in.12345"

    async def test_metadata_fetch_failure_skips_document(self):
        """If metadata API returns non-200 for an identifier, that identifier is skipped."""
        search_resp_1 = _ia_search_response(["eparlib.nic.in.12345", "eparlib.nic.in.99"])
        meta_fail = MagicMock(status_code=404)
        meta_ok = _ia_metadata_response(
            "eparlib.nic.in.99",
            "https://eparlib.sansad.in/handle/123456789/99",
        )

        client = AsyncMock(spec=httpx.AsyncClient)
        # search page 1, meta for 12345 (fails), meta for 99 (ok)
        client.get.side_effect = [search_resp_1, meta_fail, meta_ok]

        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            provider = InternetArchiveProvider(client, corpus="LS", rate_delay=0.0)
            doc_refs = await provider.discover()

        assert len(doc_refs) == 1
        assert doc_refs[0].canonical_doc_id == "99"


# ── InternetArchiveProvider.discover() — RS corpus (Phase 9, PRD v1.3) ───────

class TestInternetArchiveProviderDiscoverRS:
    async def test_rs_citation_url_is_ia_item_url(self):
        """PRD v3.0 (Non-Neg #9 reversal): RS citation_url is the archive.org item URL."""
        search_resp_1 = _ia_search_response(["eparlib.nic.in.55501"])
        meta_resp = MagicMock(status_code=200)
        meta_resp.json.return_value = {
            "server": "ia801205.us.archive.org",
            "dir": "/5/items/eparlib.nic.in.55501",
            "files": [{"name": "RS_20_02_12_djvu.txt", "format": "DjVuTXT"}],
            "metadata": {
                "identifier": "eparlib.nic.in.55501",
                "eparlib_date": "2020-02-12",
                "title": "Rajya Sabha Debates",
            },
        }

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [search_resp_1, meta_resp]

        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            provider = InternetArchiveProvider(client, corpus="RS", rate_delay=0.0)
            doc_refs = await provider.discover()

        assert len(doc_refs) == 1
        ref = doc_refs[0]
        assert ref.corpus == "RS"
        assert ref.citation_url == "https://archive.org/details/eparlib.nic.in.55501"
        assert "rsdebate.nic.in" not in (ref.citation_url or "")
        assert ref.canonical_doc_id == "55501"

    async def test_rs_lok_sabha_number_always_null(self):
        """PRD v3.0: lok_sabha_number is LS-only; RS DocumentRefs carry null even if present in metadata."""
        search_resp_1 = _ia_search_response(["eparlib.nic.in.55501"])
        meta_resp = MagicMock(status_code=200)
        meta_resp.json.return_value = {
            "server": "ia801205.us.archive.org",
            "dir": "/5/items/eparlib.nic.in.55501",
            "files": [{"name": "RS_20_02_12_djvu.txt", "format": "DjVuTXT"}],
            "metadata": {
                "identifier": "eparlib.nic.in.55501",
                "eparlib_date": "2020-02-12",
                "eparlib_lok_sabha_number": "17",  # spurious on an RS item — must be ignored
                "title": "Rajya Sabha Debates",
            },
        }

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [search_resp_1, meta_resp]

        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            provider = InternetArchiveProvider(client, corpus="RS", rate_delay=0.0)
            doc_refs = await provider.discover()

        assert doc_refs[0].metadata["lok_sabha_number"] is None

    async def test_rs_no_derivable_handle_still_cites_ia_item(self, caplog):
        """PRD v3.0: an RS IA item with no derivable handle still cites the archive.org item URL.

        citation_url is null only when no IA identifier exists; here the
        identifier is present (just not an eparlib.nic.in.{N} handle), so the
        IA item URL is used and the item is tracked via the identifier.
        """
        search_resp_1 = _ia_search_response(["rs_misc_item_no_handle"])
        meta_resp = MagicMock(status_code=200)
        meta_resp.json.return_value = {
            "server": "ia801205.us.archive.org",
            "dir": "/5/items/rs_misc_item_no_handle",
            "files": [{"name": "RS_19_07_22_djvu.txt", "format": "DjVuTXT"}],
            "metadata": {
                "identifier": "rs_misc_item_no_handle",
                "eparlib_date": "2019-07-22",
                "title": "Rajya Sabha Debates (untagged)",
            },
        }

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [search_resp_1, meta_resp]

        import logging

        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            with caplog.at_level(logging.WARNING):
                provider = InternetArchiveProvider(client, corpus="RS", rate_delay=0.0)
                doc_refs = await provider.discover()

        assert len(doc_refs) == 1
        ref = doc_refs[0]
        assert ref.citation_url == "https://archive.org/details/rs_misc_item_no_handle"
        # The item is still tracked via the IA identifier as canonical id.
        assert ref.canonical_doc_id == "rs_misc_item_no_handle"

    async def test_rs_unmatched_identifier_retained_ls_skipped(self):
        """An identifier with no handle is retained for RS but skipped for LS — divergent behavior."""
        search_resp = _ia_search_response(["weird_identifier_42"])
        meta_resp = MagicMock(status_code=200)
        meta_resp.json.return_value = {
            "server": "ia801205.us.archive.org",
            "dir": "/5/items/weird_identifier_42",
            "files": [{"name": "weird_djvu.txt", "format": "DjVuTXT"}],
            "metadata": {"identifier": "weird_identifier_42", "title": "X"},
        }

        # RS run: retained
        client_rs = AsyncMock(spec=httpx.AsyncClient)
        client_rs.get.side_effect = [search_resp, meta_resp]
        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            rs_refs = await InternetArchiveProvider(client_rs, corpus="RS", rate_delay=0.0).discover()

        # LS run: skipped (metadata never fetched because identifier is skipped first)
        search_resp_ls = _ia_search_response(["weird_identifier_42"])
        client_ls = AsyncMock(spec=httpx.AsyncClient)
        client_ls.get.side_effect = [search_resp_ls]
        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            ls_refs = await InternetArchiveProvider(client_ls, corpus="LS", rate_delay=0.0).discover()

        assert len(rs_refs) == 1
        assert len(ls_refs) == 0


# ── InternetArchiveProvider.fetch() ──────────────────────────────────────────

class TestInternetArchiveProviderFetch:
    def _make_doc_ref(self, handle_n: str = "12345") -> DocumentRef:
        identifier = f"eparlib.nic.in.{handle_n}"
        return DocumentRef(
            corpus="LS",
            provider="internet_archive",
            format="ia_text",
            fetch_url=f"https://ia801205.us.archive.org/5/items/{identifier}/LSD_djvu.txt",
            canonical_doc_id=handle_n,
            citation_url=f"https://archive.org/details/eparlib.nic.in.{handle_n}",
            metadata={"identifier": identifier},
        )

    async def test_fetch_returns_djvu_text(self):
        djvu_content = "SHRI NARENDRA MODI:\nSpeech text here.\n"
        resp = MagicMock(status_code=200, text=djvu_content)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = resp

        provider = InternetArchiveProvider(client, corpus="LS", rate_delay=0.0)
        result = await provider.fetch(self._make_doc_ref())

        assert isinstance(result, str)
        assert "NARENDRA MODI" in result

    async def test_fetch_returns_none_on_failure(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = MagicMock(status_code=503)

        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            provider = InternetArchiveProvider(client, corpus="LS", rate_delay=0.0)
            result = await provider.fetch(self._make_doc_ref())

        assert result is None
