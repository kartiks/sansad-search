"""
Tests for GET /api/status — live-count response shapes.

The route now issues two queries per request:
  conn.fetch()    — live counts from speeches + qa_exchanges grouped by source
  conn.fetchrow() — most recent run_completed_at from index_status

make_mock_pool(fetch_result=..., fetchrow_result=...) wires both.
"""
from __future__ import annotations

import datetime
from datetime import timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.lib.db import get_pool
from api.lib.meilisearch_client import get_client
from tests.api.conftest import make_mock_meili_client, make_mock_pool


_RUN_AT = datetime.datetime(2026, 5, 15, 14, 30, 0, tzinfo=timezone.utc)


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _live_row(source: str, count: int, date_from=None, date_to=None) -> dict:
    """Simulate one row from the live-counts GROUP BY query."""
    return {
        "source": source,
        "count": count,
        "date_from": date_from,
        "date_to": date_to,
    }


def _last_updated_row(run_at=_RUN_AT) -> dict:
    return {"run_completed_at": run_at}


_DEFAULT_LIVE_ROWS = [
    _live_row("CA", 8200,
              datetime.date(1946, 12, 9), datetime.date(1950, 11, 26)),
    _live_row("LS", 198000,
              datetime.date(2014, 6, 4),  datetime.date(2026, 5, 15)),
    _live_row("RS", 143800,
              datetime.date(2014, 6, 11), datetime.date(2026, 4, 20)),
]


def _get_client(pool_mock=None, meili_mock=None):
    if pool_mock:
        app.dependency_overrides[get_pool] = lambda: pool_mock
    if meili_mock:
        app.dependency_overrides[get_client] = lambda: meili_mock
    return TestClient(app)


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def setup_teardown():
    with patch("api.main.init_pool", new_callable=AsyncMock), \
         patch("api.main.close_pool", new_callable=AsyncMock):
        yield
    app.dependency_overrides.clear()


# ── Populated response ────────────────────────────────────────────────────────

class TestPopulatedResponse:
    def test_status_ok(self):
        pool = make_mock_pool(
            fetch_result=_DEFAULT_LIVE_ROWS,
            fetchrow_result=_last_updated_row(),
        )
        with _get_client(pool, make_mock_meili_client()) as client:
            resp = client.get("/api/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_total_records_is_sum_of_sources(self):
        pool = make_mock_pool(
            fetch_result=_DEFAULT_LIVE_ROWS,
            fetchrow_result=_last_updated_row(),
        )
        with _get_client(pool, make_mock_meili_client()) as client:
            body = client.get("/api/status").json()
        assert body["total_records"] == 8200 + 198000 + 143800

    def test_total_equals_sum_of_sources(self):
        pool = make_mock_pool(
            fetch_result=_DEFAULT_LIVE_ROWS,
            fetchrow_result=_last_updated_row(),
        )
        with _get_client(pool, make_mock_meili_client()) as client:
            body = client.get("/api/status").json()
        sources = body["sources"]
        computed = (
            sources["ca"]["count"] + sources["ls"]["count"] + sources["rs"]["count"]
        )
        assert computed == body["total_records"], (
            f"total_records ({body['total_records']}) must equal sum of source counts "
            f"({computed})"
        )

    def test_last_updated_is_iso_timestamp(self):
        pool = make_mock_pool(
            fetch_result=_DEFAULT_LIVE_ROWS,
            fetchrow_result=_last_updated_row(),
        )
        with _get_client(pool, make_mock_meili_client()) as client:
            body = client.get("/api/status").json()
        assert body["last_updated"] is not None
        datetime.datetime.fromisoformat(body["last_updated"].replace("Z", "+00:00"))

    def test_source_date_ranges_present(self):
        pool = make_mock_pool(
            fetch_result=_DEFAULT_LIVE_ROWS,
            fetchrow_result=_last_updated_row(),
        )
        with _get_client(pool, make_mock_meili_client()) as client:
            body = client.get("/api/status").json()
        ca = body["sources"]["ca"]
        assert ca["date_from"] == "1946-12-09"
        assert ca["date_to"] == "1950-11-26"

    def test_all_three_sources_present(self):
        pool = make_mock_pool(
            fetch_result=_DEFAULT_LIVE_ROWS,
            fetchrow_result=_last_updated_row(),
        )
        with _get_client(pool, make_mock_meili_client()) as client:
            body = client.get("/api/status").json()
        sources = body["sources"]
        assert "ca" in sources
        assert "ls" in sources
        assert "rs" in sources

    def test_reads_from_db_not_meilisearch(self):
        """Status route must read from PostgreSQL only; Meilisearch is not called."""
        pool = make_mock_pool(
            fetch_result=_DEFAULT_LIVE_ROWS,
            fetchrow_result=_last_updated_row(),
        )
        meili = make_mock_meili_client(search_side_effect=Exception("Meili unavailable"))
        with _get_client(pool, meili) as client:
            resp = client.get("/api/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_last_updated_null_when_no_index_status_row(self):
        """Live counts present but index_status empty → last_updated is null."""
        pool = make_mock_pool(
            fetch_result=_DEFAULT_LIVE_ROWS,
            fetchrow_result=None,
        )
        with _get_client(pool, make_mock_meili_client()) as client:
            body = client.get("/api/status").json()
        assert body["status"] == "ok"
        assert body["last_updated"] is None


# ── Never-run response ────────────────────────────────────────────────────────

class TestNeverRunResponse:
    def test_never_run_returns_ok(self):
        pool = make_mock_pool(fetch_result=[], fetchrow_result=None)
        with _get_client(pool, make_mock_meili_client()) as client:
            body = client.get("/api/status").json()
        assert body["status"] == "ok"

    def test_never_run_total_is_zero(self):
        pool = make_mock_pool(fetch_result=[], fetchrow_result=None)
        with _get_client(pool, make_mock_meili_client()) as client:
            body = client.get("/api/status").json()
        assert body["total_records"] == 0

    def test_never_run_last_updated_is_null(self):
        """On never-run: last_updated must be null. The UI converts null to 'Never'."""
        pool = make_mock_pool(fetch_result=[], fetchrow_result=None)
        with _get_client(pool, make_mock_meili_client()) as client:
            body = client.get("/api/status").json()
        assert body["last_updated"] is None

    def test_never_run_source_counts_are_zero(self):
        pool = make_mock_pool(fetch_result=[], fetchrow_result=None)
        with _get_client(pool, make_mock_meili_client()) as client:
            body = client.get("/api/status").json()
        for source in ("ca", "ls", "rs"):
            assert body["sources"][source]["count"] == 0

    def test_never_run_source_dates_are_null(self):
        """Zero-indexed sources must have null date_from and date_to."""
        pool = make_mock_pool(fetch_result=[], fetchrow_result=None)
        with _get_client(pool, make_mock_meili_client()) as client:
            body = client.get("/api/status").json()
        for source in ("ca", "ls", "rs"):
            s = body["sources"][source]
            assert s["date_from"] is None, f"{source}.date_from must be null"
            assert s["date_to"] is None, f"{source}.date_to must be null"


# ── Unavailable response ──────────────────────────────────────────────────────

class TestUnavailableResponse:
    def test_db_exception_returns_unavailable(self):
        pool = make_mock_pool(fetch_side_effect=Exception("DB connection lost"))
        with _get_client(pool, make_mock_meili_client()) as client:
            body = client.get("/api/status").json()
        assert body["status"] == "unavailable"

    def test_unavailable_is_still_200(self):
        """503 is wrong; the unavailable response is still HTTP 200."""
        pool = make_mock_pool(fetch_side_effect=Exception("DB down"))
        with _get_client(pool, make_mock_meili_client()) as client:
            resp = client.get("/api/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "unavailable"


# ── Missing source in live rows ───────────────────────────────────────────────

class TestMissingSource:
    def test_absent_source_has_zero_count_and_null_dates(self):
        """CA absent from live rows → count=0, date_from=None, date_to=None."""
        rows = [
            _live_row("LS", 557,
                      datetime.date(2024, 1, 1), datetime.date(2024, 6, 30)),
            _live_row("RS", 0, None, None),
        ]
        pool = make_mock_pool(fetch_result=rows, fetchrow_result=_last_updated_row())
        with _get_client(pool, make_mock_meili_client()) as client:
            body = client.get("/api/status").json()
        ca = body["sources"]["ca"]
        assert ca["count"] == 0
        assert ca["date_from"] is None
        assert ca["date_to"] is None

    def test_total_reflects_only_present_sources(self):
        """total_records equals the sum of whichever sources are actually in the index."""
        rows = [_live_row("LS", 557,
                          datetime.date(2024, 1, 1), datetime.date(2024, 6, 30))]
        pool = make_mock_pool(fetch_result=rows, fetchrow_result=_last_updated_row())
        with _get_client(pool, make_mock_meili_client()) as client:
            body = client.get("/api/status").json()
        assert body["total_records"] == 557
        assert body["sources"]["ca"]["count"] == 0
        assert body["sources"]["ls"]["count"] == 557
        assert body["sources"]["rs"]["count"] == 0
