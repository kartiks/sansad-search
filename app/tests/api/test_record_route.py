"""
Tests for GET /api/record/{id} — F09 record detail endpoint.

All tests use dependency overrides; no real DB connections required.
"""
from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.lib.db import get_pool
from api.lib.meilisearch_client import get_client
from tests.api.conftest import make_mock_meili_client, make_mock_pool


# ── Row helpers ───────────────────────────────────────────────────────────────

def _speech_row(**overrides):
    """Dict-like asyncpg Record for a speech record."""
    base = {
        "id": "3f2a1b00-0000-0000-0000-000000000001",
        "source": "LS",
        "proceeding_type": "debate",
        "date": datetime.date(2023, 3, 15),
        "session_name": "Budget Session 2023",
        "session_number": 7,
        "sitting_number": 42,
        "subject": "General Discussion on the Union Budget",
        "full_text_en": "Mr. Speaker, I rise to speak on...",
        "lang_original": "en",
        "time_of_day": "14:35",
        "word_count": 1820,
        "is_translated": False,
        "has_untranslated_content": False,
        "page_reference": None,
        "source_url": "https://eparlib.sansad.in/example",
        "sequence_within_sitting": 7,
        "volume": None,
        "speaker_name": "Jairam Ramesh",
        "speaker_role": "member",
        "speaker_party": "INC",
        "speaker_constituency_or_state": "Karnataka",
        "speaker_name_unresolved": False,
        "question_number": None,
        "questioner_names": None,
        "questioner_party": None,
        "minister_name": None,
        "ministry": None,
        "record_type": "speech",
    }
    base.update(overrides)
    return base


def _qa_row(**overrides):
    """Dict-like asyncpg Record for a Q+A record."""
    base = {
        "id": "qa2b1b00-0000-0000-0000-000000000001",
        "source": "LS",
        "proceeding_type": "starred_question",
        "date": datetime.date(2023, 8, 4),
        "session_name": "Monsoon Session 2023",
        "session_number": 8,
        "sitting_number": 12,
        "subject": "Implementation of National Health Mission",
        "full_text_en": "Q: What is the status of NHM?...",
        "lang_original": "en",
        "time_of_day": None,
        "word_count": 540,
        "is_translated": False,
        "has_untranslated_content": False,
        "page_reference": None,
        "source_url": "https://eparlib.sansad.in/qa-example",
        "sequence_within_sitting": 3,
        "volume": None,
        "speaker_name": None,
        "speaker_role": None,
        "speaker_party": None,
        "speaker_constituency_or_state": None,
        "speaker_name_unresolved": None,
        "question_number": 42,
        "questioner_names": ["Shri A. Kumar"],
        "questioner_party": "BJP",
        "minister_name": "Dr. Mansukh Mandaviya",
        "ministry": "Ministry of Health and Family Welfare",
        "record_type": "qa",
    }
    base.update(overrides)
    return base


def _sitting_rows(current_id, current_seq, total=5):
    """Build sitting rows list with current record at current_seq."""
    rows = []
    for i in range(1, total + 1):
        row_id = current_id if i == current_seq else f"other-id-{i:04d}"
        rows.append({"id": row_id, "sequence_within_sitting": i})
    return rows


def _get_client(pool_mock=None, meili_mock=None):
    if pool_mock:
        app.dependency_overrides[get_pool] = lambda: pool_mock
    if meili_mock:
        app.dependency_overrides[get_client] = lambda: meili_mock
    return TestClient(app)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def setup_teardown():
    with patch("api.main.init_pool", new_callable=AsyncMock), \
         patch("api.main.close_pool", new_callable=AsyncMock):
        yield
    app.dependency_overrides.clear()


# ── 200 — Speech record ───────────────────────────────────────────────────────

class TestGetSpeechRecord:
    def test_returns_200(self):
        row = _speech_row()
        sitting = _sitting_rows(row["id"], row["sequence_within_sitting"])
        pool = make_mock_pool(fetchrow_result=row, fetch_result=sitting)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            resp = client.get(f"/api/record/{row['id']}")
        assert resp.status_code == 200

    def test_record_type_is_speech(self):
        row = _speech_row()
        sitting = _sitting_rows(row["id"], row["sequence_within_sitting"])
        pool = make_mock_pool(fetchrow_result=row, fetch_result=sitting)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["record_type"] == "speech"

    def test_date_display_formatted(self):
        row = _speech_row()
        sitting = _sitting_rows(row["id"], row["sequence_within_sitting"])
        pool = make_mock_pool(fetchrow_result=row, fetch_result=sitting)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["date_display"] == "15 March 2023"

    def test_date_iso_string(self):
        row = _speech_row()
        sitting = _sitting_rows(row["id"], row["sequence_within_sitting"])
        pool = make_mock_pool(fetchrow_result=row, fetch_result=sitting)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["date"] == "2023-03-15"

    def test_proceeding_type_label_formatted(self):
        row = _speech_row()
        sitting = _sitting_rows(row["id"], row["sequence_within_sitting"])
        pool = make_mock_pool(fetchrow_result=row, fetch_result=sitting)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["proceeding_type_label"] == "Debate"

    def test_all_required_fields_present(self):
        row = _speech_row()
        sitting = _sitting_rows(row["id"], row["sequence_within_sitting"])
        pool = make_mock_pool(fetchrow_result=row, fetch_result=sitting)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        for field in ("id", "record_type", "source", "proceeding_type",
                      "proceeding_type_label", "date", "date_display",
                      "full_text_en", "lang_original", "sequence_within_sitting",
                      "sitting_total", "adjacent"):
            assert field in body, f"Missing field: {field}"

    def test_adjacent_field_has_prev_and_next_keys(self):
        row = _speech_row()
        sitting = _sitting_rows(row["id"], row["sequence_within_sitting"])
        pool = make_mock_pool(fetchrow_result=row, fetch_result=sitting)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert "prev_id" in body["adjacent"]
        assert "next_id" in body["adjacent"]


# ── 200 — Adjacent navigation ─────────────────────────────────────────────────

class TestAdjacentNavigation:
    def test_sitting_total_matches_sitting_size(self):
        row = _speech_row(sequence_within_sitting=3)
        sitting = _sitting_rows(row["id"], 3, total=7)
        pool = make_mock_pool(fetchrow_result=row, fetch_result=sitting)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["sitting_total"] == 7

    def test_prev_id_correct(self):
        row = _speech_row(sequence_within_sitting=3)
        sitting = _sitting_rows(row["id"], 3, total=5)
        pool = make_mock_pool(fetchrow_result=row, fetch_result=sitting)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["adjacent"]["prev_id"] == "other-id-0002"

    def test_next_id_correct(self):
        row = _speech_row(sequence_within_sitting=3)
        sitting = _sitting_rows(row["id"], 3, total=5)
        pool = make_mock_pool(fetchrow_result=row, fetch_result=sitting)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["adjacent"]["next_id"] == "other-id-0004"

    def test_prev_id_null_at_lower_boundary(self):
        row = _speech_row(sequence_within_sitting=1)
        sitting = _sitting_rows(row["id"], 1, total=5)
        pool = make_mock_pool(fetchrow_result=row, fetch_result=sitting)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["adjacent"]["prev_id"] is None

    def test_next_id_null_at_upper_boundary(self):
        row = _speech_row(sequence_within_sitting=5)
        sitting = _sitting_rows(row["id"], 5, total=5)
        pool = make_mock_pool(fetchrow_result=row, fetch_result=sitting)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["adjacent"]["next_id"] is None

    def test_both_null_for_single_record_sitting(self):
        row = _speech_row(sequence_within_sitting=1)
        sitting = [{"id": row["id"], "sequence_within_sitting": 1}]
        pool = make_mock_pool(fetchrow_result=row, fetch_result=sitting)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["adjacent"]["prev_id"] is None
        assert body["adjacent"]["next_id"] is None
        assert body["sitting_total"] == 1


# ── 200 — Q+A record ─────────────────────────────────────────────────────────

class TestGetQARecord:
    def test_returns_200(self):
        row = _qa_row()
        sitting = _sitting_rows(row["id"], row["sequence_within_sitting"], total=3)
        pool = make_mock_pool(fetchrow_result=row, fetch_result=sitting)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            resp = client.get(f"/api/record/{row['id']}")
        assert resp.status_code == 200

    def test_record_type_is_qa(self):
        row = _qa_row()
        sitting = _sitting_rows(row["id"], row["sequence_within_sitting"], total=3)
        pool = make_mock_pool(fetchrow_result=row, fetch_result=sitting)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["record_type"] == "qa"

    def test_qa_fields_present(self):
        row = _qa_row()
        sitting = _sitting_rows(row["id"], row["sequence_within_sitting"], total=3)
        pool = make_mock_pool(fetchrow_result=row, fetch_result=sitting)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["question_number"] == 42
        assert body["questioner_names"] == ["Shri A. Kumar"]
        assert body["minister_name"] == "Dr. Mansukh Mandaviya"

    def test_proceeding_type_label_starred(self):
        row = _qa_row()
        sitting = _sitting_rows(row["id"], row["sequence_within_sitting"], total=3)
        pool = make_mock_pool(fetchrow_result=row, fetch_result=sitting)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["proceeding_type_label"] == "Starred Question"


# ── 404 — Not found ───────────────────────────────────────────────────────────

class TestRecordNotFound:
    def test_returns_404_when_no_row(self):
        pool = make_mock_pool(fetchrow_result=None)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            resp = client.get("/api/record/3f2a1b00-0000-0000-0000-000000000099")
        assert resp.status_code == 404

    def test_404_response_shape(self):
        pool = make_mock_pool(fetchrow_result=None)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get("/api/record/3f2a1b00-0000-0000-0000-000000000099").json()
        assert body["error"] == "not_found"
        assert body["message"] == "Record not found."

    def test_invalid_uuid_returns_404(self):
        # DB will raise an exception on invalid UUID cast; service returns None → 404
        pool = make_mock_pool(fetchrow_side_effect=Exception("invalid input for UUID"))
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            resp = client.get("/api/record/not-a-uuid")
        assert resp.status_code == 404


# ── Separation of concerns ────────────────────────────────────────────────────

class TestRecordServesFromPostgres:
    def test_meilisearch_not_called(self):
        """Record detail must read from PostgreSQL only."""
        row = _speech_row()
        sitting = _sitting_rows(row["id"], row["sequence_within_sitting"])
        pool = make_mock_pool(fetchrow_result=row, fetch_result=sitting)
        meili = make_mock_meili_client(
            search_side_effect=Exception("Meili should not be called")
        )
        with _get_client(pool, meili) as client:
            resp = client.get(f"/api/record/{row['id']}")
        assert resp.status_code == 200
