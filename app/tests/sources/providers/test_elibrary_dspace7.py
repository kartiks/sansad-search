"""
Tests for ElibraryDSpace7Provider.

Covers:
- discover(): pagination, date filtering, TEXT-bundle resolution, DocumentRef shape
- fetch(): text content download
- Helpers: _get_meta, _extract_handle_number, _parse_session_number, _parse_lok_sabha_number
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ingest.sources._provider import DocumentRef
from ingest.sources.providers.elibrary_dspace7 import (
    COLLECTION_UUID,
    ELIBRARY_API_BASE,
    ElibraryDSpace7Provider,
    _extract_handle_number,
    _get_meta,
    _parse_lok_sabha_number,
    _parse_session_number,
)


# ── Fixture helpers ────────────────────────────────────────────────────────────

def _make_item(
    uuid: str = "abc-123",
    handle: str = "123456789/1506664",
    date_issued: str = "2025-02-01",
    ls_number: str = "18",
    session: str = "IV",
) -> dict:
    """Build a minimal DSpace 7 search result item."""
    return {
        "uuid": uuid,
        "handle": handle,
        "metadata": {
            "dc.date.issued": [{"value": date_issued}],
            "dc.identifier.loksabhanumber": [{"value": ls_number}],
            "dc.identifier.sessionnumber": [{"value": session}],
        },
    }


def _search_response(items: list[dict], total_elements: int | None = None) -> dict:
    """Wrap items in a DSpace 7 search API response envelope."""
    objects = [{"_embedded": {"indexableObject": item}} for item in items]
    return {
        "_embedded": {
            "searchResult": {
                "_embedded": {"objects": objects},
                "totalElements": total_elements or len(items),
            }
        }
    }


def _bundles_response(text_bundle_uuid: str = "text-bundle-uuid") -> dict:
    return {
        "_embedded": {
            "bundles": [
                {"name": "ORIGINAL", "uuid": "orig-uuid"},
                {"name": "TEXT", "uuid": text_bundle_uuid},
                {"name": "THUMBNAIL", "uuid": "thumb-uuid"},
            ]
        }
    }


def _bitstreams_response(bs_uuid: str = "bs-uuid", name: str = "debate.pdf.txt") -> dict:
    return {
        "_embedded": {
            "bitstreams": [
                {"uuid": bs_uuid, "name": name},
            ]
        }
    }


def _mock_response(data: dict) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = data
    return resp


# ── Unit tests: helper functions ───────────────────────────────────────────────

class TestGetMeta:
    def test_returns_first_value(self):
        item = {"metadata": {"dc.date.issued": [{"value": "2025-02-01"}]}}
        assert _get_meta(item, "dc.date.issued") == "2025-02-01"

    def test_missing_field_returns_none(self):
        item = {"metadata": {}}
        assert _get_meta(item, "dc.date.issued") is None

    def test_empty_list_returns_none(self):
        item = {"metadata": {"dc.date.issued": []}}
        assert _get_meta(item, "dc.date.issued") is None


class TestExtractHandleNumber:
    def test_standard_handle(self):
        assert _extract_handle_number("123456789/1506664") == "1506664"

    def test_short_handle(self):
        assert _extract_handle_number("123456789/1") == "1"

    def test_invalid_format_returns_none(self):
        assert _extract_handle_number("notahandle") is None

    def test_wrong_prefix_returns_none(self):
        assert _extract_handle_number("987654321/1234") is None


class TestParseSessionNumber:
    def test_integer_string(self):
        assert _parse_session_number("5") == 5

    def test_roman_iv(self):
        assert _parse_session_number("IV") == 4

    def test_roman_lowercase(self):
        assert _parse_session_number("iv") == 4

    def test_roman_xiv(self):
        assert _parse_session_number("XIV") == 14

    def test_none_returns_none(self):
        assert _parse_session_number(None) is None

    def test_invalid_returns_none(self):
        assert _parse_session_number("ZZZ") is None


class TestParseLokSabhaNumber:
    def test_integer_string(self):
        assert _parse_lok_sabha_number("18") == 18

    def test_int(self):
        assert _parse_lok_sabha_number(17) == 17

    def test_none_returns_none(self):
        assert _parse_lok_sabha_number(None) is None

    def test_invalid_returns_none(self):
        assert _parse_lok_sabha_number("ABC") is None


# ── Integration: discover() ────────────────────────────────────────────────────

class TestElibraryDiscover:
    """discover() produces correctly shaped DocumentRefs with TEXT bitstream URLs."""

    @pytest.mark.asyncio
    async def test_single_item_produces_doc_ref(self):
        """A single in-scope item produces one DocumentRef with the expected fields."""
        item = _make_item(
            uuid="item-uuid-1",
            handle="123456789/1506664",
            date_issued="2025-02-01",
            ls_number="18",
            session="IV",
        )
        search_resp = _mock_response(_search_response([item]))
        bundles_resp = _mock_response(_bundles_response(text_bundle_uuid="tbundle-1"))
        bitstreams_resp = _mock_response(_bitstreams_response(bs_uuid="bs-uuid-1"))
        # Second page returns empty
        empty_resp = _mock_response(_search_response([]))

        client = AsyncMock(spec=httpx.AsyncClient)

        with patch(
            "ingest.sources.providers.elibrary_dspace7.fetch_with_retry",
            side_effect=[search_resp, bundles_resp, bitstreams_resp, empty_resp],
        ):
            provider = ElibraryDSpace7Provider(
                client, date_from="2019-01-01", rate_delay=0
            )
            refs = await provider.discover()

        assert len(refs) == 1
        ref = refs[0]
        assert ref.corpus == "LS"
        assert ref.provider == "elibrary_dspace7"
        assert ref.format == "elibrary_text"
        assert ref.canonical_doc_id == "1506664"
        assert ref.citation_url == "https://elibrary.sansad.in/handle/123456789/1506664"
        assert ref.fetch_url == f"{ELIBRARY_API_BASE}/core/bitstreams/bs-uuid-1/content"
        assert ref.metadata["date"] == "2025-02-01"
        assert ref.metadata["lok_sabha_number"] == 18
        assert ref.metadata["session_number"] == 4  # IV → 4

    @pytest.mark.asyncio
    async def test_date_from_filters_old_items(self):
        """Items before date_from are skipped; items on/after are included."""
        items = [
            _make_item(uuid="old", handle="123456789/100", date_issued="2018-03-01"),
            _make_item(uuid="new", handle="123456789/200", date_issued="2020-07-15"),
        ]
        search_resp = _mock_response(_search_response(items))
        bundles_resp = _mock_response(_bundles_response())
        bitstreams_resp = _mock_response(_bitstreams_response())
        empty_resp = _mock_response(_search_response([]))

        client = AsyncMock(spec=httpx.AsyncClient)

        with patch(
            "ingest.sources.providers.elibrary_dspace7.fetch_with_retry",
            side_effect=[search_resp, bundles_resp, bitstreams_resp, empty_resp],
        ):
            provider = ElibraryDSpace7Provider(
                client, date_from="2019-01-01", rate_delay=0
            )
            refs = await provider.discover()

        assert len(refs) == 1
        assert refs[0].canonical_doc_id == "200"

    @pytest.mark.asyncio
    async def test_date_to_filters_out_post_scope_items(self):
        """Items after date_to are skipped; in-scope items on the same page are kept."""
        items = [
            _make_item(uuid="in-scope", handle="123456789/300", date_issued="2020-01-15"),
            _make_item(uuid="out-of-scope", handle="123456789/400", date_issued="2023-06-01"),
        ]
        search_resp = _mock_response(_search_response(items))
        bundles_resp = _mock_response(_bundles_response())
        bitstreams_resp = _mock_response(_bitstreams_response())

        client = AsyncMock(spec=httpx.AsyncClient)

        with patch(
            "ingest.sources.providers.elibrary_dspace7.fetch_with_retry",
            side_effect=[search_resp, bundles_resp, bitstreams_resp],
        ):
            provider = ElibraryDSpace7Provider(
                client, date_from="2019-01-01", date_to="2021-12-31", rate_delay=0
            )
            refs = await provider.discover()

        assert len(refs) == 1
        assert refs[0].canonical_doc_id == "300"

    @pytest.mark.asyncio
    async def test_out_of_order_post_scope_does_not_halt_discovery(self):
        """A post-scope item appearing before an in-scope item (unreliable API sort)
        must not terminate pagination — the in-scope item must still be collected."""
        items = [
            # Post-scope item appears first (as happens on elibrary.sansad.in page 0)
            _make_item(uuid="future", handle="123456789/9001", date_issued="2025-01-31"),
            # In-scope item follows on the same page
            _make_item(uuid="target", handle="123456789/9002", date_issued="2024-03-15"),
        ]
        search_resp = _mock_response(_search_response(items))
        bundles_resp = _mock_response(_bundles_response())
        bitstreams_resp = _mock_response(_bitstreams_response())

        client = AsyncMock(spec=httpx.AsyncClient)

        with patch(
            "ingest.sources.providers.elibrary_dspace7.fetch_with_retry",
            side_effect=[search_resp, bundles_resp, bitstreams_resp],
        ):
            provider = ElibraryDSpace7Provider(
                client, date_from="2024-01-01", date_to="2024-06-30", rate_delay=0
            )
            refs = await provider.discover()

        assert len(refs) == 1
        assert refs[0].canonical_doc_id == "9002"

    @pytest.mark.asyncio
    async def test_item_with_no_text_bundle_is_skipped(self):
        """An item whose bundles response has no TEXT bundle is silently skipped."""
        item = _make_item(uuid="no-text", handle="123456789/500", date_issued="2021-03-01")
        search_resp = _mock_response(_search_response([item]))
        # Bundles response has no TEXT bundle
        bundles_resp = _mock_response({
            "_embedded": {"bundles": [{"name": "ORIGINAL", "uuid": "orig"}]}
        })
        empty_resp = _mock_response(_search_response([]))

        client = AsyncMock(spec=httpx.AsyncClient)

        with patch(
            "ingest.sources.providers.elibrary_dspace7.fetch_with_retry",
            side_effect=[search_resp, bundles_resp, empty_resp],
        ):
            provider = ElibraryDSpace7Provider(
                client, date_from="2019-01-01", rate_delay=0
            )
            refs = await provider.discover()

        assert len(refs) == 0


# ── Integration: fetch() ───────────────────────────────────────────────────────

class TestElibraryFetch:
    """fetch() downloads and returns text content from the bitstream URL."""

    @pytest.mark.asyncio
    async def test_fetch_returns_text(self):
        debate_text = "SHRI SPEAKER: Order, order. The House will come to order."
        resp = MagicMock(spec=httpx.Response)
        resp.text = debate_text

        client = AsyncMock(spec=httpx.AsyncClient)
        ref = DocumentRef(
            corpus="LS",
            provider="elibrary_dspace7",
            format="elibrary_text",
            fetch_url=f"{ELIBRARY_API_BASE}/core/bitstreams/bs-xyz/content",
            canonical_doc_id="1506664",
            citation_url="https://elibrary.sansad.in/handle/123456789/1506664",
            metadata={"date": "2025-02-01"},
        )

        with patch(
            "ingest.sources.providers.elibrary_dspace7.fetch_with_retry",
            return_value=resp,
        ):
            provider = ElibraryDSpace7Provider(client, rate_delay=0)
            text = await provider.fetch(ref)

        assert text == debate_text

    @pytest.mark.asyncio
    async def test_fetch_returns_none_on_failure(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        ref = DocumentRef(
            corpus="LS",
            provider="elibrary_dspace7",
            format="elibrary_text",
            fetch_url=f"{ELIBRARY_API_BASE}/core/bitstreams/bad/content",
            canonical_doc_id="999",
            citation_url=None,
            metadata={},
        )

        with patch(
            "ingest.sources.providers.elibrary_dspace7.fetch_with_retry",
            return_value=None,
        ):
            provider = ElibraryDSpace7Provider(client, rate_delay=0)
            result = await provider.fetch(ref)

        assert result is None
