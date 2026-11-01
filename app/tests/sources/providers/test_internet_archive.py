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
    @staticmethod
    def _rs_meta_response(identifier: str = "rsdebate.nic.in.48275", **extra) -> MagicMock:
        """IA metadata for a Rajya Sabha mirror item (rsdebate_* fields, as published)."""
        resp = MagicMock(status_code=200)
        meta = {
            "identifier": identifier,
            "creator": "Rajya Sabha Secretariat",
            "rsdebate_debate_date": "7-Dec-2004",
            "rsdebate_debate_title": "Demand and supply of LPG",
            "rsdebate_question_type": "Unstarred",
            "rsdebate_question_number": "541",
            "rsdebate_questioner_name": "ABU ASIM AZMI",
            "rsdebate_ministers_name": "MANI SHANKAR AIYAR",
            "rsdebate_ministry": "PETROLEUM AND NATURAL GAS",
            "rsdebate_session_number": "203",
            "rsdebate_page_number_from_to": "148-149",
            "rsdebate_document_url": "https://rsdebate.nic.in/bitstream/123456789/48275/1/PQ.pdf",
            "title": "Demand and supply of LPG (7-Dec-2004)",
        }
        meta.update(extra)
        resp.json.return_value = {
            "server": "ia801205.us.archive.org",
            "dir": f"/5/items/{identifier}",
            "files": [{"name": "IQ_203_07122004_U541_djvu.txt", "format": "DjVuTXT"}],
            "metadata": meta,
        }
        return resp

    async def _discover_rs(self, identifiers, *meta_responses):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [_ia_search_response(identifiers), *meta_responses]
        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            provider = InternetArchiveProvider(client, corpus="RS", rate_delay=0.0)
            return await provider.discover()

    async def test_rs_uses_rajya_sabha_mirror_query(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        provider = InternetArchiveProvider(client, corpus="RS")
        assert provider._query.startswith("identifier:rsdebate.nic.in")
        assert "eparlib" not in provider._query

    async def test_ls_query_excludes_committee_reports(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        provider = InternetArchiveProvider(client, corpus="LS")
        assert "eparlib.nic.in" in provider._query
        assert "Committee Reports" in provider._query

    async def test_rs_citation_url_and_handle(self):
        refs = await self._discover_rs(["rsdebate.nic.in.48275"], self._rs_meta_response())
        assert len(refs) == 1
        ref = refs[0]
        assert ref.corpus == "RS"
        assert ref.citation_url == "https://archive.org/details/rsdebate.nic.in.48275"
        assert ref.canonical_doc_id == "48275"

    async def test_rs_metadata_mapped_to_parser_fields(self):
        refs = await self._discover_rs(["rsdebate.nic.in.48275"], self._rs_meta_response())
        m = refs[0].metadata
        assert m["eparlib_date"] == "7-Dec-2004"
        assert m["eparlib_question_type"] == "Unstarred"
        assert m["eparlib_question_number"] == "541"
        assert m["eparlib_members"] == "ABU ASIM AZMI"
        assert m["eparlib_minister_name"] == "MANI SHANKAR AIYAR"
        assert m["eparlib_relation_ministry"] == "PETROLEUM AND NATURAL GAS"
        assert m["eparlib_page_range"] == "148-149"

    async def test_rs_lok_sabha_number_always_null(self):
        refs = await self._discover_rs(
            ["rsdebate.nic.in.48275"],
            self._rs_meta_response(eparlib_lok_sabha_number="17"),  # spurious; must be ignored
        )
        assert refs[0].metadata["lok_sabha_number"] is None

    async def test_identifiers_from_other_house_mirror_skipped(self):
        """An eparlib (Lok Sabha) item never becomes an RS document, and vice versa."""
        refs = await self._discover_rs(
            ["rsdebate.nic.in.48275", "eparlib.nic.in.55501"], self._rs_meta_response()
        )
        assert [r.canonical_doc_id for r in refs] == ["48275"]

    async def test_known_documents_skip_metadata_fetch(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [
            _ia_search_response(["rsdebate.nic.in.1", "rsdebate.nic.in.2"]),
            self._rs_meta_response("rsdebate.nic.in.2"),
        ]
        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            provider = InternetArchiveProvider(
                client, corpus="RS", rate_delay=0.0, is_known=lambda cid: cid == "1"
            )
            refs = await provider.discover()
        assert [r.canonical_doc_id for r in refs] == ["2"]
        assert client.get.call_count == 2   # listing + one metadata request

    async def test_committee_report_item_skipped(self):
        meta = _ia_metadata_response("eparlib.nic.in.9", "https://eparlib.sansad.in/handle/123456789/9")
        meta.json.return_value["metadata"]["eparlib_appears_in_collections"] = "Parliamentary Committee Reports"
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [_ia_search_response(["eparlib.nic.in.9"]), meta]
        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            refs = await InternetArchiveProvider(client, corpus="LS", rate_delay=0.0).discover()
        assert refs == []


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


class TestStreamingDiscovery:
    """iter_discover yields each document as soon as its metadata arrives, and
    every request it makes waits on the provider's rate limiter first."""

    def _client(self):
        ids = ["eparlib.nic.in.1", "eparlib.nic.in.2"]
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [
            _ia_search_response(ids),
            _ia_metadata_response(ids[0], "https://eparlib.sansad.in/handle/123456789/1"),
            _ia_metadata_response(ids[1], "https://eparlib.sansad.in/handle/123456789/2"),
        ]
        return client

    async def test_first_document_arrives_before_second_metadata_request(self):
        client = self._client()
        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            provider = InternetArchiveProvider(client, corpus="LS", rate_delay=0.0)
            stream = provider.iter_discover()
            first = await stream.__anext__()
            assert first.canonical_doc_id == "1"
            assert client.get.await_count == 2  # search page + first item's metadata
            rest = [ref async for ref in stream]
        assert [r.canonical_doc_id for r in rest] == ["2"]

    async def test_every_request_waits_on_the_limiter(self):
        client = self._client()
        waits = []
        provider = InternetArchiveProvider(client, corpus="LS", rate_delay=2.5)

        async def record_wait():
            waits.append(client.get.await_count)  # requests made before this wait

        provider._limiter.wait = record_wait
        refs = await provider.discover()
        assert len(refs) == 2
        # listing page + two metadata requests, each preceded by its own wait
        assert waits == [0, 1, 2]
        assert provider._limiter.interval == 2.5
