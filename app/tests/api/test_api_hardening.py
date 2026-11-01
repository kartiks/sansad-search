"""
Tests for API hardening fixes (code review, 2026-10-30):

1. Filter values are validated and escaped before reaching Meilisearch.
2. (ranking rules — see tests/test_setup_meilisearch.py)
3. Non-ASCII (e.g. Hindi) queries are accepted.
4. Database outages return 503, not 404; ids are validated as UUIDs.
5. The Meilisearch client has a timeout and is closed on shutdown.
6. CORS fails closed when ALLOWED_ORIGINS is unset.
"""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest
from fastapi.testclient import TestClient

from api.lib import meilisearch_client
from api.lib.db import get_pool, is_valid_uuid
from api.lib.meilisearch_client import get_client
from api.main import _allowed_origins, app
from api.services.query_expander import strip_stop_words
from api.services.search import build_filter_expression
from tests.api.conftest import make_mock_meili_client, make_mock_pool

VALID_ID = "3f2a1b00-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def _lifespan_noop():
    with patch("api.main.init_pool", new_callable=AsyncMock), \
         patch("api.main.close_pool", new_callable=AsyncMock):
        yield
    app.dependency_overrides.clear()


def _client(pool=None, meili=None) -> TestClient:
    app.dependency_overrides[get_pool] = lambda: pool or make_mock_pool()
    app.dependency_overrides[get_client] = lambda: meili or make_mock_meili_client()
    return TestClient(app)


def _search(body, meili=None):
    meili = meili or make_mock_meili_client()
    with _client(meili=meili) as client:
        resp = client.post("/api/search", json=body)
    return resp, meili


# ── 1. Filter validation and escaping ─────────────────────────────────────────

class TestFilterValidation:
    @pytest.mark.parametrize("sources", [
        ["XX"],
        ["LS", "ls"],
        ['LS"] OR source = "X'],
    ])
    def test_unknown_source_returns_400(self, sources):
        resp, meili = _search({"query": "budget", "filters": {"sources": sources}})
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"] == "validation_error"
        assert body["code"] == "source_invalid"
        meili.index.return_value.search.assert_not_called()

    def test_unknown_proceeding_type_returns_400(self):
        resp, meili = _search({
            "query": "budget",
            "filters": {"proceeding_types": ['debate"] OR proceeding_type EXISTS OR x IN ["']},
        })
        assert resp.status_code == 400
        assert resp.json()["code"] == "proceeding_type_invalid"
        meili.index.return_value.search.assert_not_called()

    @pytest.mark.parametrize("field", ["date_from", "date_to"])
    @pytest.mark.parametrize("value", [
        "2023-1-5",
        "15-03-2023",
        "2023-02-30",                 # not a real date
        "2023-03-15\n",               # trailing newline
        "२०२३-०३-१५",                 # Devanagari digits
        '2023-03-15" OR date > "0',   # injection attempt
    ])
    def test_invalid_date_returns_400(self, field, value):
        resp, meili = _search({"query": "budget", "filters": {field: value}})
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"] == "validation_error"
        assert body["code"] == "date_invalid"
        assert field in body["message"]
        meili.index.return_value.search.assert_not_called()

    def test_valid_filters_reach_meilisearch(self):
        resp, meili = _search({
            "query": "budget",
            "filters": {
                "sources": ["LS", "RS"],
                "proceeding_types": ["starred_question"],
                "date_from": "2020-01-01",
                "date_to": "2020-12-31",
            },
        })
        assert resp.status_code == 200
        kwargs = meili.index.return_value.search.call_args.kwargs
        assert kwargs["filter"] == (
            'source IN ["LS", "RS"] AND proceeding_type IN ["starred_question"] '
            'AND date >= "2020-01-01" AND date <= "2020-12-31"'
        )

    def test_date_range_order_still_checked(self):
        resp, _ = _search({
            "query": "budget",
            "filters": {"date_from": "2021-01-01", "date_to": "2020-01-01"},
        })
        assert resp.status_code == 400
        assert resp.json()["code"] == "date_range_invalid"


class TestFilterEscaping:
    def test_backslash_is_escaped(self):
        expr = build_filter_expression({"speaker": "a\\b"})
        assert expr == 'speaker_name CONTAINS "a\\\\b"'

    def test_trailing_backslash_cannot_escape_closing_quote(self):
        # Before the fix: speaker_name CONTAINS "x\" — the closing quote was
        # escaped, leaving the literal open.
        expr = build_filter_expression({"speaker": "x\\"})
        assert expr == 'speaker_name CONTAINS "x\\\\"'

    def test_backslash_quote_sequence_stays_inside_literal(self):
        expr = build_filter_expression({"session": 'a\\" OR source = "LS'})
        assert expr == 'session_name CONTAINS "a\\\\\\" OR source = \\"LS"'

    def test_subject_is_escaped(self):
        expr = build_filter_expression({"subject": 'say "hi"'})
        assert expr == 'subject CONTAINS "say \\"hi\\""'

    def test_list_values_are_escaped_in_service(self):
        # Defence in depth: the service escapes even if validation is bypassed.
        expr = build_filter_expression({"sources": ['LS"]']})
        assert expr == 'source IN ["LS\\"]"]'


# ── 3. Non-ASCII queries ──────────────────────────────────────────────────────

class TestUnicodeQueries:
    @pytest.mark.parametrize("query", ["संविधान", "का", "भारत का संविधान", "தமிழ்"])
    def test_non_ascii_query_is_searched(self, query):
        resp, meili = _search({"query": query})
        assert resp.status_code == 200, resp.json()
        assert meili.index.return_value.search.call_args.args[0] == query

    def test_single_non_ascii_letter_is_too_short(self):
        resp, _ = _search({"query": "क"})
        assert resp.status_code == 400
        assert resp.json()["code"] == "query_too_short"

    def test_hindi_query_is_not_only_stopwords(self):
        clean, only_stopwords = strip_stop_words("the संविधान")
        assert clean == "संविधान"
        assert only_stopwords is False

    def test_punctuation_only_still_too_short(self):
        resp, _ = _search({"query": "।।"})  # Devanagari danda
        assert resp.status_code == 400
        assert resp.json()["code"] == "query_too_short"


# ── 4. Database errors → 503; UUID validation ─────────────────────────────────

_DB_ERRORS = [
    asyncpg.exceptions.ConnectionDoesNotExistError("connection was closed"),
    asyncpg.exceptions.CannotConnectNowError("the database system is starting up"),
    ConnectionRefusedError("connection refused"),
    asyncio.TimeoutError(),
]

_ENDPOINTS = [
    f"/api/record/{VALID_ID}",
    f"/api/record/{VALID_ID}/adjacent?direction=next&from_seq=3",
    f"/api/debug/processed/{VALID_ID}",
    f"/api/debug/raw/{VALID_ID}",
]


class TestDatabaseErrors:
    @pytest.mark.parametrize("path", _ENDPOINTS)
    @pytest.mark.parametrize("exc", _DB_ERRORS, ids=lambda e: type(e).__name__)
    def test_query_error_returns_503(self, path, exc):
        pool = make_mock_pool(fetchrow_side_effect=exc)
        with _client(pool=pool) as client:
            resp = client.get(path)
        assert resp.status_code == 503
        assert resp.json() == {
            "error": "database_unavailable",
            "message": "The database is temporarily unavailable.",
        }

    @pytest.mark.parametrize("path", _ENDPOINTS)
    def test_pool_acquire_error_returns_503(self, path):
        pool = MagicMock()
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(side_effect=OSError("network unreachable"))
        cm.__aexit__ = AsyncMock(return_value=False)
        pool.acquire = MagicMock(return_value=cm)
        with _client(pool=pool) as client:
            resp = client.get(path)
        assert resp.status_code == 503

    @pytest.mark.parametrize("path", _ENDPOINTS[:2])
    def test_sitting_query_error_returns_503_not_partial_data(self, path):
        # The focal row resolves but the second (sitting / batch) query fails:
        # previously this returned 200 with wrong has_prev/has_next or an
        # empty batch.
        row = {
            "id": VALID_ID, "source": "LS", "date": None, "sitting_number": 1,
            "sequence_within_sitting": 3,
        }
        pool = make_mock_pool(
            fetchrow_result=row,
            fetch_side_effect=asyncpg.exceptions.ConnectionDoesNotExistError("closed"),
        )
        with _client(pool=pool) as client:
            resp = client.get(path)
        assert resp.status_code == 503

    def test_pool_not_initialised_returns_503(self):
        # No get_pool override: the real dependency raises because the pool
        # was never created.
        app.dependency_overrides[get_client] = lambda: make_mock_meili_client()
        with TestClient(app) as client:
            resp = client.get(f"/api/record/{VALID_ID}")
        assert resp.status_code == 503
        assert resp.json()["error"] == "database_unavailable"

    def test_missing_row_is_still_404(self):
        pool = make_mock_pool(fetchrow_result=None)
        with _client(pool=pool) as client:
            resp = client.get(f"/api/record/{VALID_ID}")
        assert resp.status_code == 404
        assert resp.json()["error"] == "not_found"

    def test_unexpected_error_is_not_reported_as_outage(self):
        # Programming errors are not swallowed as 404 or disguised as 503.
        pool = make_mock_pool(fetchrow_side_effect=KeyError("bug"))
        _client(pool=pool)  # installs the dependency overrides
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/record/{VALID_ID}")
        assert resp.status_code == 500


class TestUuidValidation:
    @pytest.mark.parametrize("path", [
        "/api/record/not-a-uuid",
        "/api/record/not-a-uuid/adjacent?direction=next&from_seq=3",
        "/api/debug/processed/not-a-uuid",
        "/api/debug/raw/not-a-uuid",
        "/api/record/3f2a1b00-0000-0000-0000-00000000000z",
        # uuid.UUID() accepts these, but asyncpg rejects them (was a 503)
        "/api/record/{3f2a1b00-0000-0000-0000-000000000001}",
        "/api/record/urn:uuid:3f2a1b00-0000-0000-0000-000000000001",
        "/api/debug/raw/3f2a1b0000000000000000000000000001",
    ])
    def test_invalid_uuid_returns_404_without_querying(self, path):
        pool = make_mock_pool()
        with _client(pool=pool) as client:
            resp = client.get(path)
        assert resp.status_code == 404
        assert resp.json()["error"] == "not_found"
        pool.acquire.assert_not_called()

    def test_is_valid_uuid(self):
        assert is_valid_uuid(VALID_ID)
        assert is_valid_uuid(VALID_ID.upper())
        assert not is_valid_uuid("")
        assert not is_valid_uuid("qa2b1b00-0000-0000-0000-000000000001")
        assert not is_valid_uuid("{" + VALID_ID + "}")
        assert not is_valid_uuid("urn:uuid:" + VALID_ID)
        assert not is_valid_uuid(VALID_ID.replace("-", ""))
        assert not is_valid_uuid(VALID_ID + "\n")


# ── 5. Meilisearch client timeout and close ───────────────────────────────────

class TestMeilisearchClient:
    @pytest.fixture(autouse=True)
    def _reset_client(self, monkeypatch):
        monkeypatch.setattr(meilisearch_client, "_client", None)
        monkeypatch.setenv("MEILISEARCH_URL", "http://meili.test")
        monkeypatch.setenv("MEILISEARCH_SEARCH_KEY", "search-key")
        yield
        meilisearch_client._client = None

    def test_client_created_with_default_timeout(self, monkeypatch):
        monkeypatch.delenv("MEILISEARCH_TIMEOUT_SECONDS", raising=False)
        with patch.object(meilisearch_client, "AsyncClient") as cls:
            meilisearch_client.get_client()
        assert cls.call_args.kwargs["timeout"] == meilisearch_client.DEFAULT_TIMEOUT_SECONDS

    def test_timeout_overridable_by_env(self, monkeypatch):
        monkeypatch.setenv("MEILISEARCH_TIMEOUT_SECONDS", "2")
        with patch.object(meilisearch_client, "AsyncClient") as cls:
            meilisearch_client.get_client()
        assert cls.call_args.kwargs["timeout"] == 2

    @pytest.mark.parametrize("raw", ["abc", "0", "-1"])
    def test_invalid_timeout_falls_back_to_default(self, monkeypatch, raw):
        monkeypatch.setenv("MEILISEARCH_TIMEOUT_SECONDS", raw)
        with patch.object(meilisearch_client, "AsyncClient") as cls:
            meilisearch_client.get_client()
        assert cls.call_args.kwargs["timeout"] == meilisearch_client.DEFAULT_TIMEOUT_SECONDS

    def test_real_client_carries_timeout(self):
        client = meilisearch_client.get_client()
        try:
            assert client.http_client.timeout.read == meilisearch_client.DEFAULT_TIMEOUT_SECONDS
        finally:
            asyncio.run(meilisearch_client.close_client())

    def test_close_client_closes_and_resets(self):
        fake = MagicMock()
        fake.aclose = AsyncMock()
        meilisearch_client._client = fake
        asyncio.run(meilisearch_client.close_client())
        fake.aclose.assert_awaited_once()
        assert meilisearch_client._client is None

    def test_close_client_without_client_is_noop(self):
        asyncio.run(meilisearch_client.close_client())
        assert meilisearch_client._client is None

    def test_lifespan_closes_client_on_shutdown(self):
        with patch("api.main.close_client", new_callable=AsyncMock) as close:
            with TestClient(app):
                close.assert_not_awaited()
        close.assert_awaited_once()


# ── 6. CORS fails closed ──────────────────────────────────────────────────────

class TestAllowedOrigins:
    def test_unset_fails_closed_and_warns(self, monkeypatch, caplog):
        monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
        with caplog.at_level(logging.WARNING, logger="api.main"):
            assert _allowed_origins() == []
        assert "ALLOWED_ORIGINS is not set" in caplog.text

    def test_blank_fails_closed(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_ORIGINS", " , ")
        assert _allowed_origins() == []

    def test_parses_list(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.example, http://localhost:5173")
        assert _allowed_origins() == ["https://a.example", "http://localhost:5173"]

    def test_wildcard_never_added(self, monkeypatch):
        monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
        assert "*" not in _allowed_origins()
