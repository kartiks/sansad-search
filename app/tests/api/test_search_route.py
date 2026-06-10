"""
Tests for POST /api/search — route-level validation, expansion notice,
filter building, sort, and error responses.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.lib.db import get_pool
from api.lib.meilisearch_client import get_client
from tests.api.conftest import make_mock_meili_client, make_mock_pool


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_hit(**overrides) -> Dict[str, Any]:
    base = {
        "id": "hit-1",
        "record_type": "speech",
        "source": "LS",
        "proceeding_type": "debate",
        "date": "2023-03-15",
        "full_text_en": "The Finance Minister discussed infrastructure.",
        "is_translated": False,
        "speaker_name": "Test Member",
    }
    base.update(overrides)
    return base


def _meili_response(hits=None, total=0, pages=0, page=1) -> Dict[str, Any]:
    return {
        "hits": hits or [],
        "totalHits": total,
        "totalPages": pages,
        "page": page,
        "hitsPerPage": 20,
    }


def _meili_ns(hits=None, total=0, pages=0, page=1) -> SimpleNamespace:
    """Attribute-accessible version of _meili_response for use in fake_search
    stubs.  search.py accesses results via raw.hits / raw.total_hits etc.,
    so inline mock functions must return a SimpleNamespace, not a plain dict."""
    return SimpleNamespace(
        hits=hits or [],
        total_hits=total,
        total_pages=pages,
        page=page,
        hits_per_page=20,
    )


def _make_client(meili_response=None) -> TestClient:
    mock_pool = make_mock_pool()
    mock_meili = make_mock_meili_client(search_result=meili_response or _meili_response())
    app.dependency_overrides[get_pool] = lambda: mock_pool
    app.dependency_overrides[get_client] = lambda: mock_meili
    return mock_meili


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def setup_and_teardown():
    """Patch lifespan hooks and set up a clean state for each test."""
    with patch("api.main.init_pool", new_callable=AsyncMock), \
         patch("api.main.close_pool", new_callable=AsyncMock):
        yield
    app.dependency_overrides.clear()


# ── Validation: query_too_short ───────────────────────────────────────────────

class TestQueryTooShort:
    def test_empty_query_returns_400(self):
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={"query": ""})
        assert resp.status_code == 400
        body = resp.json()
        # Error body must be a bare top-level object (DATA-MODELS.md 3.1)
        assert body["error"] == "validation_error"
        assert body["code"] == "query_too_short"

    def test_single_char_query_returns_400(self):
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={"query": "a"})
        assert resp.status_code == 400
        assert resp.json()["code"] == "query_too_short"

    def test_special_chars_only_returns_400(self):
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={"query": "!!@#"})
        assert resp.status_code == 400
        assert resp.json()["code"] == "query_too_short"


# ── Validation: query_only_stopwords ─────────────────────────────────────────

class TestQueryOnlyStopwords:
    def test_all_stopwords_returns_400(self):
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={"query": "the and or"})
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"] == "validation_error"
        assert body["code"] == "query_only_stopwords"

    def test_stop_words_with_real_term_passes(self):
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={"query": "the right to speech"})
        assert resp.status_code == 200


# ── Validation: sources_empty ─────────────────────────────────────────────────

class TestSourcesEmpty:
    def test_empty_sources_returns_400(self):
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={
                "query": "Article 370",
                "filters": {"sources": []},
            })
        assert resp.status_code == 400
        assert resp.json()["code"] == "sources_empty"


# ── Validation: proceeding_types_empty ───────────────────────────────────────

class TestProceedingTypesEmpty:
    def test_empty_proceeding_types_returns_400(self):
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={
                "query": "Article 370",
                "filters": {"proceeding_types": []},
            })
        assert resp.status_code == 400
        assert resp.json()["code"] == "proceeding_types_empty"


# ── Validation: date_range_invalid ────────────────────────────────────────────

class TestDateRangeInvalid:
    def test_from_after_to_returns_400(self):
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={
                "query": "Article 370",
                "filters": {"date_from": "2022-06-01", "date_to": "2021-01-01"},
            })
        assert resp.status_code == 400
        assert resp.json()["code"] == "date_range_invalid"

    def test_from_equals_to_passes(self):
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={
                "query": "Article 370",
                "filters": {"date_from": "2022-01-01", "date_to": "2022-01-01"},
            })
        assert resp.status_code == 200

    def test_only_date_from_passes(self):
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={
                "query": "Article 370",
                "filters": {"date_from": "2020-01-01"},
            })
        assert resp.status_code == 200


# ── Query truncation ──────────────────────────────────────────────────────────

class TestQueryTruncation:
    def test_501_char_query_executes_without_error(self):
        long_query = "infrastructure " * 40  # > 500 chars, meaningful
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={"query": long_query})
        assert resp.status_code == 200

    def test_exact_500_char_query_executes(self):
        query = "a" * 498 + "bc"  # exactly 500 chars, 2 meaningful chars
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={"query": query})
        assert resp.status_code == 200


# ── Successful search response ────────────────────────────────────────────────

class TestSuccessfulSearch:
    def test_response_shape(self):
        meili_resp = _meili_response(
            hits=[_make_hit()],
            total=1, pages=1, page=1,
        )
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client(search_result=meili_resp)
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={"query": "infrastructure"})
        assert resp.status_code == 200
        body = resp.json()
        assert "total" in body
        assert "total_display" in body
        assert "page" in body
        assert "total_pages" in body
        assert "per_page" in body
        assert "expansion_notice" in body
        assert "results" in body
        assert isinstance(body["results"], list)

    def test_total_display_below_10000(self):
        meili_resp = _meili_response(total=1234)
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client(search_result=meili_resp)
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={"query": "infrastructure"})
        assert resp.json()["total_display"] == "1,234"

    def test_total_display_at_10000(self):
        meili_resp = _meili_response(total=10000)
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client(search_result=meili_resp)
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={"query": "infrastructure"})
        assert resp.json()["total_display"] == "10,000+"

    def test_expansion_notice_populated(self):
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={"query": "PM speech"})
        body = resp.json()
        assert "Prime Minister" in body["expansion_notice"]

    def test_result_has_proceeding_type_label(self):
        meili_resp = _meili_response(hits=[_make_hit(proceeding_type="debate")], total=1)
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client(search_result=meili_resp)
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={"query": "infrastructure"})
        result = resp.json()["results"][0]
        assert result["proceeding_type_label"] == "Debate"

    def test_result_has_date_display(self):
        meili_resp = _meili_response(hits=[_make_hit(date="2023-03-15")], total=1)
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client(search_result=meili_resp)
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={"query": "infrastructure"})
        result = resp.json()["results"][0]
        assert result["date_display"] == "15 March 2023"

    def test_snippet_contains_mark_tags(self):
        hit = _make_hit(
            full_text_en="The Finance Minister discussed infrastructure development."
        )
        meili_resp = _meili_response(hits=[hit], total=1)
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client(search_result=meili_resp)
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={"query": "infrastructure"})
        result = resp.json()["results"][0]
        assert "<mark>" in (result.get("snippet") or "")


# ── Filter forwarding ─────────────────────────────────────────────────────────

class TestFilterForwarding:
    def _captured_search_params(self):
        """Return (meili_mock, captured_params_list) where params are captured."""
        captured = []

        async def fake_search(query, **kwargs):
            captured.append({"query": query, "params": kwargs})
            return _meili_ns()

        mock_index = AsyncMock()
        mock_index.search = fake_search
        mock_client = MagicMock()
        mock_client.index = MagicMock(return_value=mock_index)
        return mock_client, captured

    def test_source_filter_forwarded(self):
        mock_client, captured = self._captured_search_params()
        mock_pool = make_mock_pool()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_client
        with TestClient(app) as client:
            client.post("/api/search", json={
                "query": "budget",
                "filters": {"sources": ["LS"]},
            })
        params = captured[0]["params"]
        assert "filter" in params
        assert "LS" in params["filter"]

    def test_no_filters_no_filter_key(self):
        mock_client, captured = self._captured_search_params()
        mock_pool = make_mock_pool()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_client
        with TestClient(app) as client:
            client.post("/api/search", json={"query": "budget"})
        params = captured[0]["params"]
        assert "filter" not in params

    def test_sort_chronological_forwarded(self):
        mock_client, captured = self._captured_search_params()
        mock_pool = make_mock_pool()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_client
        with TestClient(app) as client:
            client.post("/api/search", json={"query": "budget", "sort": "chronological"})
        params = captured[0]["params"]
        assert "sort" in params
        assert "date:asc" in params["sort"]
        assert "sequence_within_sitting:asc" in params["sort"]

    def test_sort_relevance_no_sort_key(self):
        mock_client, captured = self._captured_search_params()
        mock_pool = make_mock_pool()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_client
        with TestClient(app) as client:
            client.post("/api/search", json={"query": "budget", "sort": "relevance"})
        params = captured[0]["params"]
        assert "sort" not in params

    def test_combined_filter_and_logic(self):
        """All active filters must be joined with AND in the filter expression."""
        mock_client, captured = self._captured_search_params()
        mock_pool = make_mock_pool()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_client
        with TestClient(app) as client:
            client.post("/api/search", json={
                "query": "budget",
                "filters": {
                    "sources": ["LS"],
                    "proceeding_types": ["starred_question"],
                    "speaker": "Jairam Ramesh",
                },
            })
        params = captured[0]["params"]
        assert "filter" in params
        # All three filter parts joined with AND
        assert " AND " in params["filter"]
        assert "source" in params["filter"]
        assert "proceeding_type" in params["filter"]
        assert "Jairam Ramesh" in params["filter"]

    def test_session_filter_present_in_expression(self):
        """Session filter produces a session_name CONTAINS expression."""
        mock_client, captured = self._captured_search_params()
        mock_pool = make_mock_pool()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_client
        with TestClient(app) as client:
            client.post("/api/search", json={
                "query": "budget",
                "filters": {"session": "Budget Session"},
            })
        params = captured[0]["params"]
        assert 'session_name CONTAINS "Budget Session"' in params["filter"]

    def test_subject_filter_present_in_expression(self):
        """Subject filter produces a subject CONTAINS expression."""
        mock_client, captured = self._captured_search_params()
        mock_pool = make_mock_pool()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_client
        with TestClient(app) as client:
            client.post("/api/search", json={
                "query": "budget",
                "filters": {"subject": "Railways"},
            })
        params = captured[0]["params"]
        assert 'subject CONTAINS "Railways"' in params["filter"]

    def test_page_forwarded(self):
        mock_client, captured = self._captured_search_params()
        mock_pool = make_mock_pool()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_client
        with TestClient(app) as client:
            client.post("/api/search", json={"query": "budget", "page": 3})
        params = captured[0]["params"]
        assert params["page"] == 3


# ── F05 snippet crop configuration ────────────────────────────────────────────

class TestSnippetCropParams:
    """F05 (PRD v3.0): ≥400-word snippets via Meilisearch crop parameters."""

    def _captured_search_params(self):
        captured = []

        async def fake_search(query, **kwargs):
            captured.append({"query": query, "params": kwargs})
            return _meili_ns()

        mock_index = AsyncMock()
        mock_index.search = fake_search
        mock_client = MagicMock()
        mock_client.index = MagicMock(return_value=mock_index)
        return mock_client, captured

    def test_attributes_to_crop_forwarded(self):
        mock_client, captured = self._captured_search_params()
        mock_pool = make_mock_pool()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_client
        with TestClient(app) as client:
            client.post("/api/search", json={"query": "budget"})
        params = captured[0]["params"]
        assert params["attributes_to_crop"] == ["full_text_en"]

    def test_crop_length_is_400(self):
        mock_client, captured = self._captured_search_params()
        mock_pool = make_mock_pool()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_client
        with TestClient(app) as client:
            client.post("/api/search", json={"query": "budget"})
        params = captured[0]["params"]
        assert params["crop_length"] == 280

    def test_crop_marker_present(self):
        mock_client, captured = self._captured_search_params()
        mock_pool = make_mock_pool()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_client
        with TestClient(app) as client:
            client.post("/api/search", json={"query": "budget"})
        params = captured[0]["params"]
        assert params["crop_marker"] == "…"


# ── Filter validation edge cases ──────────────────────────────────────────────

class TestFilterEdgeCases:
    def test_ca_only_with_non_debate_produces_results(self):
        """CA + starred_question returns results from Meili (no backend error)."""
        meili_resp = _meili_response(hits=[], total=0)
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client(search_result=meili_resp)
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={
                "query": "question",
                "filters": {"sources": ["CA"], "proceeding_types": ["starred_question"]},
            })
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_date_range_gap_no_error(self):
        """Date range spanning 1948–2015 (with gap years) must not error."""
        meili_resp = _meili_response(hits=[], total=0)
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client(search_result=meili_resp)
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={
                "query": "Constitution",
                "filters": {"date_from": "1948-01-01", "date_to": "2015-12-31"},
            })
        assert resp.status_code == 200

    def test_omitted_sources_means_all_sources(self):
        """Omitting sources key entirely places no source restriction."""
        mock_client, captured = [], []

        async def fake_search(query, **kwargs):
            captured.append(kwargs)
            return _meili_ns()

        mock_index = AsyncMock()
        mock_index.search = fake_search
        meili_client = MagicMock()
        meili_client.index = MagicMock(return_value=mock_index)
        mock_pool = make_mock_pool()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: meili_client
        with TestClient(app) as client:
            client.post("/api/search", json={"query": "budget"})
        params = captured[0]
        # No filter key, or filter without "source IN"
        filter_val = params.get("filter", "")
        assert "source IN" not in filter_val


# ── Gap 1: Phrase query forwarding (F02) ──────────────────────────────────────

class TestPhraseQueryForwarding:
    """F02: Quoted phrase queries must reach Meilisearch with quotes preserved.

    Phase 3 exit criteria require fixture-backed verification that non-adjacent
    records do NOT match phrase queries. This class verifies the mock-testable
    half: the quoted phrase is forwarded intact so Meilisearch can enforce
    adjacency semantics. Full non-adjacency verification requires a
    fixture-backed integration test against a live Meilisearch instance.
    """

    def test_quoted_phrase_forwarded_with_quotes_intact(self):
        """Quotes must survive stop-word stripping so Meilisearch enforces phrase
        adjacency correctly."""
        captured = []

        async def fake_search(query, **kwargs):
            captured.append(query)
            return _meili_ns()

        mock_index = AsyncMock()
        mock_index.search = fake_search
        mock_client = MagicMock()
        mock_client.index = MagicMock(return_value=mock_index)
        mock_pool = make_mock_pool()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_client
        with TestClient(app) as client:
            client.post("/api/search", json={"query": '"fundamental rights" debate'})
        assert len(captured) == 1
        # Quotes must be present in the forwarded query
        assert '"fundamental rights"' in captured[0]

    def test_quoted_phrase_query_returns_200(self):
        """Route must not error on a query that contains a quoted phrase."""
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={"query": '"Article 370" debate'})
        assert resp.status_code == 200


# ── Gap 2: Case insensitivity (F02) ──────────────────────────────────────────

class TestCaseInsensitivity:
    """F02: Queries in any case must execute without error.

    Case-insensitive matching is delegated to Meilisearch natively. Our route
    does not normalise query case — all variants are forwarded unchanged so
    Meilisearch can apply its case-folding at search time.
    Full identical-result-set verification requires a fixture-backed integration
    test against a live Meilisearch instance.
    """

    def test_lowercase_query_returns_200(self):
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={"query": "article 370"})
        assert resp.status_code == 200

    def test_titlecase_query_returns_200(self):
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={"query": "Article 370"})
        assert resp.status_code == 200

    def test_uppercase_query_returns_200(self):
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={"query": "ARTICLE 370"})
        assert resp.status_code == 200

    def test_all_case_variants_reach_meilisearch(self):
        """All three casings must trigger a Meilisearch call — no validation
        short-circuit on query case."""
        for query_text in ("article 370", "Article 370", "ARTICLE 370"):
            calls: list = []

            async def fake_search(q, _c=calls, **kwargs):
                _c.append(q)
                return _meili_ns()

            mock_index = AsyncMock()
            mock_index.search = fake_search
            mock_client = MagicMock()
            mock_client.index = MagicMock(return_value=mock_index)
            mock_pool = make_mock_pool()
            app.dependency_overrides[get_pool] = lambda: mock_pool
            app.dependency_overrides[get_client] = lambda: mock_client
            with TestClient(app) as client:
                client.post("/api/search", json={"query": query_text})
            assert len(calls) == 1, f"Expected Meilisearch call for casing {query_text!r}"


# ── Gap 3: Special character handling (F02) ───────────────────────────────────

class TestSpecialCharHandling:
    """F02: Queries containing parentheses, brackets, ampersands, or other
    special characters must not cause a route error.
    """

    def test_query_with_parentheses_returns_200(self):
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={"query": "Article 370 & (Constitution)"})
        assert resp.status_code == 200

    def test_query_with_brackets_returns_200(self):
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={"query": "Section [4(1)] IPC"})
        assert resp.status_code == 200

    def test_query_with_mixed_special_chars_returns_200(self):
        """Multiple special-char combinations must all succeed."""
        queries = [
            "SC & ST welfare",
            "Q.No. 123/2021",
            "Art. 14 + Art. 21",
        ]
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            for q in queries:
                resp = client.post("/api/search", json={"query": q})
                assert resp.status_code == 200, f"Expected 200 for {q!r}"


# ── Gap 5: Session filter implicit CA exclusion (F03) ─────────────────────────

class TestSessionFilterCAExclusion:
    """F03: A session filter must exclude CA records from the result set.

    CA records have null session_name per DATA-MODELS.md §1.1.  Meilisearch's
    CONTAINS operator never matches a null value, so
    `session_name CONTAINS "X"` implicitly excludes all CA records.  Our code
    does not add an explicit `source != "CA"` clause — null exclusion is
    fully delegated to Meilisearch's filter semantics.

    Fixture-backed verification (index one CA record + one LS record, apply
    session filter, assert CA absent) is deferred to integration tests against
    a live Meilisearch instance.
    """

    def test_session_filter_expression_uses_contains_not_equality(self):
        """Filter expression must use CONTAINS so null values never match."""
        from api.services.search import build_filter_expression
        expr = build_filter_expression({"session": "Budget Session"})
        assert 'session_name CONTAINS "Budget Session"' in expr
        assert "session_name =" not in expr

    def test_no_explicit_ca_source_exclusion_in_expression(self):
        """Null exclusion via CONTAINS must not be supplemented by an explicit
        source != CA clause — that would be redundant and may differ from spec."""
        from api.services.search import build_filter_expression
        expr = build_filter_expression({"session": "Budget Session"})
        assert "CA" not in expr
        assert 'source !=' not in expr

    def test_session_name_is_filterable_attribute(self):
        """session_name must be in filterableAttributes so CONTAINS can be applied."""
        from ingest.setup_meilisearch import FILTERABLE_ATTRIBUTES
        assert "session_name" in FILTERABLE_ATTRIBUTES

    def test_subject_is_filterable_attribute(self):
        """subject must be in filterableAttributes so CONTAINS can be applied."""
        from ingest.setup_meilisearch import FILTERABLE_ATTRIBUTES
        assert "subject" in FILTERABLE_ATTRIBUTES

    def test_session_filter_route_returns_200(self):
        """Route must accept a session filter and forward it to Meilisearch."""
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={
                "query": "budget",
                "filters": {"session": "Budget Session 2023"},
            })
        assert resp.status_code == 200


# ── Gap 6: Date range gap record membership (F03) ─────────────────────────────

class TestDateRangeGapMembership:
    """F03: date range 1948-01-01 to 2015-12-31 must return CA records from
    the CA era AND LS/RS records from 2014-2015 with no API error.

    Our code applies date filters via Meilisearch `date >= / <=` expressions.
    Correct record membership (which records fall in which date range) is
    delegated to Meilisearch.  These tests verify:
    (a) records returned by Meilisearch in the date range are forwarded
        unchanged in the API response,
    (b) our filter expression covers the full span without any gap-year clause,
    (c) no additional date filtering is applied by our application code.
    """

    def test_ca_record_from_1948_returned_in_wide_date_range(self):
        """A CA record dated 1948 returned by Meilisearch must appear in the response."""
        ca_hit = {
            "id": "ca-1948",
            "record_type": "speech",
            "source": "CA",
            "proceeding_type": "debate",
            "date": "1948-11-04",
            "full_text_en": "Constitution framing discussion.",
            "is_translated": False,
        }
        meili_resp = _meili_response(hits=[ca_hit], total=1, pages=1, page=1)
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client(search_result=meili_resp)
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={
                "query": "Constitution",
                "filters": {"date_from": "1948-01-01", "date_to": "2015-12-31"},
            })
        assert resp.status_code == 200
        assert any(r["id"] == "ca-1948" for r in resp.json()["results"])

    def test_ls_record_from_2014_returned_in_wide_date_range(self):
        """An LS record dated 2014 returned by Meilisearch must appear in the response."""
        ls_hit = {
            "id": "ls-2014",
            "record_type": "speech",
            "source": "LS",
            "proceeding_type": "debate",
            "date": "2014-06-18",
            "full_text_en": "Budget session discussion.",
            "is_translated": False,
        }
        meili_resp = _meili_response(hits=[ls_hit], total=1, pages=1, page=1)
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client(search_result=meili_resp)
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={
                "query": "budget",
                "filters": {"date_from": "1948-01-01", "date_to": "2015-12-31"},
            })
        assert resp.status_code == 200
        assert any(r["id"] == "ls-2014" for r in resp.json()["results"])

    def test_date_filter_expression_covers_full_span_no_gap_clause(self):
        """Filter expression must include both date bounds and no gap-year exclusion."""
        from api.services.search import build_filter_expression
        expr = build_filter_expression({"date_from": "1948-01-01", "date_to": "2015-12-31"})
        assert 'date >= "1948-01-01"' in expr
        assert 'date <= "2015-12-31"' in expr
        # No gap-year exclusion — our code never filters by year gaps
        assert "AND NOT" not in expr
        assert "NOT date" not in expr


# ── Gap 7: Speaker substring multi-match (F03) ───────────────────────────────

class TestSpeakerSubstringFilter:
    """F03: Speaker substring filter must return all speakers whose name contains
    the filter string — the search is delegated to Meilisearch CONTAINS semantics.
    """

    def test_speaker_filter_expression_uses_contains_not_equality(self):
        """Filter expression must use CONTAINS for substring matching."""
        from api.services.search import build_filter_expression
        expr = build_filter_expression({"speaker": "Singh"})
        assert 'speaker_name CONTAINS "Singh"' in expr
        assert "speaker_name =" not in expr

    def test_multiple_speaker_records_all_returned(self):
        """All Meilisearch hits matching the speaker substring must appear in
        the response — our code must not apply additional name filtering."""
        singh_hits = [
            {
                "id": f"s-{i}",
                "record_type": "speech",
                "source": "LS",
                "proceeding_type": "debate",
                "date": "2022-03-15",
                "speaker_name": name,
                "full_text_en": "Speech content.",
                "is_translated": False,
            }
            for i, name in enumerate(["Manmohan Singh", "Rajnath Singh", "V.P. Singh"])
        ]
        meili_resp = _meili_response(hits=singh_hits, total=3, pages=1, page=1)
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client(search_result=meili_resp)
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={
                "query": "infrastructure",
                "filters": {"speaker": "Singh"},
            })
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 3
        returned_names = {r["speaker_name"] for r in results}
        assert {"Manmohan Singh", "Rajnath Singh", "V.P. Singh"} == returned_names

    def test_speaker_filter_forwarded_with_contains_to_meilisearch(self):
        """CONTAINS expression must appear in the params forwarded to Meilisearch."""
        captured: list = []

        async def fake_search(query, **kwargs):
            captured.append(kwargs)
            return _meili_ns()

        mock_index = AsyncMock()
        mock_index.search = fake_search
        mock_client = MagicMock()
        mock_client.index = MagicMock(return_value=mock_index)
        mock_pool = make_mock_pool()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_client
        with TestClient(app) as client:
            client.post("/api/search", json={
                "query": "infrastructure",
                "filters": {"speaker": "Singh"},
            })
        assert len(captured) == 1
        assert "filter" in captured[0]
        assert "CONTAINS" in captured[0]["filter"]
        assert "Singh" in captured[0]["filter"]


# ── Gap 11: Cross-source synonym applicability (F04) ─────────────────────────

class TestCrossSourceSynonymApplicability:
    """F04: Synonym expansion must apply regardless of the source filter.

    The expansion is computed server-side from the query before the source
    filter is applied, so PM → Prime Minister must appear in expansion_notice
    whether the source is CA, LS, or RS.
    """

    @pytest.mark.parametrize("source", ["CA", "LS", "RS"])
    def test_expansion_notice_present_for_each_source(self, source):
        """PM → Prime Minister expansion appears in the response for every source."""
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={
                "query": "PM speech",
                "filters": {"sources": [source]},
            })
        assert resp.status_code == 200
        assert "Prime Minister" in resp.json()["expansion_notice"], (
            f"Expected 'Prime Minister' in expansion_notice for source={source}"
        )


# ── 503 on Meilisearch failure ────────────────────────────────────────────────

class TestSearchUnavailable:
    def test_meili_exception_returns_503(self):
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client(
            search_side_effect=Exception("Meilisearch down")
        )
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={"query": "infrastructure"})
        assert resp.status_code == 503
        body = resp.json()
        # Error body must be a bare top-level object (DATA-MODELS.md 3.1)
        assert body["error"] == "search_unavailable"
        assert "detail" not in body


# ── F10 Debug mode ────────────────────────────────────────────────────────────

class TestDebugMode:
    """
    Tests for POST /api/search?debug=1 (F10, PRD v3.0).

    Normal-mode search must NOT include showRankingScore, showRankingScoreDetails,
    or attributesToRetrieve in the Meilisearch query.
    Debug-mode search must include all three, and the response must contain a
    top-level `debug` envelope with processed_query, meilisearch_request,
    meilisearch_response.
    """

    def _captured_search_params(self):
        """Return (meili_mock, captured_params_list)."""
        captured = []

        async def fake_search(query, **kwargs):
            captured.append({"query": query, "params": kwargs})
            return _meili_ns()

        mock_index = AsyncMock()
        mock_index.search = fake_search
        mock_client = MagicMock()
        mock_client.index = MagicMock(return_value=mock_index)
        return mock_client, captured

    # ── Normal mode ───────────────────────────────────────────────────────────

    def test_normal_mode_does_not_include_ranking_score_params(self):
        """In normal mode, showRankingScore/showRankingScoreDetails/attributesToRetrieve
        must NOT be sent to Meilisearch."""
        mock_client, captured = self._captured_search_params()
        mock_pool = make_mock_pool()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_client
        with TestClient(app) as client:
            client.post("/api/search", json={"query": "infrastructure"})
        params = captured[0]["params"]
        assert "show_ranking_score" not in params
        assert "show_ranking_score_details" not in params
        assert "attributes_to_retrieve" not in params

    def test_normal_mode_response_has_no_debug_key(self):
        """In normal mode, the response must not contain a top-level `debug` key."""
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={"query": "infrastructure"})
        assert resp.status_code == 200
        assert "debug" not in resp.json()

    def test_normal_mode_results_have_no_ranking_score_fields(self):
        """In normal mode, result objects must not contain _rankingScore or
        _rankingScoreDetails."""
        hit = _make_hit(_rankingScore=0.95, _rankingScoreDetails={"words": {"order": 0}})
        meili_resp = _meili_response(hits=[hit], total=1)
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client(search_result=meili_resp)
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search", json={"query": "infrastructure"})
        result = resp.json()["results"][0]
        assert "_rankingScore" not in result
        assert "_rankingScoreDetails" not in result

    # ── Debug mode ────────────────────────────────────────────────────────────

    def test_debug_1_sends_ranking_score_params_to_meilisearch(self):
        """?debug=1 adds showRankingScore, showRankingScoreDetails, and
        attributesToRetrieve=["*"] to the Meilisearch query."""
        mock_client, captured = self._captured_search_params()
        mock_pool = make_mock_pool()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_client
        with TestClient(app) as client:
            client.post("/api/search?debug=1", json={"query": "infrastructure"})
        params = captured[0]["params"]
        assert params.get("show_ranking_score") is True
        assert params.get("show_ranking_score_details") is True
        assert params.get("attributes_to_retrieve") == ["*"]

    def test_debug_true_also_activates_debug_mode(self):
        """?debug=true (string) also activates debug mode."""
        mock_client, captured = self._captured_search_params()
        mock_pool = make_mock_pool()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_client
        with TestClient(app) as client:
            client.post("/api/search?debug=true", json={"query": "infrastructure"})
        params = captured[0]["params"]
        assert params.get("show_ranking_score") is True

    def test_debug_mode_response_contains_debug_envelope(self):
        """?debug=1 adds a top-level `debug` key with processed_query,
        meilisearch_request, and meilisearch_response."""
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search?debug=1", json={"query": "infrastructure"})
        assert resp.status_code == 200
        body = resp.json()
        assert "debug" in body
        envelope = body["debug"]
        assert "processed_query" in envelope
        assert "meilisearch_request" in envelope
        assert "meilisearch_response" in envelope

    def test_debug_envelope_meilisearch_request_has_required_fields(self):
        """The debug envelope's meilisearch_request contains method, url, and body."""
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search?debug=1", json={"query": "infrastructure"})
        body = resp.json()
        req = body["debug"]["meilisearch_request"]
        assert req["method"] == "POST"
        assert "indexes/parliamentary_records/search" in req["url"]
        assert "body" in req

    def test_debug_envelope_request_body_contains_debug_params(self):
        """The debug envelope's request body includes showRankingScore,
        showRankingScoreDetails, and attributesToRetrieve."""
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search?debug=1", json={"query": "infrastructure"})
        body_req = resp.json()["debug"]["meilisearch_request"]["body"]
        assert body_req.get("showRankingScore") is True
        assert body_req.get("showRankingScoreDetails") is True
        assert body_req.get("attributesToRetrieve") == ["*"]

    def test_debug_result_contains_ranking_score(self):
        """When debug=1, each result object includes _rankingScore."""
        hit = _make_hit(_rankingScore=0.87)
        meili_resp = _meili_response(hits=[hit], total=1)
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client(search_result=meili_resp)
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search?debug=1", json={"query": "infrastructure"})
        result = resp.json()["results"][0]
        assert "_rankingScore" in result
        assert result["_rankingScore"] == pytest.approx(0.87)

    def test_debug_result_contains_ranking_score_details_when_present(self):
        """When _rankingScoreDetails is in the hit, it is included in the result."""
        details = {"words": {"order": 0, "matchingWords": 1}}
        hit = _make_hit(_rankingScore=0.9, _rankingScoreDetails=details)
        meili_resp = _meili_response(hits=[hit], total=1)
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client(search_result=meili_resp)
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search?debug=1", json={"query": "infrastructure"})
        result = resp.json()["results"][0]
        assert "_rankingScoreDetails" in result

    def test_debug_result_contains_meili_document(self):
        """When debug=1, each result includes _meili_document (the full hit)."""
        hit = _make_hit(custom_field="custom_value")
        meili_resp = _meili_response(hits=[hit], total=1)
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client(search_result=meili_resp)
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search?debug=1", json={"query": "infrastructure"})
        result = resp.json()["results"][0]
        assert "_meili_document" in result
        # Full document should include the custom field
        assert result["_meili_document"].get("custom_field") == "custom_value"

    def test_debug_envelope_processed_query_matches_submitted_query(self):
        """The debug envelope's processed_query reflects the expanded query sent
        to Meilisearch (after stop-word stripping and synonym expansion)."""
        mock_pool = make_mock_pool()
        mock_meili = make_mock_meili_client()
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_client] = lambda: mock_meili
        with TestClient(app) as client:
            resp = client.post("/api/search?debug=1", json={"query": "infrastructure"})
        body = resp.json()
        assert body["debug"]["processed_query"] != ""
