"""
Tests for GET /api/status — three response shapes and F07 requirements.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.lib.db import get_pool
from api.lib.meilisearch_client import get_client
from tests.api.conftest import make_mock_meili_client, make_mock_pool


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _make_row(**overrides):
    """Return a dict-like row simulating an asyncpg Record."""
    base = {
        "id": 1,
        "run_completed_at": datetime(2026, 5, 15, 14, 30, 0, tzinfo=timezone.utc),
        "total_records": 350000,
        "ca_count": 8200,
        "ca_date_from": "1946-12-09",
        "ca_date_to": "1950-11-26",
        "ls_count": 198000,
        "ls_date_from": "2014-06-04",
        "ls_date_to": "2026-05-15",
        "rs_count": 143800,
        "rs_date_from": "2014-06-11",
        "rs_date_to": "2026-04-20",
    }
    base.update(overrides)
    return base


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
        row = _make_row()
        pool = make_mock_pool(fetchrow_result=row)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            resp = client.get("/api/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_total_records(self):
        row = _make_row(total_records=350000)
        pool = make_mock_pool(fetchrow_result=row)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            resp = client.get("/api/status")
        assert resp.json()["total_records"] == 350000

    def test_total_equals_sum_of_sources(self):
        row = _make_row(ca_count=100, ls_count=200, rs_count=300, total_records=600)
        pool = make_mock_pool(fetchrow_result=row)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get("/api/status").json()
        sources = body["sources"]
        computed_total = (
            sources["ca"]["count"] + sources["ls"]["count"] + sources["rs"]["count"]
        )
        assert computed_total == body["total_records"], (
            f"total_records ({body['total_records']}) must equal sum of source counts "
            f"({computed_total})"
        )

    def test_last_updated_is_iso_timestamp(self):
        row = _make_row()
        pool = make_mock_pool(fetchrow_result=row)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get("/api/status").json()
        assert body["last_updated"] is not None
        # Should be parseable as ISO 8601
        datetime.fromisoformat(body["last_updated"].replace("Z", "+00:00"))

    def test_source_date_ranges_present(self):
        row = _make_row()
        pool = make_mock_pool(fetchrow_result=row)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get("/api/status").json()
        ca = body["sources"]["ca"]
        assert ca["date_from"] == "1946-12-09"
        assert ca["date_to"] == "1950-11-26"

    def test_all_three_sources_present(self):
        row = _make_row()
        pool = make_mock_pool(fetchrow_result=row)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get("/api/status").json()
        sources = body["sources"]
        assert "ca" in sources
        assert "ls" in sources
        assert "rs" in sources

    def test_reads_from_db_not_meilisearch(self):
        """
        Status route must read from PostgreSQL only; Meilisearch is not called.
        """
        row = _make_row()
        pool = make_mock_pool(fetchrow_result=row)
        meili = make_mock_meili_client(search_side_effect=Exception("Meili unavailable"))
        with _get_client(pool, meili) as client:
            resp = client.get("/api/status")
        # Must still return 200 even though Meilisearch would fail
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ── Never-run response ────────────────────────────────────────────────────────

class TestNeverRunResponse:
    def test_never_run_returns_ok(self):
        pool = make_mock_pool(fetchrow_result=None)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get("/api/status").json()
        assert body["status"] == "ok"

    def test_never_run_total_is_zero(self):
        pool = make_mock_pool(fetchrow_result=None)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get("/api/status").json()
        assert body["total_records"] == 0

    def test_never_run_last_updated_is_null(self):
        """
        On never-run: last_updated must be null (not "Never" or a date string).
        The UI layer converts null to "Never" display text.
        """
        pool = make_mock_pool(fetchrow_result=None)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get("/api/status").json()
        assert body["last_updated"] is None

    def test_never_run_source_counts_are_zero(self):
        pool = make_mock_pool(fetchrow_result=None)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get("/api/status").json()
        for source in ("ca", "ls", "rs"):
            assert body["sources"][source]["count"] == 0

    def test_never_run_source_dates_are_null(self):
        """Zero-indexed sources must have null date_from and date_to."""
        pool = make_mock_pool(fetchrow_result=None)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get("/api/status").json()
        for source in ("ca", "ls", "rs"):
            s = body["sources"][source]
            assert s["date_from"] is None, f"{source}.date_from must be null, not {s['date_from']!r}"
            assert s["date_to"] is None, f"{source}.date_to must be null, not {s['date_to']!r}"


# ── Unavailable response ──────────────────────────────────────────────────────

class TestUnavailableResponse:
    def test_db_exception_returns_unavailable(self):
        pool = make_mock_pool(fetchrow_side_effect=Exception("DB connection lost"))
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get("/api/status").json()
        assert body["status"] == "unavailable"

    def test_unavailable_is_still_200(self):
        """503 is wrong; the unavailable response is still HTTP 200."""
        pool = make_mock_pool(fetchrow_side_effect=Exception("DB down"))
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            resp = client.get("/api/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "unavailable"


# ── Zero-count source row ─────────────────────────────────────────────────────

class TestZeroCountSource:
    def test_zero_source_has_null_dates(self):
        """A source with 0 records must have null date_from and date_to."""
        row = _make_row(ca_count=0, ca_date_from=None, ca_date_to=None, total_records=341800)
        pool = make_mock_pool(fetchrow_result=row)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get("/api/status").json()
        ca = body["sources"]["ca"]
        assert ca["count"] == 0
        assert ca["date_from"] is None
        assert ca["date_to"] is None
